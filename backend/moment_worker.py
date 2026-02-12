"""
[INPUT]: 依赖 backend.core.database/backend.core.postgres 的连接生命周期函数；依赖 backend.repositories.moment 的 MomentRepository；依赖 backend.services.notification 的 NotificationService；依赖 backend.core.config 的 settings
[OUTPUT]: 对外提供独立进程 worker：轮询领取到期 moments 并发送兑现消息（站内消息），支持并发与失败重试
[POS]: backend 的离线执行入口，与 FastAPI Web 进程解耦；可水平扩容多个 worker 实例
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import List

# 关键点：在导入任何可能触发 asyncpg/事件循环行为的模块之前先设置策略
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]

from .core.config import settings
from .core.database import connect_to_mongo, close_mongo_connection
from .core.postgres import connect_to_postgres, close_postgres_connection
from .repositories.moment import MomentRepository
from .services.notification import NotificationService
from .models.moment import MomentInDB


logger = logging.getLogger(__name__)


def _retry_backoff_seconds() -> int:
    """失败重试退避（最小实现：固定退避）。

    备注：deliver_attempts 在 DB 内递增并限制 max_attempts；
    这里先用固定退避，避免引入额外读写与分支复杂度。
    """
    return 60


async def _handle_one_moment(
    moment: MomentInDB,
    notifier: NotificationService,
    repo: MomentRepository,
    semaphore: asyncio.Semaphore,
) -> None:
    async with semaphore:
        # 关键点：使用 timezone-aware UTC，避免 Postgres TIMESTAMPTZ 比较发生隐式时区偏移
        now = datetime.now(timezone.utc)
        try:
            await notifier.send_moment_notification(moment)
            await repo.mark_delivered(moment.moment_id, delivered_at=now)
            logger.info("Moment delivered: moment_id=%s conv_id=%s", moment.moment_id, moment.conversation_id)
        except Exception as e:
            next_retry_at = now + timedelta(seconds=_retry_backoff_seconds())
            await repo.mark_delivery_failed(
                moment_id=moment.moment_id,
                now=now,
                next_retry_at=next_retry_at,
                error_message=str(e)[:2000],
            )
            logger.warning(
                "Moment delivery failed: moment_id=%s next_retry_at=%s err=%s",
                moment.moment_id,
                next_retry_at.isoformat(),
                str(e),
                exc_info=True,
            )


async def run_worker_loop() -> None:
    """Worker 主循环：领取 due moments → 并发发送 → 更新状态。"""
    await connect_to_mongo()
    await connect_to_postgres()

    repo = MomentRepository()
    notifier = NotificationService()
    semaphore = asyncio.Semaphore(settings.MOMENT_WORKER_MAX_CONCURRENCY)

    logger.info(
        "Moment worker started: poll=%.2fs batch=%d lock=%ds concurrency=%d max_attempts=%d",
        settings.MOMENT_WORKER_POLL_INTERVAL_SECONDS,
        settings.MOMENT_WORKER_BATCH_SIZE,
        settings.MOMENT_WORKER_LOCK_SECONDS,
        settings.MOMENT_WORKER_MAX_CONCURRENCY,
        settings.MOMENT_WORKER_MAX_ATTEMPTS,
    )

    try:
        while True:
            now = datetime.now(timezone.utc)
            lock_expires_at = now + timedelta(seconds=settings.MOMENT_WORKER_LOCK_SECONDS)

            moments: List[MomentInDB] = await repo.claim_due_moments(
                now=now,
                limit=settings.MOMENT_WORKER_BATCH_SIZE,
                lock_expires_at=lock_expires_at,
                max_attempts=settings.MOMENT_WORKER_MAX_ATTEMPTS,
            )

            if moments:
                logger.info("Claimed due moments: n=%d", len(moments))
                tasks = [
                    asyncio.create_task(_handle_one_moment(m, notifier, repo, semaphore))
                    for m in moments
                ]
                await asyncio.gather(*tasks)
                # 立刻进入下一轮，提升吞吐
                continue

            await asyncio.sleep(settings.MOMENT_WORKER_POLL_INTERVAL_SECONDS)

    except asyncio.CancelledError:
        raise
    except KeyboardInterrupt:
        logger.info("Moment worker received KeyboardInterrupt, shutting down...")
    finally:
        await close_postgres_connection()
        await close_mongo_connection()
        logger.info("Moment worker stopped.")


async def main() -> None:
    """CLI 入口。"""
    await run_worker_loop()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(main())

