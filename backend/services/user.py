"""
[INPUT]: 依赖 backend.repositories.user 的 UserRepository，依赖 backend.models.user 的 UserCreate/UserResponse
[OUTPUT]: 对外提供 UserService 类，封装用户业务逻辑
[POS]: backend/services 的用户业务逻辑层，被 Router 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from typing import Optional, List
from datetime import datetime
import uuid
from ..repositories.user import UserRepository
from ..models.user import UserCreate, UserResponse
from ..core.exceptions import ResourceNotFoundError, DuplicateKeyError


class UserService:
    """用户生命周期管理

    职责：
    - 创建用户，校验用户名唯一性
    - 查询用户
    - 删除用户（未来可扩展为级联删除）
    """

    def __init__(self):
        self.repo = UserRepository()

    async def create_user(self, data: UserCreate) -> UserResponse:
        """创建用户"""
        # 检查用户名是否已存在
        existing = await self.repo.find_one({"username": data.username})
        if existing:
            raise DuplicateKeyError(f"用户名已存在: {data.username}")

        # 创建用户文档
        user_doc = {
            "user_id": str(uuid.uuid4()),
            "username": data.username,
            "created_at": datetime.utcnow(),
        }

        user_in_db = await self.repo.create(user_doc)

        return UserResponse(
            user_id=user_in_db.user_id,
            username=user_in_db.username,
            created_at=user_in_db.created_at,
        )

    async def get_user(self, user_id: str) -> Optional[UserResponse]:
        """获取用户，返回 None 表示不存在"""
        user = await self.repo.find_one({"user_id": user_id})
        if not user:
            return None

        return UserResponse(
            user_id=user.user_id,
            username=user.username,
            created_at=user.created_at,
        )

    async def list_users(self, limit: int = 100, skip: int = 0) -> List[UserResponse]:
        """列出所有用户"""
        users = await self.repo.find_many(
            {}, limit=limit, skip=skip, sort=[("created_at", -1)]
        )

        return [
            UserResponse(
                user_id=u.user_id,
                username=u.username,
                created_at=u.created_at,
            )
            for u in users
        ]

    async def delete_user(self, user_id: str) -> bool:
        """删除用户"""
        result = await self.repo.delete({"user_id": user_id})
        if not result:
            raise ResourceNotFoundError(f"用户不存在: {user_id}")
        return True
