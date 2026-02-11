"""
[INPUT]: 依赖 backend.repositories.moment 的 MomentRepository，依赖 backend.repositories.message 的 MessageRepository，依赖 backend.repositories.conversation 的 ConversationRepository，依赖 backend.models.moment 的 MomentCreate/MomentResponse/MomentInDB，依赖 dateparser 的时间解析
[OUTPUT]: 对外提供 MomentService 类，封装关键时刻识别/存储/确认/取消，以及 pending moment 的获取与 AI 状态更新
[POS]: backend/services 的关键时刻业务逻辑层，被 Router 和 LLMService 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import uuid
import re
from dateparser import parse as parse_date

from ..repositories.moment import MomentRepository
from ..repositories.message import MessageRepository
from ..repositories.conversation import ConversationRepository
from ..models.moment import MomentCreate, MomentResponse, MomentInDB
from ..core.exceptions import ResourceNotFoundError

logger = logging.getLogger(__name__)


class MomentService:
    """关键时刻识别与存储服务

    职责：
    1. 从LLM返回的moment信息中创建关键时刻
    2. 时间解析（自然语言 → datetime）
    3. 关键时刻存储

    去重策略（Good Taste）：
    - 取消“时间窗口 + 文本相似度”的服务端猜测
    - 去重由上游在每次对话时注入的 open_moments 驱动：
      LLM 若判断“新识别 moment 与 open_moments 中任意一条同一件事”，则直接返回 moment=null，避免重复创建
    """

    def __init__(self):
        self.moment_repo = MomentRepository()
        self.message_repo = MessageRepository()
        self.conv_repo = ConversationRepository()

    async def create_moment_from_llm_response(
        self,
        conv_id: str,
        user_id: str,
        moment_data: Dict[str, Any],
        context_messages: List[Dict[str, str]],
    ) -> Optional[MomentResponse]:
        """从LLM返回的moment信息创建关键时刻

        Args:
            conv_id: 会话ID
            user_id: 用户ID
            moment_data: LLM返回的moment字段内容
            context_messages: 相关对话上下文

        Returns:
            MomentResponse 如果成功创建，否则返回 None
        """
        if not moment_data or not moment_data.get("is_moment"):
            return None

        # 1. 解析时间
        event_time = self._parse_time(
            moment_data.get("time"), moment_data.get("event_description")
        )
        if not event_time:
            logger.warning(f"无法解析时间: {moment_data.get('time')}")
            return None

        # 2. 创建新的关键时刻
        # 备注：去重由 LLM 基于 open_moments 决策完成；服务端不再做相似度猜测
        return await self._create_moment(
            user_id, conv_id, event_time, moment_data, context_messages
        )

    def _parse_time(self, time_str: Optional[str], event_desc: Optional[str]) -> Optional[datetime]:
        """解析自然语言时间表达式

        使用 dateparser 解析时间，如果失败则尝试从事件描述中提取
        """
        if not time_str:
            time_str = event_desc or ""

        if not time_str:
            return None

        # 使用 dateparser 解析
        # dateparser的settings参数接受字典
        parsed_time = parse_date(
            time_str,
            settings={
                "RELATIVE_BASE": datetime.now(),
                "PREFER_DATES_FROM": "future",
            },
        )

        if parsed_time:
            # 确保是未来时间
            if parsed_time < datetime.now():
                # 如果是今天的时间但已过期，可能是明天
                parsed_time = parsed_time + timedelta(days=1)
            return parsed_time

        # 如果解析失败，尝试简单的关键词匹配
        now = datetime.now()
        if "明天" in time_str or "明早" in time_str:
            parsed_time = now + timedelta(days=1)
            # 尝试提取时间
            hour_match = re.search(r"(\d{1,2})[点时]", time_str)
            if hour_match:
                parsed_time = parsed_time.replace(hour=int(hour_match.group(1)))
            return parsed_time

        if "后天" in time_str:
            parsed_time = now + timedelta(days=2)
            hour_match = re.search(r"(\d{1,2})[点时]", time_str)
            if hour_match:
                parsed_time = parsed_time.replace(hour=int(hour_match.group(1)))
            return parsed_time

        return None

    async def _create_moment(
        self,
        user_id: str,
        conv_id: str,
        event_time: datetime,
        moment_data: Dict[str, Any],
        context_messages: List[Dict[str, str]],
    ) -> MomentResponse:
        """创建新的关键时刻"""
        # 计算提醒时间（根据重要程度和事件类型）
        remind_time = self._calculate_remind_time(
            event_time, moment_data.get("importance", "mid"), moment_data.get("type", "event")
        )

        # 关键时刻确认逻辑（由 AI 决策，Good Taste：用一个布尔值消灭分支爆炸）
        # - needs_user_confirm=true  → pending（confirmed=false，等待用户确认）
        # - needs_user_confirm=false → scheduled（confirmed=true，直接进入调度队列）
        needs_user_confirm_raw = moment_data.get("needs_user_confirm", True)
        if isinstance(needs_user_confirm_raw, bool):
            needs_user_confirm = needs_user_confirm_raw
        elif isinstance(needs_user_confirm_raw, str):
            v = needs_user_confirm_raw.strip().lower()
            if v in ("false", "0", "no", "n", "否", "不需要"):
                needs_user_confirm = False
            elif v in ("true", "1", "yes", "y", "是", "需要"):
                needs_user_confirm = True
            else:
                needs_user_confirm = True
        else:
            needs_user_confirm = True

        moment_doc = {
            "moment_id": str(uuid.uuid4()),
            "user_id": user_id,
            "conversation_id": conv_id,
            "event_time": event_time,
            "remind_time": remind_time,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "type": moment_data.get("type", "event"),
            "event_description": moment_data.get("event_description", ""),
            "emotion": moment_data.get("emotion"),
            "emotion_level": moment_data.get("emotion_level"),
            "importance": moment_data.get("importance", "mid"),
            "suggested_action": moment_data.get("suggested_action", "message"),
            "suggested_timing": moment_data.get("suggested_timing"),
            "first_message": moment_data.get("first_message"),
            "ai_attitude": moment_data.get("ai_attitude"),
            "reason": moment_data.get("reason"),
            "status": 1,
            "confirmed": (not needs_user_confirm),
            "executed_at": None,
            "context_messages": context_messages,
        }

        moment_in_db = await self.moment_repo.create(moment_doc)

        logger.info(f"创建关键时刻: moment_id={moment_in_db.moment_id}")

        return MomentResponse(
            moment_id=moment_in_db.moment_id,
            user_id=moment_in_db.user_id,
            conversation_id=moment_in_db.conversation_id,
            event_time=moment_in_db.event_time,
            remind_time=moment_in_db.remind_time,
            created_at=moment_in_db.created_at,
            updated_at=moment_in_db.updated_at,
            type=moment_in_db.type,
            event_description=moment_in_db.event_description,
            emotion=moment_in_db.emotion,
            emotion_level=moment_in_db.emotion_level,
            importance=moment_in_db.importance,
            suggested_action=moment_in_db.suggested_action,
            suggested_timing=moment_in_db.suggested_timing,
            first_message=moment_in_db.first_message,
            ai_attitude=moment_in_db.ai_attitude,
            reason=moment_in_db.reason,
            status=moment_in_db.status,
            confirmed=moment_in_db.confirmed,
            executed_at=moment_in_db.executed_at,
            context_messages=moment_in_db.context_messages,
        )

    def _calculate_remind_time(
        self, event_time: datetime, importance: str, moment_type: str
    ) -> datetime:
        """计算提醒时间

        根据PRD中的调度策略：
        - event + high: 事件前30分钟
        - event + mid: 事件前1小时
        - event + low: 事件前2小时
        - habit: 每天固定时间（这里简化为事件时间）
        - emotion + high: 立即（这里设为事件时间）
        - emotion + mid: 次日回访（这里设为事件时间+1天）
        """
        if moment_type == "event":
            if importance == "high":
                return event_time - timedelta(minutes=30)
            elif importance == "mid":
                return event_time - timedelta(hours=1)
            else:  # low
                return event_time - timedelta(hours=2)
        elif moment_type == "habit":
            return event_time  # 简化处理
        else:  # emotion
            if importance == "high":
                return datetime.utcnow() + timedelta(minutes=5)  # 5分钟后
            else:
                return event_time + timedelta(days=1)  # 次日

    async def create_moment(self, data: MomentCreate) -> MomentResponse:
        """手动创建关键时刻"""
        remind_time = self._calculate_remind_time(
            data.event_time, data.importance, data.type
        )

        moment_doc = {
            "moment_id": str(uuid.uuid4()),
            "user_id": data.user_id,
            "conversation_id": data.conversation_id,
            "event_time": data.event_time,
            "remind_time": remind_time,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "type": data.type,
            "event_description": data.event_description,
            "emotion": data.emotion,
            "emotion_level": data.emotion_level,
            "importance": data.importance,
            "suggested_action": data.suggested_action,
            "suggested_timing": data.suggested_timing,
            "first_message": data.first_message,
            "ai_attitude": data.ai_attitude,
            "reason": data.reason,
            "status": 1,
            "confirmed": False,
            "executed_at": None,
            "context_messages": None,
        }

        moment_in_db = await self.moment_repo.create(moment_doc)

        return MomentResponse(
            moment_id=moment_in_db.moment_id,
            user_id=moment_in_db.user_id,
            conversation_id=moment_in_db.conversation_id,
            event_time=moment_in_db.event_time,
            remind_time=moment_in_db.remind_time,
            created_at=moment_in_db.created_at,
            updated_at=moment_in_db.updated_at,
            type=moment_in_db.type,
            event_description=moment_in_db.event_description,
            emotion=moment_in_db.emotion,
            emotion_level=moment_in_db.emotion_level,
            importance=moment_in_db.importance,
            suggested_action=moment_in_db.suggested_action,
            suggested_timing=moment_in_db.suggested_timing,
            first_message=moment_in_db.first_message,
            ai_attitude=moment_in_db.ai_attitude,
            reason=moment_in_db.reason,
            status=moment_in_db.status,
            confirmed=moment_in_db.confirmed,
            executed_at=moment_in_db.executed_at,
            context_messages=moment_in_db.context_messages,
        )

    async def get_user_moments(
        self, user_id: str, status: Optional[str] = None, limit: int = 100, skip: int = 0
    ) -> List[MomentResponse]:
        """获取用户的关键时刻列表"""
        query = {"user_id": user_id}
        if status:
            # 兼容输入：pending/scheduled/completed/cancelled 或 "1"/"2"/"3"
            if status in ("pending", "scheduled", "completed", "cancelled"):
                if status == "pending":
                    query["status"] = 1
                    query["confirmed"] = False
                elif status == "scheduled":
                    query["status"] = 1
                    query["confirmed"] = True
                elif status == "completed":
                    query["status"] = 2
                else:
                    query["status"] = 3
            else:
                try:
                    query["status"] = int(status)
                except Exception:
                    # 非法 status 直接忽略过滤，让调用方能拿到全量数据定位问题
                    pass

        moments = await self.moment_repo.find_many(
            query, limit=limit, skip=skip, sort=[("event_time", 1)]
        )

        return [
            MomentResponse(
                moment_id=m.moment_id,
                user_id=m.user_id,
                conversation_id=m.conversation_id,
                event_time=m.event_time,
                remind_time=m.remind_time,
                created_at=m.created_at,
                updated_at=m.updated_at,
                type=m.type,
                event_description=m.event_description,
                emotion=m.emotion,
                emotion_level=m.emotion_level,
                importance=m.importance,
                suggested_action=m.suggested_action,
            suggested_timing=m.suggested_timing,
                first_message=m.first_message,
                ai_attitude=m.ai_attitude,
            reason=m.reason,
                status=m.status,
                confirmed=m.confirmed,
                executed_at=m.executed_at,
                context_messages=m.context_messages,
            )
            for m in moments
        ]

    async def get_moment(self, moment_id: str) -> Optional[MomentResponse]:
        """获取关键时刻详情"""
        moment = await self.moment_repo.find_one({"moment_id": moment_id})
        if not moment:
            return None

        return MomentResponse(
            moment_id=moment.moment_id,
            user_id=moment.user_id,
            conversation_id=moment.conversation_id,
            event_time=moment.event_time,
            remind_time=moment.remind_time,
            created_at=moment.created_at,
            updated_at=moment.updated_at,
            type=moment.type,
            event_description=moment.event_description,
            emotion=moment.emotion,
            emotion_level=moment.emotion_level,
            importance=moment.importance,
            suggested_action=moment.suggested_action,
            suggested_timing=moment.suggested_timing,
            first_message=moment.first_message,
            ai_attitude=moment.ai_attitude,
            reason=moment.reason,
            status=moment.status,
            confirmed=moment.confirmed,
            executed_at=moment.executed_at,
            context_messages=moment.context_messages,
        )

    async def confirm_moment(self, moment_id: str) -> MomentResponse:
        """确认关键时刻"""
        moment = await self.moment_repo.update(
            {"moment_id": moment_id},
            {"confirmed": True, "status": 1, "updated_at": datetime.utcnow()},
        )
        if not moment:
            raise ResourceNotFoundError(f"关键时刻不存在: {moment_id}")

        return MomentResponse(
            moment_id=moment.moment_id,
            user_id=moment.user_id,
            conversation_id=moment.conversation_id,
            event_time=moment.event_time,
            remind_time=moment.remind_time,
            created_at=moment.created_at,
            updated_at=moment.updated_at,
            type=moment.type,
            event_description=moment.event_description,
            emotion=moment.emotion,
            emotion_level=moment.emotion_level,
            importance=moment.importance,
            suggested_action=moment.suggested_action,
            suggested_timing=moment.suggested_timing,
            first_message=moment.first_message,
            ai_attitude=moment.ai_attitude,
            reason=moment.reason,
            status=moment.status,
            confirmed=moment.confirmed,
            executed_at=moment.executed_at,
            context_messages=moment.context_messages,
        )

    async def cancel_moment(self, moment_id: str) -> MomentResponse:
        """取消关键时刻"""
        moment = await self.moment_repo.update(
            {"moment_id": moment_id},
            {"status": 3, "updated_at": datetime.utcnow()},
        )
        if not moment:
            raise ResourceNotFoundError(f"关键时刻不存在: {moment_id}")

        return MomentResponse(
            moment_id=moment.moment_id,
            user_id=moment.user_id,
            conversation_id=moment.conversation_id,
            event_time=moment.event_time,
            remind_time=moment.remind_time,
            created_at=moment.created_at,
            updated_at=moment.updated_at,
            type=moment.type,
            event_description=moment.event_description,
            emotion=moment.emotion,
            emotion_level=moment.emotion_level,
            importance=moment.importance,
            suggested_action=moment.suggested_action,
            suggested_timing=moment.suggested_timing,
            first_message=moment.first_message,
            ai_attitude=moment.ai_attitude,
            reason=moment.reason,
            status=moment.status,
            confirmed=moment.confirmed,
            executed_at=moment.executed_at,
            context_messages=moment.context_messages,
        )

    async def get_latest_pending_moment(self, user_id: str) -> Optional[MomentInDB]:
        """获取当前用户最近一个 pending 关键时刻。

        pending 定义：
        - status=1 且 confirmed=false（confirmed=true 则视为 scheduled）
        """
        return await self.moment_repo.find_latest_user_pending_moment(user_id)

    async def get_open_moments(self, user_id: str, limit: int = 200) -> List[MomentInDB]:
        """获取当前用户所有“未完成且未取消”的关键时刻（open moments）。

        open 定义：
        - status != 2（completed）
        - status != 3（cancelled）
        """
        return await self.moment_repo.find_user_open_moments(user_id, limit=limit)

    async def apply_ai_pending_moment_update(
        self, moment_id: str, action: str
    ) -> Optional[MomentResponse]:
        """让 AI 驱动 pending moment 的状态迁移。

        允许的 action:
        - none: 不更新
        - confirm: confirmed=true（进入 scheduled 语义）
        - cancel: status=3
        - complete: status=2 + executed_at=now
        """
        action_norm = (action or "").strip().lower()
        if action_norm in ("", "none", "no", "null"):
            return None

        now = datetime.utcnow()
        if action_norm == "confirm":
            update_doc = {"confirmed": True, "status": 1, "updated_at": now}
        elif action_norm == "cancel":
            update_doc = {"status": 3, "updated_at": now}
        elif action_norm == "complete":
            update_doc = {"status": 2, "executed_at": now, "updated_at": now}
        else:
            # 未知 action：直接忽略，让上游日志定位提示词问题
            return None

        moment = await self.moment_repo.update({"moment_id": moment_id}, update_doc)
        if not moment:
            raise ResourceNotFoundError(f"关键时刻不存在: {moment_id}")

        return MomentResponse(
            moment_id=moment.moment_id,
            user_id=moment.user_id,
            conversation_id=moment.conversation_id,
            event_time=moment.event_time,
            remind_time=moment.remind_time,
            created_at=moment.created_at,
            updated_at=moment.updated_at,
            type=moment.type,
            event_description=moment.event_description,
            emotion=moment.emotion,
            emotion_level=moment.emotion_level,
            importance=moment.importance,
            suggested_action=moment.suggested_action,
            suggested_timing=moment.suggested_timing,
            first_message=moment.first_message,
            ai_attitude=moment.ai_attitude,
            reason=moment.reason,
            status=moment.status,
            confirmed=moment.confirmed,
            executed_at=moment.executed_at,
            context_messages=moment.context_messages,
        )
