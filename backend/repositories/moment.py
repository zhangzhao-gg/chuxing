"""
[INPUT]: 依赖 asyncpg 的连接池与 Record，依赖 backend.models.moment 的 MomentInDB，依赖 backend.core.postgres 的 pg
[OUTPUT]: 对外提供 MomentRepository 类，封装关键时刻数据的 CRUD 操作
[POS]: backend/repositories 的关键时刻数据访问层，被 MomentService 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from typing import Dict, Any, List, Optional, Iterable
from datetime import datetime

import asyncpg
import json

from ..models.moment import MomentInDB
from ..core.postgres import pg


_COLUMNS: Iterable[str] = (
    "moment_id",
    "user_id",
    "conversation_id",
    "event_time",
    "remind_time",
    "created_at",
    "updated_at",
    "type",
    "event_description",
    "emotion",
    "emotion_level",
    "importance",
    "suggested_action",
    "suggested_timing",
    "first_message",
    "ai_attitude",
    "reason",
    "status",
    "confirmed",
    "executed_at",
    "context_messages",
)

_ALLOWED_SORT_COLUMNS = {"event_time", "created_at", "remind_time"}
_SELECT_COLUMNS_SQL = ", ".join(_COLUMNS)
_SELECT_COLUMNS_SQL_M = ", ".join([f"m.{c}" for c in _COLUMNS])


class MomentRepository:
    """关键时刻数据仓储

    提供关键时刻相关的数据库操作
    """

    def __init__(self):
        if not pg.pool:
            raise RuntimeError("PostgreSQL 连接池未初始化")

    def _to_model(self, record: asyncpg.Record) -> MomentInDB:
        """PostgreSQL 记录 → MomentInDB 模型"""
        data = dict(record)
        # 有些环境下 jsonb 会被解码成 str，这里兜底反序列化
        cm = data.get("context_messages")
        if isinstance(cm, str):
            try:
                data["context_messages"] = json.loads(cm)
            except Exception:
                # 保持原值让上层更容易定位脏数据
                pass
        return MomentInDB(**data)

    def _normalize_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """写入 PG 前做类型规范化（尤其是 jsonb）。"""
        doc = dict(document)
        if "context_messages" in doc and doc["context_messages"] is not None:
            # asyncpg 对 json/jsonb 默认期望 str；这里统一序列化
            if not isinstance(doc["context_messages"], str):
                doc["context_messages"] = json.dumps(
                    doc["context_messages"], ensure_ascii=False, separators=(",", ":")
                )
        return doc

    async def create(self, document: Dict[str, Any]) -> MomentInDB:
        """插入关键时刻记录"""
        document = self._normalize_document(document)
        columns = list(_COLUMNS)
        placeholders = ", ".join(f"${idx}" for idx in range(1, len(columns) + 1))
        values = [document.get(col) for col in columns]
        sql = (
            f"INSERT INTO moments ({', '.join(columns)}) "
            f"VALUES ({placeholders}) RETURNING {_SELECT_COLUMNS_SQL}"
        )
        async with pg.pool.acquire() as conn:
            record = await conn.fetchrow(sql, *values)
        return self._to_model(record)

    async def find_one(self, query: Dict[str, Any]) -> Optional[MomentInDB]:
        """查询单个关键时刻"""
        moment_id = query.get("moment_id")
        if not moment_id:
            return None
        async with pg.pool.acquire() as conn:
            record = await conn.fetchrow(
                f"SELECT {_SELECT_COLUMNS_SQL} FROM moments WHERE moment_id = $1",
                moment_id,
            )
        return self._to_model(record) if record else None

    async def find_many(
        self,
        query: Dict[str, Any],
        limit: int = 100,
        skip: int = 0,
        sort: Optional[List[tuple]] = None,
    ) -> List[MomentInDB]:
        """查询多个关键时刻"""
        conditions = []
        values: List[Any] = []

        if "user_id" in query:
            values.append(query["user_id"])
            conditions.append(f"user_id = ${len(values)}")
        if "status" in query:
            values.append(query["status"])
            conditions.append(f"status = ${len(values)}")
        if "confirmed" in query:
            values.append(query["confirmed"])
            conditions.append(f"confirmed = ${len(values)}")
        if "conversation_id" in query:
            values.append(query["conversation_id"])
            conditions.append(f"conversation_id = ${len(values)}")

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

        order_clause = ""
        if sort:
            column, direction = sort[0]
            if column in _ALLOWED_SORT_COLUMNS:
                order_clause = " ORDER BY {} {}".format(
                    column, "ASC" if direction == 1 else "DESC"
                )

        values.extend([limit, skip])
        sql = (
            f"SELECT {_SELECT_COLUMNS_SQL} FROM moments"
            f"{where_clause}{order_clause} LIMIT ${len(values) - 1} OFFSET ${len(values)}"
        )

        async with pg.pool.acquire() as conn:
            records = await conn.fetch(sql, *values)
        return [self._to_model(record) for record in records]

    async def update(self, query: Dict[str, Any], update: Dict[str, Any]) -> Optional[MomentInDB]:
        """更新关键时刻，返回更新后的记录"""
        moment_id = query.get("moment_id")
        if not moment_id:
            return None

        update = self._normalize_document(update)
        set_clauses = []
        values: List[Any] = []
        for key, value in update.items():
            if key not in _COLUMNS:
                continue
            values.append(value)
            set_clauses.append(f"{key} = ${len(values)}")

        if not set_clauses:
            return await self.find_one({"moment_id": moment_id})

        values.append(moment_id)
        sql = (
            f"UPDATE moments SET {', '.join(set_clauses)} "
            f"WHERE moment_id = ${len(values)} RETURNING {_SELECT_COLUMNS_SQL}"
        )

        async with pg.pool.acquire() as conn:
            record = await conn.fetchrow(sql, *values)
        return self._to_model(record) if record else None

    async def find_pending_moments(
        self, remind_time_before: datetime, limit: int = 100
    ) -> List[MomentInDB]:
        """查找待触达的关键时刻（用于调度）"""
        async with pg.pool.acquire() as conn:
            records = await conn.fetch(
                f"SELECT {_SELECT_COLUMNS_SQL} FROM moments "
                "WHERE remind_time <= $1 "
                "  AND status = 1 "
                "  AND confirmed = TRUE "
                "  AND executed_at IS NULL "
                "  AND (next_retry_at IS NULL OR next_retry_at <= $1) "
                "  AND (delivery_lock_expires_at IS NULL OR delivery_lock_expires_at <= $1) "
                "ORDER BY remind_time ASC LIMIT $2",
                remind_time_before,
                limit,
            )
        return [self._to_model(record) for record in records]

    async def claim_due_moments(
        self,
        now: datetime,
        limit: int,
        lock_expires_at: datetime,
        max_attempts: int,
    ) -> List[MomentInDB]:
        """抢占式领取到期 moments（多 worker 并发安全）。

        设计：
        - 不引入新的 status 编码，避免 API/模型约束破坏
        - 通过 delivery_lock_expires_at + SKIP LOCKED 实现“领取锁”
        - deliver_attempts 递增，用于限制最大重试次数
        """
        sql = f"""
        WITH due AS (
            SELECT moment_id
            FROM moments
            WHERE status = 1
              AND confirmed = TRUE
              AND executed_at IS NULL
              AND conversation_id IS NOT NULL
              AND remind_time <= $1
              AND (next_retry_at IS NULL OR next_retry_at <= $1)
              AND (delivery_lock_expires_at IS NULL OR delivery_lock_expires_at <= $1)
              AND deliver_attempts < $4
            ORDER BY remind_time ASC
            FOR UPDATE SKIP LOCKED
            LIMIT $2
        )
        UPDATE moments m
        SET deliver_attempts = COALESCE(m.deliver_attempts, 0) + 1,
            delivery_locked_at = $1,
            delivery_lock_expires_at = $3,
            updated_at = $1
        FROM due
        WHERE m.moment_id = due.moment_id
        RETURNING {_SELECT_COLUMNS_SQL_M};
        """
        async with pg.pool.acquire() as conn:
            records = await conn.fetch(sql, now, limit, lock_expires_at, max_attempts)
        return [self._to_model(record) for record in records]

    async def mark_delivered(self, moment_id: str, delivered_at: datetime) -> Optional[MomentInDB]:
        """标记兑现发送成功：status=2 + executed_at=delivered_at，并清理锁/重试信息。"""
        sql = (
            "UPDATE moments SET "
            "status = 2, executed_at = $2, "
            "delivery_locked_at = NULL, delivery_lock_expires_at = NULL, "
            "next_retry_at = NULL, last_delivery_error = NULL, "
            "updated_at = $2 "
            "WHERE moment_id = $1 "
            f"RETURNING {_SELECT_COLUMNS_SQL}"
        )
        async with pg.pool.acquire() as conn:
            record = await conn.fetchrow(sql, moment_id, delivered_at)
        return self._to_model(record) if record else None

    async def mark_delivery_failed(
        self,
        moment_id: str,
        now: datetime,
        next_retry_at: datetime,
        error_message: str,
    ) -> Optional[MomentInDB]:
        """标记兑现发送失败：释放锁 + 写入 last_delivery_error/next_retry_at。"""
        sql = (
            "UPDATE moments SET "
            "delivery_locked_at = NULL, delivery_lock_expires_at = NULL, "
            "last_delivery_error = $2, next_retry_at = $3, "
            "updated_at = $4 "
            "WHERE moment_id = $1 "
            f"RETURNING {_SELECT_COLUMNS_SQL}"
        )
        async with pg.pool.acquire() as conn:
            record = await conn.fetchrow(sql, moment_id, error_message, next_retry_at, now)
        return self._to_model(record) if record else None

    async def find_latest_user_pending_moment(self, user_id: str) -> Optional[MomentInDB]:
        """获取用户最近一个 pending 关键时刻（status=1 且 confirmed=false）。

        备注：
        - status 编码：pending=1 scheduled=1 completed=2 cancelled=3
        - pending vs scheduled 通过 confirmed 字段区分
        """
        async with pg.pool.acquire() as conn:
            record = await conn.fetchrow(
                f"SELECT {_SELECT_COLUMNS_SQL} FROM moments "
                "WHERE user_id = $1 AND status = 1 AND confirmed = FALSE "
                "ORDER BY updated_at DESC, created_at DESC LIMIT 1",
                user_id,
            )
        return self._to_model(record) if record else None

    async def find_user_open_moments(self, user_id: str, limit: int = 200) -> List[MomentInDB]:
        """获取用户所有“未完成且未取消”的关键时刻（用于对话侧注入给 LLM）。

        约定：
        - completed=2
        - cancelled=3
        - 其余状态都视为 open（当前主要是 status=1，pending/scheduled 由 confirmed 区分）
        """
        async with pg.pool.acquire() as conn:
            records = await conn.fetch(
                f"SELECT {_SELECT_COLUMNS_SQL} FROM moments "
                "WHERE user_id = $1 AND status = 1 AND executed_at IS NULL "
                "ORDER BY event_time ASC LIMIT $2",
                user_id,
                limit,
            )
        return [self._to_model(record) for record in records]

    async def find_user_recent_closed_moments(
        self, user_id: str, *, recent_days: int = 7, limit: int = 20
    ) -> List[MomentInDB]:
        """获取用户近期已兑现或已取消的关键时刻（用于 LLM 去重：避免刚完成/取消就重复创建）。

        closed 定义：
        - status=2（completed / 已兑现）
        - status=3（cancelled / 已取消）
        仅取最近 recent_days 天内的，按 updated_at 降序。
        """
        async with pg.pool.acquire() as conn:
            records = await conn.fetch(
                f"SELECT {_SELECT_COLUMNS_SQL} FROM moments "
                "WHERE user_id = $1 "
                "  AND (status = 2 OR status = 3) "
                "  AND updated_at >= NOW() - make_interval(days => $2) "
                "ORDER BY updated_at DESC LIMIT $3",
                user_id,
                recent_days,
                limit,
            )
        return [self._to_model(record) for record in records]
