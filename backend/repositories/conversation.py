"""
[INPUT]: 依赖 backend.repositories.base 的 BaseRepository，依赖 backend.models.conversation 的 ConversationInDB，依赖 backend.core.database 的 db
[OUTPUT]: 对外提供 ConversationRepository 类，封装会话数据的 CRUD 操作
[POS]: backend/repositories 的会话数据访问层，被 ConversationService 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from typing import Dict, Any
from .base import BaseRepository
from ..models.conversation import ConversationInDB
from ..core.database import db


class ConversationRepository(BaseRepository[ConversationInDB]):
    """会话数据仓储

    提供会话相关的数据库操作
    """

    def __init__(self):
        super().__init__(db.db.conversations)

    def _to_model(self, doc: Dict[str, Any]) -> ConversationInDB:
        """MongoDB 文档 → ConversationInDB 模型"""
        return ConversationInDB(
            conversation_id=doc["conversation_id"],
            user_id=doc["user_id"],
            agent_id=doc["agent_id"],
            title=doc.get("title"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )
