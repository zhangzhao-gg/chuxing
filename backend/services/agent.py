"""
[INPUT]: 依赖 backend.repositories.agent 的 AgentRepository，依赖 backend.models.agent 的 AgentCreate/AgentResponse
[OUTPUT]: 对外提供 AgentService 类，封装 Agent 业务逻辑
[POS]: backend/services 的 Agent 业务逻辑层，被 Router 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from typing import Optional, List
from datetime import datetime
import uuid
from ..repositories.agent import AgentRepository
from ..models.agent import AgentCreate, AgentResponse
from ..core.exceptions import ResourceNotFoundError


class AgentService:
    """Agent 配置管理

    职责：
    - 创建 Agent，设置 system_prompt 和 model
    - 更新 Agent 配置
    - 查询 Agent
    - 删除 Agent
    """

    def __init__(self):
        self.repo = AgentRepository()

    async def create_agent(self, data: AgentCreate) -> AgentResponse:
        """创建 Agent"""
        agent_doc = {
            "agent_id": str(uuid.uuid4()),
            "name": data.name,
            "system_prompt": data.system_prompt,
            "model": data.model,
            "created_at": datetime.utcnow(),
        }

        agent_in_db = await self.repo.create(agent_doc)

        return AgentResponse(
            agent_id=agent_in_db.agent_id,
            name=agent_in_db.name,
            system_prompt=agent_in_db.system_prompt,
            model=agent_in_db.model,
            created_at=agent_in_db.created_at,
        )

    async def update_agent(self, agent_id: str, data: AgentCreate) -> AgentResponse:
        """更新 Agent 配置"""
        update_doc = {
            "name": data.name,
            "system_prompt": data.system_prompt,
            "model": data.model,
        }

        agent = await self.repo.update({"agent_id": agent_id}, update_doc)
        if not agent:
            raise ResourceNotFoundError(f"Agent 不存在: {agent_id}")

        return AgentResponse(
            agent_id=agent.agent_id,
            name=agent.name,
            system_prompt=agent.system_prompt,
            model=agent.model,
            created_at=agent.created_at,
        )

    async def get_agent(self, agent_id: str) -> Optional[AgentResponse]:
        """获取 Agent，返回 None 表示不存在"""
        agent = await self.repo.find_one({"agent_id": agent_id})
        if not agent:
            return None

        return AgentResponse(
            agent_id=agent.agent_id,
            name=agent.name,
            system_prompt=agent.system_prompt,
            model=agent.model,
            created_at=agent.created_at,
        )

    async def list_agents(self, limit: int = 100, skip: int = 0) -> List[AgentResponse]:
        """列出所有 Agent"""
        agents = await self.repo.find_many(
            {}, limit=limit, skip=skip, sort=[("created_at", -1)]
        )

        return [
            AgentResponse(
                agent_id=a.agent_id,
                name=a.name,
                system_prompt=a.system_prompt,
                model=a.model,
                created_at=a.created_at,
            )
            for a in agents
        ]

    async def delete_agent(self, agent_id: str) -> bool:
        """删除 Agent"""
        result = await self.repo.delete({"agent_id": agent_id})
        if not result:
            raise ResourceNotFoundError(f"Agent 不存在: {agent_id}")
        return True
