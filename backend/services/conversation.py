"""
[INPUT]: 依赖 backend.repositories.conversation 的 ConversationRepository，依赖 backend.repositories.user 的 UserRepository，依赖 backend.repositories.agent 的 AgentRepository，依赖 backend.models.conversation 的 ConversationCreate/ConversationResponse
[OUTPUT]: 对外提供 ConversationService 类，封装会话业务逻辑
[POS]: backend/services 的会话业务逻辑层，被 Router 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from typing import Optional, List
from datetime import datetime
import uuid
from ..repositories.conversation import ConversationRepository
from ..repositories.user import UserRepository
from ..repositories.agent import AgentRepository
from ..models.conversation import ConversationCreate, ConversationResponse
from ..core.exceptions import ResourceNotFoundError


class ConversationService:
    """会话生命周期管理

    职责：
    - 创建会话，校验 user 和 agent 存在性
    - 查询会话
    - 删除会话（未来可扩展为级联删除消息）
    """

    def __init__(self):
        self.conv_repo = ConversationRepository()
        self.user_repo = UserRepository()
        self.agent_repo = AgentRepository()

    async def create_conversation(
        self, data: ConversationCreate
    ) -> ConversationResponse:
        """创建会话"""
        # 校验用户存在
        user = await self.user_repo.find_one({"user_id": data.user_id})
        if not user:
            raise ResourceNotFoundError(f"用户不存在: {data.user_id}")

        # 校验 Agent 存在
        agent = await self.agent_repo.find_one({"agent_id": data.agent_id})
        if not agent:
            raise ResourceNotFoundError(f"Agent 不存在: {data.agent_id}")

        # 创建会话文档
        now = datetime.utcnow()
        conv_doc = {
            "conversation_id": str(uuid.uuid4()),
            "user_id": data.user_id,
            "agent_id": data.agent_id,
            "title": data.title,
            "created_at": now,
            "updated_at": now,
        }

        conv_in_db = await self.conv_repo.create(conv_doc)

        return ConversationResponse(
            conversation_id=conv_in_db.conversation_id,
            user_id=conv_in_db.user_id,
            agent_id=conv_in_db.agent_id,
            title=conv_in_db.title,
            created_at=conv_in_db.created_at,
            updated_at=conv_in_db.updated_at,
        )

    async def get_conversation(self, conv_id: str) -> Optional[ConversationResponse]:
        """获取会话，返回 None 表示不存在"""
        conv = await self.conv_repo.find_one({"conversation_id": conv_id})
        if not conv:
            return None

        return ConversationResponse(
            conversation_id=conv.conversation_id,
            user_id=conv.user_id,
            agent_id=conv.agent_id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )

    async def list_user_conversations(
        self, user_id: str, limit: int = 100, skip: int = 0
    ) -> List[ConversationResponse]:
        """获取用户所有会话"""
        convs = await self.conv_repo.find_many(
            {"user_id": user_id}, limit=limit, skip=skip, sort=[("updated_at", -1)]
        )

        return [
            ConversationResponse(
                conversation_id=c.conversation_id,
                user_id=c.user_id,
                agent_id=c.agent_id,
                title=c.title,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in convs
        ]

    async def update_conversation_timestamp(self, conv_id: str) -> None:
        """更新会话的最后更新时间（在新消息时调用）"""
        await self.conv_repo.update(
            {"conversation_id": conv_id}, {"updated_at": datetime.utcnow()}
        )

    async def delete_conversation(self, conv_id: str) -> bool:
        """删除会话"""
        result = await self.conv_repo.delete({"conversation_id": conv_id})
        if not result:
            raise ResourceNotFoundError(f"会话不存在: {conv_id}")
        return True
