"""
[INPUT]: 依赖 backend.repositories.base 的 BaseRepository，依赖 backend.models.message 的 MessageInDB，依赖 backend.core.database 的 db
[OUTPUT]: 对外提供 MessageRepository 类，封装消息数据的 CRUD 操作
[POS]: backend/repositories 的消息数据访问层，被 MessageService 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from typing import Dict, Any
from .base import BaseRepository
from ..models.message import MessageInDB
from ..core.database import db


class MessageRepository(BaseRepository[MessageInDB]):
    """消息数据仓储

    提供消息相关的数据库操作
    """

    def __init__(self):
        super().__init__(db.db.messages)

    def _to_model(self, doc: Dict[str, Any]) -> MessageInDB:
        """MongoDB 文档 → MessageInDB 模型"""
        return MessageInDB(
            message_id=doc["message_id"],
            conversation_id=doc["conversation_id"],
            role=doc["role"],
            content=doc["content"],
            token_count=doc.get("token_count"),
            created_at=doc["created_at"],
        )
