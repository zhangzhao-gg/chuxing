"""
[INPUT]: 依赖 backend.repositories.base 的 BaseRepository，依赖 backend.models.agent 的 AgentInDB，依赖 backend.core.database 的 db
[OUTPUT]: 对外提供 AgentRepository 类，封装 Agent 数据的 CRUD 操作
[POS]: backend/repositories 的 Agent 数据访问层，被 AgentService 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from typing import Dict, Any
from .base import BaseRepository
from ..models.agent import AgentInDB
from ..core.database import db


class AgentRepository(BaseRepository[AgentInDB]):
    """Agent 数据仓储

    提供 Agent 相关的数据库操作
    """

    def __init__(self):
        super().__init__(db.db.agents)

    def _to_model(self, doc: Dict[str, Any]) -> AgentInDB:
        """MongoDB 文档 → AgentInDB 模型"""
        return AgentInDB(
            agent_id=doc["agent_id"],
            name=doc["name"],
            system_prompt=doc["system_prompt"],
            model=doc["model"],
            created_at=doc["created_at"],
        )
