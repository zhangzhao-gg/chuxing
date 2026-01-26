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
            f"VALUES ({placeholders}) RETURNING *"
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
                "SELECT * FROM moments WHERE moment_id = $1", moment_id
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
            "SELECT * FROM moments"
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
            f"WHERE moment_id = ${len(values)} RETURNING *"
        )

        async with pg.pool.acquire() as conn:
            record = await conn.fetchrow(sql, *values)
        return self._to_model(record) if record else None

    async def find_similar_moments(
        self,
        user_id: str,
        event_time: datetime,
        conversation_id: Optional[str] = None,
        time_window_hours: int = 2,
    ) -> List[MomentInDB]:
        """查找相似的关键时刻（用于去重）"""
        start_time = event_time.replace(
            hour=max(0, event_time.hour - time_window_hours),
            minute=0,
            second=0,
            microsecond=0,
        )
        end_time = event_time.replace(
            hour=min(23, event_time.hour + time_window_hours),
            minute=59,
            second=59,
            microsecond=999999,
        )

        conditions = [
            "user_id = $1",
            "event_time >= $2",
            "event_time <= $3",
            "status <> 'cancelled'",
        ]
        values: List[Any] = [user_id, start_time, end_time]

        if conversation_id:
            values.append(conversation_id)
            conditions.append(f"conversation_id = ${len(values)}")

        sql = (
            "SELECT * FROM moments WHERE "
            + " AND ".join(conditions)
            + " ORDER BY event_time DESC LIMIT 10"
        )

        async with pg.pool.acquire() as conn:
            records = await conn.fetch(sql, *values)
        return [self._to_model(record) for record in records]

    async def find_pending_moments(
        self, remind_time_before: datetime, limit: int = 100
    ) -> List[MomentInDB]:
        """查找待触达的关键时刻（用于调度）"""
        async with pg.pool.acquire() as conn:
            records = await conn.fetch(
                "SELECT * FROM moments "
                "WHERE remind_time <= $1 AND status = 'scheduled' "
                "ORDER BY remind_time ASC LIMIT $2",
                remind_time_before,
                limit,
            )
        return [self._to_model(record) for record in records]
