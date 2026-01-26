"""
Windows-friendly Uvicorn entrypoint.

Why: asyncpg can be flaky on Windows with the default Proactor event loop.
This entrypoint forces SelectorEventLoopPolicy before importing the app.

Run:
  uv run uvicorn backend.win_entrypoint:app --port 8000
"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]

from .main import app  # noqa: E402

