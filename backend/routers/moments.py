"""
[INPUT]: 依赖 fastapi 的 APIRouter/HTTPException，依赖 backend.services.moment 的 MomentService，依赖 backend.models.moment 的 MomentCreate/MomentResponse
[OUTPUT]: 对外提供关键时刻管理 REST API 路由
[POS]: backend/routers 的关键时刻管理路由，被 main.py 注册
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
from ..services.moment import MomentService
from ..models.moment import MomentCreate, MomentResponse
from ..core.exceptions import ResourceNotFoundError

router = APIRouter()


def get_moment_service() -> MomentService:
    """依赖注入：获取 MomentService 实例"""
    return MomentService()


@router.post("", response_model=MomentResponse, status_code=201)
async def create_moment(
    data: MomentCreate, service: MomentService = Depends(get_moment_service)
):
    """手动创建关键时刻"""
    try:
        return await service.create_moment(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=List[MomentResponse])
async def list_moments(
    user_id: str = Query(..., description="用户 ID"),
    status: Optional[str] = Query(None, description="状态过滤（pending/scheduled/completed/cancelled）"),
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
    service: MomentService = Depends(get_moment_service),
):
    """获取用户的关键时刻列表"""
    return await service.get_user_moments(user_id, status=status, limit=limit, skip=skip)


@router.get("/{moment_id}", response_model=MomentResponse)
async def get_moment(
    moment_id: str, service: MomentService = Depends(get_moment_service)
):
    """获取关键时刻详情"""
    moment = await service.get_moment(moment_id)
    if not moment:
        raise HTTPException(status_code=404, detail=f"关键时刻不存在: {moment_id}")
    return moment


@router.post("/{moment_id}/confirm", response_model=MomentResponse)
async def confirm_moment(
    moment_id: str, service: MomentService = Depends(get_moment_service)
):
    """确认关键时刻（将其状态改为scheduled）"""
    try:
        return await service.confirm_moment(moment_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{moment_id}/cancel", response_model=MomentResponse)
async def cancel_moment(
    moment_id: str, service: MomentService = Depends(get_moment_service)
):
    """取消关键时刻"""
    try:
        return await service.cancel_moment(moment_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
