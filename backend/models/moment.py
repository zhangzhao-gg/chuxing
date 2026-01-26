"""
[INPUT]: 依赖 pydantic 的 BaseModel，依赖 datetime/uuid 标准库
[OUTPUT]: 对外提供 MomentCreate/MomentResponse/MomentInDB 三个模型
[POS]: backend/models 的关键时刻数据模型，被 MomentRepository 和 MomentService 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal, Optional, List, Dict, Any


class MomentCreate(BaseModel):
    """创建关键时刻请求体（手动创建时使用）"""

    user_id: str = Field(..., description="用户 ID")
    conversation_id: Optional[str] = Field(None, description="会话 ID")
    type: Literal["event", "habit", "emotion"] = Field(..., description="关键时刻类型")
    event_time: datetime = Field(..., description="事件发生时间")
    event_description: str = Field(..., min_length=1, description="事件描述")
    emotion: Optional[str] = Field(None, description="情绪标签")
    emotion_level: Optional[int] = Field(None, ge=0, le=5, description="情绪强度 0-5")
    importance: Literal["low", "mid", "high"] = Field(..., description="重要程度")
    suggested_action: Literal["call", "message"] = Field(
        default="message", description="建议触达方式"
    )
    suggested_timing: Optional[Literal["before_event", "after_event", "on_time"]] = Field(
        None, description="建议触达时机"
    )
    first_message: Optional[str] = Field(None, description="触达时的第一句话")
    ai_attitude: Optional[str] = Field(None, description="AI的态度（鼓励/安慰/祝贺等）")
    reason: Optional[str] = Field(None, description="关键时刻判断理由")


class MomentResponse(BaseModel):
    """关键时刻响应体（对外暴露）"""

    moment_id: str = Field(..., description="关键时刻 ID")
    user_id: str = Field(..., description="用户 ID")
    conversation_id: Optional[str] = Field(None, description="会话 ID")
    event_time: datetime = Field(..., description="事件发生时间")
    remind_time: datetime = Field(..., description="提醒时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    type: Literal["event", "habit", "emotion"] = Field(..., description="关键时刻类型")
    event_description: str = Field(..., description="事件描述")
    emotion: Optional[str] = Field(None, description="情绪标签")
    emotion_level: Optional[int] = Field(None, description="情绪强度 0-5")
    importance: Literal["low", "mid", "high"] = Field(..., description="重要程度")
    suggested_action: Literal["call", "message"] = Field(..., description="建议触达方式")
    suggested_timing: Optional[Literal["before_event", "after_event", "on_time"]] = Field(
        None, description="建议触达时机"
    )
    first_message: Optional[str] = Field(None, description="触达时的第一句话")
    ai_attitude: Optional[str] = Field(None, description="AI的态度")
    reason: Optional[str] = Field(None, description="关键时刻判断理由")
    status: Literal["pending", "scheduled", "completed", "cancelled"] = Field(
        ..., description="状态"
    )
    confirmed: bool = Field(default=False, description="用户是否确认")
    executed_at: Optional[datetime] = Field(None, description="实际执行时间")
    context_messages: Optional[List[Dict[str, Any]]] = Field(
        None, description="相关对话上下文"
    )

    model_config = {"from_attributes": True}


class MomentInDB(BaseModel):
    """关键时刻数据库模型（内部使用）"""

    moment_id: str
    user_id: str
    conversation_id: Optional[str] = None
    event_time: datetime
    remind_time: datetime
    created_at: datetime
    updated_at: datetime
    type: Literal["event", "habit", "emotion"]
    event_description: str
    emotion: Optional[str] = None
    emotion_level: Optional[int] = None
    importance: Literal["low", "mid", "high"]
    suggested_action: Literal["call", "message"]
    suggested_timing: Optional[Literal["before_event", "after_event", "on_time"]] = None
    first_message: Optional[str] = None
    ai_attitude: Optional[str] = None
    reason: Optional[str] = None
    status: Literal["pending", "scheduled", "completed", "cancelled"]
    confirmed: bool = False
    executed_at: Optional[datetime] = None
    context_messages: Optional[List[Dict[str, Any]]] = None

    model_config = {"from_attributes": True}
