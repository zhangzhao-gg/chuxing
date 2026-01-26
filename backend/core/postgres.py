"""
[INPUT]: 依赖 asyncpg 的 create_pool，依赖 backend.core.config 的 settings
[OUTPUT]: 对外提供 pg 全局对象、connect_to_postgres/close_postgres_connection 生命周期函数
[POS]: backend/core 的 PostgreSQL 连接管理器，被 main.py 与 MomentRepository 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import logging
from typing import Optional

import asyncpg

from .config import settings

logger = logging.getLogger(__name__)


class PostgresDatabase:
    """PostgreSQL 连接池封装"""

    pool: Optional[asyncpg.Pool] = None


pg = PostgresDatabase()


async def connect_to_postgres() -> None:
    """应用启动时调用：建立连接池 + 创建表结构"""
    logger.info(
        "正在连接 PostgreSQL: %s:%s/%s",
        settings.POSTGRES_HOST,
        settings.POSTGRES_PORT,
        settings.POSTGRES_DB_NAME,
    )
    pg.pool = await asyncpg.create_pool(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB_NAME,
        min_size=1,
        max_size=10,
    )

    # 测试连接
    async with pg.pool.acquire() as conn:
        await conn.execute("SELECT 1")
    logger.info("PostgreSQL 连接成功")

    await create_pg_schema()


async def close_postgres_connection() -> None:
    """应用关闭时调用：关闭连接池"""
    logger.info("正在关闭 PostgreSQL 连接")
    if pg.pool:
        await pg.pool.close()
        logger.info("PostgreSQL 连接已关闭")


async def create_pg_schema() -> None:
    """创建 Postgres 表结构（幂等操作）"""
    logger.info("开始创建 PostgreSQL 表结构")
    if not pg.pool:
        raise RuntimeError("PostgreSQL 连接池未初始化")

    async with pg.pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS moments (
                moment_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                conversation_id TEXT NULL,
                event_time TIMESTAMPTZ NOT NULL,
                remind_time TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                type TEXT NOT NULL,
                event_description TEXT NOT NULL,
                emotion TEXT NULL,
                emotion_level INTEGER NULL,
                importance TEXT NOT NULL,
                suggested_action TEXT NOT NULL,
                suggested_timing TEXT NULL,
                first_message TEXT NULL,
                ai_attitude TEXT NULL,
                reason TEXT NULL,
                status TEXT NOT NULL,
                confirmed BOOLEAN NOT NULL DEFAULT FALSE,
                executed_at TIMESTAMPTZ NULL,
                context_messages JSONB NULL
            );
            """
        )

        await conn.execute("ALTER TABLE moments ADD COLUMN IF NOT EXISTS suggested_timing TEXT NULL;")
        await conn.execute("ALTER TABLE moments ADD COLUMN IF NOT EXISTS reason TEXT NULL;")

        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_moments_user_event "
            "ON moments (user_id, event_time);"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_moments_remind_status "
            "ON moments (remind_time, status);"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_moments_user_event_type "
            "ON moments (user_id, event_time, type);"
        )

    logger.info("PostgreSQL 表结构创建完成")
