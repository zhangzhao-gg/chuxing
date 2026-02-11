"""
[INPUT]: 依赖 fastapi 的 APIRouter/HTTPException，依赖 backend.services.message 的 MessageService，依赖 backend.services.llm 的 LLMService，依赖 backend.services.conversation 的 ConversationService，依赖 backend.services.moment 的 MomentService，依赖 backend.models.message 的 MessageCreate/MessageResponse
[OUTPUT]: 对外提供核心对话接口 POST /conversations/{conv_id}/chat
[POS]: backend/routers 的核心对话路由，被 main.py 注册，是整个数据流的汇聚点
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List
import logging
import json
from ..services.message import MessageService
from ..services.llm import LLMService
from ..services.conversation import ConversationService
from ..services.moment import MomentService
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


def get_moment_service() -> MomentService:
    """依赖注入：获取 MomentService 实例"""
    return MomentService()


@router.post(
    "/conversations/{conv_id}/chat", response_model=MessageResponse, status_code=200
)
async def chat(
    conv_id: str,
    body: MessageCreate,
    message_service: MessageService = Depends(get_message_service),
    llm_service: LLMService = Depends(get_llm_service),
    conv_service: ConversationService = Depends(get_conversation_service),
    moment_service: MomentService = Depends(get_moment_service),
):
    """核心对话接口

    数据流：
    1. 保存 user message
    2. 查询当前用户所有 open moments（未完成且未取消）并注入给 LLM
    3. 调用 LLMService 生成回复（同时进行情绪识别、关键时刻判断、open moments 状态更新）
    4. 保存 assistant message
    5. 更新会话时间戳
    6. 如果识别到关键时刻，创建关键时刻记录
    7. 返回 assistant 回复
    """
    try:
        # 1. 保存用户消息
        logger.info(f"收到用户消息: conv_id={conv_id}, length={len(body.content)}")
        user_msg = await message_service.create_message(conv_id, "user", body.content)

        # 2. 获取会话信息（用于 user_id 以及 open moments 注入）
        conversation = await conv_service.get_conversation(conv_id)
        if not conversation:
            raise ResourceNotFoundError(f"会话不存在: {conv_id}")

        # 3. 获取“当前用户所有未完成且未取消的关键时刻（open moments）”，并携带给 LLM
        open_moments = await moment_service.get_open_moments(conversation.user_id)
        open_moments_payload = []
        for m in open_moments:
            # 只带必要字段，避免上下文膨胀；时间统一 ISO8601 字符串，保证可 JSON 序列化
            open_moments_payload.append(
                {
                    "moment_id": m.moment_id,
                    "type": m.type,
                    "event_time": m.event_time.isoformat(),
                    "remind_time": m.remind_time.isoformat(),
                    "event_description": m.event_description,
                    "importance": m.importance,
                    "suggested_action": m.suggested_action,
                    "status": m.status,
                    "confirmed": m.confirmed,
                }
            )

        # 4. 调用 LLM 生成回复（同时进行情绪识别和关键时刻判断 + open moments 状态更新）
        llm_response = await llm_service.generate_response(
            conv_id, body.content, open_moments=open_moments_payload
        )
        assistant_content = llm_response["chat_response"]
        moment_data = llm_response.get("moment")
        moment_updates = llm_response.get("moment_updates") or []

        # 4.1 让 AI 驱动 open moments 的状态变更（失败不影响对话流程）
        if open_moments_payload and isinstance(moment_updates, list) and moment_updates:
            allowed_ids = {m["moment_id"] for m in open_moments_payload if "moment_id" in m}
            for upd in moment_updates:
                if not isinstance(upd, dict):
                    continue
                moment_id = upd.get("moment_id")
                action = (upd.get("action") or "").strip().lower()
                if not moment_id or moment_id not in allowed_ids:
                    continue
                try:
                    updated = await moment_service.apply_ai_pending_moment_update(
                        moment_id, action
                    )
                    if updated:
                        logger.info(
                            "AI 更新 moment: moment_id=%s action=%s reason=%s",
                            moment_id,
                            action,
                            upd.get("reason"),
                        )
                except Exception as e:
                    logger.warning(f"AI 更新 moment 失败: {e}", exc_info=True)

        # 5. 保存助手消息
        assistant_msg = await message_service.create_message(
            conv_id, "assistant", assistant_content
        )

        # 6. 更新会话时间戳
        await conv_service.update_conversation_timestamp(conv_id)

        # 7. 如果识别到关键时刻，创建关键时刻记录
        if moment_data:
            try:
                # 获取最近10轮对话上下文
                recent_messages = await message_service.get_conversation_messages(
                    conv_id, limit=10
                )
                context_messages = [
                    {"role": msg.role, "content": msg.content} for msg in recent_messages
                ]

                # 用户收到 AI 消息时，打印 AI 的关键信息（用于调试/观测）
                # - reason/event_description 来自 LLM 的 moment 字段
                # - context_messages 来自当前会话最近10轮消息（与入库 moment 一致）
                logger.info(
                    "AI moment context: conv_id=%s event_description=%s reason=%s context_messages=%s",
                    conv_id,
                    moment_data.get("event_description"),
                    moment_data.get("reason"),
                    json.dumps(context_messages, ensure_ascii=False)[:2000],
                )

                moment = await moment_service.create_moment_from_llm_response(
                    conv_id,
                    conversation.user_id,
                    moment_data,
                    context_messages,
                )
                if moment:
                    logger.info(
                        f"创建关键时刻: moment_id={moment.moment_id}, event_time={moment.event_time}"
                    )
            except Exception as e:
                # 关键时刻创建失败不影响对话流程
                logger.warning(f"关键时刻创建失败: {e}", exc_info=True)
        else:
            # 没有识别到 moment 时，也输出同样字段，便于统一检索日志
            logger.info(
                "AI moment context: conv_id=%s event_description=%s reason=%s context_messages=%s",
                conv_id,
                None,
                None,
                None,
            )

        logger.info(
            f"对话完成: user_msg_id={user_msg.message_id}, assistant_msg_id={assistant_msg.message_id}, emotion_level={llm_response.get('emotion_level', 0)}"
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
