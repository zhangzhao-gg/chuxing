"""
backend.models - Pydantic 数据模型模块

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from .user import UserCreate, UserResponse, UserInDB
from .agent import AgentCreate, AgentResponse, AgentInDB
from .conversation import ConversationCreate, ConversationResponse, ConversationInDB
from .message import MessageCreate, MessageResponse, MessageInDB

__all__ = [
    "UserCreate",
    "UserResponse",
    "UserInDB",
    "AgentCreate",
    "AgentResponse",
    "AgentInDB",
    "ConversationCreate",
    "ConversationResponse",
    "ConversationInDB",
    "MessageCreate",
    "MessageResponse",
    "MessageInDB",
]
