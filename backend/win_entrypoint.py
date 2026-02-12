"""
[INPUT]: 依赖 asyncio 的 WindowsSelectorEventLoopPolicy，依赖 backend.main 的 app
[OUTPUT]: 对外提供 app 实例（从 backend.main 重新导出）
[POS]: backend 的 Windows 兼容入口点，替代 backend.main:app；强制 SelectorEventLoopPolicy 避免 asyncpg 在 Proactor 事件循环下的问题
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md

Run:
  uv run uvicorn backend.win_entrypoint:app --port 8000
"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]

from .main import app  # noqa: E402

