"""
[INPUT]: 依赖 typer.testing 的 CliRunner，依赖 unittest，依赖 backend 侧 routers 的依赖注入点，依赖 cli 的 chat start 命令入口
[OUTPUT]: 生成 tests/ 目录下的 Markdown 报告（模拟人类在 CLI 中逐条对话），并断言查重/状态更新符合预期
[POS]: backend/tests 的 CLI 端到端（内存态）回归：从 CLI → APIClient → FastAPI → Router → Service 的链路
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
import unittest
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from typer.testing import CliRunner

from backend.routers import conversations as conversations_router
from backend.routers import messages as messages_router
from cli.main import app as cli_app


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _Message:
    message_id: str
    conversation_id: str
    role: str
    content: str
    token_count: Optional[int]
    created_at: datetime


@dataclass
class _Conversation:
    conversation_id: str
    user_id: str
    agent_id: str
    title: Optional[str]
    created_at: datetime
    updated_at: datetime


@dataclass
class _Moment:
    moment_id: str
    user_id: str
    conversation_id: str
    type: str
    event_time: datetime
    remind_time: datetime
    event_description: str
    importance: str
    suggested_action: str
    status: int
    confirmed: bool
    executed_at: Optional[datetime] = None


class _FakeMessageService:
    def __init__(self) -> None:
        self._by_conv: Dict[str, List[_Message]] = {}

    async def create_message(self, conv_id: str, role: str, content: str) -> _Message:
        msg = _Message(
            message_id=str(uuid.uuid4()),
            conversation_id=conv_id,
            role=role,
            content=content,
            token_count=len(content),
            created_at=_utcnow(),
        )
        self._by_conv.setdefault(conv_id, []).append(msg)
        return msg

    async def get_conversation_messages(
        self, conv_id: str, limit: int = 50, skip: int = 0
    ) -> List[_Message]:
        messages = self._by_conv.get(conv_id, [])
        if skip:
            messages = messages[skip:]
        if limit is not None:
            messages = messages[-limit:]
        return list(messages)


class _FakeConversationService:
    def __init__(self) -> None:
        self._by_id: Dict[str, _Conversation] = {}

    async def create_conversation(self, data: Any) -> Dict[str, Any]:
        conv_id = str(uuid.uuid4())
        now = _utcnow()
        conv = _Conversation(
            conversation_id=conv_id,
            user_id=data.user_id,
            agent_id=data.agent_id,
            title=getattr(data, "title", None),
            created_at=now,
            updated_at=now,
        )
        self._by_id[conv_id] = conv
        # FastAPI 会基于 response_model 做序列化；这里用 dict+datetime 让它自动转
        return {
            "conversation_id": conv.conversation_id,
            "user_id": conv.user_id,
            "agent_id": conv.agent_id,
            "title": conv.title,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
        }

    async def get_conversation(self, conv_id: str) -> Optional[_Conversation]:
        return self._by_id.get(conv_id)

    async def update_conversation_timestamp(self, conv_id: str) -> None:
        conv = self._by_id.get(conv_id)
        if conv:
            conv.updated_at = _utcnow()


class _FakeMomentService:
    def __init__(self, get_turn: Optional[Callable[[], int]] = None) -> None:
        self._moments: Dict[str, _Moment] = {}
        self.created_count = 0
        self.events: List[Dict[str, Any]] = []
        self._get_turn = get_turn

    def _turn(self) -> Optional[int]:
        if not self._get_turn:
            return None
        try:
            return int(self._get_turn())
        except Exception:
            return None

    async def get_open_moments(self, user_id: str, limit: int = 200) -> List[_Moment]:
        items = [
            m
            for m in self._moments.values()
            if m.user_id == user_id and m.status not in (2, 3)
        ]
        items.sort(key=lambda x: (x.event_time, x.moment_id), reverse=True)
        return items[:limit]

    async def apply_ai_pending_moment_update(
        self, moment_id: str, action: str
    ) -> Optional[Dict[str, Any]]:
        m = self._moments.get(moment_id)
        if not m:
            self.events.append(
                {
                    "type": "moment_update",
                    "turn": self._turn(),
                    "moment_id": moment_id,
                    "action": action,
                    "result": "not_found",
                }
            )
            return None

        a = (action or "").strip().lower()
        now = _utcnow()
        if a == "confirm":
            m.confirmed = True
            m.status = 1
        elif a == "cancel":
            m.status = 3
        elif a == "complete":
            m.status = 2
            m.executed_at = now
        else:
            self.events.append(
                {
                    "type": "moment_update",
                    "turn": self._turn(),
                    "moment_id": moment_id,
                    "action": action,
                    "result": "ignored",
                }
            )
            return None

        self.events.append(
            {
                "type": "moment_update",
                "turn": self._turn(),
                "moment_id": moment_id,
                "action": a,
                "result": "applied",
                "status": m.status,
                "confirmed": m.confirmed,
                "executed_at": m.executed_at.isoformat() if m.executed_at else None,
            }
        )
        return {"moment_id": moment_id, "action": a}

    async def create_moment_from_llm_response(
        self,
        conv_id: str,
        user_id: str,
        moment_data: Dict[str, Any],
        context_messages: List[Dict[str, str]],
    ) -> Optional[_Moment]:
        if not moment_data or not moment_data.get("is_moment"):
            return None

        event_time = _utcnow() + timedelta(days=1)
        remind_time = event_time - timedelta(hours=1)
        moment_id = str(uuid.uuid4())
        m = _Moment(
            moment_id=moment_id,
            user_id=user_id,
            conversation_id=conv_id,
            type=moment_data.get("type", "event"),
            event_time=event_time,
            remind_time=remind_time,
            event_description=moment_data.get("event_description", ""),
            importance=moment_data.get("importance", "mid"),
            suggested_action=moment_data.get("suggested_action", "message"),
            status=1,
            confirmed=False,
        )
        self._moments[moment_id] = m
        self.created_count += 1
        self.events.append(
            {
                "type": "moment_create",
                "turn": self._turn(),
                "moment_id": moment_id,
                "event_description": m.event_description,
            }
        )
        return m


class _FakeLLMService:
    """固定话题：同一场面试；情绪大起大落；去重 + 状态更新由 turn 驱动。"""

    def __init__(self) -> None:
        self.turn = 0
        self.calls: List[Dict[str, Any]] = []

    async def generate_response(
        self, conv_id: str, user_message: str, open_moments: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        self.turn += 1
        open_moments = open_moments or []

        emotion_level = 5 if (self.turn % 4 in (1, 2)) else 0
        emotion_tags = ["panic", "overwhelmed"] if emotion_level == 5 else ["calm"]

        if not open_moments:
            result = {
                "chat_response": "（CLI模拟）我听到了：你在为同一个面试反复摇摆。我会陪你把这件事撑过去。",
                "emotion_tags": emotion_tags,
                "emotion_level": emotion_level,
                "moment": {
                    "is_moment": True,
                    "type": "event",
                    "time": "明天早上8点",
                    "event_description": "明天早上8点的面试",
                    "importance": "high",
                    "suggested_action": "message",
                    "reason": "首轮识别到明确未来事件，值得后续触达",
                },
                "moment_updates": [],
            }
            self.calls.append(
                {
                    "turn": self.turn,
                    "user_message": user_message,
                    "open_moments": open_moments,
                    "dedup_decision": "create_new_moment (open_moments is empty)",
                    "result": result,
                }
            )
            return result

        target_id = open_moments[0]["moment_id"]
        updates: List[Dict[str, Any]] = []
        if self.turn == 10:
            updates.append({"moment_id": target_id, "action": "confirm", "reason": "用户希望我提醒并确认"})
        if self.turn == 55:
            updates.append({"moment_id": target_id, "action": "complete", "reason": "用户明确说面试结束"})

        result = {
            "chat_response": "（CLI模拟）我在。我们把这场面试拆成一个可执行的小步骤。",
            "emotion_tags": emotion_tags,
            "emotion_level": emotion_level,
            "moment": None,
            "moment_updates": updates,
        }
        self.calls.append(
            {
                "turn": self.turn,
                "user_message": user_message,
                "open_moments": open_moments,
                "dedup_decision": "moment=null (dedup against open_moments)",
                "result": result,
            }
        )
        return result


class _FakeAPIClient:
    """替换 CLI 的 APIClient：把 sync 方法桥接到内存 FastAPI app。"""

    def __init__(self, base_url: str, app: FastAPI) -> None:
        self.base_url = (base_url or "http://test").rstrip("/")
        self._app = app

    def close(self) -> None:
        return None

    def create_conversation(self, user_id: str, agent_id: str, title: Optional[str] = None) -> Dict[str, Any]:
        async def _do():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self._app), base_url="http://test"
            ) as client:
                payload: Dict[str, Any] = {"user_id": user_id, "agent_id": agent_id}
                if title:
                    payload["title"] = title
                resp = await client.post("/api/conversations", json=payload)
                resp.raise_for_status()
                return resp.json()

        return asyncio.run(_do())

    def send_message(self, conv_id: str, content: str) -> Dict[str, Any]:
        async def _do():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self._app), base_url="http://test"
            ) as client:
                resp = await client.post(f"/api/conversations/{conv_id}/chat", json={"content": content})
                resp.raise_for_status()
                return resp.json()

        return asyncio.run(_do())


class TestCliChatStartDedupReport(unittest.TestCase):
    def test_cli_chat_start_55_turns_and_write_md_report(self) -> None:
        # 1) 内存 FastAPI app：只挂 conversations + messages
        app = FastAPI()
        app.include_router(conversations_router.router, prefix="/api/conversations", tags=["conversations"])
        app.include_router(messages_router.router, prefix="/api", tags=["messages"])

        fake_messages = _FakeMessageService()
        fake_convs = _FakeConversationService()
        fake_llm = _FakeLLMService()
        fake_moments = _FakeMomentService(get_turn=lambda: fake_llm.turn)

        # conversations router DI
        app.dependency_overrides[conversations_router.get_conversation_service] = lambda: fake_convs
        # messages router DI
        app.dependency_overrides[messages_router.get_message_service] = lambda: fake_messages
        app.dependency_overrides[messages_router.get_conversation_service] = lambda: fake_convs
        app.dependency_overrides[messages_router.get_moment_service] = lambda: fake_moments
        app.dependency_overrides[messages_router.get_llm_service] = lambda: fake_llm

        report_path = Path(__file__).with_name("cli_chat_dedup_55_turns_report.md")

        # 2) 准备 55 轮“人类逐条输入”的消息 + exit
        user_id = "user_cli_1"
        agent_id = "agent_cli_1"
        user_lines: List[str] = []
        for i in range(1, 56):
            if i % 6 == 1:
                user_lines.append(f"第{i}轮：我快崩溃了，我怕明天早上8点的面试会失败。")
            elif i % 6 == 2:
                user_lines.append(f"第{i}轮：我又突然兴奋起来，觉得我一定能拿下这场面试！")
            elif i % 6 == 3:
                user_lines.append(f"第{i}轮：我现在很愤怒，为什么同一件面试让我这么痛苦？")
            elif i % 6 == 4:
                user_lines.append(f"第{i}轮：我开始麻木了，但还是绕不开明天的面试。")
            elif i % 6 == 5:
                user_lines.append(f"第{i}轮：我又很害怕，心跳很快，面试两个字都让我发抖。")
            else:
                tail = "（我已经面试结束了）" if i == 55 else ""
                user_lines.append(f"第{i}轮：我还是在想这场面试要怎么准备。{tail}")

        cli_input = "\n".join(user_lines + ["exit"]) + "\n"

        # 3) patch CLI 的 APIClient，让它打内存 app；然后用 CliRunner 运行 chat start
        runner = CliRunner()

        def _fake_client_factory(api_url: str):
            return _FakeAPIClient(api_url, app=app)

        try:
            with patch("cli.commands.chat.APIClient", side_effect=_fake_client_factory):
                result = runner.invoke(
                    cli_app,
                    ["chat", "start", "--user-id", user_id, "--agent-id", agent_id, "--api-url", "http://test"],
                    input=cli_input,
                )
                # Typer/Click 退出码：0 表示正常退出
                self.assertEqual(result.exit_code, 0, msg=result.output)

            # 4) 写 Markdown 报告：对话过程 + 识别过程 + 查重过程
            md: List[str] = []
            md.append("# CLI 逐条对话查重回归报告（55轮）")
            md.append("")
            md.append(f"- 生成时间: `{_utcnow().isoformat()}`")
            md.append("- 场景: CLI `chat start` 交互模式（逐条输入，最后 exit）")
            md.append("- 主题: `同一场明天早上8点的面试`（单一话题）")
            md.append("- 要求: 保存 对话过程 + 关键时刻识别过程 + 查重过程")
            md.append("")
            md.append("## CLI 命令")
            md.append("")
            md.append("```")
            md.append(f"uv run cli chat start --user-id {user_id} --agent-id {agent_id} --api-url http://test")
            md.append("```")
            md.append("")

            # 转录：依赖 FakeLLM 的 calls 与对话输入序列对齐
            md.append("## 逐轮记录")
            md.append("")
            for i in range(1, 56):
                call = fake_llm.calls[i - 1]
                r = call["result"]
                turn_events = [ev for ev in fake_moments.events if ev.get("turn") == i]
                md.append(f"### Turn {i:02d}")
                md.append("")
                md.append("#### 用户输入（CLI）")
                md.append(user_lines[i - 1])
                md.append("")
                md.append("#### Router 注入 open_moments（用于查重/匹配）")
                oms = call.get("open_moments") or []
                md.append(f"- count: **{len(oms)}**")
                for m in oms[:10]:
                    md.append(
                        f"  - moment_id=`{m.get('moment_id')}` status={m.get('status')} confirmed={m.get('confirmed')} desc={m.get('event_description')}"
                    )
                if len(oms) > 10:
                    md.append("  - ...（已截断，仅展示前10条）")
                md.append("")
                md.append("#### 关键时刻识别过程（LLM 输出）")
                md.append(f"- emotion_level: `{r.get('emotion_level')}` tags={r.get('emotion_tags')}")
                md.append(f"- dedup_decision: **{call.get('dedup_decision')}**")
                md.append(f"- moment: `{r.get('moment')}`")
                md.append(f"- moment_updates: `{r.get('moment_updates')}`")
                md.append("")
                md.append("#### 查重过程（解释）")
                md.append(
                    "- 规则：若新识别事件与 open_moments 任意一条是同一件事，则必须 `moment=null`；否则可创建新 moment。"
                )
                md.append("")
                md.append("#### 关键时刻状态更新落地（Service 层效果）")
                if turn_events:
                    for ev in turn_events:
                        md.append(f"- {ev}")
                else:
                    md.append("- （无）本轮没有创建/更新关键时刻")
                md.append("")
                md.append("#### Assistant 输出（CLI 展示内容）")
                md.append(r.get("chat_response", ""))
                md.append("")
                md.append("---")
                md.append("")

            md.append("## 断言与结果")
            md.append("")
            md.append(f"- moment_created_count: **{fake_moments.created_count}**（期望 1）")
            md.append(f"- open_moments_final_count: **{len([m for m in fake_moments._moments.values() if m.status not in (2,3)])}**")
            md.append("")
            if len(fake_moments._moments) == 1:
                m = next(iter(fake_moments._moments.values()))
                md.append(f"- moment_id: `{m.moment_id}`")
                md.append(f"- confirmed: **{m.confirmed}**（期望 True，Turn 10 confirm）")
                md.append(f"- status: **{m.status}**（期望 2，Turn 55 complete）")
                md.append(f"- executed_at: `{m.executed_at.isoformat() if m.executed_at else None}`")
            md.append("")

            report_path.write_text("\n".join(md), encoding="utf-8")

            # 关键断言
            self.assertEqual(fake_moments.created_count, 1)
            self.assertEqual(len(fake_moments._moments), 1)
            m = next(iter(fake_moments._moments.values()))
            self.assertTrue(m.confirmed)
            self.assertEqual(m.status, 2)
            self.assertIsNotNone(m.executed_at)
            self.assertTrue(report_path.exists())
        finally:
            # 确保即使断言失败也尽量留下 CLI 输出（排错价值极高）
            if not report_path.exists():
                report_path.write_text(
                    "# CLI 逐条对话查重回归报告（生成失败）\n\n（测试过程中提前异常，未生成逐轮细节）\n",
                    encoding="utf-8",
                )

