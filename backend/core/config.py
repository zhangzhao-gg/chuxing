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

    # === PostgreSQL 配置 ===
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB_NAME: str = "llm_chat"

    # === OpenAI 配置 ===
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: Optional[str] = None

    # === LLM 上下文配置 ===
    MAX_CONTEXT_TOKENS: int = 4096

    # === 上下文压缩配置 ===
    ENABLE_CONTEXT_COMPRESSION: bool = False  # 是否启用上下文压缩
    COMPRESSION_THRESHOLD: int = 30  # 触发压缩的消息数阈值
    COMPRESSION_TARGET: int = 10  # 压缩后保留的消息数

    # === 服务器配置 ===
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # === Moment 兑现调度（Worker）配置 ===
    # 备注：Web 进程不负责兑现发送；兑现由独立 worker 轮询并抢锁执行
    MOMENT_WORKER_POLL_INTERVAL_SECONDS: float = 2.0  # 轮询间隔
    MOMENT_WORKER_BATCH_SIZE: int = 50  # 每次领取的 moments 数
    MOMENT_WORKER_LOCK_SECONDS: int = 300  # 领取锁 TTL，避免 worker 崩溃导致永久卡死
    MOMENT_WORKER_MAX_CONCURRENCY: int = 10  # 并发发送数（站内消息/第三方通道都受它约束）
    MOMENT_WORKER_MAX_ATTEMPTS: int = 8  # 最大重试次数（超过后进入“冻结”，等待人工处理）

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


# 全局配置实例
settings = Settings()
