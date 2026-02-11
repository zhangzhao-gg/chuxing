"""
[INPUT]: 依赖 backend.services.message 的 MessageService，依赖 backend.repositories.agent 的 AgentRepository，依赖 backend.repositories.conversation 的 ConversationRepository，依赖 openai 的 AsyncOpenAI，依赖 backend.core.config 的 settings
[OUTPUT]: 对外提供 LLMService 类，封装 LLM 调用与上下文管理逻辑（支持携带 open_moments，并返回 moment_updates）
[POS]: backend/services 的 LLM 核心逻辑层，被 Router 的 /chat 接口消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from typing import List, Dict, Any, Optional
import logging
import json
import re
from openai import AsyncOpenAI
from .message import MessageService
from .context_compression import ContextCompressionService
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
        self.compression_service = ContextCompressionService()
        self.agent_repo = AgentRepository()
        self.conv_repo = ConversationRepository()

        # 初始化 OpenAI 客户端
        openai_params = {"api_key": settings.OPENAI_API_KEY}
        if settings.OPENAI_BASE_URL:
            openai_params["base_url"] = settings.OPENAI_BASE_URL

        self.openai_client = AsyncOpenAI(**openai_params)
        self.max_context_tokens = settings.MAX_CONTEXT_TOKENS

    async def generate_response(
        self,
        conv_id: str,
        user_message: str,
        open_moments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """核心方法：生成 LLM 回复，同时进行情绪识别和关键时刻判断

        流程：
        1. 获取 conversation → agent_id
        2. 获取 agent → system_prompt + model
        3. 加载历史消息（最近 50 条）
        4. 检查是否需要压缩上下文
        5. 构建上下文 = [system(包含 open_moments)] + (compressed_summary or history) + [user]
        6. 裁剪上下文（保留 system + 最新 user，删除中间历史）
        7. 调用 OpenAI API（要求返回JSON格式，包含对话回复、情绪、关键时刻）
        8. 解析返回的JSON，提取对话回复、情绪信息、关键时刻信息

        Returns:
            {
                "chat_response": str,  # 对话回复
                "emotion_tags": List[str],  # 情绪标签
                "emotion_level": int,  # 情绪强度 0-5
                "moment": Optional[Dict],  # 关键时刻信息（如果有）
                "moment_updates": List[Dict],  # AI 对 open_moments 的状态更新指令（可能为空数组）
            }
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

        # 4. 检查是否需要压缩上下文
        history_messages = [{"role": msg.role, "content": msg.content} for msg in history]

        if self.compression_service.should_compress(len(history_messages)):
            logger.info(f"触发上下文压缩: 当前消息数={len(history_messages)}, 阈值={settings.COMPRESSION_THRESHOLD}")
            history_messages = await self._compress_context(history_messages)

        # 5. 构建上下文（增强system prompt，要求返回结构化信息 + 携带 open_moments）
        open_moments_json = (
            json.dumps(open_moments, ensure_ascii=False, separators=(",", ":"))
            if open_moments is not None
            else "[]"
        )
        enhanced_system_prompt = self._build_enhanced_system_prompt(
            agent.system_prompt, open_moments_json
        )
        messages = self._build_context(
            enhanced_system_prompt,
            history_messages,
            user_message,
        )

        # 6. 裁剪上下文
        messages = self._trim_context(messages, self.max_context_tokens)

        # 7. 调用 OpenAI（要求返回JSON格式）
        try:
            logger.info(
                f"调用 OpenAI: model={agent.model}, messages_count={len(messages)}"
            )
            
            create_params = {
                "model": agent.model,
                "messages": messages,
                # 降低温度：结构化输出优先，减少“非JSON”概率
                "temperature": 0.3,
                "max_tokens": 2048,  # 增加token限制，因为需要返回更多信息
            }
            
            # 优先尝试强制 JSON；若兼容服务不支持 response_format，再降级重试
            response = await self._call_with_optional_json_response_format(create_params)
            response_content = response.choices[0].message.content
            logger.info(f"OpenAI 响应成功: length={len(response_content)}")

            # 8. 解析 JSON；若失败，自动重试一次（temperature=0.0）避免偶发纯文本
            parsed = self._try_parse_llm_json(response_content)
            if parsed is None:
                logger.warning(
                    "LLM返回JSON解析失败，触发一次重试（强制只输出JSON）。前200字符: %s",
                    response_content[:200],
                )
                retry_params = dict(create_params)
                retry_params["temperature"] = 0.0
                retry_response = await self._call_with_optional_json_response_format(
                    retry_params
                )
                retry_content = retry_response.choices[0].message.content
                parsed = self._try_parse_llm_json(retry_content)
                if parsed is None:
                    logger.warning(
                        "LLM重试后仍无法解析JSON，降级返回纯文本。前200字符: %s",
                        retry_content[:200],
                    )
                    return {
                        "chat_response": retry_content,
                        "emotion_tags": [],
                        "emotion_level": 0,
                        "moment": None,
                        "moment_updates": [],
                    }

            return self._normalize_llm_result(parsed)

        except Exception as e:
            logger.error(f"OpenAI 调用失败: {e}")
            raise OpenAIAPIError(f"OpenAI 调用失败: {e}")

    def _build_enhanced_system_prompt(self, original_prompt: str, open_moments_json: str) -> str:
        """增强系统提示词，要求LLM返回结构化信息（并携带 open_moments 供状态更新/去重）。"""
        return f"""{original_prompt}

你将额外收到“当前用户所有未完成且未取消的关键时刻（open_moments）”，格式为 JSON 数组（可能为空）：
open_moments = {open_moments_json}

你需要结合用户最新消息，判断它是否对应 open_moments 中的某一个关键时刻，并在返回中给出 moment_updates（可为空数组）。

去重规则（必须遵守）：
- 如果你识别到的关键时刻与 open_moments 中任意一条描述的是同一件事（同一事件/同一情绪/同一习惯），则 **不要** 再创建新的 moment，必须返回 moment=null。
- 只有当用户明确提出了一个“不同于 open_moments 的新关键时刻”时，才返回 moment 对象用于创建新记录。

重要：请以JSON格式返回你的回复，必须包含以下字段：
1. chat_response: 你的对话回复（自然、有温度的文本）
2. emotion_tags: 用户当前的情绪标签列表（如：["nervous", "anxious"] 或 ["happy", "excited"]）
3. emotion_level: 情绪强度（0-5的整数，0=无情绪，5=强烈情绪）
4. moment: 关键时刻信息（如果用户提到了未来事件、重要情绪或习惯，则填写此字段；否则为null）
5. moment_updates: 对 open_moments 的状态更新指令数组（如果没有需要更新的关键时刻，则必须返回空数组 []）

moment字段格式（如果存在）：
{{
    "is_moment": true,
    "type": "event/habit/emotion",
    "time": "自然语言时间描述（如：明天早上8点）",
    "event_description": "事件描述",
    "emotion": "情绪标签",
    "emotion_level": 0-5或null,
    "importance": "low/mid/high",
    "suggested_action": "call/message",
    "suggested_timing": "before_event/after_event/on_time",
    "ai_attitude": "AI的态度（鼓励/安慰/祝贺等）",
    "first_message": "触达时的第一句话（50字以内）",
    "reason": "判断理由",
    "needs_user_confirm": true/false
}}

needs_user_confirm 规则（必须遵守）：
- true 表示：你认为需要在对话中让用户明确确认“是否要我提醒/是否要我在某时间触达”，后端会把该 moment 作为 pending（confirmed=false）。
- false 表示：你认为无需用户确认也能直接调度（例如用户明确说“提醒我/到时候别忘了/请你在X点提醒”等），后端会直接将该 moment 视为 scheduled（confirmed=true）。

moment_updates 字段格式（数组，可能为空）：
[
  {{
    "moment_id": "要更新的关键时刻ID（必须来自 open_moments）",
    "action": "confirm/cancel/complete",
    "reason": "为什么要这样更新（可选，用于审计/调试）"
  }}
]

请严格按照JSON格式返回，不要包含任何markdown代码块标记。"""

    def _coerce_bool(self, value: Any, default: bool) -> bool:
        """把 LLM 的松散布尔值规范化为 bool。"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("true", "1", "yes", "y", "是", "需要"):
                return True
            if v in ("false", "0", "no", "n", "否", "不需要"):
                return False
        return default

    async def _call_with_optional_json_response_format(self, create_params: Dict[str, Any]):
        """调用 OpenAI/兼容服务：优先携带 response_format=json_object；不支持则自动降级。"""
        params_with_json = dict(create_params)
        params_with_json["response_format"] = {"type": "json_object"}
        try:
            return await self.openai_client.chat.completions.create(**params_with_json)
        except Exception as e:
            # 兼容：部分 OpenAI 兼容服务不支持 response_format
            logger.info("response_format=json_object 不支持，降级重试: %s", e)
            params_plain = dict(create_params)
            params_plain.pop("response_format", None)
            return await self.openai_client.chat.completions.create(**params_plain)

    def _try_parse_llm_json(self, response_content: str) -> Optional[Dict[str, Any]]:
        """尽力从 LLM 输出中提取 JSON 对象；失败返回 None。"""
        try:
            json_match = re.search(r"\{[\s\S]*\}", response_content)
            if json_match:
                return json.loads(json_match.group())
            return json.loads(response_content)
        except Exception:
            return None

    def _normalize_llm_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """规范化 LLM 的结构化输出，保证下游字段类型稳定。"""
        chat_response = result.get("chat_response", "")
        emotion_tags = result.get("emotion_tags", [])
        emotion_level = result.get("emotion_level", 0)
        moment = result.get("moment")
        moment_updates = result.get("moment_updates")

        if moment and isinstance(moment, dict) and moment.get("is_moment"):
            # needs_user_confirm：缺省按“需要确认”处理，避免误调度
            moment["needs_user_confirm"] = self._coerce_bool(
                moment.get("needs_user_confirm"), default=True
            )
        else:
            moment = None

        # moment_updates：允许为空数组；只保留我们认可的字段形状，避免下游被“意外结构”污染
        normalized_updates: List[Dict[str, Any]] = []
        if isinstance(moment_updates, list):
            for item in moment_updates:
                if not isinstance(item, dict):
                    continue
                moment_id = item.get("moment_id")
                action = (item.get("action") or "").strip().lower()
                if not moment_id or not isinstance(moment_id, str):
                    continue
                if action not in ("confirm", "cancel", "complete"):
                    # 不接受 none/空/未知动作；上游以“没有该更新项”表达 none
                    continue
                normalized_updates.append(
                    {
                        "moment_id": moment_id,
                        "action": action,
                        "reason": item.get("reason"),
                    }
                )

        return {
            "chat_response": chat_response
            if isinstance(chat_response, str)
            else str(chat_response),
            "emotion_tags": emotion_tags if isinstance(emotion_tags, list) else [],
            "emotion_level": emotion_level if isinstance(emotion_level, int) else 0,
            "moment": moment,
            "moment_updates": normalized_updates,
        }

    async def _compress_context(
        self, history_messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """压缩上下文

        策略：
        1. 保留最近的 COMPRESSION_TARGET 条消息
        2. 将更早的消息压缩为摘要
        3. 摘要作为 system 角色的消息插入

        Args:
            history_messages: 历史消息列表

        Returns:
            压缩后的消息列表
        """
        target_count = settings.COMPRESSION_TARGET

        if len(history_messages) <= target_count:
            return history_messages

        # 分割消息：需要压缩的 + 保留的
        messages_to_compress = history_messages[:-target_count]
        messages_to_keep = history_messages[-target_count:]

        # 调用压缩服务生成摘要
        summary = await self.compression_service.compress_messages(
            messages_to_compress, target_count
        )

        # 构建压缩后的上下文
        compressed_context = [
            {
                "role": "system",
                "content": f"[历史对话摘要]\n{summary}\n[以下是最近的对话]"
            }
        ]
        compressed_context.extend(messages_to_keep)

        logger.info(
            f"上下文压缩完成: {len(history_messages)} 条 → 摘要 + {len(messages_to_keep)} 条"
        )

        return compressed_context

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
