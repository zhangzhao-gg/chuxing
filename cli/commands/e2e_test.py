"""
[INPUT]: 依赖 typer 的 Typer/Option，依赖 rich 的 Console，依赖 asyncpg（直连 PostgreSQL 调整 remind_time），依赖 cli.client 的 APIClient，依赖 commands.agent 的 DEFAULT_MOMENT_DEFINITION，依赖标准库 asyncio/os/time/datetime
[OUTPUT]: 对外提供 test-conversation 端到端测试命令（e2e test-conversation）
[POS]: cli/commands 的端到端自动化测试入口；验证 对话→moment识别→确认→兑现 全链路；内置 502 重试
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from rich.console import Console

from ..client import APIClient

app = typer.Typer()
console = Console()
BJ_TZ = timezone(timedelta(hours=8))

# ================================================================
#  马拉松备赛主题 — 20 轮对话，自然触发 10+ 关键时刻
# ================================================================

CONVERSATION_MESSAGES = [
    # 1. 马拉松比赛（高优先事件）
    "我报名了下个月15号的城市半程马拉松，第一次跑半马，挺紧张的，到时候记得给我加油鼓劲",
    # 2. 配速测试（明确提醒）
    "教练说这周六早上要跑个15公里测试一下配速，提醒我别忘了",
    # 3. 医院体检（明确提醒）
    "对了，下周一上午我得去医院做个运动体检，看看膝盖的老伤，提醒我别迟到",
    # 4. 情绪：担心膝盖（情绪关键时刻）
    "有点担心体检结果，万一膝盖不行怎么办，好焦虑好害怕",
    # 5. 晨跑习惯（习惯追踪）
    "我打算从明天开始每天早上六点起来晨跑训练，帮我盯着别偷懒",
    # 6. 买跑鞋（明确提醒）
    "下周三下午要去运动品店买双新跑鞋，旧的磨损太严重了，到点提醒我出门",
    # 7. 跑姿调整（明确提醒）
    "教练让我下周五傍晚去他那里调整跑步姿势，纠正一下步幅，提醒我别忘了",
    # 8. 公司年会（事件提醒）
    "这周四晚上公司有年会，那天就不训练了，得穿正装出席，提醒我提前准备好衣服",
    # 9. 碳水储备（定时提醒）
    "比赛前三天开始碳水储备期，到时候提醒我多吃面条和米饭，这很重要",
    # 10. 装备整理（赛前提醒）
    "比赛前一晚一定要把装备都收拾好，号码布、芯片计时器、能量胶，提醒我检查一遍",
    # 11. 比赛当天（早起提醒）
    "比赛当天凌晨四点半就得起床出发去赛事起点，提醒我定好闹钟",
    # 12. 赛后拉伸（事后提醒）
    "跑完赛后拉伸非常重要，比赛结束后提醒我一定要做15分钟拉伸别偷懒直接回家",
    # 13. 赛后庆祝（事件）
    "半马跑完我想约几个朋友去吃火锅庆祝一下，提醒我赛后发消息召集大家",
    # 14. 长距离拉练（习惯追踪）
    "每周日做一个长距离拉练，比赛前这个习惯一定要坚持住，每周日提醒我",
    # 15. 减量训练（赛前阶段提醒）
    "赛前一周要减量训练，教练说跑量减到平时的一半，到时候提醒我注意休息",
    # 16. 冰浴恢复（赛后提醒）
    "比赛完第二天安排一次冰浴恢复，帮助肌肉恢复，提醒我预约冰浴",
    # 17. 拿体检报告（明确提醒）
    "下下周要去拿体检报告，希望一切正常，到时候提醒我去医院取报告",
    # 18. 最近失眠严重（情绪关键时刻）
    "最近压力太大了经常失眠到凌晨三四点，整个人状态很差，感觉快撑不住了",
    # 19. 补给策略规划（赛前提醒）
    "突然想到比赛当天的补给策略也要提前规划，每5公里补水，比赛前一天提醒我准备好能量胶和盐丸",
    # 20. 兴奋期待（正面情绪 + 总结）
    "想想完赛的成就感就激动，这几周一定要好好准备不能松懈",
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


async def _expedite_remind_times(moment_ids: List[str]) -> int:
    """直连 PostgreSQL，把指定 moments 的 remind_time 设为过去，让 worker 立即领取。"""
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
        # result 形如 "UPDATE N"
        return int(result.split()[-1]) if result else 0
    finally:
        await pool.close()


# ================================================================
#  主测试命令
# ================================================================

@app.command("test-conversation")
def test_conversation(
    api_url: str = typer.Option("http://localhost:8000", "--api-url", help="API 地址"),
    model: str = typer.Option("deepseek-chat", "--model", "-m", help="LLM 模型名"),
    worker_timeout: float = typer.Option(120.0, "--worker-timeout", help="等 worker 兑现的超时秒数"),
    out_dir: Path = typer.Option(
        Path("docs/reports"), "--out-dir",
        help="报告输出目录", dir_okay=True, file_okay=False,
    ),
):
    """端到端测试：自然对话 → LLM 识别关键时刻 → 确认 → worker 兑现 → 生成报告。

    前置条件:
    - 后端 FastAPI 已启动（uv run uvicorn backend.main:app --port 8000）
    - moment_worker 已启动（uv run python -m backend.moment_worker）
    """
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"e2e_conversation_test_{run_id}.md"
    client = APIClient(api_url)
    started_at = _now_utc()

    # 报告内容
    md: List[str] = []
    md.append("# 端到端对话测试报告")
    md.append("")
    md.append(f"- **run_id**: `{run_id}`")
    md.append(f"- **started_at**: `{_fmt_bj(started_at)}`")
    md.append(f"- **model**: `{model}`")
    md.append(f"- **topic**: 马拉松备赛（{len(CONVERSATION_MESSAGES)} 轮对话）")
    md.append("")

    try:
        # ============================================================
        #  1. 创建资源
        # ============================================================
        console.print("[cyan]1. 创建测试资源...[/cyan]")
        username = f"e2e_test_{run_id}"
        user = client.create_user(username)
        user_id = user["user_id"]

        from .agent import DEFAULT_MOMENT_DEFINITION
        system_prompt = (
            f"你的名字是：小初\n\n"
            f"你是一个温暖、贴心的生活陪伴助手，善于发现用户话语中的关键时刻。"
            f"你只用简体中文回复。\n\n"
            f"{DEFAULT_MOMENT_DEFINITION}"
        )
        agent = client.create_agent(
            name=f"e2e_agent_{run_id}", system_prompt=system_prompt, model=model,
        )
        agent_id = agent["agent_id"]
        conv = client.create_conversation(user_id, agent_id, title=f"e2e:{run_id}")
        conv_id = conv["conversation_id"]

        md.append("## 1. 资源创建")
        md.append("")
        md.append(f"| 资源 | ID |")
        md.append("|---|---|")
        md.append(f"| user | `{user_id}` (username: {username}) |")
        md.append(f"| agent | `{agent_id}` (model: {model}) |")
        md.append(f"| conversation | `{conv_id}` |")
        md.append("")
        console.print(f"  [green]OK[/green] user={user_id}, conv={conv_id}")

        # ============================================================
        #  2. 发送对话消息
        # ============================================================
        console.print(f"[cyan]2. 发送 {len(CONVERSATION_MESSAGES)} 轮对话...[/cyan]")
        md.append("## 2. 对话记录")
        md.append("")
        md.append("| # | 用户消息 | AI 回复（摘要） |")
        md.append("|---:|---|---|")

        transcript: List[Dict[str, str]] = []
        for i, msg in enumerate(CONVERSATION_MESSAGES, start=1):
            console.print(f"  [{i}/{len(CONVERSATION_MESSAGES)}] {_truncate(msg, 40)}")
            ai_content = ""
            # 重试机制：502 / 网络闪断 自动重试（最多 3 次）
            for attempt in range(3):
                try:
                    resp = client.send_message(conv_id, msg)
                    ai_content = (resp.get("content") or "") if isinstance(resp, dict) else ""
                    break
                except Exception as e:
                    if attempt < 2:
                        console.print(f"    [yellow]RETRY[/yellow] {e} (attempt {attempt + 1}/3)")
                        time.sleep(3)
                    else:
                        ai_content = f"[ERROR: {e}]"
                        console.print(f"    [red]ERR[/red] {e}")
            transcript.append({"user": msg, "ai": ai_content})
            md.append(f"| {i} | {_escape_md(_truncate(msg))} | {_escape_md(_truncate(ai_content))} |")
            # 轮次间隔，给 LLM 和 DB 喘息
            time.sleep(1)

        md.append("")
        console.print(f"  [green]OK[/green] 完成 {len(transcript)} 轮对话")

        # ============================================================
        #  3. 获取所有识别到的关键时刻
        # ============================================================
        console.print("[cyan]3. 获取关键时刻列表...[/cyan]")
        all_moments = client.list_moments(user_id, limit=500)
        conv_moments = [m for m in all_moments if m.get("conversation_id") == conv_id]
        conv_moments.sort(key=lambda x: x.get("created_at") or "")

        md.append("## 3. 识别到的关键时刻")
        md.append("")
        md.append(f"**总计**: {len(conv_moments)} 个")
        md.append("")
        if conv_moments:
            md.append("| # | type | importance | event_description | status | confirmed | event_time | remind_time |")
            md.append("|---:|---|---|---|---|---|---|---|")
            for i, m in enumerate(conv_moments, start=1):
                md.append(
                    f"| {i} | {m.get('type')} | {m.get('importance')} "
                    f"| {_escape_md(_truncate(m.get('event_description',''), 40))} "
                    f"| {_status_label(m.get('status',0), m.get('confirmed',False))} "
                    f"| {m.get('confirmed')} "
                    f"| {_fmt_bj(m.get('event_time'))} "
                    f"| {_fmt_bj(m.get('remind_time'))} |"
                )
            md.append("")

        console.print(f"  [green]OK[/green] 识别到 {len(conv_moments)} 个关键时刻")
        if len(conv_moments) < 10:
            console.print(f"  [yellow]WARN[/yellow] 未达到 10 个目标（当前 {len(conv_moments)}）")

        # ============================================================
        #  4. 确认所有 pending 的关键时刻
        # ============================================================
        console.print("[cyan]4. 确认 pending 关键时刻...[/cyan]")
        confirmed_ids: List[str] = []
        confirm_log: List[Dict[str, Any]] = []
        for m in conv_moments:
            mid = m["moment_id"]
            status = m.get("status", 0)
            confirmed = m.get("confirmed", False)
            label_before = _status_label(status, confirmed)

            if status == 1 and not confirmed:
                try:
                    result = client.confirm_moment(mid)
                    label_after = _status_label(result.get("status", 0), result.get("confirmed", False))
                    confirm_log.append({"moment_id": mid, "before": label_before, "after": label_after})
                    console.print(f"  {mid[:8]}... {label_before} -> {label_after}")
                except Exception as e:
                    confirm_log.append({"moment_id": mid, "before": label_before, "after": f"ERROR: {e}"})
            elif status == 1 and confirmed:
                confirm_log.append({"moment_id": mid, "before": label_before, "after": "already scheduled"})

            if status == 1:
                confirmed_ids.append(mid)

        md.append("## 4. 关键时刻确认")
        md.append("")
        if confirm_log:
            md.append("| moment_id | before | after |")
            md.append("|---|---|---|")
            for cl in confirm_log:
                md.append(f"| `{cl['moment_id'][:12]}...` | {cl['before']} | {cl['after']} |")
            md.append("")
        console.print(f"  [green]OK[/green] 处理了 {len(confirm_log)} 个 moment")

        # ============================================================
        #  5. 调整 remind_time 使 worker 可立即兑现
        # ============================================================
        if confirmed_ids:
            console.print(f"[cyan]5. 调整 {len(confirmed_ids)} 个 moment 的 remind_time...[/cyan]")
            updated_count = asyncio.run(_expedite_remind_times(confirmed_ids))
            console.print(f"  [green]OK[/green] 更新了 {updated_count} 行")
            md.append("## 5. Remind Time 调整（测试加速）")
            md.append("")
            md.append(f"通过直连 PostgreSQL 将 {len(confirmed_ids)} 个 scheduled moment 的 remind_time 设为过去，使 worker 立即领取。")
            md.append(f"实际更新 **{updated_count}** 行。")
            md.append("")

        # ============================================================
        #  6. 等待 worker 兑现
        # ============================================================
        console.print(f"[cyan]6. 等待 worker 兑现（超时 {worker_timeout}s）...[/cyan]")
        md.append("## 6. 兑现等待")
        md.append("")

        deadline = time.time() + worker_timeout
        delivered_count = 0
        poll_round = 0

        while time.time() < deadline and confirmed_ids:
            poll_round += 1
            time.sleep(3)
            # 重新拉取 moments 状态
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

        # ============================================================
        #  7. 最终状态汇总
        # ============================================================
        console.print("[cyan]7. 生成最终报告...[/cyan]")
        final_moments = client.list_moments(user_id, limit=500)
        final_conv_moments = [m for m in final_moments if m.get("conversation_id") == conv_id]
        final_conv_moments.sort(key=lambda x: x.get("created_at") or "")

        md.append("## 7. 最终关键时刻状态")
        md.append("")
        md.append("| # | moment_id | event_description | status | executed_at | first_message |")
        md.append("|---:|---|---|---|---|---|")
        for i, m in enumerate(final_conv_moments, start=1):
            md.append(
                f"| {i} | `{m['moment_id'][:12]}...` "
                f"| {_escape_md(_truncate(m.get('event_description',''), 35))} "
                f"| **{_status_label(m.get('status',0), m.get('confirmed',False))}** "
                f"| {_fmt_bj(m.get('executed_at'))} "
                f"| {_escape_md(_truncate(m.get('first_message','') or '', 30))} |"
            )
        md.append("")

        # 统计
        status_counts: Dict[str, int] = {}
        for m in final_conv_moments:
            label = _status_label(m.get("status", 0), m.get("confirmed", False))
            status_counts[label] = status_counts.get(label, 0) + 1

        md.append("### 统计")
        md.append("")
        for label, count in sorted(status_counts.items()):
            md.append(f"- {label}: **{count}**")
        md.append(f"- 总计: **{len(final_conv_moments)}**")
        md.append("")

        # ============================================================
        #  8. 对话完整记录
        # ============================================================
        md.append("## 8. 完整对话记录")
        md.append("")
        for i, t in enumerate(transcript, start=1):
            md.append(f"### 第 {i} 轮")
            md.append("")
            md.append(f"**用户**: {t['user']}")
            md.append("")
            md.append(f"**AI**: {t['ai']}")
            md.append("")

        # ============================================================
        #  9. 测试结论
        # ============================================================
        total = len(final_conv_moments)
        completed = status_counts.get("completed", 0)
        pass_moments = total >= 10
        # 兑现率以"全部 moment 都完成"为标准（worker 会自动领取已过期的 scheduled moment）
        pass_delivery = completed == total and total > 0

        md.append("## 9. 测试结论")
        md.append("")
        md.append(f"- 关键时刻识别: **{'PASS' if pass_moments else 'FAIL'}** ({total} 个，目标 >= 10)")
        md.append(f"- 兑现完成率: **{'PASS' if pass_delivery else 'FAIL'}** ({completed}/{total})")
        md.append(f"- 总结: **{'ALL PASS' if (pass_moments and pass_delivery) else 'PARTIAL FAIL'}**")
        md.append("")
        md.append(f"---")
        md.append(f"_报告生成时间: {_fmt_bj(_now_utc())}_")

        # 写入报告
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(md), encoding="utf-8")

        if pass_moments and pass_delivery:
            console.print(f"\n[bold green]ALL PASS[/bold green] 报告: {report_path.as_posix()}")
        else:
            console.print(f"\n[bold yellow]PARTIAL FAIL[/bold yellow] 报告: {report_path.as_posix()}")
            if not pass_moments:
                console.print(f"  [yellow]关键时刻数 {total} < 10[/yellow]")
            if not pass_delivery:
                console.print(f"  [yellow]兑现 {completed}/{len(confirmed_ids)}[/yellow]")

    except Exception as e:
        md.append(f"\n## ERROR\n\n`{type(e).__name__}: {e}`\n")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(md), encoding="utf-8")
        console.print(f"[red]ERR[/red] {e}")
        console.print(f"报告已保存: {report_path.as_posix()}")
        raise typer.Exit(1)
    finally:
        client.close()
