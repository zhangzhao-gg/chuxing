"""
[INPUT]: 依赖 backend.repositories.message 的 MessageRepository，依赖 backend.models.message 的 MessageResponse，依赖 tiktoken 的编码器
[OUTPUT]: 对外提供 MessageService 类，封装消息业务逻辑
[POS]: backend/services 的消息业务逻辑层，被 LLMService 和 Router 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from typing import List, Dict, Any, Literal
from datetime import datetime
import uuid
import tiktoken
from ..repositories.message import MessageRepository
from ..models.message import MessageResponse


class MessageService:
    """消息持久化与查询

    职责：
    - 保存消息到数据库
    - 查询对话历史
    - 计算 token 数量（使用 tiktoken）
    """

    def __init__(self):
        self.repo = MessageRepository()
        # GPT-4 和 GPT-3.5 使用的编码器
        self.encoder = tiktoken.get_encoding("cl100k_base")

    async def create_message(
        self,
        conv_id: str,
        role: Literal["user", "assistant", "system"],
        content: str,
    ) -> MessageResponse:
        """保存消息到数据库"""
        # 计算 token 数
        token_count = self._count_tokens([{"role": role, "content": content}])

        msg_doc = {
            "message_id": str(uuid.uuid4()),
            "conversation_id": conv_id,
            "role": role,
            "content": content,
            "token_count": token_count,
            "created_at": datetime.utcnow(),
        }

        msg_in_db = await self.repo.create(msg_doc)

        return MessageResponse(
            message_id=msg_in_db.message_id,
            conversation_id=msg_in_db.conversation_id,
            role=msg_in_db.role,
            content=msg_in_db.content,
            token_count=msg_in_db.token_count,
            created_at=msg_in_db.created_at,
        )

    async def get_conversation_messages(
        self, conv_id: str, limit: int = 50, skip: int = 0
    ) -> List[MessageResponse]:
        """获取对话历史（按时间顺序）"""
        messages = await self.repo.find_many(
            {"conversation_id": conv_id},
            limit=limit,
            skip=skip,
            sort=[("created_at", 1)],  # 升序，最早的在前面
        )

        return [
            MessageResponse(
                message_id=m.message_id,
                conversation_id=m.conversation_id,
                role=m.role,
                content=m.content,
                token_count=m.token_count,
                created_at=m.created_at,
            )
            for m in messages
        ]

    def _count_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """计算消息列表的 token 数

        参考 OpenAI 官方计算方法：
        - 每条消息固定开销：4 tokens（role + content 分隔符）
        - 每次对话固定开销：2 tokens
        """
        num_tokens = 0
        for msg in messages:
            num_tokens += 4  # 每条消息的固定开销
            num_tokens += len(self.encoder.encode(msg["content"]))
        num_tokens += 2  # 每次对话的固定开销
        return num_tokens
