"""
backend.core - 核心配置与基础设施模块

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from .config import settings
from .database import db, connect_to_mongo, close_mongo_connection
from .exceptions import (
    BaseError,
    RepositoryError,
    DocumentNotFoundError,
    DuplicateKeyError,
    BusinessError,
    ResourceNotFoundError,
    InvalidOperationError,
    LLMError,
    OpenAIRateLimitError,
    OpenAIAPIError,
)

__all__ = [
    "settings",
    "db",
    "connect_to_mongo",
    "close_mongo_connection",
    "BaseError",
    "RepositoryError",
    "DocumentNotFoundError",
    "DuplicateKeyError",
    "BusinessError",
    "ResourceNotFoundError",
    "InvalidOperationError",
    "LLMError",
    "OpenAIRateLimitError",
    "OpenAIAPIError",
]
