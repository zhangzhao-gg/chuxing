"""
[INPUT]: 依赖 pydantic 的 BaseModel，依赖 datetime/uuid 标准库
[OUTPUT]: 对外提供 MessageCreate/MessageResponse/MessageInDB 三个模型
[POS]: backend/models 的消息数据模型，被 MessageRepository 和 MessageService 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal, Optional


class MessageCreate(BaseModel):
    """创建消息请求体（仅用于 API 接收用户消息）"""

    content: str = Field(..., min_length=1, description="消息内容")


class MessageResponse(BaseModel):
    """消息响应体（对外暴露）"""

    message_id: str = Field(..., description="消息 ID")
    conversation_id: str = Field(..., description="会话 ID")
    role: Literal["user", "assistant", "system"] = Field(..., description="角色")
    content: str = Field(..., description="消息内容")
    token_count: Optional[int] = Field(None, description="Token 数量")
    created_at: datetime = Field(..., description="创建时间")

    model_config = {"from_attributes": True}


class MessageInDB(BaseModel):
    """消息数据库模型（内部使用）"""

    message_id: str
    conversation_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    token_count: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}
