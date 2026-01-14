"""
[INPUT]: 依赖 pydantic 的 BaseModel，依赖 datetime/uuid 标准库
[OUTPUT]: 对外提供 ConversationCreate/ConversationResponse/ConversationInDB 三个模型
[POS]: backend/models 的会话数据模型，被 ConversationRepository 和 ConversationService 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class ConversationCreate(BaseModel):
    """创建会话请求体"""

    user_id: str = Field(..., description="用户 ID")
    agent_id: str = Field(..., description="Agent ID")
    title: Optional[str] = Field(None, max_length=200, description="会话标题（可选）")


class ConversationResponse(BaseModel):
    """会话响应体（对外暴露）"""

    conversation_id: str = Field(..., description="会话 ID")
    user_id: str = Field(..., description="用户 ID")
    agent_id: str = Field(..., description="Agent ID")
    title: Optional[str] = Field(None, description="会话标题")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")

    model_config = {"from_attributes": True}


class ConversationInDB(BaseModel):
    """会话数据库模型（内部使用）"""

    conversation_id: str
    user_id: str
    agent_id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
