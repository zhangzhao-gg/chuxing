"""
[INPUT]: 依赖 openai 的 AsyncOpenAI，依赖 backend.core.config 的 settings
[OUTPUT]: 对外提供 ContextCompressionService 类，封装上下文压缩逻辑
[POS]: backend/services 的上下文压缩服务，被 LLMService 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from typing import List, Dict, Any
import logging
from openai import AsyncOpenAI
from ..core.config import settings
from ..core.exceptions import LLMError

logger = logging.getLogger(__name__)


class ContextCompressionService:
    """上下文压缩服务

    职责：
    - 将长对话历史压缩为简洁摘要
    - 使用 LLM 提取关键信息
    - 保留重要上下文，减少 token 消耗

    压缩策略：
    - 当消息数超过阈值时触发
    - 保留最近的消息（用户最关心的）
    - 将较早的消息压缩为摘要
    """

    def __init__(self):
        # 初始化 OpenAI 客户端
        openai_params = {"api_key": settings.OPENAI_API_KEY}
        if settings.OPENAI_BASE_URL:
            openai_params["base_url"] = settings.OPENAI_BASE_URL

        self.openai_client = AsyncOpenAI(**openai_params)
        self.compression_model = "gpt-4o-mini"  # 使用快速模型进行压缩

    async def compress_messages(
        self, messages: List[Dict[str, Any]], target_count: int
    ) -> str:
        """压缩消息列表为摘要

        Args:
            messages: 需要压缩的消息列表
            target_count: 目标保留的消息数（用于计算压缩比例）

        Returns:
            压缩后的摘要文本
        """
        if not messages:
            return ""

        # 构建压缩提示词
        conversation_text = self._format_messages_for_compression(messages)

        compression_prompt = f"""请将以下对话历史压缩为简洁的摘要，保留关键信息和上下文。

要求：
1. 提取对话中的关键事实、决策和结论
2. 保留重要的背景信息和用户偏好
3. 使用第三人称客观描述
4. 摘要长度控制在原对话的 1/3 左右
5. 使用中文输出

对话历史：
{conversation_text}

请输出压缩摘要："""

        try:
            logger.info(f"开始压缩上下文: 原始消息数={len(messages)}")

            response = await self.openai_client.chat.completions.create(
                model=self.compression_model,
                messages=[
                    {"role": "system", "content": "你是一个专业的对话摘要助手，擅长提取关键信息。"},
                    {"role": "user", "content": compression_prompt}
                ],
                temperature=0.3,  # 较低温度，保证摘要稳定
                max_tokens=500,
            )

            summary = response.choices[0].message.content.strip()
            logger.info(f"上下文压缩完成: 摘要长度={len(summary)}")

            return summary

        except Exception as e:
            logger.error(f"上下文压缩失败: {e}")
            # 压缩失败时返回简单的消息计数摘要
            return f"[对话摘要: 共 {len(messages)} 条消息，包含用户和助手的多轮对话]"

    def _format_messages_for_compression(self, messages: List[Dict[str, Any]]) -> str:
        """格式化消息列表为文本，用于压缩"""
        formatted = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if role == "user":
                formatted.append(f"用户: {content}")
            elif role == "assistant":
                formatted.append(f"助手: {content}")
            elif role == "system":
                formatted.append(f"系统: {content}")

        return "\n".join(formatted)

    def should_compress(self, message_count: int) -> bool:
        """判断是否需要压缩

        Args:
            message_count: 当前消息数量

        Returns:
            是否需要压缩
        """
        if not settings.ENABLE_CONTEXT_COMPRESSION:
            return False

        return message_count > settings.COMPRESSION_THRESHOLD
