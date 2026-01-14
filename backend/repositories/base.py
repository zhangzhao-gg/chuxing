"""
[INPUT]: 依赖 motor.motor_asyncio 的 AsyncIOMotorCollection，依赖 typing 的泛型
[OUTPUT]: 对外提供 BaseRepository 抽象类，定义通用 CRUD 方法
[POS]: backend/repositories 的基类，被所有具体 Repository 继承
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from typing import Generic, TypeVar, Optional, List, Dict, Any
from abc import ABC, abstractmethod
from motor.motor_asyncio import AsyncIOMotorCollection

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """通用 CRUD 仓储基类

    设计哲学：
    - 封装 MongoDB 操作细节
    - 提供类型安全的查询接口
    - 通过 _to_model 抽象方法实现文档到模型的转换
    - 返回 Optional[T] 让上层处理 None 情况，代码自证正确
    """

    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def create(self, document: Dict[str, Any]) -> T:
        """插入文档"""
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return self._to_model(document)

    async def find_one(self, query: Dict[str, Any]) -> Optional[T]:
        """查询单个文档，返回 None 表示不存在"""
        doc = await self.collection.find_one(query)
        return self._to_model(doc) if doc else None

    async def find_many(
        self,
        query: Dict[str, Any],
        limit: int = 100,
        skip: int = 0,
        sort: Optional[List[tuple]] = None,
    ) -> List[T]:
        """查询多个文档"""
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        docs = await cursor.to_list(length=limit)
        return [self._to_model(doc) for doc in docs]

    async def update(self, query: Dict[str, Any], update: Dict[str, Any]) -> Optional[T]:
        """更新文档，返回更新后的文档"""
        doc = await self.collection.find_one_and_update(
            query, {"$set": update}, return_document=True
        )
        return self._to_model(doc) if doc else None

    async def delete(self, query: Dict[str, Any]) -> bool:
        """删除文档，返回是否成功"""
        result = await self.collection.delete_one(query)
        return result.deleted_count > 0

    async def count(self, query: Dict[str, Any]) -> int:
        """统计文档数量"""
        return await self.collection.count_documents(query)

    @abstractmethod
    def _to_model(self, doc: Dict[str, Any]) -> T:
        """将 MongoDB 文档转换为 Pydantic 模型

        子类必须实现此方法，定义转换逻辑
        """
        pass
