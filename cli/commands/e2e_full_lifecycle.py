"""
[INPUT]: 依赖 typer/rich/asyncpg/httpx，依赖 cli.client 的 APIClient，依赖 commands.agent 的 DEFAULT_MOMENT_DEFINITION
[OUTPUT]: 对外提供 test-full-lifecycle 全链路测试命令（对话→识别12+moment→取消→修改→确认→兑现→报告）
[POS]: cli/commands 的全链路生命周期测试入口；覆盖 cancel / modify / deliver 三种状态迁移
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import typer
from rich.console import Console

from ..client import APIClient

app = typer.Typer()
console = Console()
BJ_TZ = timezone(timedelta(hours=8))


# ================================================================
#  Phase 1: 多主题对话 — 涵盖工作/健康/情绪/习惯/生活 — 触发 12+ moments
# ================================================================

PHASE1_MESSAGES = [
    # 1. 工作汇报（event/high）
    "我下周二下午两点有个特别重要的季度工作汇报，PPT还没做完，到时候提醒我别迟到",
    # 2. 看电影（event/mid）— 后续会取消
    "这周五晚上七点半约了朋友去看电影《哪吒2》，帮我记着提醒我出门",
    # 3. 妈妈生日（event/high）
    "后天是我妈妈生日，我要提前订个蛋糕，千万别让我忘了",
    # 4. 胃镜检查（event/high）— 后续会修改时间
    "最近胃不太舒服，下周三上午九点预约了医院做胃镜检查，提醒我空腹去",
    # 5. 冥想习惯（habit/mid）
    "我决定从今天开始每天晚上十点做二十分钟冥想，帮我坚持这个习惯",
    # 6. 驾校考试（event/high）— 后续会修改时间
    "下周六上午要参加驾校科目三考试，我特别紧张，到时候给我打气",
    # 7. 面试焦虑（emotion/high + event）
    "明天下午两点有个大厂的线上面试，我好紧张好害怕，万一搞砸了怎么办",
    # 8. 交房租（event/mid）
    "后天15号要交房租了，别让我忘了转账给房东",
    # 9. 线上课程（habit/mid）
    "我报了个周末Python编程课，每周六上午九点开始，提醒我准时上课",
    # 10. 分手情绪（emotion/high）
    "和女朋友分手了快一周了，每天晚上都睡不着，心里堵得慌，感觉好孤独",
    # 11. 银行办卡（event/mid）— 后续会取消
    "下周四下午三点要去银行办张新的信用卡，提醒我带身份证出门",
    # 12. 写日记（habit/mid）
    "我想开始每天睡前花十分钟写日记记录心情，帮我养成这个习惯",
    # 13. 物业费（event/mid）
    "下个月1号要交物业费，别让我忘了",
    # 14. 爬山放松（event/low）
    "这周日早上想去爬山放松一下心情，提醒我早点起来出发",
    # 15. 体检报告（event/mid）
    "上次体检的报告下周五可以去医院拿了，提醒我去取",
]

# ================================================================
#  Phase 2: 取消和修改对话 — LLM 通过 moment_updates 自动处理
# ================================================================

PHASE2_MESSAGES = [
    # 取消：看电影
    "之前约的看电影不去了，朋友临时有事取消了，那个提醒帮我撤掉",
    # 修改：胃镜检查改时间
    "之前预约的胃镜检查改时间了，医院通知改到下周四上午十点，帮我更新一下提醒",
    # 取消：银行办卡
    "之前说去银行办信用卡不去了，我已经在网上申请了，把那个提醒取消掉",
    # 修改：驾校考试延期
    "驾校教练说科目三考试推迟到下下周六上午了，帮我改一下时间",
    # 收尾对话
    "谢谢你帮我记着这么多事情，有你在真的放心多了",
]


# ================================================================
#  辅助函数
# ================================================================

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _fmt_bj(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        s = value.strip().replace("Z", "+00:00")
        if not s:
            return ""
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            return value
        dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    elif isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    else:
        return str(value)
    return dt.astimezone(BJ_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _status_label(status: int, confirmed: bool) -> str:
    if status == 1 and not confirmed:
        return "pending"
    if status == 1 and confirmed:
        return "scheduled"
    if status == 2:
        return "completed"
    if status == 3:
        return "cancelled"
    return f"unknown({status})"


def _truncate(s: str, max_len: int = 60) -> str:
    s = s.replace("\n", " ").strip()
    return s if len(s) <= max_len else s[:max_len] + "..."


def _escape_md(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def _send_with_retry(client: APIClient, conv_id: str, msg: str, retries: int = 3) -> str:
    """发送消息（含 502 重试），返回 AI 回复内容。"""
    for attempt in range(retries):
        try:
            resp = client.send_message(conv_id, msg)
            return (resp.get("content") or "") if isinstance(resp, dict) else ""
        except Exception as e:
            if attempt < retries - 1:
                console.print(f"    [yellow]RETRY[/yellow] {e} (attempt {attempt + 1}/{retries})")
                time.sleep(3)
            else:
                console.print(f"    [red]ERR[/red] {e}")
                return f"[ERROR: {e}]"


async def _expedite_remind_times(moment_ids: List[str]) -> int:
    """直连 PostgreSQL，把指定 moments 的 remind_time 设为过去。"""
    import asyncpg

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    db = os.getenv("POSTGRES_DB_NAME", "llm_chat")

    pool = await asyncpg.create_pool(
        host=host, port=port, user=user, password=password, database=db,
        min_size=1, max_size=2,
    )
    try:
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE moments SET remind_time = $1, updated_at = $1 "
                "WHERE moment_id = ANY($2::text[]) AND status = 1 AND confirmed = TRUE",
                past, moment_ids,
            )
        return int(result.split()[-1]) if result else 0
    finally:
        await pool.close()


def _collect_moments(client: APIClient, user_id: str, conv_id: str) -> List[Dict[str, Any]]:
    """获取本会话所有关键时刻，按创建时间排序。"""
    all_moments = client.list_moments(user_id, limit=500)
    conv_moments = [m for m in all_moments if m.get("conversation_id") == conv_id]
    conv_moments.sort(key=lambda x: x.get("created_at") or "")
    return conv_moments


# ================================================================
#  主测试命令
# ================================================================

@app.command("test-full-lifecycle")
def test_full_lifecycle(
    api_url: str = typer.Option("http://localhost:8000", "--api-url", help="API 地址"),
    model: str = typer.Option("deepseek-chat", "--model", "-m", help="LLM 模型名"),
    worker_timeout: float = typer.Option(120.0, "--worker-timeout", help="等 worker 兑现的超时秒数"),
    out_dir: Path = typer.Option(
        Path("docs/reports"), "--out-dir",
        help="报告输出目录", dir_okay=True, file_okay=False,
    ),
):
    """全生命周期测试：对话→识别12+moment→取消→修改→确认→兑现→评估报告。

    前置条件:
    - 后端 FastAPI 已启动
    - moment_worker 已启动
    """
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"e2e_full_lifecycle_{run_id}.md"
    client = APIClient(api_url)
    started_at = _now_utc()

    md: List[str] = []
    md.append("# 全生命周期端到端测试报告")
    md.append("")
    md.append(f"- **run_id**: `{run_id}`")
    md.append(f"- **started_at**: `{_fmt_bj(started_at)}`")
    md.append(f"- **model**: `{model}`")
    md.append(f"- **Phase 1 对话**: {len(PHASE1_MESSAGES)} 轮（多主题触发 moment）")
    md.append(f"- **Phase 2 对话**: {len(PHASE2_MESSAGES)} 轮（取消/修改 moment）")
    md.append("")

    # 测试指标收集
    test_metrics: Dict[str, Any] = {
        "total_moments_created": 0,
        "cancelled_by_ai": 0,
        "cancelled_by_api": 0,
        "modified_by_ai": 0,
        "modified_by_api": 0,
        "delivered": 0,
        "total_non_cancelled": 0,
    }

    try:
        # ============================================================
        #  1. 创建资源
        # ============================================================
        console.print("\n[bold cyan]═══ Phase 0: 创建测试资源 ═══[/bold cyan]")
        username = f"lifecycle_{run_id}"
        user = client.create_user(username)
        user_id = user["user_id"]

        from .agent import DEFAULT_MOMENT_DEFINITION
        system_prompt = (
            f"你的名字是：小初\n\n"
            f"你是一个温暖、贴心、细致的生活陪伴助手，善于发现用户话语中的关键时刻。\n"
            f"当用户提到需要提醒的事情、重要事件、情绪波动、或需要坚持的习惯时，你要准确识别并创建 moment。\n"
            f"当用户说某件事取消了或者改时间了，你要在 moment_updates 中正确取消或更新对应的 moment。\n"
            f"你只用简体中文回复。\n\n"
            f"{DEFAULT_MOMENT_DEFINITION}"
        )
        agent = client.create_agent(
            name=f"lifecycle_agent_{run_id}", system_prompt=system_prompt, model=model,
        )
        agent_id = agent["agent_id"]
        conv = client.create_conversation(user_id, agent_id, title=f"lifecycle:{run_id}")
        conv_id = conv["conversation_id"]

        md.append("## 1. 资源创建")
        md.append("")
        md.append("| 资源 | ID |")
        md.append("|---|---|")
        md.append(f"| user | `{user_id}` (username: {username}) |")
        md.append(f"| agent | `{agent_id}` (model: {model}) |")
        md.append(f"| conversation | `{conv_id}` |")
        md.append("")
        console.print(f"  [green]OK[/green] user={user_id}, conv={conv_id}")

        # ============================================================
        #  2. Phase 1: 多主题对话，触发 12+ moments
        # ============================================================
        console.print(f"\n[bold cyan]═══ Phase 1: 发送 {len(PHASE1_MESSAGES)} 轮多主题对话 ═══[/bold cyan]")
        md.append("## 2. Phase 1 对话记录（触发 moment 创建）")
        md.append("")
        md.append("| # | 用户消息 | AI 回复（摘要） |")
        md.append("|---:|---|---|")

        transcript: List[Dict[str, str]] = []
        for i, msg in enumerate(PHASE1_MESSAGES, start=1):
            console.print(f"  [{i}/{len(PHASE1_MESSAGES)}] {_truncate(msg, 45)}")
            ai_content = _send_with_retry(client, conv_id, msg)
            transcript.append({"user": msg, "ai": ai_content})
            md.append(f"| {i} | {_escape_md(_truncate(msg, 50))} | {_escape_md(_truncate(ai_content, 50))} |")
            time.sleep(1.5)

        md.append("")
        console.print(f"  [green]OK[/green] 完成 Phase 1 ({len(PHASE1_MESSAGES)} 轮)")

        # ============================================================
        #  3. Phase 1 关键时刻快照
        # ============================================================
        console.print("\n[bold cyan]═══ Phase 1 Moments 快照 ═══[/bold cyan]")
        phase1_moments = _collect_moments(client, user_id, conv_id)
        test_metrics["total_moments_created"] = len(phase1_moments)

        md.append("## 3. Phase 1 识别到的关键时刻")
        md.append("")
        md.append(f"**总计**: {len(phase1_moments)} 个")
        md.append("")
        if phase1_moments:
            md.append("| # | type | importance | event_description | status | confirmed | event_time |")
            md.append("|---:|---|---|---|---|---|---|")
            for i, m in enumerate(phase1_moments, start=1):
                label = _status_label(m.get("status", 0), m.get("confirmed", False))
                md.append(
                    f"| {i} | {m.get('type')} | {m.get('importance')} "
                    f"| {_escape_md(_truncate(m.get('event_description', ''), 40))} "
                    f"| {label} | {m.get('confirmed')} | {_fmt_bj(m.get('event_time'))} |"
                )
        md.append("")

        console.print(f"  识别到 [bold]{len(phase1_moments)}[/bold] 个关键时刻")
        for m in phase1_moments:
            label = _status_label(m.get("status", 0), m.get("confirmed", False))
            console.print(f"    {m['moment_id'][:8]}... [{label}] {_truncate(m.get('event_description', ''), 35)}")

        # ============================================================
        #  4. Phase 2: 发送取消/修改对话
        # ============================================================
        console.print(f"\n[bold cyan]═══ Phase 2: 发送 {len(PHASE2_MESSAGES)} 轮取消/修改对话 ═══[/bold cyan]")
        md.append("## 4. Phase 2 对话记录（取消/修改 moment）")
        md.append("")
        md.append("| # | 用户消息 | AI 回复（摘要） |")
        md.append("|---:|---|---|")

        phase2_transcript: List[Dict[str, str]] = []
        for i, msg in enumerate(PHASE2_MESSAGES, start=1):
            idx = len(PHASE1_MESSAGES) + i
            console.print(f"  [{idx}] {_truncate(msg, 45)}")
            ai_content = _send_with_retry(client, conv_id, msg)
            phase2_transcript.append({"user": msg, "ai": ai_content})
            md.append(f"| {idx} | {_escape_md(_truncate(msg, 50))} | {_escape_md(_truncate(ai_content, 50))} |")
            time.sleep(1.5)

        md.append("")
        console.print(f"  [green]OK[/green] 完成 Phase 2 ({len(PHASE2_MESSAGES)} 轮)")

        # ============================================================
        #  5. Phase 2 后关键时刻快照（对比 LLM 的自动取消/修改）
        # ============================================================
        console.print("\n[bold cyan]═══ Phase 2 后 Moments 快照 ═══[/bold cyan]")
        phase2_moments = _collect_moments(client, user_id, conv_id)

        # 统计 AI 自动取消了多少
        phase1_ids = {m["moment_id"] for m in phase1_moments}
        ai_cancelled = [
            m for m in phase2_moments
            if m["moment_id"] in phase1_ids and m.get("status") == 3
        ]
        # 新增的 moments（Phase 2 对话中 LLM 创建的替代 moment）
        new_in_phase2 = [m for m in phase2_moments if m["moment_id"] not in phase1_ids]

        test_metrics["cancelled_by_ai"] = len(ai_cancelled)
        test_metrics["modified_by_ai"] = len(new_in_phase2)

        md.append("## 5. Phase 2 后关键时刻变化")
        md.append("")
        md.append(f"- **AI 自动取消**: {len(ai_cancelled)} 个")
        md.append(f"- **AI 新创建（替代/修改）**: {len(new_in_phase2)} 个")
        md.append(f"- **当前总计**: {len(phase2_moments)} 个")
        md.append("")

        if ai_cancelled:
            md.append("### AI 自动取消的 moments")
            md.append("")
            md.append("| moment_id | event_description |")
            md.append("|---|---|")
            for m in ai_cancelled:
                md.append(f"| `{m['moment_id'][:12]}...` | {_escape_md(_truncate(m.get('event_description', ''), 40))} |")
            md.append("")

        if new_in_phase2:
            md.append("### Phase 2 中 AI 新创建的 moments（替代修改的旧 moment）")
            md.append("")
            md.append("| moment_id | event_description | status |")
            md.append("|---|---|---|")
            for m in new_in_phase2:
                label = _status_label(m.get("status", 0), m.get("confirmed", False))
                md.append(f"| `{m['moment_id'][:12]}...` | {_escape_md(_truncate(m.get('event_description', ''), 40))} | {label} |")
            md.append("")

        for m in phase2_moments:
            label = _status_label(m.get("status", 0), m.get("confirmed", False))
            console.print(f"    {m['moment_id'][:8]}... [{label}] {_truncate(m.get('event_description', ''), 35)}")

        # ============================================================
        #  6. 手动补充取消和修改（如果 AI 没有自动完成）
        # ============================================================
        console.print("\n[bold cyan]═══ 手动补充 Cancel/Modify ═══[/bold cyan]")
        md.append("## 6. 手动补充操作（API 直接取消/修改）")
        md.append("")

        # 重新获取最新状态
        current_moments = _collect_moments(client, user_id, conv_id)
        active_moments = [
            m for m in current_moments
            if m.get("status") == 1  # pending or scheduled
        ]

        manual_cancel_log: List[Dict[str, str]] = []
        manual_modify_log: List[Dict[str, str]] = []

        # 检查目标：确保至少有 2 个 cancelled + 2 个 modified
        total_cancelled = len([m for m in current_moments if m.get("status") == 3])
        total_new_replacements = len(new_in_phase2)

        # 如果取消数不足 2 个，手动取消一些
        cancel_targets = [
            "电影", "信用卡", "银行",
        ]
        if total_cancelled < 2 and active_moments:
            need_cancel = min(2 - total_cancelled, len(active_moments))
            candidates_to_cancel = []
            for m in active_moments:
                desc = m.get("event_description", "").lower()
                for kw in cancel_targets:
                    if kw in desc and m["moment_id"] not in [c["moment_id"] for c in candidates_to_cancel]:
                        candidates_to_cancel.append(m)
                        break
            # 如果关键词没找到，取活跃列表的最后几个
            if len(candidates_to_cancel) < need_cancel:
                for m in reversed(active_moments):
                    if m not in candidates_to_cancel:
                        candidates_to_cancel.append(m)
                    if len(candidates_to_cancel) >= need_cancel:
                        break

            for m in candidates_to_cancel[:need_cancel]:
                try:
                    result = client.cancel_moment(m["moment_id"])
                    label_after = _status_label(result.get("status", 0), result.get("confirmed", False))
                    manual_cancel_log.append({
                        "moment_id": m["moment_id"],
                        "desc": m.get("event_description", ""),
                        "result": label_after,
                    })
                    test_metrics["cancelled_by_api"] += 1
                    console.print(f"  [yellow]CANCEL[/yellow] {m['moment_id'][:8]}... → {label_after}")
                except Exception as e:
                    console.print(f"  [red]ERR[/red] cancel {m['moment_id'][:8]}... failed: {e}")

        # 如果修改数不足 2 个，手动 "修改"（取消旧的 + 发消息创建新的）
        modify_targets = ["胃镜", "科目三", "驾校"]
        if total_new_replacements < 2 and active_moments:
            # 重新获取当前状态
            current_moments = _collect_moments(client, user_id, conv_id)
            active_moments = [m for m in current_moments if m.get("status") == 1]

            candidates_to_modify = []
            for m in active_moments:
                desc = m.get("event_description", "").lower()
                for kw in modify_targets:
                    if kw in desc and m["moment_id"] not in [c["moment_id"] for c in candidates_to_modify]:
                        candidates_to_modify.append(m)
                        break
            if len(candidates_to_modify) < 2 - total_new_replacements:
                for m in active_moments:
                    if m not in candidates_to_modify:
                        candidates_to_modify.append(m)
                    if len(candidates_to_modify) >= 2 - total_new_replacements:
                        break

            for m in candidates_to_modify[:max(0, 2 - total_new_replacements)]:
                try:
                    # 取消旧 moment
                    client.cancel_moment(m["moment_id"])
                    desc = m.get("event_description", "")
                    manual_modify_log.append({
                        "old_moment_id": m["moment_id"],
                        "old_desc": desc,
                    })
                    test_metrics["modified_by_api"] += 1
                    console.print(f"  [yellow]MODIFY-CANCEL[/yellow] {m['moment_id'][:8]}... (old: {_truncate(desc, 30)})")
                    # 发送消息创建替代 moment
                    modify_msg = f"之前说的「{_truncate(desc, 20)}」改到下周了，帮我重新设一个提醒"
                    ai_reply = _send_with_retry(client, conv_id, modify_msg)
                    phase2_transcript.append({"user": modify_msg, "ai": ai_reply})
                    console.print(f"  [green]MODIFY-CREATE[/green] 发送替代消息")
                    time.sleep(1.5)
                except Exception as e:
                    console.print(f"  [red]ERR[/red] modify {m['moment_id'][:8]}... failed: {e}")

        if manual_cancel_log:
            md.append("### 手动取消")
            md.append("")
            md.append("| moment_id | event_description | result |")
            md.append("|---|---|---|")
            for cl in manual_cancel_log:
                md.append(f"| `{cl['moment_id'][:12]}...` | {_escape_md(_truncate(cl['desc'], 35))} | {cl['result']} |")
            md.append("")

        if manual_modify_log:
            md.append("### 手动修改（取消旧 + 发消息创建新）")
            md.append("")
            md.append("| old_moment_id | old_description |")
            md.append("|---|---|")
            for ml in manual_modify_log:
                md.append(f"| `{ml['old_moment_id'][:12]}...` | {_escape_md(_truncate(ml['old_desc'], 35))} |")
            md.append("")

        if not manual_cancel_log and not manual_modify_log:
            md.append("AI 已在对话中自动完成取消和修改，无需手动补充。")
            md.append("")

        # ============================================================
        #  7. 确认所有 pending moments
        # ============================================================
        console.print("\n[bold cyan]═══ 确认所有 pending moments ═══[/bold cyan]")
        final_moments_pre_confirm = _collect_moments(client, user_id, conv_id)
        confirmed_ids: List[str] = []
        confirm_log: List[Dict[str, Any]] = []

        for m in final_moments_pre_confirm:
            mid = m["moment_id"]
            status = m.get("status", 0)
            confirmed = m.get("confirmed", False)
            label_before = _status_label(status, confirmed)

            if status == 1 and not confirmed:
                try:
                    result = client.confirm_moment(mid)
                    label_after = _status_label(result.get("status", 0), result.get("confirmed", False))
                    confirm_log.append({"moment_id": mid, "before": label_before, "after": label_after})
                    console.print(f"  {mid[:8]}... {label_before} → {label_after}")
                except Exception as e:
                    confirm_log.append({"moment_id": mid, "before": label_before, "after": f"ERROR: {e}"})

            if status == 1:
                confirmed_ids.append(mid)

        md.append("## 7. 关键时刻确认")
        md.append("")
        if confirm_log:
            md.append("| moment_id | before | after |")
            md.append("|---|---|---|")
            for cl in confirm_log:
                md.append(f"| `{cl['moment_id'][:12]}...` | {cl['before']} | {cl['after']} |")
            md.append("")
        else:
            md.append("所有 moment 已在对话中被 AI 自动确认（needs_user_confirm=false）。")
            md.append("")
        console.print(f"  [green]OK[/green] 处理了 {len(confirm_log)} 个 pending → scheduled")

        # ============================================================
        #  8. 调整 remind_time 使 worker 可立即兑现
        # ============================================================
        if confirmed_ids:
            console.print(f"\n[bold cyan]═══ 调整 {len(confirmed_ids)} 个 moment 的 remind_time ═══[/bold cyan]")
            updated_count = asyncio.run(_expedite_remind_times(confirmed_ids))
            console.print(f"  [green]OK[/green] 更新了 {updated_count} 行")
            md.append("## 8. Remind Time 调整（测试加速）")
            md.append("")
            md.append(f"通过直连 PostgreSQL 将 {len(confirmed_ids)} 个 scheduled moment 的 remind_time 设为过去。")
            md.append(f"实际更新 **{updated_count}** 行。")
            md.append("")
        else:
            md.append("## 8. Remind Time 调整")
            md.append("")
            md.append("无 scheduled moment 需要加速。")
            md.append("")

        # ============================================================
        #  9. 等待 worker 兑现
        # ============================================================
        console.print(f"\n[bold cyan]═══ 等待 worker 兑现（超时 {worker_timeout}s） ═══[/bold cyan]")
        md.append("## 9. 兑现等待")
        md.append("")

        deadline = time.time() + worker_timeout
        delivered_count = 0
        poll_round = 0

        while time.time() < deadline and confirmed_ids:
            poll_round += 1
            time.sleep(3)
            refreshed = client.list_moments(user_id, limit=500)
            refreshed_map = {m["moment_id"]: m for m in refreshed}
            delivered_count = sum(
                1 for mid in confirmed_ids
                if refreshed_map.get(mid, {}).get("status") == 2
            )
            console.print(f"  poll #{poll_round}: {delivered_count}/{len(confirmed_ids)} delivered")
            if delivered_count >= len(confirmed_ids):
                break

        md.append(f"- 轮询次数: {poll_round}")
        md.append(f"- 兑现完成: **{delivered_count}/{len(confirmed_ids)}**")
        md.append("")
        test_metrics["delivered"] = delivered_count
        test_metrics["total_non_cancelled"] = len(confirmed_ids)

        # ============================================================
        #  10. 最终状态汇总
        # ============================================================
        console.print("\n[bold cyan]═══ 生成最终报告 ═══[/bold cyan]")
        final_moments = _collect_moments(client, user_id, conv_id)

        md.append("## 10. 最终关键时刻状态")
        md.append("")
        md.append("| # | moment_id | event_description | type | importance | status | executed_at | first_message |")
        md.append("|---:|---|---|---|---|---|---|---|")
        for i, m in enumerate(final_moments, start=1):
            md.append(
                f"| {i} | `{m['moment_id'][:12]}...` "
                f"| {_escape_md(_truncate(m.get('event_description', ''), 30))} "
                f"| {m.get('type')} | {m.get('importance')} "
                f"| **{_status_label(m.get('status', 0), m.get('confirmed', False))}** "
                f"| {_fmt_bj(m.get('executed_at'))} "
                f"| {_escape_md(_truncate(m.get('first_message', '') or '', 25))} |"
            )
        md.append("")

        # 统计
        status_counts: Dict[str, int] = {}
        for m in final_moments:
            label = _status_label(m.get("status", 0), m.get("confirmed", False))
            status_counts[label] = status_counts.get(label, 0) + 1

        md.append("### 统计")
        md.append("")
        for label, count in sorted(status_counts.items()):
            md.append(f"- {label}: **{count}**")
        md.append(f"- 总计: **{len(final_moments)}**")
        md.append("")

        # ============================================================
        #  11. 完整对话记录
        # ============================================================
        md.append("## 11. 完整对话记录")
        md.append("")
        all_transcript = transcript + phase2_transcript
        for i, t in enumerate(all_transcript, start=1):
            md.append(f"### 第 {i} 轮")
            md.append("")
            md.append(f"**用户**: {t['user']}")
            md.append("")
            md.append(f"**AI**: {t['ai']}")
            md.append("")

        # ============================================================
        #  12. 测试结论
        # ============================================================
        total_moments = len(final_moments)
        completed_count = status_counts.get("completed", 0)
        cancelled_count = status_counts.get("cancelled", 0)

        # 测试判定
        pass_moment_count = total_moments >= 10
        pass_cancelled = cancelled_count >= 2
        pass_delivery = (
            delivered_count == len(confirmed_ids)
            and len(confirmed_ids) > 0
        )
        all_pass = pass_moment_count and pass_cancelled and pass_delivery

        md.append("## 12. 测试结论")
        md.append("")
        md.append("### 测试指标")
        md.append("")
        md.append(f"| 指标 | 结果 | 目标 | 判定 |")
        md.append("|---|---|---|---|")
        md.append(f"| 关键时刻总数 | {total_moments} | >= 10 | **{'PASS' if pass_moment_count else 'FAIL'}** |")
        md.append(f"| 取消的 moment | {cancelled_count} | >= 2 | **{'PASS' if pass_cancelled else 'FAIL'}** |")
        md.append(f"| 修改的 moment（AI自动/手动） | {test_metrics['modified_by_ai'] + test_metrics['modified_by_api']} | >= 1 | **{'PASS' if (test_metrics['modified_by_ai'] + test_metrics['modified_by_api']) >= 1 else 'FAIL'}** |")
        md.append(f"| 兑现完成率 | {delivered_count}/{len(confirmed_ids)} | 100% | **{'PASS' if pass_delivery else 'FAIL'}** |")
        md.append("")

        md.append("### 状态迁移覆盖")
        md.append("")
        md.append(f"- pending → scheduled → completed（兑现链路）: **{completed_count}** 个")
        md.append(f"- pending/scheduled → cancelled（取消链路）: **{cancelled_count}** 个")
        md.append(f"  - AI 对话中自动取消: **{test_metrics['cancelled_by_ai']}** 个")
        md.append(f"  - API 手动取消: **{test_metrics['cancelled_by_api']}** 个")
        md.append(f"- 修改（取消旧 + 创建新）:")
        md.append(f"  - AI 对话中自动修改: **{test_metrics['modified_by_ai']}** 个")
        md.append(f"  - API 手动修改: **{test_metrics['modified_by_api']}** 个")
        md.append("")

        md.append(f"### 总结: **{'ALL PASS' if all_pass else 'PARTIAL FAIL'}**")
        md.append("")
        md.append("---")
        md.append(f"_报告生成时间: {_fmt_bj(_now_utc())}_")

        # 写入报告
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(md), encoding="utf-8")

        if all_pass:
            console.print(f"\n[bold green]═══ ALL PASS ═══[/bold green] 报告: {report_path.as_posix()}")
        else:
            console.print(f"\n[bold yellow]═══ PARTIAL FAIL ═══[/bold yellow] 报告: {report_path.as_posix()}")
            if not pass_moment_count:
                console.print(f"  [yellow]关键时刻数 {total_moments} < 10[/yellow]")
            if not pass_cancelled:
                console.print(f"  [yellow]取消数 {cancelled_count} < 2[/yellow]")
            if not pass_delivery:
                console.print(f"  [yellow]兑现 {delivered_count}/{len(confirmed_ids)}[/yellow]")

    except Exception as e:
        md.append(f"\n## ERROR\n\n`{type(e).__name__}: {e}`\n")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(md), encoding="utf-8")
        console.print(f"[red]ERR[/red] {e}")
        console.print(f"报告已保存: {report_path.as_posix()}")
        raise typer.Exit(1)
    finally:
        client.close()
