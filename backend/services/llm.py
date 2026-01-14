"""
[INPUT]: 依赖 backend.services.message 的 MessageService，依赖 backend.repositories.agent 的 AgentRepository，依赖 backend.repositories.conversation 的 ConversationRepository，依赖 openai 的 AsyncOpenAI，依赖 backend.core.config 的 settings
[OUTPUT]: 对外提供 LLMService 类，封装 LLM 调用与上下文管理逻辑
[POS]: backend/services 的 LLM 核心逻辑层，被 Router 的 /chat 接口消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from typing import List, Dict, Any
import logging
from openai import AsyncOpenAI
from .message import MessageService
from ..repositories.agent import AgentRepository
from ..repositories.conversation import ConversationRepository
from ..core.config import settings
from ..core.exceptions import ResourceNotFoundError, LLMError, OpenAIAPIError

logger = logging.getLogger(__name__)


class LLMService:
    """LLM 调用与上下文编排

    这是整个系统的核心价值所在。

    职责：
    1. 加载历史消息
    2. 构建上下文：[system_prompt] + history + [user_message]
    3. 裁剪上下文（滑动窗口策略，保留 system + 最新 user）
    4. 调用 OpenAI API
    5. 返回 assistant 回复

    设计哲学：
    - 上下文是计算结果，而非存储状态
    - 消除特殊情况：空历史、首条消息、token 超限用统一逻辑处理
    - 系统提示词始终存在，保证 agent 人格稳定
    """

    def __init__(self):
        self.message_service = MessageService()
        self.agent_repo = AgentRepository()
        self.conv_repo = ConversationRepository()

        # 初始化 OpenAI 客户端
        openai_params = {"api_key": settings.OPENAI_API_KEY}
        if settings.OPENAI_BASE_URL:
            openai_params["base_url"] = settings.OPENAI_BASE_URL

        self.openai_client = AsyncOpenAI(**openai_params)
        self.max_context_tokens = settings.MAX_CONTEXT_TOKENS

    async def generate_response(self, conv_id: str, user_message: str) -> str:
        """核心方法：生成 LLM 回复

        流程：
        1. 获取 conversation → agent_id
        2. 获取 agent → system_prompt + model
        3. 加载历史消息（最近 50 条）
        4. 构建上下文 = [system] + history + [user]
        5. 裁剪上下文（保留 system + 最新 user，删除中间历史）
        6. 调用 OpenAI API
        7. 返回 assistant 内容
        """
        # 1. 获取会话信息
        conversation = await self.conv_repo.find_one({"conversation_id": conv_id})
        if not conversation:
            raise ResourceNotFoundError(f"会话不存在: {conv_id}")

        # 2. 获取 Agent 配置
        agent = await self.agent_repo.find_one({"agent_id": conversation.agent_id})
        if not agent:
            raise ResourceNotFoundError(f"Agent 不存在: {conversation.agent_id}")

        # 3. 加载历史消息（不包括当前 user_message）
        history = await self.message_service.get_conversation_messages(
            conv_id, limit=50
        )

        # 4. 构建上下文
        messages = self._build_context(
            agent.system_prompt,
            [{"role": msg.role, "content": msg.content} for msg in history],
            user_message,
        )

        # 5. 裁剪上下文
        messages = self._trim_context(messages, self.max_context_tokens)

        # 6. 调用 OpenAI
        try:
            logger.info(
                f"调用 OpenAI: model={agent.model}, messages_count={len(messages)}"
            )
            response = await self.openai_client.chat.completions.create(
                model=agent.model,
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
            )
            assistant_content = response.choices[0].message.content
            logger.info(f"OpenAI 响应成功: length={len(assistant_content)}")
            return assistant_content

        except Exception as e:
            logger.error(f"OpenAI 调用失败: {e}")
            raise OpenAIAPIError(f"OpenAI 调用失败: {e}")

    def _build_context(
        self, system_prompt: str, history: List[Dict[str, Any]], user_msg: str
    ) -> List[Dict[str, str]]:
        """拼接上下文

        消除特殊情况：
        - history 为空时：[system] + [] + [user] 自然成立
        - 首条消息：系统提示词始终存在
        """
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_msg})
        return messages

    def _trim_context(
        self, messages: List[Dict[str, str]], max_tokens: int
    ) -> List[Dict[str, str]]:
        """裁剪上下文（滑动窗口策略）

        策略：
        1. 计算总 token 数
        2. 如果超出限制：
           - 保留 messages[0]（system prompt，固定前置）
           - 保留 messages[-1]（最新 user 消息，必须响应）
           - 从 messages[1:-1]（历史对话）中间开始删除最早的消息
        3. 循环删除直到满足 token 限制

        Good Taste 体现：
        - 统一处理各种情况，无需特殊分支
        - 保留 agent 人格（system prompt）
        - 保留用户意图（最新消息）
        """
        total_tokens = self.message_service._count_tokens(messages)

        if total_tokens <= max_tokens:
            return messages

        # 只有 system + user 的情况，直接返回
        if len(messages) <= 2:
            return messages

        # 保留首尾，删除中间历史
        system_msg = messages[0]
        user_msg = messages[-1]
        history = messages[1:-1]

        # 从历史消息开头开始删除（保留最近对话）
        while history and total_tokens > max_tokens:
            removed = history.pop(0)
            total_tokens -= self.message_service._count_tokens([removed])

        final_messages = [system_msg] + history + [user_msg]
        logger.info(
            f"上下文裁剪: 原始 {len(messages)} 条 → 裁剪后 {len(final_messages)} 条"
        )
        return final_messages
