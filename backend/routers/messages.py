"""
[INPUT]: 依赖 fastapi 的 APIRouter/HTTPException，依赖 backend.services.message 的 MessageService，依赖 backend.services.llm 的 LLMService，依赖 backend.services.conversation 的 ConversationService，依赖 backend.models.message 的 MessageCreate/MessageResponse
[OUTPUT]: 对外提供核心对话接口 POST /conversations/{conv_id}/chat
[POS]: backend/routers 的核心对话路由，被 main.py 注册，是整个数据流的汇聚点
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List
import logging
from ..services.message import MessageService
from ..services.llm import LLMService
from ..services.conversation import ConversationService
from ..models.message import MessageCreate, MessageResponse
from ..core.exceptions import ResourceNotFoundError, LLMError

logger = logging.getLogger(__name__)

router = APIRouter()


def get_message_service() -> MessageService:
    """依赖注入：获取 MessageService 实例"""
    return MessageService()


def get_llm_service() -> LLMService:
    """依赖注入：获取 LLMService 实例"""
    return LLMService()


def get_conversation_service() -> ConversationService:
    """依赖注入：获取 ConversationService 实例"""
    return ConversationService()


@router.post(
    "/conversations/{conv_id}/chat", response_model=MessageResponse, status_code=200
)
async def chat(
    conv_id: str,
    body: MessageCreate,
    message_service: MessageService = Depends(get_message_service),
    llm_service: LLMService = Depends(get_llm_service),
    conv_service: ConversationService = Depends(get_conversation_service),
):
    """核心对话接口

    数据流：
    1. 保存 user message
    2. 调用 LLMService 生成回复
    3. 保存 assistant message
    4. 更新会话时间戳
    5. 返回 assistant 回复
    """
    try:
        # 1. 保存用户消息
        logger.info(f"收到用户消息: conv_id={conv_id}, length={len(body.content)}")
        user_msg = await message_service.create_message(conv_id, "user", body.content)

        # 2. 调用 LLM 生成回复
        assistant_content = await llm_service.generate_response(conv_id, body.content)

        # 3. 保存助手消息
        assistant_msg = await message_service.create_message(
            conv_id, "assistant", assistant_content
        )

        # 4. 更新会话时间戳
        await conv_service.update_conversation_timestamp(conv_id)

        logger.info(
            f"对话完成: user_msg_id={user_msg.message_id}, assistant_msg_id={assistant_msg.message_id}"
        )

        return assistant_msg

    except ResourceNotFoundError as e:
        # 会话或 Agent 不存在
        raise HTTPException(status_code=404, detail=str(e))

    except LLMError as e:
        # LLM 调用失败
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: {e}")

    except Exception as e:
        # 未知错误
        logger.exception("未知错误", exc_info=e)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/conversations/{conv_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    conv_id: str,
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    message_service: MessageService = Depends(get_message_service),
):
    """获取对话历史"""
    return await message_service.get_conversation_messages(
        conv_id, limit=limit, skip=skip
    )
