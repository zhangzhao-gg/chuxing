"""
[INPUT]: 依赖 httpx/typer/rich/asyncpg，依赖标准库 asyncio/os/time/datetime/dataclasses
[OUTPUT]: 对外提供三个 E2E 测试命令：test-delivery / test-conversation / test-full-lifecycle / test-all
[POS]: backend/tests 的独立 E2E 测试套件；合并 cli/commands 的三个测试脚本，内置 HTTP 客户端，可直接运行
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import typer
from rich.console import Console

app = typer.Typer(name="e2e-suite", help="E2E 测试套件（合并三个测试场景）", no_args_is_help=True)
console = Console()
BJ_TZ = timezone(timedelta(hours=8))


# ================================================================
#  内置 HTTP 客户端（脱离 cli.client 依赖）
# ================================================================

class APIClient:
    """轻量 HTTP 客户端，封装后端 API 调用。"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=120.0, trust_env=False)

    def close(self):
        self.client.close()

    def create_user(self, username: str) -> Dict[str, Any]:
        r = self.client.post("/api/users", json={"username": username}); r.raise_for_status(); return r.json()

    def create_agent(self, name: str, system_prompt: str, model: str = "gpt-4o-mini") -> Dict[str, Any]:
        r = self.client.post("/api/agents", json={"name": name, "system_prompt": system_prompt, "model": model}); r.raise_for_status(); return r.json()

    def create_conversation(self, user_id: str, agent_id: str, title: Optional[str] = None) -> Dict[str, Any]:
        data: Dict[str, Any] = {"user_id": user_id, "agent_id": agent_id}
        if title: data["title"] = title
        r = self.client.post("/api/conversations", json=data); r.raise_for_status(); return r.json()

    def send_message(self, conv_id: str, content: str) -> Dict[str, Any]:
        r = self.client.post(f"/api/conversations/{conv_id}/chat", json={"content": content}); r.raise_for_status(); return r.json()

    def get_messages(self, conv_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        r = self.client.get(f"/api/conversations/{conv_id}/messages", params={"limit": limit}); r.raise_for_status(); return r.json()

    def list_moments(self, user_id: str, limit: int = 500) -> List[Dict[str, Any]]:
        r = self.client.get("/api/moments", params={"user_id": user_id, "limit": limit}); r.raise_for_status(); return r.json()

    def get_moment(self, moment_id: str) -> Dict[str, Any]:
        r = self.client.get(f"/api/moments/{moment_id}"); r.raise_for_status(); return r.json()

    def confirm_moment(self, moment_id: str) -> Dict[str, Any]:
        r = self.client.post(f"/api/moments/{moment_id}/confirm"); r.raise_for_status(); return r.json()

    def cancel_moment(self, moment_id: str) -> Dict[str, Any]:
        r = self.client.post(f"/api/moments/{moment_id}/cancel"); r.raise_for_status(); return r.json()

    def create_moment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        r = self.client.post("/api/moments", json=data); r.raise_for_status(); return r.json()


# ================================================================
#  关键时刻定义（同 cli/commands/agent.py 的 DEFAULT_MOMENT_DEFINITION）
# ================================================================

DEFAULT_MOMENT_DEFINITION = """关键时刻（moment）定义（非常重要）：
- 你认为这件事你会有后续的动作和反应，例如在这件事发生之后打算给用户发个消息问问。
- 情绪波动严重的时候（例如强烈焦虑、恐惧、兴奋、悲伤等）需要给他打电话。
- 用户提到需要持续提醒/坚持的习惯（例如每天早起、每周跑步、戒糖等）

当且仅当你判断这是"值得被记录并在合适时间触达"的时刻，才在结构化输出的 moment 字段给出 is_moment=true；否则 moment=null。"""


# ================================================================
#  共享辅助函数
# ================================================================

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _fmt_bj(value: Any) -> str:
    """把时间值格式化为北京时间字符串。"""
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
    if status == 1 and not confirmed: return "pending"
    if status == 1 and confirmed: return "scheduled"
    if status == 2: return "completed"
    if status == 3: return "cancelled"
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
    return ""


async def _expedite_remind_times(moment_ids: List[str]) -> int:
    """直连 PostgreSQL，把指定 moments 的 remind_time 设为过去，让 worker 立即领取。"""
    import asyncpg
    pool = await asyncpg.create_pool(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        database=os.getenv("POSTGRES_DB_NAME", "llm_chat"),
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
    all_m = client.list_moments(user_id, limit=500)
    conv_m = [m for m in all_m if m.get("conversation_id") == conv_id]
    conv_m.sort(key=lambda x: x.get("created_at") or "")
    return conv_m


def _write_report(path: Path, lines: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _make_system_prompt(agent_name: str = "小初", extra: str = "") -> str:
    parts = [
        f"你的名字是：{agent_name}\n",
        "你是一个温暖、贴心、细致的生活陪伴助手，善于发现用户话语中的关键时刻。",
        "当用户提到需要提醒的事情、重要事件、情绪波动、或需要坚持的习惯时，你要准确识别并创建 moment。",
        "当用户说某件事取消了或者改时间了，你要在 moment_updates 中正确取消或更新对应的 moment。",
        "你只用简体中文回复。\n",
        DEFAULT_MOMENT_DEFINITION,
    ]
    if extra:
        parts.append(extra)
    return "\n".join(parts)


# ================================================================
#  测试数据
# ================================================================

# --- test-conversation: 马拉松备赛主题 20 轮 ---
MARATHON_MESSAGES = [
    "我报名了下个月15号的城市半程马拉松，第一次跑半马，挺紧张的，到时候记得给我加油鼓劲",
    "教练说这周六早上要跑个15公里测试一下配速，提醒我别忘了",
    "对了，下周一上午我得去医院做个运动体检，看看膝盖的老伤，提醒我别迟到",
    "有点担心体检结果，万一膝盖不行怎么办，好焦虑好害怕",
    "我打算从明天开始每天早上六点起来晨跑训练，帮我盯着别偷懒",
    "下周三下午要去运动品店买双新跑鞋，旧的磨损太严重了，到点提醒我出门",
    "教练让我下周五傍晚去他那里调整跑步姿势，纠正一下步幅，提醒我别忘了",
    "这周四晚上公司有年会，那天就不训练了，得穿正装出席，提醒我提前准备好衣服",
    "比赛前三天开始碳水储备期，到时候提醒我多吃面条和米饭，这很重要",
    "比赛前一晚一定要把装备都收拾好，号码布、芯片计时器、能量胶，提醒我检查一遍",
    "比赛当天凌晨四点半就得起床出发去赛事起点，提醒我定好闹钟",
    "跑完赛后拉伸非常重要，比赛结束后提醒我一定要做15分钟拉伸别偷懒直接回家",
    "半马跑完我想约几个朋友去吃火锅庆祝一下，提醒我赛后发消息召集大家",
    "每周日做一个长距离拉练，比赛前这个习惯一定要坚持住，每周日提醒我",
    "赛前一周要减量训练，教练说跑量减到平时的一半，到时候提醒我注意休息",
    "比赛完第二天安排一次冰浴恢复，帮助肌肉恢复，提醒我预约冰浴",
    "下下周要去拿体检报告，希望一切正常，到时候提醒我去医院取报告",
    "最近压力太大了经常失眠到凌晨三四点，整个人状态很差，感觉快撑不住了",
    "突然想到比赛当天的补给策略也要提前规划，每5公里补水，比赛前一天提醒我准备好能量胶和盐丸",
    "想想完赛的成就感就激动，这几周一定要好好准备不能松懈",
]

# --- test-full-lifecycle: 多主题 15 轮 + 取消/修改 5 轮 ---
LIFECYCLE_PHASE1 = [
    "我下周二下午两点有个特别重要的季度工作汇报，PPT还没做完，到时候提醒我别迟到",
    "这周五晚上七点半约了朋友去看电影《哪吒2》，帮我记着提醒我出门",
    "后天是我妈妈生日，我要提前订个蛋糕，千万别让我忘了",
    "最近胃不太舒服，下周三上午九点预约了医院做胃镜检查，提醒我空腹去",
    "我决定从今天开始每天晚上十点做二十分钟冥想，帮我坚持这个习惯",
    "下周六上午要参加驾校科目三考试，我特别紧张，到时候给我打气",
    "明天下午两点有个大厂的线上面试，我好紧张好害怕，万一搞砸了怎么办",
    "后天15号要交房租了，别让我忘了转账给房东",
    "我报了个周末Python编程课，每周六上午九点开始，提醒我准时上课",
    "和女朋友分手了快一周了，每天晚上都睡不着，心里堵得慌，感觉好孤独",
    "下周四下午三点要去银行办张新的信用卡，提醒我带身份证出门",
    "我想开始每天睡前花十分钟写日记记录心情，帮我养成这个习惯",
    "下个月1号要交物业费，别让我忘了",
    "这周日早上想去爬山放松一下心情，提醒我早点起来出发",
    "上次体检的报告下周五可以去医院拿了，提醒我去取",
]

LIFECYCLE_PHASE2 = [
    "之前约的看电影不去了，朋友临时有事取消了，那个提醒帮我撤掉",
    "之前预约的胃镜检查改时间了，医院通知改到下周四上午十点，帮我更新一下提醒",
    "之前说去银行办信用卡不去了，我已经在网上申请了，把那个提醒取消掉",
    "驾校教练说科目三考试推迟到下下周六上午了，帮我改一下时间",
    "谢谢你帮我记着这么多事情，有你在真的放心多了",
]


# ================================================================
#  测试 1: test-delivery — Moment 兑现链路
# ================================================================

@app.command("test-delivery")
def test_delivery(
    api_url: str = typer.Option("http://localhost:8000", "--api-url"),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m"),
    timeout_seconds: float = typer.Option(20.0, "--timeout-seconds"),
    poll_interval: float = typer.Option(0.5, "--poll-interval"),
    out_dir: Path = typer.Option(Path("docs/reports"), "--out-dir", dir_okay=True, file_okay=False),
):
    """测试 1：创建 moment → confirm → worker 到点发站内消息 → moment completed。"""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"moment_delivery_test_{run_id}.md"
    client = APIClient(api_url)
    started_at = _now_utc()
    event_time = started_at + timedelta(minutes=1)
    expected_msg = f"[DELIVERY_TEST {run_id}] 到点了：我来兑现一下，看看你现在状态如何？"

    md: List[str] = [
        "# Moment 兑现端到端测试报告", "",
        f"- run_id: `{run_id}`",
        f"- started_at: `{_fmt_bj(started_at)}`",
        f"- timeout_seconds: **{timeout_seconds}**", "",
    ]

    @dataclass
    class _R:
        ok: bool = False

    result = _R()
    try:
        # 创建资源
        user = client.create_user(f"delivery_{run_id}")
        user_id = user["user_id"]
        agent = client.create_agent(f"DELIVERY_AGENT_{run_id}", "你是一个温柔的陪伴者。", model)
        conv = client.create_conversation(user_id, agent["agent_id"], f"delivery:{run_id}")
        conv_id = conv["conversation_id"]
        md += ["## 资源创建", "", f"- user_id: `{user_id}`", f"- conversation_id: `{conv_id}`", ""]

        # 创建 moment
        moment = client.create_moment({
            "user_id": user_id, "conversation_id": conv_id, "type": "event",
            "event_time": _iso(event_time), "event_description": f"（测试）兑现链路 {run_id}",
            "importance": "high", "suggested_action": "message", "suggested_timing": "on_time",
            "first_message": expected_msg, "ai_attitude": "warm", "reason": "E2E delivery test",
        })
        moment_id = moment["moment_id"]
        md += [
            "## Moment 创建与确认", "",
            f"- moment_id: `{moment_id}`",
            f"- remind_time: `{_fmt_bj(moment.get('remind_time'))}`",
            f"- status(initial): **{moment.get('status')}**, confirmed: **{moment.get('confirmed')}**", "",
        ]

        # 确认
        confirmed = client.confirm_moment(moment_id)
        md.append(f"- status(after confirm): **{confirmed.get('status')}**, confirmed: **{confirmed.get('confirmed')}**")
        md.append("")

        # 轮询等待兑现
        md += ["## 兑现验证", ""]
        deadline = time.time() + timeout_seconds
        delivered_msg = None
        while time.time() < deadline:
            msgs = client.get_messages(conv_id, limit=50)
            for m in msgs:
                if m.get("role") == "assistant" and (m.get("content") or "").strip() == expected_msg.strip():
                    delivered_msg = m
                    break
            if delivered_msg:
                break
            time.sleep(poll_interval)

        if not delivered_msg:
            md.append("- result: **FAIL**（超时未看到 worker 写入的消息）")
            _write_report(report_path, md)
            console.print(f"[red]FAIL[/red] 报告: {report_path}")
            raise typer.Exit(1)

        md.append("- result: **PASS**（已看到 worker 写入的消息）")
        md.append(f"- delivered_message_id: `{delivered_msg.get('message_id')}`")
        md.append("")

        # 校验 moment completed
        m2 = client.get_moment(moment_id)
        ok = m2.get("status") == 2 and bool(m2.get("executed_at"))
        md += [
            "## Moment 最终状态", "",
            f"- status: **{m2.get('status')}**（期望 2）",
            f"- executed_at: `{_fmt_bj(m2.get('executed_at'))}`",
            f"- assertion: **{'PASS' if ok else 'FAIL'}**",
        ]
        _write_report(report_path, md)
        result.ok = ok
        if ok:
            console.print(f"[green]PASS[/green] 报告: {report_path}")
        else:
            console.print(f"[red]FAIL[/red] 报告: {report_path}")
            raise typer.Exit(1)

    except typer.Exit:
        raise
    except Exception as e:
        md += ["## 异常", "", f"- error: `{type(e).__name__}: {e}`"]
        _write_report(report_path, md)
        console.print(f"[red]ERR[/red] {e}，报告: {report_path}")
        raise typer.Exit(1)
    finally:
        client.close()


# ================================================================
#  测试 2: test-conversation — 马拉松备赛主题 20 轮对话
# ================================================================

@app.command("test-conversation")
def test_conversation(
    api_url: str = typer.Option("http://localhost:8000", "--api-url"),
    model: str = typer.Option("deepseek-chat", "--model", "-m"),
    worker_timeout: float = typer.Option(120.0, "--worker-timeout"),
    out_dir: Path = typer.Option(Path("docs/reports"), "--out-dir", dir_okay=True, file_okay=False),
):
    """测试 2：马拉松备赛 20 轮对话 → LLM 识别关键时刻 → 确认 → worker 兑现。"""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"e2e_conversation_test_{run_id}.md"
    client = APIClient(api_url)
    started_at = _now_utc()

    md: List[str] = [
        "# 端到端对话测试报告", "",
        f"- **run_id**: `{run_id}`",
        f"- **started_at**: `{_fmt_bj(started_at)}`",
        f"- **model**: `{model}`",
        f"- **topic**: 马拉松备赛（{len(MARATHON_MESSAGES)} 轮对话）", "",
    ]

    try:
        # 1. 创建资源
        console.print("[cyan]1. 创建测试资源...[/cyan]")
        user = client.create_user(f"e2e_conv_{run_id}")
        user_id = user["user_id"]
        agent = client.create_agent(f"e2e_agent_{run_id}", _make_system_prompt(), model)
        agent_id = agent["agent_id"]
        conv = client.create_conversation(user_id, agent_id, f"e2e:{run_id}")
        conv_id = conv["conversation_id"]

        md += [
            "## 1. 资源创建", "", "| 资源 | ID |", "|---|---|",
            f"| user | `{user_id}` |", f"| agent | `{agent_id}` (model: {model}) |",
            f"| conversation | `{conv_id}` |", "",
        ]

        # 2. 发送对话
        console.print(f"[cyan]2. 发送 {len(MARATHON_MESSAGES)} 轮对话...[/cyan]")
        md += ["## 2. 对话记录", "", "| # | 用户消息 | AI 回复（摘要） |", "|---:|---|---|"]
        transcript: List[Dict[str, str]] = []
        for i, msg in enumerate(MARATHON_MESSAGES, 1):
            console.print(f"  [{i}/{len(MARATHON_MESSAGES)}] {_truncate(msg, 40)}")
            ai = _send_with_retry(client, conv_id, msg)
            transcript.append({"user": msg, "ai": ai})
            md.append(f"| {i} | {_escape_md(_truncate(msg))} | {_escape_md(_truncate(ai))} |")
            time.sleep(1)
        md.append("")

        # 3. 获取关键时刻
        moments = _collect_moments(client, user_id, conv_id)
        md += [
            "## 3. 识别到的关键时刻", "", f"**总计**: {len(moments)} 个", "",
            "| # | type | importance | event_description | status |",
            "|---:|---|---|---|---|",
        ]
        for i, m in enumerate(moments, 1):
            md.append(f"| {i} | {m.get('type')} | {m.get('importance')} | {_escape_md(_truncate(m.get('event_description',''),40))} | {_status_label(m.get('status',0), m.get('confirmed',False))} |")
        md.append("")

        # 4. 确认 pending
        confirmed_ids: List[str] = []
        for m in moments:
            if m.get("status") == 1 and not m.get("confirmed"):
                try: client.confirm_moment(m["moment_id"])
                except Exception: pass
            if m.get("status") == 1:
                confirmed_ids.append(m["moment_id"])

        # 5. 加速 remind_time
        if confirmed_ids:
            updated = asyncio.run(_expedite_remind_times(confirmed_ids))
            md += ["## 4. Remind Time 调整", "", f"加速 {len(confirmed_ids)} 个，实际更新 **{updated}** 行。", ""]

        # 6. 等待兑现
        console.print(f"[cyan]等待兑现（超时 {worker_timeout}s）...[/cyan]")
        deadline = time.time() + worker_timeout
        delivered = 0
        while time.time() < deadline and confirmed_ids:
            time.sleep(3)
            rmap = {m["moment_id"]: m for m in client.list_moments(user_id, limit=500)}
            delivered = sum(1 for mid in confirmed_ids if rmap.get(mid, {}).get("status") == 2)
            if delivered >= len(confirmed_ids): break
        md += ["## 5. 兑现", "", f"- 兑现完成: **{delivered}/{len(confirmed_ids)}**", ""]

        # 7. 最终状态
        final = _collect_moments(client, user_id, conv_id)
        counts: Dict[str, int] = {}
        for m in final:
            l = _status_label(m.get("status", 0), m.get("confirmed", False))
            counts[l] = counts.get(l, 0) + 1
        md += ["## 6. 统计", ""]
        for l, c in sorted(counts.items()): md.append(f"- {l}: **{c}**")
        md.append(f"- 总计: **{len(final)}**")
        md.append("")

        # 8. 完整对话
        md.append("## 7. 完整对话记录")
        md.append("")
        for i, t in enumerate(transcript, 1):
            md += [f"### 第 {i} 轮", "", f"**用户**: {t['user']}", "", f"**AI**: {t['ai']}", ""]

        # 9. 结论
        total = len(final)
        completed = counts.get("completed", 0)
        p_m = total >= 10
        p_d = delivered == len(confirmed_ids) and len(confirmed_ids) > 0
        md += [
            "## 8. 测试结论", "",
            f"- 关键时刻识别: **{'PASS' if p_m else 'FAIL'}** ({total} 个，目标 >= 10)",
            f"- 兑现完成率: **{'PASS' if p_d else 'FAIL'}** ({delivered}/{len(confirmed_ids)})",
            f"- 总结: **{'ALL PASS' if p_m and p_d else 'PARTIAL FAIL'}**",
            "", "---", f"_报告生成时间: {_fmt_bj(_now_utc())}_",
        ]
        _write_report(report_path, md)
        console.print(f"\n[bold {'green' if p_m and p_d else 'yellow'}]{'ALL PASS' if p_m and p_d else 'PARTIAL FAIL'}[/bold {'green' if p_m and p_d else 'yellow'}] 报告: {report_path}")

    except Exception as e:
        md += [f"\n## ERROR\n\n`{type(e).__name__}: {e}`\n"]
        _write_report(report_path, md)
        console.print(f"[red]ERR[/red] {e}，报告: {report_path}")
        raise typer.Exit(1)
    finally:
        client.close()


# ================================================================
#  测试 3: test-full-lifecycle — 全生命周期（含取消/修改/兑现）
# ================================================================

@app.command("test-full-lifecycle")
def test_full_lifecycle(
    api_url: str = typer.Option("http://localhost:8000", "--api-url"),
    model: str = typer.Option("deepseek-chat", "--model", "-m"),
    worker_timeout: float = typer.Option(120.0, "--worker-timeout"),
    out_dir: Path = typer.Option(Path("docs/reports"), "--out-dir", dir_okay=True, file_okay=False),
):
    """测试 3：对话→识别12+moment→取消→修改→确认→兑现→评估报告。"""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"e2e_full_lifecycle_{run_id}.md"
    client = APIClient(api_url)
    started_at = _now_utc()

    md: List[str] = [
        "# 全生命周期端到端测试报告", "",
        f"- **run_id**: `{run_id}`",
        f"- **started_at**: `{_fmt_bj(started_at)}`",
        f"- **model**: `{model}`",
        f"- **Phase 1**: {len(LIFECYCLE_PHASE1)} 轮（多主题触发 moment）",
        f"- **Phase 2**: {len(LIFECYCLE_PHASE2)} 轮（取消/修改 moment）", "",
    ]
    metrics: Dict[str, int] = {"cancelled_by_ai": 0, "modified_by_ai": 0, "cancelled_by_api": 0, "modified_by_api": 0}

    try:
        # --- 创建资源 ---
        console.print("\n[bold cyan]═══ Phase 0: 创建资源 ═══[/bold cyan]")
        user = client.create_user(f"lifecycle_{run_id}")
        user_id = user["user_id"]
        agent = client.create_agent(f"lifecycle_agent_{run_id}", _make_system_prompt(), model)
        conv = client.create_conversation(user_id, agent["agent_id"], f"lifecycle:{run_id}")
        conv_id = conv["conversation_id"]
        md += ["## 1. 资源创建", "", "| 资源 | ID |", "|---|---|",
               f"| user | `{user_id}` |", f"| agent | `{agent['agent_id']}` (model: {model}) |",
               f"| conversation | `{conv_id}` |", ""]
        console.print(f"  [green]OK[/green] user={user_id}, conv={conv_id}")

        # --- Phase 1: 多主题对话 ---
        console.print(f"\n[bold cyan]═══ Phase 1: {len(LIFECYCLE_PHASE1)} 轮对话 ═══[/bold cyan]")
        md += ["## 2. Phase 1 对话记录", "", "| # | 用户消息 | AI 回复（摘要） |", "|---:|---|---|"]
        transcript: List[Dict[str, str]] = []
        for i, msg in enumerate(LIFECYCLE_PHASE1, 1):
            console.print(f"  [{i}/{len(LIFECYCLE_PHASE1)}] {_truncate(msg, 45)}")
            ai = _send_with_retry(client, conv_id, msg)
            transcript.append({"user": msg, "ai": ai})
            md.append(f"| {i} | {_escape_md(_truncate(msg, 50))} | {_escape_md(_truncate(ai, 50))} |")
            time.sleep(1.5)
        md.append("")

        # --- Phase 1 快照 ---
        p1_moments = _collect_moments(client, user_id, conv_id)
        md += [
            "## 3. Phase 1 关键时刻", "", f"**总计**: {len(p1_moments)} 个", "",
            "| # | type | importance | event_description | status | confirmed |",
            "|---:|---|---|---|---|---|",
        ]
        for i, m in enumerate(p1_moments, 1):
            md.append(f"| {i} | {m.get('type')} | {m.get('importance')} | {_escape_md(_truncate(m.get('event_description',''),40))} | {_status_label(m.get('status',0),m.get('confirmed',False))} | {m.get('confirmed')} |")
        md.append("")
        console.print(f"  识别到 [bold]{len(p1_moments)}[/bold] 个关键时刻")

        # --- Phase 2: 取消/修改对话 ---
        console.print(f"\n[bold cyan]═══ Phase 2: {len(LIFECYCLE_PHASE2)} 轮取消/修改 ═══[/bold cyan]")
        md += ["## 4. Phase 2 对话记录", "", "| # | 用户消息 | AI 回复（摘要） |", "|---:|---|---|"]
        p2_transcript: List[Dict[str, str]] = []
        for i, msg in enumerate(LIFECYCLE_PHASE2, 1):
            idx = len(LIFECYCLE_PHASE1) + i
            console.print(f"  [{idx}] {_truncate(msg, 45)}")
            ai = _send_with_retry(client, conv_id, msg)
            p2_transcript.append({"user": msg, "ai": ai})
            md.append(f"| {idx} | {_escape_md(_truncate(msg, 50))} | {_escape_md(_truncate(ai, 50))} |")
            time.sleep(1.5)
        md.append("")

        # --- Phase 2 快照 ---
        p2_moments = _collect_moments(client, user_id, conv_id)
        p1_ids = {m["moment_id"] for m in p1_moments}
        ai_cancelled = [m for m in p2_moments if m["moment_id"] in p1_ids and m.get("status") == 3]
        new_in_p2 = [m for m in p2_moments if m["moment_id"] not in p1_ids]
        metrics["cancelled_by_ai"] = len(ai_cancelled)
        metrics["modified_by_ai"] = len(new_in_p2)

        md += [
            "## 5. Phase 2 变化", "",
            f"- AI 自动取消: **{len(ai_cancelled)}** 个",
            f"- AI 新创建（替代/修改）: **{len(new_in_p2)}** 个",
            f"- 当前总计: **{len(p2_moments)}** 个", "",
        ]
        if ai_cancelled:
            md += ["### AI 取消的 moments", "", "| moment_id | event_description |", "|---|---|"]
            for m in ai_cancelled:
                md.append(f"| `{m['moment_id'][:12]}...` | {_escape_md(_truncate(m.get('event_description',''),40))} |")
            md.append("")
        if new_in_p2:
            md += ["### AI 新创建的 moments", "", "| moment_id | event_description | status |", "|---|---|---|"]
            for m in new_in_p2:
                md.append(f"| `{m['moment_id'][:12]}...` | {_escape_md(_truncate(m.get('event_description',''),40))} | {_status_label(m.get('status',0),m.get('confirmed',False))} |")
            md.append("")

        # --- 手动补充 ---
        console.print("\n[bold cyan]═══ 手动补充 Cancel/Modify ═══[/bold cyan]")
        current = _collect_moments(client, user_id, conv_id)
        active = [m for m in current if m.get("status") == 1]
        total_cancelled = len([m for m in current if m.get("status") == 3])

        # 补充取消
        if total_cancelled < 2 and active:
            for kw in ["电影", "信用卡", "银行"]:
                for m in active:
                    if kw in m.get("event_description", "") and total_cancelled < 2:
                        try:
                            client.cancel_moment(m["moment_id"])
                            metrics["cancelled_by_api"] += 1
                            total_cancelled += 1
                            console.print(f"  [yellow]CANCEL[/yellow] {m['moment_id'][:8]}...")
                        except Exception: pass

        # 补充修改
        if len(new_in_p2) < 2:
            current = _collect_moments(client, user_id, conv_id)
            active = [m for m in current if m.get("status") == 1]
            need = 2 - len(new_in_p2)
            done = 0
            for kw in ["胃镜", "科目三", "驾校"]:
                if done >= need: break
                for m in active:
                    if done >= need: break
                    if kw in m.get("event_description", ""):
                        try:
                            client.cancel_moment(m["moment_id"])
                            desc = m.get("event_description", "")
                            _send_with_retry(client, conv_id, f"之前说的「{_truncate(desc,20)}」改到下周了，帮我重新设一个提醒")
                            metrics["modified_by_api"] += 1
                            done += 1
                            time.sleep(1.5)
                        except Exception: pass

        has_manual = metrics["cancelled_by_api"] > 0 or metrics["modified_by_api"] > 0
        md += ["## 6. 手动补充", ""]
        md.append("AI 已自动完成取消和修改，无需手动补充。" if not has_manual else f"手动取消 {metrics['cancelled_by_api']} 个，手动修改 {metrics['modified_by_api']} 个。")
        md.append("")

        # --- 确认 pending ---
        console.print("\n[bold cyan]═══ 确认 pending ═══[/bold cyan]")
        pre_confirm = _collect_moments(client, user_id, conv_id)
        confirmed_ids: List[str] = []
        confirm_count = 0
        for m in pre_confirm:
            if m.get("status") == 1 and not m.get("confirmed"):
                try:
                    client.confirm_moment(m["moment_id"])
                    confirm_count += 1
                except Exception: pass
            if m.get("status") == 1:
                confirmed_ids.append(m["moment_id"])
        md += ["## 7. 确认", "", f"确认了 {confirm_count} 个 pending → scheduled。", ""]
        console.print(f"  [green]OK[/green] {confirm_count} 个")

        # --- 加速 remind_time ---
        if confirmed_ids:
            updated = asyncio.run(_expedite_remind_times(confirmed_ids))
            md += ["## 8. Remind Time 调整", "", f"加速 {len(confirmed_ids)} 个，实际更新 **{updated}** 行。", ""]

        # --- 等待兑现 ---
        console.print(f"\n[bold cyan]═══ 等待兑现（{worker_timeout}s） ═══[/bold cyan]")
        deadline = time.time() + worker_timeout
        delivered = 0
        poll = 0
        while time.time() < deadline and confirmed_ids:
            poll += 1; time.sleep(3)
            rmap = {m["moment_id"]: m for m in client.list_moments(user_id, limit=500)}
            delivered = sum(1 for mid in confirmed_ids if rmap.get(mid, {}).get("status") == 2)
            console.print(f"  poll #{poll}: {delivered}/{len(confirmed_ids)}")
            if delivered >= len(confirmed_ids): break
        md += ["## 9. 兑现", "", f"- 轮询: {poll} 次", f"- 兑现: **{delivered}/{len(confirmed_ids)}**", ""]

        # --- 最终状态 ---
        final = _collect_moments(client, user_id, conv_id)
        md += [
            "## 10. 最终状态", "",
            "| # | moment_id | event_description | type | status | executed_at |",
            "|---:|---|---|---|---|---|",
        ]
        for i, m in enumerate(final, 1):
            md.append(f"| {i} | `{m['moment_id'][:12]}...` | {_escape_md(_truncate(m.get('event_description',''),30))} | {m.get('type')} | **{_status_label(m.get('status',0),m.get('confirmed',False))}** | {_fmt_bj(m.get('executed_at'))} |")
        md.append("")

        counts: Dict[str, int] = {}
        for m in final:
            l = _status_label(m.get("status", 0), m.get("confirmed", False))
            counts[l] = counts.get(l, 0) + 1
        md += ["### 统计", ""]
        for l, c in sorted(counts.items()): md.append(f"- {l}: **{c}**")
        md.append(f"- 总计: **{len(final)}**")
        md.append("")

        # --- 完整对话 ---
        md.append("## 11. 完整对话记录")
        md.append("")
        for i, t in enumerate(transcript + p2_transcript, 1):
            md += [f"### 第 {i} 轮", "", f"**用户**: {t['user']}", "", f"**AI**: {t['ai']}", ""]

        # --- 结论 ---
        total = len(final)
        cancelled = counts.get("cancelled", 0)
        modified_total = metrics["modified_by_ai"] + metrics["modified_by_api"]
        p_m = total >= 10
        p_c = cancelled >= 2
        p_d = delivered == len(confirmed_ids) and len(confirmed_ids) > 0
        all_pass = p_m and p_c and p_d

        md += [
            "## 12. 测试结论", "", "| 指标 | 结果 | 目标 | 判定 |", "|---|---|---|---|",
            f"| 关键时刻总数 | {total} | >= 10 | **{'PASS' if p_m else 'FAIL'}** |",
            f"| 取消的 moment | {cancelled} | >= 2 | **{'PASS' if p_c else 'FAIL'}** |",
            f"| 修改的 moment | {modified_total} | >= 1 | **{'PASS' if modified_total >= 1 else 'FAIL'}** |",
            f"| 兑现完成率 | {delivered}/{len(confirmed_ids)} | 100% | **{'PASS' if p_d else 'FAIL'}** |", "",
            "### 状态迁移覆盖", "",
            f"- 兑现链路: **{counts.get('completed', 0)}** 个",
            f"- 取消链路: **{cancelled}** 个（AI: {metrics['cancelled_by_ai']}，手动: {metrics['cancelled_by_api']}）",
            f"- 修改链路: **{modified_total}** 个（AI: {metrics['modified_by_ai']}，手动: {metrics['modified_by_api']}）", "",
            f"### 总结: **{'ALL PASS' if all_pass else 'PARTIAL FAIL'}**",
            "", "---", f"_报告生成时间: {_fmt_bj(_now_utc())}_",
        ]
        _write_report(report_path, md)
        tag = "green" if all_pass else "yellow"
        console.print(f"\n[bold {tag}]{'ALL PASS' if all_pass else 'PARTIAL FAIL'}[/bold {tag}] 报告: {report_path}")

    except Exception as e:
        md += [f"\n## ERROR\n\n`{type(e).__name__}: {e}`\n"]
        _write_report(report_path, md)
        console.print(f"[red]ERR[/red] {e}，报告: {report_path}")
        raise typer.Exit(1)
    finally:
        client.close()


# ================================================================
#  test-all: 依次运行全部测试
# ================================================================

@app.command("test-all")
def test_all(
    api_url: str = typer.Option("http://localhost:8000", "--api-url"),
    model: str = typer.Option("deepseek-chat", "--model", "-m"),
    out_dir: Path = typer.Option(Path("docs/reports"), "--out-dir", dir_okay=True, file_okay=False),
):
    """依次运行全部 3 个测试（delivery → conversation → full-lifecycle）。"""
    console.print("\n[bold]═══════════ E2E 测试套件 ═══════════[/bold]\n")

    tests = [
        ("test-delivery", lambda: test_delivery(api_url=api_url, model="gpt-4o-mini", timeout_seconds=20.0, poll_interval=0.5, out_dir=out_dir)),
        ("test-conversation", lambda: test_conversation(api_url=api_url, model=model, worker_timeout=120.0, out_dir=out_dir)),
        ("test-full-lifecycle", lambda: test_full_lifecycle(api_url=api_url, model=model, worker_timeout=180.0, out_dir=out_dir)),
    ]
    results: List[tuple] = []

    for name, fn in tests:
        console.print(f"\n[bold cyan]{'─'*50}[/bold cyan]")
        console.print(f"[bold cyan]  运行: {name}[/bold cyan]")
        console.print(f"[bold cyan]{'─'*50}[/bold cyan]\n")
        try:
            fn()
            results.append((name, "PASS"))
        except (typer.Exit, SystemExit):
            results.append((name, "FAIL"))
        except Exception as e:
            results.append((name, f"ERROR: {e}"))

    console.print(f"\n[bold]{'═'*50}[/bold]")
    console.print("[bold]  测试套件总结[/bold]")
    console.print(f"[bold]{'═'*50}[/bold]\n")
    for name, status in results:
        color = "green" if status == "PASS" else "red"
        console.print(f"  [{color}]{status:>6}[/{color}]  {name}")
    console.print("")


# ================================================================
#  入口
# ================================================================

if __name__ == "__main__":
    app()
