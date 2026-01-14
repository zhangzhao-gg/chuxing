"""
[INPUT]: 依赖 pydantic-settings 的 BaseSettings，依赖 python-dotenv 加载 .env
[OUTPUT]: 对外提供 Settings 类和全局 settings 实例
[POS]: backend/core 的配置管理器，被所有需要读取环境变量的模块消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """应用全局配置"""

    # === MongoDB 配置 ===
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "llm_chat"

    # === OpenAI 配置 ===
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: Optional[str] = None

    # === LLM 上下文配置 ===
    MAX_CONTEXT_TOKENS: int = 4096

    # === 服务器配置 ===
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


# 全局配置实例
settings = Settings()
