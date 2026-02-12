"""
[INPUT]: 依赖 backend.services.message 的 MessageService（写入站内消息），依赖 backend.models.moment 的 MomentInDB
[OUTPUT]: 对外提供 NotificationService（兑现发送：把 moment 转为用户可见消息）
[POS]: backend/services 的通知发送层，被 moment_worker 消费；未来可扩展短信/Push/电话等 provider
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ..models.moment import MomentInDB
from ..models.message import MessageResponse
from .message import MessageService


class NotificationService:
    """通知发送服务（当前仅实现：站内消息）。"""

    def __init__(self) -> None:
        self.message_service = MessageService()

    def build_moment_message(self, moment: MomentInDB, now: Optional[datetime] = None) -> str:
        """把 moment 渲染成用户可读的兑现消息文案。

        Good Taste：
        - 优先使用 LLM 产出的 first_message（它更贴近人味）
        - 没有则走统一模板，避免分支爆炸
        """
        now = now or datetime.now(timezone.utc)

        if moment.first_message and moment.first_message.strip():
            return moment.first_message.strip()

        desc = (moment.event_description or "").strip()
        if desc:
            return f"提醒你一下：你之前提到「{desc}」。我在这儿，随时陪你。"
        return f"提醒你一下：到点了（{now.isoformat()}）。我在这儿，随时陪你。"

    async def send_moment_notification(self, moment: MomentInDB) -> MessageResponse:
        """发送 moment 兑现消息。

        当前策略：写入该 moment 所属会话（conversation_id）为一条 assistant 消息。
        备注：避免向对话历史中注入额外 system 消息，造成提示词语义污染。
        """
        if not moment.conversation_id:
            raise ValueError("moment.conversation_id 为空，无法发送站内消息")

        content = self.build_moment_message(moment)
        return await self.message_service.create_message(
            moment.conversation_id,
            "assistant",
            content,
        )

