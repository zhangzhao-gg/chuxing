"""
[INPUT]: 依赖 fastapi 的 FastAPI，依赖 backend.core.database 与 backend.core.postgres 的连接生命周期函数，依赖 backend.routers 的所有路由模块
[OUTPUT]: 对外提供 FastAPI 应用实例 app，供 uvicorn 启动
[POS]: backend 的应用入口，被 uvicorn 直接调用
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging
from .core.database import connect_to_mongo, close_mongo_connection
from .core.postgres import connect_to_postgres, close_postgres_connection
from .routers import users, agents, conversations, messages, moments

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理

    启动时：连接 MongoDB/PostgreSQL + 创建索引
    关闭时：关闭连接池
    """
    logger.info("应用启动中...")
    await connect_to_mongo()
    await connect_to_postgres()
    logger.info("应用启动完成")

    yield

    logger.info("应用关闭中...")
    await close_postgres_connection()
    await close_mongo_connection()
    logger.info("应用关闭完成")


# 创建 FastAPI 应用
app = FastAPI(
    title="LLM Chat System",
    description="生产级 LLM 交互系统 - FastAPI + MongoDB + OpenAI",
    version="1.0.0",
    lifespan=lifespan,
)


# 注册路由
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(conversations.router, prefix="/api/conversations", tags=["conversations"])
app.include_router(messages.router, prefix="/api", tags=["messages"])
app.include_router(moments.router, prefix="/api/moments", tags=["moments"])


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "service": "llm-chat-system"}


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "LLM Chat System API",
        "docs": "/docs",
        "health": "/health",
    }
