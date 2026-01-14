"""
[INPUT]: 依赖 fastapi 的 APIRouter/HTTPException，依赖 backend.services.user 的 UserService，依赖 backend.models.user 的 UserCreate/UserResponse
[OUTPUT]: 对外提供用户管理 REST API 路由
[POS]: backend/routers 的用户管理路由，被 main.py 注册
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List
from ..services.user import UserService
from ..models.user import UserCreate, UserResponse
from ..core.exceptions import DuplicateKeyError, ResourceNotFoundError

router = APIRouter()


def get_user_service() -> UserService:
    """依赖注入：获取 UserService 实例"""
    return UserService()


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(data: UserCreate, service: UserService = Depends(get_user_service)):
    """创建用户"""
    try:
        return await service.create_user(data)
    except DuplicateKeyError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=List[UserResponse])
async def list_users(
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
    service: UserService = Depends(get_user_service),
):
    """列出所有用户"""
    return await service.list_users(limit=limit, skip=skip)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, service: UserService = Depends(get_user_service)):
    """获取用户详情"""
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"用户不存在: {user_id}")
    return user


@router.delete("/{user_id}", response_model=dict)
async def delete_user(user_id: str, service: UserService = Depends(get_user_service)):
    """删除用户"""
    try:
        await service.delete_user(user_id)
        return {"success": True}
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
