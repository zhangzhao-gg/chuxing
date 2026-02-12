"""
[INPUT]: 依赖 typer.testing 的 CliRunner，依赖 asyncpg/PostgreSQL（真实落库），依赖 unittest，依赖 backend/messages 的依赖注入点，依赖 cli chat start
[OUTPUT]: 在 backend/tests 下生成 Markdown 报告（CLI 逐条对话 + moment 识别/查重/状态更新 + 数据库快照），并断言：DB moments>=10 且 >=5 个发生状态变更
[POS]: backend/tests 的“真落库”回归：CLI → APIClient → FastAPI → Router → (PostgreSQL moments)
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import asyncio
import subprocess
import threading
import time
import unittest
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from typer.testing import CliRunner

from backend.core.config import settings
from backend.core.postgres import connect_to_postgres, close_postgres_connection, pg
from backend.repositories.moment import MomentRepository
from backend.routers import conversations as conversations_router
from backend.routers import messages as messages_router
from cli.main import app as cli_app


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> str:
    return dt.isoformat() if dt else "null"


@dataclass
class _Message:
    message_id: str
    conversation_id: str
    role: str
    content: str
    token_count: Optional[int]
    created_at: datetime


@dataclass
class _Conversation:
    conversation_id: str
    user_id: str
    agent_id: str
    title: Optional[str]
    created_at: datetime
    updated_at: datetime


class _FakeMessageService:
    """消息仍走内存（Mongo 不参与本测试），用于支撑 /chat 的上下文读取。"""

    def __init__(self) -> None:
        self._by_conv: Dict[str, List[_Message]] = {}

    async def create_message(self, conv_id: str, role: str, content: str) -> _Message:
        msg = _Message(
            message_id=str(uuid.uuid4()),
            conversation_id=conv_id,
            role=role,
            content=content,
            token_count=len(content),
            created_at=_utcnow(),
        )
        self._by_conv.setdefault(conv_id, []).append(msg)
        return msg

    async def get_conversation_messages(
        self, conv_id: str, limit: int = 50, skip: int = 0
    ) -> List[_Message]:
        messages = self._by_conv.get(conv_id, [])
        if skip:
            messages = messages[skip:]
        if limit is not None:
            messages = messages[-limit:]
        return list(messages)


class _FakeConversationService:
    """会话走内存（Mongo 不参与本测试），用于提供 user_id。"""

    def __init__(self) -> None:
        self._by_id: Dict[str, _Conversation] = {}

    async def create_conversation(self, data: Any) -> Dict[str, Any]:
        conv_id = str(uuid.uuid4())
        now = _utcnow()
        conv = _Conversation(
            conversation_id=conv_id,
            user_id=data.user_id,
            agent_id=data.agent_id,
            title=getattr(data, "title", None),
            created_at=now,
            updated_at=now,
        )
        self._by_id[conv_id] = conv
        return {
            "conversation_id": conv.conversation_id,
            "user_id": conv.user_id,
            "agent_id": conv.agent_id,
            "title": conv.title,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
        }

    async def get_conversation(self, conv_id: str) -> Optional[_Conversation]:
        return self._by_id.get(conv_id)

    async def update_conversation_timestamp(self, conv_id: str) -> None:
        conv = self._by_id.get(conv_id)
        if conv:
            conv.updated_at = _utcnow()


class _PostgresMomentService:
    """仅负责 moments（PostgreSQL）相关能力：open_moments + 更新状态 + 创建 moment。"""

    def __init__(
        self,
        repo: MomentRepository,
        events: List[Dict[str, Any]],
        get_turn: Optional[Callable[[], int]] = None,
    ) -> None:
        self.repo = repo
        self.events = events
        self._get_turn = get_turn

    def _turn(self) -> Optional[int]:
        if not self._get_turn:
            return None
        try:
            return int(self._get_turn())
        except Exception:
            return None

    async def get_open_moments(self, user_id: str, limit: int = 200):
        return await self.repo.find_user_open_moments(user_id, limit=limit)

    async def apply_ai_pending_moment_update(self, moment_id: str, action: str):
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        a = (action or "").strip().lower()
        if a == "confirm":
            update_doc = {"confirmed": True, "status": 1, "updated_at": now}
        elif a == "cancel":
            update_doc = {"status": 3, "updated_at": now}
        elif a == "complete":
            update_doc = {"status": 2, "executed_at": now, "updated_at": now}
        else:
            return None

        updated = await self.repo.update({"moment_id": moment_id}, update_doc)
        self.events.append(
            {
                "type": "moment_update",
                "turn": self._turn(),
                "moment_id": moment_id,
                "action": a,
                "status": getattr(updated, "status", None) if updated else None,
                "confirmed": getattr(updated, "confirmed", None) if updated else None,
                "executed_at": _iso(getattr(updated, "executed_at", None)) if updated else None,
            }
        )
        return updated

    def _parse_event_time(self, time_str: Optional[str]) -> datetime:
        # 测试里用 ISO8601 字符串，保证可预测
        if not time_str:
            return _utcnow() + timedelta(days=1)
        try:
            return datetime.fromisoformat(time_str)
        except Exception:
            return _utcnow() + timedelta(days=1)

    async def create_moment_from_llm_response(
        self,
        conv_id: str,
        user_id: str,
        moment_data: Dict[str, Any],
        context_messages: List[Dict[str, str]],
    ):
        if not moment_data or not moment_data.get("is_moment"):
            return None

        event_time = self._parse_event_time(moment_data.get("time"))
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        remind_time = event_time - timedelta(hours=1)
        now = datetime.utcnow().replace(tzinfo=timezone.utc)

        doc = {
            "moment_id": str(uuid.uuid4()),
            "user_id": user_id,
            "conversation_id": conv_id,
            "event_time": event_time,
            "remind_time": remind_time,
            "created_at": now,
            "updated_at": now,
            "type": moment_data.get("type", "event"),
            "event_description": moment_data.get("event_description", ""),
            "emotion": moment_data.get("emotion"),
            "emotion_level": moment_data.get("emotion_level"),
            "importance": moment_data.get("importance", "mid"),
            "suggested_action": moment_data.get("suggested_action", "message"),
            "suggested_timing": moment_data.get("suggested_timing"),
            "first_message": moment_data.get("first_message"),
            "ai_attitude": moment_data.get("ai_attitude"),
            "reason": moment_data.get("reason"),
            "status": 1,
            "confirmed": False,
            "executed_at": None,
            "context_messages": context_messages,
        }
        created = await self.repo.create(doc)
        self.events.append(
            {
                "type": "moment_create",
                "turn": self._turn(),
                "moment_id": created.moment_id,
                "event_time": _iso(created.event_time),
                "desc": created.event_description,
            }
        )
        return created


class _FakeLLMService:
    """单一话题（面试），制造大幅情绪起伏，并产生 >=10 个 moments + >=5 个状态变更。"""

    def __init__(self) -> None:
        self.turn = 0
        self.calls: List[Dict[str, Any]] = []

    def _moment_defs(self) -> List[Dict[str, Any]]:
        # 10 个“同一话题下不同子任务”的关键时刻（time 用 ISO 便于测试解析）
        base_time = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)
        out: List[Dict[str, Any]] = []
        for i in range(1, 11):
            t = base_time + timedelta(hours=i)
            out.append(
                {
                    "is_moment": True,
                    "type": "event",
                    "time": t.isoformat(),
                    "event_description": f"[M{i}] 面试准备子任务{i}（同一场面试）",
                    "importance": "high" if i <= 3 else "mid",
                    "suggested_action": "message",
                    "reason": "同一话题下的不同可执行节点，后续触达有价值",
                }
            )
        return out

    async def generate_response(
        self, conv_id: str, user_message: str, open_moments: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        self.turn += 1
        open_moments = open_moments or []

        # 情绪大起大落
        emotion_level = 5 if (self.turn % 4 in (1, 2)) else 0
        emotion_tags = ["panic", "overwhelmed"] if emotion_level == 5 else ["calm"]

        moment = None
        updates: List[Dict[str, Any]] = []

        # 前 10 轮：每轮创建一个新 moment（与已有 open_moments 不同子任务，不触发去重）
        if self.turn <= 10:
            moment = self._moment_defs()[self.turn - 1]

        # 后续轮次：同一话题反复提起，按 open_moments 去重（moment=null）
        # 同时对 5 个不同 moment 做状态变更（>=5）
        def _find_id(marker: str) -> Optional[str]:
            for m in open_moments:
                if marker in (m.get("event_description") or ""):
                    return m.get("moment_id")
            return None

        if self.turn in (15, 20, 25, 30, 35):
            mapping = {
                15: ("[M1]", "confirm", "用户确认需要提醒这个子任务"),
                20: ("[M2]", "confirm", "用户确认需要提醒这个子任务"),
                25: ("[M3]", "cancel", "用户表示这个子任务不需要了"),
                30: ("[M4]", "complete", "用户表示这个子任务已完成"),
                35: ("[M5]", "complete", "用户表示这个子任务已完成"),
            }
            marker, action, reason = mapping[self.turn]
            mid = _find_id(marker)
            if mid:
                updates.append({"moment_id": mid, "action": action, "reason": reason})

        # 去重规则（靠提示词驱动）：当 open_moments 非空且用户仍在讲同一话题时，不再新建
        if self.turn > 10:
            moment = None

        result = {
            "chat_response": "（CLI真落库模拟）我在。我们继续围绕这场面试，把焦虑拆成可执行的小步骤。",
            "emotion_tags": emotion_tags,
            "emotion_level": emotion_level,
            "moment": moment,
            "moment_updates": updates,
        }
        self.calls.append(
            {
                "turn": self.turn,
                "user_message": user_message,
                "open_moments": open_moments,
                "dedup_decision": "create" if moment else "dedup(moment=null)",
                "result": result,
            }
        )
        return result


class _FakeAPIClient:
    """替换 CLI 的 APIClient：把 sync 方法桥接到内存 FastAPI app（moments 真实落到 PG）。"""

    def __init__(self, base_url: str, app: FastAPI, loop: asyncio.AbstractEventLoop) -> None:
        self.base_url = (base_url or "http://test").rstrip("/")
        self._app = app
        self._loop = loop

    def close(self) -> None:
        return None

    def create_conversation(self, user_id: str, agent_id: str, title: Optional[str] = None) -> Dict[str, Any]:
        async def _do():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self._app), base_url="http://test"
            ) as client:
                payload: Dict[str, Any] = {"user_id": user_id, "agent_id": agent_id}
                if title:
                    payload["title"] = title
                resp = await client.post("/api/conversations", json=payload)
                resp.raise_for_status()
                return resp.json()

        fut = asyncio.run_coroutine_threadsafe(_do(), self._loop)
        return fut.result(timeout=60)

    def send_message(self, conv_id: str, content: str) -> Dict[str, Any]:
        async def _do():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self._app), base_url="http://test"
            ) as client:
                resp = await client.post(f"/api/conversations/{conv_id}/chat", json={"content": content})
                resp.raise_for_status()
                return resp.json()

        fut = asyncio.run_coroutine_threadsafe(_do(), self._loop)
        return fut.result(timeout=120)


class _LoopThread:
    """在单独线程里跑一个长期存活的 asyncio loop（asyncpg pool / ASGI 请求都绑定同一个 loop）。"""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)
        try:
            self.loop.close()
        except Exception:
            pass


def _docker_start_postgres_if_needed(host: str, port: int, db: str) -> bool:
    """尽力启动一个测试用 Postgres 容器；成功返回 True（表示由本测试启动）。"""
    container_name = "chuxing-pg-test"
    try:
        # 如果 docker 不存在或不可用，这里会抛异常
        subprocess.run(["docker", "version"], check=True, capture_output=True, text=True)
    except Exception:
        return False

    # 先尝试复用已存在容器
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, text=True)
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "-e",
            "POSTGRES_PASSWORD=postgres",
            "-e",
            f"POSTGRES_DB={db}",
            "-p",
            f"{port}:5432",
            "postgres:16",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    # 等待就绪（最多 30s）
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            import asyncpg  # local import

            asyncio.run(
                asyncpg.connect(
                    host=host, port=port, user="postgres", password="postgres", database=db
                ).close()
            )
            return True
        except Exception:
            time.sleep(1)
    return True


class TestCliChatRealDbMomentsReport(unittest.TestCase):
    def test_cli_chat_real_db_moments_and_write_md_report(self) -> None:
        # 优先使用用户已有配置（.env / 环境变量）；连不上再尝试启动测试用 docker Postgres
        original_pg = (
            settings.POSTGRES_HOST,
            settings.POSTGRES_PORT,
            settings.POSTGRES_USER,
            settings.POSTGRES_PASSWORD,
            settings.POSTGRES_DB_NAME,
        )
        test_host = "localhost"
        test_port = 55432
        test_db = "llm_chat_test"

        started_container: bool = False
        loop_thread = _LoopThread()
        try:
            # 1) 尝试连接 Postgres；失败则尽力拉起 docker
            try:
                # 先启动 loop，确保 asyncpg pool 绑定稳定的 event loop
                loop_thread.start()
                fut = asyncio.run_coroutine_threadsafe(connect_to_postgres(), loop_thread.loop)
                fut.result(timeout=30)
            except Exception:
                started_container = _docker_start_postgres_if_needed(test_host, test_port, test_db)
                if not started_container:
                    self.skipTest(
                        "PostgreSQL 不可达，且 docker 不可用。请先启动 PostgreSQL，或配置 POSTGRES_* 环境变量。"
                    )
                # 覆盖为测试库（避免污染用户默认库）
                settings.POSTGRES_HOST = test_host
                settings.POSTGRES_PORT = test_port
                settings.POSTGRES_USER = "postgres"
                settings.POSTGRES_PASSWORD = "postgres"
                settings.POSTGRES_DB_NAME = test_db
                fut = asyncio.run_coroutine_threadsafe(connect_to_postgres(), loop_thread.loop)
                fut.result(timeout=30)

            repo = MomentRepository()

            # 清理本次 user_id 的历史数据（保证断言稳定）
            user_id = "user_cli_db_1"
            async def _cleanup():
                async with pg.pool.acquire() as conn:
                    await conn.execute("DELETE FROM moments WHERE user_id = $1", user_id)
            asyncio.run_coroutine_threadsafe(_cleanup(), loop_thread.loop).result(timeout=30)

            events: List[Dict[str, Any]] = []
            fake_llm = _FakeLLMService()
            moment_service = _PostgresMomentService(
                repo=repo, events=events, get_turn=lambda: fake_llm.turn
            )
            fake_msgs = _FakeMessageService()
            fake_convs = _FakeConversationService()

            # 2) 内存 FastAPI app：conversations/messages 走内存服务；moments 走真实 PG
            app = FastAPI()
            app.include_router(conversations_router.router, prefix="/api/conversations", tags=["conversations"])
            app.include_router(messages_router.router, prefix="/api", tags=["messages"])

            app.dependency_overrides[conversations_router.get_conversation_service] = lambda: fake_convs
            app.dependency_overrides[messages_router.get_message_service] = lambda: fake_msgs
            app.dependency_overrides[messages_router.get_conversation_service] = lambda: fake_convs
            app.dependency_overrides[messages_router.get_llm_service] = lambda: fake_llm
            app.dependency_overrides[messages_router.get_moment_service] = lambda: moment_service

            # 3) CLI 逐条输入 55 轮（单一话题 + 情绪大起大落），最后 exit
            agent_id = "agent_cli_db_1"
            user_lines: List[str] = []
            for i in range(1, 56):
                if i % 6 == 1:
                    user_lines.append(f"第{i}轮：我快崩溃了，我怕明天早上8点的面试会失败。")
                elif i % 6 == 2:
                    user_lines.append(f"第{i}轮：我又突然兴奋起来，觉得我一定能拿下这场面试！")
                elif i % 6 == 3:
                    user_lines.append(f"第{i}轮：我现在很愤怒，为什么同一件面试让我这么痛苦？")
                elif i % 6 == 4:
                    user_lines.append(f"第{i}轮：我开始麻木了，但还是绕不开明天的面试。")
                elif i % 6 == 5:
                    user_lines.append(f"第{i}轮：我又很害怕，心跳很快，面试两个字都让我发抖。")
                else:
                    user_lines.append(f"第{i}轮：我还是在想这场面试要怎么准备。")

            cli_input = "\n".join(user_lines + ["exit"]) + "\n"
            runner = CliRunner()

            def _fake_client_factory(api_url: str):
                return _FakeAPIClient(api_url, app=app, loop=loop_thread.loop)

            with patch("cli.commands.chat.APIClient", side_effect=_fake_client_factory):
                result = runner.invoke(
                    cli_app,
                    ["chat", "start", "--user-id", user_id, "--agent-id", agent_id, "--api-url", "http://test"],
                    input=cli_input,
                )
                self.assertEqual(result.exit_code, 0, msg=result.output)

            # 4) 读取 DB：moments 总数 + 状态变更数
            async def _fetch():
                async with pg.pool.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT moment_id, event_description, status, confirmed, executed_at, updated_at "
                        "FROM moments WHERE user_id = $1 ORDER BY created_at ASC",
                        user_id,
                    )
                # 认为“状态变更”包括：confirmed=true 或 status in (2,3)
                changed = [
                    r
                    for r in rows
                    if bool(r["confirmed"]) or int(r["status"]) in (2, 3)
                ]
                return rows, changed

            rows, changed = asyncio.run_coroutine_threadsafe(_fetch(), loop_thread.loop).result(timeout=30)

            # 断言：至少 10 个关键时刻落库
            self.assertGreaterEqual(len(rows), 10, msg=f"rows={len(rows)}")
            # 断言：至少 5 个发生状态变更
            self.assertGreaterEqual(len(changed), 5, msg=f"changed={len(changed)}")

            # 5) 写 Markdown 报告（tests/）
            report_path = Path(__file__).with_name("cli_chat_real_db_moments_report.md")
            md: List[str] = []
            md.append("# CLI 逐条对话 + Moments 真落库 回归报告（55轮）")
            md.append("")
            md.append(f"- 生成时间: `{_utcnow().isoformat()}`")
            md.append(f"- Postgres: `{test_host}:{test_port}/{test_db}`")
            md.append(f"- user_id: `{user_id}`")
            md.append(f"- agent_id: `{agent_id}`")
            md.append("")
            md.append("## CLI 命令")
            md.append("")
            md.append("```")
            md.append(f"uv run cli chat start --user-id {user_id} --agent-id {agent_id} --api-url http://test")
            md.append("```")
            md.append("")
            md.append("## 逐轮记录（对话 / 识别 / 查重）")
            md.append("")
            for i in range(1, 56):
                call = fake_llm.calls[i - 1]
                r = call["result"]
                oms = call.get("open_moments") or []
                turn_events = [ev for ev in events if ev.get("turn") == i]

                md.append(f"### Turn {i:02d}")
                md.append("")
                md.append("#### 用户输入（CLI）")
                md.append(user_lines[i - 1])
                md.append("")
                md.append("#### Router 注入 open_moments")
                md.append(f"- count: **{len(oms)}**")
                for m in oms[:10]:
                    md.append(
                        f"  - moment_id=`{m.get('moment_id')}` status={m.get('status')} confirmed={m.get('confirmed')} desc={m.get('event_description')}"
                    )
                if len(oms) > 10:
                    md.append("  - ...（已截断，仅展示前10条）")
                md.append("")
                md.append("#### 关键时刻识别输出（LLM）")
                md.append(f"- emotion_level: `{r.get('emotion_level')}` tags={r.get('emotion_tags')}")
                md.append(f"- dedup_decision: **{call.get('dedup_decision')}**")
                md.append(f"- moment: `{r.get('moment')}`")
                md.append(f"- moment_updates: `{r.get('moment_updates')}`")
                md.append("")
                md.append("#### 查重规则（描述）")
                md.append("- 若新识别事件与 open_moments 任意一条为同一件事，则必须 `moment=null`；否则可创建新 moment。")
                md.append("")
                md.append("#### Moments 落地事件（PostgreSQL）")
                if turn_events:
                    for ev in turn_events:
                        md.append(f"- {ev}")
                else:
                    md.append("- （无）本轮没有创建/更新关键时刻")
                md.append("")
                md.append("#### Assistant 输出（CLI）")
                md.append(r.get("chat_response", ""))
                md.append("")
                md.append("---")
                md.append("")

            md.append("## 数据库快照（本次 user_id）")
            md.append("")
            md.append(f"- moments_total: **{len(rows)}**（要求 >=10）")
            md.append(f"- moments_changed: **{len(changed)}**（要求 >=5；定义：confirmed=true 或 status in (2,3)）")
            md.append("")
            md.append("| # | moment_id | status | confirmed | executed_at | updated_at | description |")
            md.append("|---:|---|---:|---|---|---|---|")
            for idx, r in enumerate(rows, start=1):
                desc = str(r["event_description"]).replace("|", "\\|")
                md.append(
                    f"| {idx} | `{r['moment_id']}` | {int(r['status'])} | {bool(r['confirmed'])}"
                    f" | {_iso(r['executed_at']) if r['executed_at'] else 'null'}"
                    f" | {_iso(r['updated_at']) if r['updated_at'] else 'null'}"
                    f" | {desc} |"
                )
            md.append("")
            md.append("## CLI 原始输出（stdout）")
            md.append("")
            md.append("```")
            md.append(result.output.rstrip())
            md.append("```")
            md.append("")

            report_path.write_text("\n".join(md), encoding="utf-8")
            self.assertTrue(report_path.exists())
        finally:
            # 关闭 PG 连接池（不强制删除容器；避免误伤用户环境）
            try:
                if loop_thread.loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        close_postgres_connection(), loop_thread.loop
                    ).result(timeout=10)
            except Exception:
                pass
            try:
                loop_thread.stop()
            except Exception:
                pass
            # 尽量恢复原配置，避免影响其它测试
            try:
                (
                    settings.POSTGRES_HOST,
                    settings.POSTGRES_PORT,
                    settings.POSTGRES_USER,
                    settings.POSTGRES_PASSWORD,
                    settings.POSTGRES_DB_NAME,
                ) = original_pg
            except Exception:
                pass

