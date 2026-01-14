"""
[INPUT]: 依赖 fastapi 的 APIRouter/HTTPException，依赖 backend.services.conversation 的 ConversationService，依赖 backend.models.conversation 的 ConversationCreate/ConversationResponse
[OUTPUT]: 对外提供会话管理 REST API 路由
[POS]: backend/routers 的会话管理路由，被 main.py 注册
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from ..services.conversation import ConversationService
from ..models.conversation import ConversationCreate, ConversationResponse
from ..core.exceptions import ResourceNotFoundError

router = APIRouter()
conv_service = ConversationService()


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(data: ConversationCreate):
    """创建会话"""
    try:
        return await conv_service.create_conversation(data)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("", response_model=List[ConversationResponse])
async def list_conversations(
    user_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
):
    """列出会话（可按 user_id 过滤）"""
    if user_id:
        return await conv_service.list_user_conversations(
            user_id, limit=limit, skip=skip
        )
    # 未来可扩展为列出所有会话
    return []


@router.get("/{conv_id}", response_model=ConversationResponse)
async def get_conversation(conv_id: str):
    """获取会话详情"""
    conv = await conv_service.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail=f"会话不存在: {conv_id}")
    return conv


@router.delete("/{conv_id}", response_model=dict)
async def delete_conversation(conv_id: str):
    """删除会话"""
    try:
        await conv_service.delete_conversation(conv_id)
        return {"success": True}
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
