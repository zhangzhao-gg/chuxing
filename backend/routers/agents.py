"""
[INPUT]: 依赖 fastapi 的 APIRouter/HTTPException，依赖 backend.services.agent 的 AgentService，依赖 backend.models.agent 的 AgentCreate/AgentResponse
[OUTPUT]: 对外提供 Agent 管理 REST API 路由
[POS]: backend/routers 的 Agent 管理路由，被 main.py 注册
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List
from ..services.agent import AgentService
from ..models.agent import AgentCreate, AgentResponse
from ..core.exceptions import ResourceNotFoundError

router = APIRouter()
agent_service = AgentService()


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(data: AgentCreate):
    """创建 Agent"""
    return await agent_service.create_agent(data)


@router.get("", response_model=List[AgentResponse])
async def list_agents(
    limit: int = Query(100, ge=1, le=500), skip: int = Query(0, ge=0)
):
    """列出所有 Agent"""
    return await agent_service.list_agents(limit=limit, skip=skip)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str):
    """获取 Agent 详情"""
    agent = await agent_service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent 不存在: {agent_id}")
    return agent


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: str, data: AgentCreate):
    """更新 Agent 配置"""
    try:
        return await agent_service.update_agent(agent_id, data)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{agent_id}", response_model=dict)
async def delete_agent(agent_id: str):
    """删除 Agent"""
    try:
        await agent_service.delete_agent(agent_id)
        return {"success": True}
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
