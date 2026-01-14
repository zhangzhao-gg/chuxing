"""
[INPUT]: 依赖 pydantic 的 BaseModel，依赖 datetime/uuid 标准库
[OUTPUT]: 对外提供 AgentCreate/AgentResponse/AgentInDB 三个模型
[POS]: backend/models 的 Agent 数据模型，被 AgentRepository 和 AgentService 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class AgentCreate(BaseModel):
    """创建 Agent 请求体"""

    name: str = Field(..., min_length=1, max_length=100, description="Agent 名称")
    system_prompt: str = Field(..., min_length=1, description="系统提示词")
    model: str = Field(
        default="gpt-4o-mini", description="OpenAI 模型名（如 gpt-4o-mini、gpt-4o）"
    )


class AgentResponse(BaseModel):
    """Agent 响应体（对外暴露）"""

    agent_id: str = Field(..., description="Agent ID")
    name: str = Field(..., description="Agent 名称")
    system_prompt: str = Field(..., description="系统提示词")
    model: str = Field(..., description="OpenAI 模型名")
    created_at: datetime = Field(..., description="创建时间")

    model_config = {"from_attributes": True}


class AgentInDB(BaseModel):
    """Agent 数据库模型（内部使用）"""

    agent_id: str
    name: str
    system_prompt: str
    model: str
    created_at: datetime

    model_config = {"from_attributes": True}
