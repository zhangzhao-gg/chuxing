"""
[INPUT]: 依赖 typer/rich 做 CLI 输出，依赖 cli.client 的 APIClient 调用后端 moments/messages 接口
[OUTPUT]: 对外提供 moment 子命令：test-delivery（端到端验证“到点兑现→发站内消息→moment completed”）
[POS]: cli/commands 的兑现测试入口；保持“薄客户端”，不内置业务，仅编排 API 调用与报告落盘
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from rich.console import Console

from ..client import APIClient


app = typer.Typer()
console = Console()
BJ_TZ = timezone(timedelta(hours=8))


@dataclass
class _TestResult:
    ok: bool
    report_path: Path
    details: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()

def _parse_dt(value: Any) -> Optional[datetime]:
    """解析 API 返回的时间字段为 datetime（尽量容错）。

    - str: 支持 ISO8601（含 Z）
    - datetime: 原样返回
    - naive datetime: 按 UTC 解释（服务端历史数据兼容）
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        s = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _fmt_bj(value: Any) -> str:
    dt = _parse_dt(value)
    if not dt:
        return ""
    return dt.astimezone(BJ_TZ).isoformat()


def _write_report(path: Path, lines: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _find_first_assistant_message(messages: List[Dict[str, Any]], expected_content: str) -> Optional[Dict[str, Any]]:
    for m in messages:
        if m.get("role") == "assistant" and (m.get("content") or "").strip() == expected_content.strip():
            return m
    return None


@app.command("test-delivery")
def test_delivery(
    api_url: str = typer.Option("http://localhost:8000", "--api-url", help="API 地址"),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="Agent 模型名（本测试不调用 LLM）"),
    timeout_seconds: float = typer.Option(20.0, "--timeout-seconds", help="等待 worker 兑现的超时（秒）"),
    poll_interval_seconds: float = typer.Option(0.5, "--poll-interval-seconds", help="轮询 messages 的间隔（秒）"),
    out_dir: Path = typer.Option(
        Path("docs/reports"),
        "--out-dir",
        help="报告输出目录（默认 docs/reports）",
        dir_okay=True,
        file_okay=False,
        readable=False,
        writable=True,
    ),
):
    """端到端测试：创建 moment → confirm → 到点由 worker 发站内消息 → moment 标记 completed。

    前置条件：
    - 后端已启动（FastAPI）
    - moment_worker 已启动（独立进程）
    """
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"moment_delivery_test_{run_id}.md"

    client = APIClient(api_url)
    started_at = _utc_now()

    # 让提醒时间“立即到期”：用 event/high，使 remind_time = event_time - 30min
    event_time = started_at + timedelta(minutes=1)
    expected_first_message = f"[DELIVERY_TEST {run_id}] 到点了：我来兑现一下，看看你现在状态如何？"

    md: List[str] = []
    md.append("# Moment 兑现（到点发消息）端到端测试报告")
    md.append("")
    md.append(f"- run_id: `{run_id}`")
    md.append(f"- started_at_utc: `{_iso(started_at)}`")
    md.append(f"- started_at_bj: `{started_at.astimezone(BJ_TZ).isoformat()}`")
    md.append(f"- api_url: `{api_url}`")
    md.append(f"- timeout_seconds: **{timeout_seconds}**")
    md.append("")

    result: Optional[_TestResult] = None

    try:
        # 1) 创建 user / agent / conversation
        username = f"delivery_test_{run_id}"
        user = client.create_user(username)
        user_id = user["user_id"]

        system_prompt = "你是一个温柔但克制的陪伴者。你只用简体中文回复。"
        agent = client.create_agent(name=f"DELIVERY_TEST_AGENT_{run_id}", system_prompt=system_prompt, model=model)
        agent_id = agent["agent_id"]

        conv = client.create_conversation(user_id=user_id, agent_id=agent_id, title=f"delivery_test:{run_id}")
        conv_id = conv["conversation_id"]

        md.append("## 资源创建")
        md.append("")
        md.append(f"- user_id: `{user_id}` (username `{username}`)")
        md.append(f"- agent_id: `{agent_id}` (model `{model}`)")
        md.append(f"- conversation_id: `{conv_id}`")
        md.append("")

        # 2) 创建 moment（confirmed=false）
        moment_payload: Dict[str, Any] = {
            "user_id": user_id,
            "conversation_id": conv_id,
            "type": "event",
            "event_time": _iso(event_time),
            "event_description": f"（测试）兑现消息链路 run_id={run_id}",
            "emotion": None,
            "emotion_level": None,
            "importance": "high",
            "suggested_action": "message",
            "suggested_timing": "on_time",
            "first_message": expected_first_message,
            "ai_attitude": "warm",
            "reason": "E2E delivery test",
        }
        moment = client.create_moment(moment_payload)
        moment_id = moment["moment_id"]

        md.append("## Moment 创建与确认")
        md.append("")
        md.append(f"- moment_id: `{moment_id}`")
        md.append(f"- event_time: `{moment.get('event_time')}`")
        md.append(f"- event_time_bj: `{_fmt_bj(moment.get('event_time'))}`")
        md.append(f"- remind_time: `{moment.get('remind_time')}`")
        md.append(f"- remind_time_bj: `{_fmt_bj(moment.get('remind_time'))}`")
        md.append(f"- confirmed(initial): **{moment.get('confirmed')}**")
        md.append(f"- status(initial): **{moment.get('status')}**")
        md.append(f"- first_message: `{expected_first_message}`")
        md.append("")

        # 3) confirm，使其进入 scheduled 语义（status=1 + confirmed=true）
        confirmed = client.confirm_moment(moment_id)
        md.append(f"- confirmed(after confirm): **{confirmed.get('confirmed')}**")
        md.append(f"- status(after confirm): **{confirmed.get('status')}**")
        md.append("")

        # 4) 等待 worker 兑现：轮询 messages，直到出现 expected_first_message
        md.append("## 兑现验证（messages / moment 状态）")
        md.append("")
        deadline = time.time() + timeout_seconds
        delivered_msg: Optional[Dict[str, Any]] = None
        last_messages: List[Dict[str, Any]] = []

        while time.time() < deadline:
            last_messages = client.get_messages(conv_id, limit=50)
            delivered_msg = _find_first_assistant_message(last_messages, expected_first_message)
            if delivered_msg:
                break
            time.sleep(poll_interval_seconds)

        checked_at = _utc_now()
        md.append(f"- checked_at_utc: `{_iso(checked_at)}`")
        md.append(f"- checked_at_bj: `{checked_at.astimezone(BJ_TZ).isoformat()}`")

        if not delivered_msg:
            md.append("- result: **FAIL**（超时未看到 worker 写入的 assistant 消息）")
            md.append("")
            md.append("### 最近 messages（最多 10 条）")
            md.append("")
            md.append("| # | role | created_at | content |")
            md.append("|---:|---|---|---|")
            for i, m in enumerate(last_messages[-10:], start=1):
                content = (m.get("content") or "").replace("\n", " ").strip()
                if len(content) > 80:
                    content = content[:80] + "…"
                md.append(f"| {i} | {m.get('role')} | {str(m.get('created_at'))[:19]} | {content} |")
            _write_report(report_path, md)
            result = _TestResult(
                ok=False,
                report_path=report_path,
                details="Timeout waiting delivered message",
            )
            raise typer.Exit(1)

        md.append("- result: **PASS**（已看到 worker 写入的 assistant 消息）")
        md.append(f"- delivered_message_id: `{delivered_msg.get('message_id')}`")
        md.append(f"- delivered_message_created_at: `{delivered_msg.get('created_at')}`")
        md.append(f"- delivered_message_created_at_bj: `{_fmt_bj(delivered_msg.get('created_at'))}`")
        md.append("")

        # 5) 校验 moment 已 completed
        m2 = client.get_moment(moment_id)
        md.append("### Moment 最终状态")
        md.append("")
        md.append(f"- status(final): **{m2.get('status')}**（期望 2=completed）")
        md.append(f"- executed_at(final): `{m2.get('executed_at')}`（期望非空）")
        md.append(f"- executed_at(final)_bj: `{_fmt_bj(m2.get('executed_at'))}`")
        md.append("")

        ok = (m2.get("status") == 2) and bool(m2.get("executed_at"))
        md.append(f"- assertion: **{'PASS' if ok else 'FAIL'}**")

        _write_report(report_path, md)
        result = _TestResult(ok=ok, report_path=report_path, details="OK" if ok else "Moment status not completed")
        if not ok:
            raise typer.Exit(1)

        console.print(f"[green][OK][/green] PASS，报告已生成: {report_path.as_posix()}")

    except typer.Exit:
        if result and not result.ok:
            console.print(f"[red][ERR][/red] FAIL，报告已生成: {result.report_path.as_posix()}")
        raise
    except Exception as e:
        md.append("## 异常")
        md.append("")
        md.append(f"- error: `{type(e).__name__}: {e}`")
        _write_report(report_path, md)
        console.print(f"[red][ERR][/red] 异常中止，报告已生成: {report_path.as_posix()}")
        raise typer.Exit(1)
    finally:
        client.close()

