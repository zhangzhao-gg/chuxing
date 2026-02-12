"""
[INPUT]: 依赖 fastapi 的 FastAPI，依赖 httpx 的 ASGITransport/AsyncClient，依赖 backend.routers.messages 的路由与依赖注入点
[OUTPUT]: 对外提供 unittest 测试用例（>=50轮对话），验证 open_moments 去重与 moment_updates 状态更新
[POS]: backend/tests 的对话回归测试：围绕单一话题，情绪大起大落，覆盖“注入 open_moments → LLM 决策 → 更新状态/去重”
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import unittest
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI

from backend.routers import messages as messages_router


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


class FakeMessageService:
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


class FakeConversationService:
    def __init__(self, conversation: _Conversation) -> None:
        self._conv = conversation

    async def get_conversation(self, conv_id: str) -> Optional[_Conversation]:
        return self._conv if conv_id == self._conv.conversation_id else None

    async def update_conversation_timestamp(self, conv_id: str) -> None:
        if conv_id == self._conv.conversation_id:
            self._conv.updated_at = _utcnow()


class FakeMomentService:
    def __init__(self) -> None:
        self._moments: Dict[str, _Moment] = {}
        self.created_count = 0
        self.events: List[Dict[str, Any]] = []

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
                {"type": "moment_update", "moment_id": moment_id, "action": action, "result": "not_found"}
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
                {"type": "moment_update", "moment_id": moment_id, "action": action, "result": "ignored"}
            )
            return None

        self.events.append(
            {
                "type": "moment_update",
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

        # 测试里不做复杂时间解析：直接给一个稳定的未来时间
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
                "moment_id": moment_id,
                "event_description": m.event_description,
                "status": m.status,
                "confirmed": m.confirmed,
            }
        )
        return m


class FakeLLMService:
    """围绕单一话题（面试），制造大幅情绪起伏，并驱动去重/状态更新。"""

    def __init__(self) -> None:
        self.turn = 0
        self.calls: List[Dict[str, Any]] = []

    async def generate_response(
        self, conv_id: str, user_message: str, open_moments: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        self.turn += 1
        open_moments = open_moments or []

        # 情绪大起大落：在 0 与 5 间来回跳，标签随之变化
        emotion_level = 5 if (self.turn % 4 in (1, 2)) else 0
        emotion_tags = ["panic", "overwhelmed"] if emotion_level == 5 else ["calm"]

        # 第 1 轮：没有 open moments → 创建新的 moment（后续围绕同一件事去重）
        if not open_moments:
            result = {
                "chat_response": "我听到了：你在为同一个面试反复摇摆。我会陪你把这件事撑过去。",
                "emotion_tags": emotion_tags,
                "emotion_level": emotion_level,
                "moment": {
                    "is_moment": True,
                    "type": "event",
                    "time": "明天早上8点",
                    "event_description": "明天早上8点的面试",
                    "importance": "high",
                    "suggested_action": "message",
                    "reason": "用户反复提及同一场即将发生的重要面试",
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

        # 已存在 open moments：同一话题 → 必须去重（moment=null），并在特定轮次更新状态
        target_id = open_moments[0]["moment_id"]
        updates: List[Dict[str, Any]] = []

        # 第 10 轮：确认（进入 scheduled 语义，但 status 仍是 1）
        if self.turn == 10:
            updates.append(
                {"moment_id": target_id, "action": "confirm", "reason": "用户表示会认真准备并希望我提醒"}
            )

        # 第 55 轮：完成（面试已结束）
        if self.turn == 55:
            updates.append(
                {"moment_id": target_id, "action": "complete", "reason": "用户明确说已经面试结束"}
            )

        result = {
            "chat_response": "我在。你可以把注意力放在下一步：把面试拆成一个可执行的小步骤。",
            "emotion_tags": emotion_tags,
            "emotion_level": emotion_level,
            "moment": None,  # 去重：同一件事不再创建新 moment
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


class TestMomentDedupAndUpdatesOver50Turns(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.conv_id = "conv_50_turns"
        self.user_id = "user_1"
        self.conversation = _Conversation(
            conversation_id=self.conv_id,
            user_id=self.user_id,
            agent_id="agent_1",
            updated_at=_utcnow(),
        )

        self.fake_message_service = FakeMessageService()
        self.fake_conv_service = FakeConversationService(self.conversation)
        self.fake_moment_service = FakeMomentService()
        self.fake_llm_service = FakeLLMService()

        app = FastAPI()
        app.include_router(messages_router.router, prefix="/api", tags=["messages"])

        # 依赖覆盖：让 /chat 完全跑在内存态，无需 DB/OpenAI
        app.dependency_overrides[messages_router.get_message_service] = (
            lambda: self.fake_message_service
        )
        app.dependency_overrides[messages_router.get_conversation_service] = (
            lambda: self.fake_conv_service
        )
        app.dependency_overrides[messages_router.get_moment_service] = (
            lambda: self.fake_moment_service
        )
        app.dependency_overrides[messages_router.get_llm_service] = (
            lambda: self.fake_llm_service
        )

        self._transport = httpx.ASGITransport(app=app)

    async def asyncTearDown(self) -> None:
        await self._transport.aclose()

    async def test_dedup_and_updates_over_50_turns_single_topic_big_emotion_swings(self) -> None:
        report_path = Path(__file__).with_name("moment_dedup_50_rounds_report.md")
        report_lines: List[str] = []
        report_lines.append("# 关键时刻查重机制回归测试报告（55轮）")
        report_lines.append("")
        report_lines.append(f"- 生成时间: `{_utcnow().isoformat()}`")
        report_lines.append("- 主题: `同一场明天早上8点的面试`（单一话题）")
        report_lines.append("- 情绪: `大起大落`（模拟 emotion_level 在 0/5 间跳变）")
        report_lines.append("- 机制: 每轮注入 `open_moments`；LLM 若命中同一件事则 `moment=null`；用 `moment_updates` 更新状态")
        report_lines.append("")

        # 55 轮对话：围绕“同一场面试”，用户情绪大起大落
        user_messages: List[str] = []
        for i in range(1, 56):
            if i % 6 == 1:
                user_messages.append(f"第{i}轮：我快崩溃了，我怕明天早上8点的面试会失败。")
            elif i % 6 == 2:
                user_messages.append(f"第{i}轮：我又突然兴奋起来，觉得我一定能拿下这场面试！")
            elif i % 6 == 3:
                user_messages.append(f"第{i}轮：我现在很愤怒，为什么同一件面试让我这么痛苦？")
            elif i % 6 == 4:
                user_messages.append(f"第{i}轮：我开始麻木了，但还是绕不开明天的面试。")
            elif i % 6 == 5:
                user_messages.append(f"第{i}轮：我又很害怕，心跳很快，面试两个字都让我发抖。")
            else:
                # 最后一轮补一句“已结束”触发 complete
                tail = "（我已经面试结束了）" if i == 55 else ""
                user_messages.append(f"第{i}轮：我还是在想这场面试要怎么准备。{tail}")

        try:
            async with httpx.AsyncClient(transport=self._transport, base_url="http://test") as client:
                for idx, content in enumerate(user_messages, start=1):
                    before_events = len(self.fake_moment_service.events)

                    resp = await client.post(
                        f"/api/conversations/{self.conv_id}/chat",
                        json={"content": content},
                    )
                    self.assertEqual(resp.status_code, 200, msg=f"turn={idx} body={resp.text}")
                    data = resp.json()
                    self.assertIn("message_id", data)
                    self.assertEqual(data["conversation_id"], self.conv_id)
                    self.assertEqual(data["role"], "assistant")
                    self.assertTrue(isinstance(data["content"], str) and len(data["content"]) > 0)

                    llm_call = self.fake_llm_service.calls[-1] if self.fake_llm_service.calls else None
                    new_events = self.fake_moment_service.events[before_events:]

                    report_lines.append(f"## Turn {idx:02d}")
                    report_lines.append("")
                    report_lines.append("### 用户消息")
                    report_lines.append(content)
                    report_lines.append("")

                    report_lines.append("### 注入 open_moments（Router → LLM）")
                    if llm_call and llm_call.get("open_moments"):
                        report_lines.append(f"- 数量: {len(llm_call['open_moments'])}")
                        for m in llm_call["open_moments"][:10]:
                            report_lines.append(
                                f"  - moment_id=`{m.get('moment_id')}` status={m.get('status')} confirmed={m.get('confirmed')} desc={m.get('event_description')}"
                            )
                        if len(llm_call["open_moments"]) > 10:
                            report_lines.append("  - ...（已截断，仅展示前10条）")
                    else:
                        report_lines.append("- 数量: 0")
                    report_lines.append("")

                    report_lines.append("### 关键时刻识别 / 查重（LLM 输出）")
                    if llm_call:
                        r = llm_call["result"]
                        report_lines.append(f"- dedup_decision: **{llm_call.get('dedup_decision')}**")
                        report_lines.append(f"- emotion_level: `{r.get('emotion_level')}` tags={r.get('emotion_tags')}")
                        report_lines.append(f"- moment: `{r.get('moment')}`")
                        report_lines.append(f"- moment_updates: `{r.get('moment_updates')}`")
                    else:
                        report_lines.append("- （缺失）未捕获到 LLM 调用记录")
                    report_lines.append("")

                    report_lines.append("### 状态更新落地（Service/Repo 侧效果）")
                    if new_events:
                        for ev in new_events:
                            report_lines.append(f"- {ev}")
                    else:
                        report_lines.append("- （无）本轮没有创建/更新关键时刻")
                    report_lines.append("")

                    report_lines.append("### Assistant 返回（API 响应）")
                    report_lines.append(data["content"])
                    report_lines.append("")
                    report_lines.append("---")
                    report_lines.append("")

            # 断言 1：整个 55 轮只创建过一次 moment（后续全部 moment=null 去重）
            self.assertEqual(self.fake_moment_service.created_count, 1)

            # 断言 2：第 10 轮触发 confirm，第 55 轮触发 complete
            self.assertEqual(len(self.fake_moment_service._moments), 1)
            m = next(iter(self.fake_moment_service._moments.values()))
            self.assertTrue(m.confirmed, msg="moment should be confirmed by turn 10")
            self.assertEqual(m.status, 2, msg="moment should be completed by turn 55")
            self.assertIsNotNone(m.executed_at, msg="executed_at should be set when completed")
        finally:
            # 无论断言是否失败，都落盘报告，便于复盘
            report_path.write_text("\n".join(report_lines), encoding="utf-8")

