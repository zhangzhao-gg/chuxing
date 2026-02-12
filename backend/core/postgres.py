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
                status SMALLINT NOT NULL,
                confirmed BOOLEAN NOT NULL DEFAULT FALSE,
                executed_at TIMESTAMPTZ NULL,
                context_messages JSONB NULL
            );
            """
        )

        await conn.execute("ALTER TABLE moments ADD COLUMN IF NOT EXISTS suggested_timing TEXT NULL;")
        await conn.execute("ALTER TABLE moments ADD COLUMN IF NOT EXISTS reason TEXT NULL;")

        # ===== 兑现发送（站内消息/短信/推送等）调度字段 =====
        # 目标：支持多 worker 并发抢占、失败重试、崩溃自动释放锁。
        await conn.execute(
            "ALTER TABLE moments ADD COLUMN IF NOT EXISTS deliver_attempts INTEGER NOT NULL DEFAULT 0;"
        )
        await conn.execute(
            "ALTER TABLE moments ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ NULL;"
        )
        await conn.execute(
            "ALTER TABLE moments ADD COLUMN IF NOT EXISTS delivery_locked_at TIMESTAMPTZ NULL;"
        )
        await conn.execute(
            "ALTER TABLE moments ADD COLUMN IF NOT EXISTS delivery_lock_expires_at TIMESTAMPTZ NULL;"
        )
        await conn.execute(
            "ALTER TABLE moments ADD COLUMN IF NOT EXISTS last_delivery_error TEXT NULL;"
        )

        # status 迁移：TEXT -> SMALLINT（pending=1 scheduled=1 completed=2 cancelled=3）
        # 备注：pending 与 scheduled 同为 1，通过 confirmed(false/true) 区分。
        await conn.execute(
            """
            DO $$
            DECLARE
                col_type TEXT;
            BEGIN
                SELECT data_type INTO col_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'moments'
                  AND column_name = 'status';

                IF col_type IN ('text', 'character varying') THEN
                    ALTER TABLE moments
                    ALTER COLUMN status TYPE SMALLINT
                    USING (
                        CASE status
                            WHEN 'pending' THEN 1
                            WHEN 'scheduled' THEN 1
                            WHEN 'completed' THEN 2
                            WHEN 'cancelled' THEN 3
                            ELSE 1
                        END
                    );
                END IF;
            END $$;
            """
        )

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
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_moments_delivery_due "
            "ON moments (remind_time, next_retry_at, delivery_lock_expires_at) "
            "WHERE status = 1 AND confirmed = TRUE AND executed_at IS NULL;"
        )

    logger.info("PostgreSQL 表结构创建完成")
