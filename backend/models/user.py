"""
[INPUT]: 依赖 pydantic 的 BaseModel，依赖 datetime/uuid 标准库
[OUTPUT]: 对外提供 UserCreate/UserResponse/UserInDB 三个模型
[POS]: backend/models 的用户数据模型，被 UserRepository 和 UserService 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class UserCreate(BaseModel):
    """创建用户请求体"""

    username: str = Field(..., min_length=1, max_length=50, description="用户名")


class UserResponse(BaseModel):
    """用户响应体（对外暴露）"""

    user_id: str = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    created_at: datetime = Field(..., description="创建时间")

    model_config = {"from_attributes": True}


class UserInDB(BaseModel):
    """用户数据库模型（内部使用）"""

    user_id: str
    username: str
    created_at: datetime

    model_config = {"from_attributes": True}
