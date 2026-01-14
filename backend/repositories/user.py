"""
[INPUT]: 依赖 backend.repositories.base 的 BaseRepository，依赖 backend.models.user 的 UserInDB，依赖 backend.core.database 的 db
[OUTPUT]: 对外提供 UserRepository 类，封装用户数据的 CRUD 操作
[POS]: backend/repositories 的用户数据访问层，被 UserService 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from typing import Dict, Any
from .base import BaseRepository
from ..models.user import UserInDB
from ..core.database import db


class UserRepository(BaseRepository[UserInDB]):
    """用户数据仓储

    提供用户相关的数据库操作
    """

    def __init__(self):
        super().__init__(db.db.users)

    def _to_model(self, doc: Dict[str, Any]) -> UserInDB:
        """MongoDB 文档 → UserInDB 模型"""
        return UserInDB(
            user_id=doc["user_id"],
            username=doc["username"],
            created_at=doc["created_at"],
        )
