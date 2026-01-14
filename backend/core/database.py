"""
[INPUT]: 依赖 motor.motor_asyncio 的 AsyncIOMotorClient，依赖 backend.core.config 的 settings
[OUTPUT]: 对外提供 db 全局对象、connect_to_mongo/close_mongo_connection 生命周期函数
[POS]: backend/core 的数据库连接管理器，被 main.py 的 lifespan 和所有 Repository 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from .config import settings
import logging

logger = logging.getLogger(__name__)


# ==================== 数据库连接管理 ====================
class Database:
    """MongoDB 连接池封装"""

    client: AsyncIOMotorClient = None
    db: AsyncIOMotorDatabase = None


# 全局数据库实例
db = Database()


async def connect_to_mongo() -> None:
    """应用启动时调用：建立连接池 + 创建索引"""
    logger.info(f"正在连接 MongoDB: {settings.MONGODB_URL}")

    db.client = AsyncIOMotorClient(settings.MONGODB_URL)
    db.db = db.client[settings.MONGODB_DB_NAME]

    # 测试连接
    try:
        await db.client.admin.command("ping")
        logger.info("MongoDB 连接成功")
    except Exception as e:
        logger.error(f"MongoDB 连接失败: {e}")
        raise

    # 创建索引
    await create_indexes()


async def close_mongo_connection() -> None:
    """应用关闭时调用：关闭连接池"""
    logger.info("正在关闭 MongoDB 连接")
    if db.client:
        db.client.close()
        logger.info("MongoDB 连接已关闭")


async def create_indexes() -> None:
    """创建所有集合的索引（幂等操作）"""
    logger.info("开始创建数据库索引")

    # === users 集合索引 ===
    await db.db.users.create_index("username", unique=True)
    await db.db.users.create_index("created_at")
    await db.db.users.create_index("user_id", unique=True)
    logger.info("users 集合索引创建完成")

    # === agents 集合索引 ===
    await db.db.agents.create_index("agent_id", unique=True)
    await db.db.agents.create_index("name")
    await db.db.agents.create_index("created_at")
    logger.info("agents 集合索引创建完成")

    # === conversations 集合索引 ===
    await db.db.conversations.create_index("conversation_id", unique=True)
    await db.db.conversations.create_index([("user_id", 1), ("created_at", -1)])
    await db.db.conversations.create_index("agent_id")
    logger.info("conversations 集合索引创建完成")

    # === messages 集合索引 ===
    await db.db.messages.create_index("message_id", unique=True)
    await db.db.messages.create_index([("conversation_id", 1), ("created_at", 1)])
    logger.info("messages 集合索引创建完成")

    logger.info("所有索引创建完成")
