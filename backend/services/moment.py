"""
[INPUT]: 依赖 backend.repositories.moment 的 MomentRepository，依赖 backend.repositories.message 的 MessageRepository，依赖 backend.repositories.conversation 的 ConversationRepository，依赖 backend.models.moment 的 MomentCreate/MomentResponse/MomentInDB，依赖 dateparser 的时间解析
[OUTPUT]: 对外提供 MomentService 类，封装关键时刻识别/存储/确认/取消/去重查询，以及 pending moment 的获取与 AI 状态更新
[POS]: backend/services 的关键时刻业务逻辑层，被 Router 和 LLMService 消费
[TIMEZONE]: 所有 datetime 输出统一为 timezone-aware UTC；_ensure_utc 规范化 naive→假定北京时间→转 UTC
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
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
    4. 去重查询（为 LLM 提供完整的 moment 视野）

    去重策略（Good Taste）：
    - 取消"时间窗口 + 文本相似度"的服务端猜测
    - 去重由上游在每次对话时注入的 dedup_moments 驱动：
      LLM 若判断"新识别 moment 与已有 moment 同一件事"，则直接返回 moment=null
    """

    def __init__(self):
        self.moment_repo = MomentRepository()
        self.message_repo = MessageRepository()
        self.conv_repo = ConversationRepository()

    # ================================================================
    #  创建
    # ================================================================

    async def create_moment_from_llm_response(
        self,
        conv_id: str,
        user_id: str,
        moment_data: Dict[str, Any],
        context_messages: List[Dict[str, str]],
    ) -> Optional[MomentResponse]:
        """从LLM返回的moment信息创建关键时刻"""
        if not moment_data or not moment_data.get("is_moment"):
            return None

        event_time = self._parse_time(
            moment_data.get("time"), moment_data.get("event_description")
        )
        if not event_time:
            logger.warning(f"无法解析时间: {moment_data.get('time')}")
            return None

        return await self._create_moment(
            user_id, conv_id, event_time, moment_data, context_messages
        )

    async def create_moment(self, data: MomentCreate) -> MomentResponse:
        """手动创建关键时刻"""
        remind_time = self._calculate_remind_time(
            data.event_time, data.importance, data.type, data.suggested_timing
        )

        now = datetime.now(timezone.utc)
        moment_doc = {
            "moment_id": str(uuid.uuid4()),
            "user_id": data.user_id,
            "conversation_id": data.conversation_id,
            "event_time": data.event_time,
            "remind_time": remind_time,
            "created_at": now,
            "updated_at": now,
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
        return self._to_response(moment_in_db)

    # ================================================================
    #  查询
    # ================================================================

    async def get_user_moments(
        self, user_id: str, status: Optional[str] = None, limit: int = 100, skip: int = 0
    ) -> List[MomentResponse]:
        """获取用户的关键时刻列表"""
        query: Dict[str, Any] = {"user_id": user_id}
        if status:
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
                    pass

        moments = await self.moment_repo.find_many(
            query, limit=limit, skip=skip, sort=[("event_time", 1)]
        )
        return [self._to_response(m) for m in moments]

    async def get_moment(self, moment_id: str) -> Optional[MomentResponse]:
        """获取关键时刻详情"""
        moment = await self.moment_repo.find_one({"moment_id": moment_id})
        if not moment:
            return None
        return self._to_response(moment)

    async def get_latest_pending_moment(self, user_id: str) -> Optional[MomentInDB]:
        """获取当前用户最近一个 pending 关键时刻。

        pending 定义：
        - status=1 且 confirmed=false（confirmed=true 则视为 scheduled）
        """
        return await self.moment_repo.find_latest_user_pending_moment(user_id)

    # ================================================================
    #  去重查询 — 注入 LLM 上下文，防止重复创建 moment
    # ================================================================

    _STATUS_LABELS: Dict[tuple, str] = {
        (1, False): "pending",
        (1, True): "scheduled",
        (2, False): "completed",
        (2, True): "completed",
        (3, False): "cancelled",
        (3, True): "cancelled",
    }

    @classmethod
    def status_label(cls, status: int, confirmed: bool) -> str:
        return cls._STATUS_LABELS.get((status, confirmed), f"unknown({status})")

    async def get_dedup_moments(
        self,
        user_id: str,
        *,
        active_limit: int = 20,
        recent_days: int = 7,
    ) -> List[Dict[str, Any]]:
        """获取用于 LLM 去重的关键时刻列表（合并 active + 近期 closed）。

        分两层：
        1. active: status=1, executed_at IS NULL（没取消 & 没兑现）
        2. recent_closed: 最近 N 天内兑现/取消的（避免刚完成就重建）

        返回精简 Dict（含 status_label 语义标签），caller 可直接 JSON 序列化注入 LLM。
        """
        active = await self.moment_repo.find_user_open_moments(
            user_id, limit=active_limit
        )
        recent_closed = await self.moment_repo.find_user_recent_closed_moments(
            user_id, recent_days=recent_days, limit=20,
        )

        def _to_dedup(m: MomentInDB) -> Dict[str, Any]:
            return {
                "moment_id": m.moment_id,
                "conversation_id": m.conversation_id,
                "type": m.type,
                "event_time": m.event_time.isoformat() if m.event_time else None,
                "remind_time": m.remind_time.isoformat() if m.remind_time else None,
                "event_description": m.event_description,
                "importance": m.importance,
                "suggested_action": m.suggested_action,
                "status_label": self.status_label(m.status, m.confirmed),
                "confirmed": m.confirmed,
            }

        # active 在前（优先级更高），按 moment_id 去重
        seen: set[str] = set()
        result: List[Dict[str, Any]] = []
        for m in [*active, *recent_closed]:
            if m.moment_id in seen:
                continue
            seen.add(m.moment_id)
            result.append(_to_dedup(m))
        return result

    # ================================================================
    #  状态变更
    # ================================================================

    async def confirm_moment(self, moment_id: str) -> MomentResponse:
        """确认关键时刻（进入 scheduled 语义，worker 可领取兑现）。

        前置校验：conversation_id 非空——没有投递目标的 moment 不允许确认，
        从入口消灭不可兑现的调度，而非在 worker 里反复重试失败。
        """
        existing = await self.moment_repo.find_one({"moment_id": moment_id})
        if not existing:
            raise ResourceNotFoundError(f"关键时刻不存在: {moment_id}")
        if not existing.conversation_id:
            raise ValueError(
                f"关键时刻 {moment_id} 缺少 conversation_id，无法确认进入调度态"
            )
        moment = await self.moment_repo.update(
            {"moment_id": moment_id},
            {"confirmed": True, "status": 1, "updated_at": datetime.now(timezone.utc)},
        )
        return self._to_response(moment)  # type: ignore[arg-type]

    async def cancel_moment(self, moment_id: str) -> MomentResponse:
        """取消关键时刻"""
        moment = await self.moment_repo.update(
            {"moment_id": moment_id},
            {"status": 3, "updated_at": datetime.now(timezone.utc)},
        )
        if not moment:
            raise ResourceNotFoundError(f"关键时刻不存在: {moment_id}")
        return self._to_response(moment)

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

        now = datetime.now(timezone.utc)
        if action_norm == "confirm":
            update_doc = {"confirmed": True, "status": 1, "updated_at": now}
        elif action_norm == "cancel":
            update_doc = {"status": 3, "updated_at": now}
        elif action_norm == "complete":
            update_doc = {"status": 2, "executed_at": now, "updated_at": now}
        else:
            return None

        moment = await self.moment_repo.update({"moment_id": moment_id}, update_doc)
        if not moment:
            raise ResourceNotFoundError(f"关键时刻不存在: {moment_id}")
        return self._to_response(moment)

    # ================================================================
    #  内部方法
    # ================================================================

    @staticmethod
    def _to_response(m: MomentInDB) -> MomentResponse:
        """MomentInDB → MomentResponse（消除重复的手动字段映射）"""
        return MomentResponse(
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

    # 北京时区常量（用户交互假定中国用户）
    _BJ_TZ = timezone(timedelta(hours=8))

    @classmethod
    def _ensure_utc(cls, dt: datetime) -> datetime:
        """把任意 datetime 规范化为 timezone-aware UTC。

        - naive datetime → 假定北京时间（UTC+8）→ 转 UTC
        - aware datetime → 直接转 UTC
        """
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=cls._BJ_TZ)
        return dt.astimezone(timezone.utc)

    def _parse_time(self, time_str: Optional[str], event_desc: Optional[str]) -> Optional[datetime]:
        """解析时间表达式（优先 ISO 8601，兜底 dateparser + 中文相对时间）。

        返回值保证：timezone-aware UTC datetime。
        """
        if not time_str:
            time_str = event_desc or ""
        if not time_str:
            return None

        # 1st: ISO 8601（LLM 被要求返回此格式，含时区）
        iso_result = self._try_parse_iso(time_str)
        if iso_result:
            return self._ensure_utc(iso_result)

        # 2nd: dateparser（处理大部分英文 + 部分中文表达）
        now_bj = datetime.now(self._BJ_TZ)
        parsed_time = parse_date(
            time_str,
            settings={
                "RELATIVE_BASE": now_bj.replace(tzinfo=None),
                "PREFER_DATES_FROM": "future",
            },
        )
        if parsed_time:
            if parsed_time.tzinfo is None and parsed_time < now_bj.replace(tzinfo=None):
                parsed_time = parsed_time + timedelta(days=1)
            return self._ensure_utc(parsed_time)

        # 3rd: 中文相对时间手动解析
        result = self._parse_chinese_relative(time_str)
        return self._ensure_utc(result) if result else None

    @staticmethod
    def _try_parse_iso(s: str) -> Optional[datetime]:
        """尝试解析 ISO 8601 格式（含 Z / +HH:MM）。"""
        s = s.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_chinese_relative(time_str: str) -> Optional[datetime]:
        """解析中文相对时间表达式（分钟/小时/天/周/月级别）。

        返回值：naive datetime（北京时间语义），由 caller 统一 _ensure_utc。
        """
        _BJ_TZ = timezone(timedelta(hours=8))
        now = datetime.now(_BJ_TZ).replace(tzinfo=None)  # naive 北京时间

        # 中文数字→阿拉伯数字（十以内简易转换）
        def _cn_num(s: str) -> int:
            cn_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                      "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
            if s.isdigit():
                return int(s)
            return cn_map.get(s, 1)

        # 提取小时部分
        def _extract_hour(s: str, default: int = 9) -> int:
            m = re.search(r"(\d{1,2})[点时:：]", s)
            if m:
                return int(m.group(1))
            if any(k in s for k in ("早上", "早晨", "上午", "晨")):
                return 7
            if any(k in s for k in ("下午",)):
                return 14
            if any(k in s for k in ("傍晚",)):
                return 17
            if any(k in s for k in ("晚上", "晚")):
                return 20
            if any(k in s for k in ("凌晨",)):
                return 4
            return default

        # 星期映射（周一=0 ... 周日=6）
        weekday_map = {
            "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
        }

        # "下周X" / "这周X"
        m = re.search(r"(下下?|这)周([一二三四五六日天])", time_str)
        if m:
            prefix, day_char = m.group(1), m.group(2)
            target_weekday = weekday_map.get(day_char, 0)
            current_weekday = now.weekday()
            if prefix == "这":
                delta = target_weekday - current_weekday
                if delta <= 0:
                    delta += 7
            elif prefix == "下下":
                delta = target_weekday - current_weekday + 14
                if delta <= 14:
                    delta += 7
            else:
                delta = target_weekday - current_weekday + 7
                if delta <= 7:
                    delta += 7
            result = now + timedelta(days=delta)
            return result.replace(hour=_extract_hour(time_str), minute=0, second=0, microsecond=0)

        # "每周X" → 下一个最近的那天
        m = re.search(r"每周([一二三四五六日天])", time_str)
        if m:
            target_weekday = weekday_map.get(m.group(1), 0)
            delta = target_weekday - now.weekday()
            if delta <= 0:
                delta += 7
            result = now + timedelta(days=delta)
            return result.replace(hour=_extract_hour(time_str), minute=0, second=0, microsecond=0)

        # "明天" / "明早"
        if "明天" in time_str or "明早" in time_str:
            result = now + timedelta(days=1)
            return result.replace(hour=_extract_hour(time_str, 8), minute=0, second=0, microsecond=0)

        # "后天"
        if "后天" in time_str:
            result = now + timedelta(days=2)
            return result.replace(hour=_extract_hour(time_str, 9), minute=0, second=0, microsecond=0)

        # "大后天"
        if "大后天" in time_str:
            result = now + timedelta(days=3)
            return result.replace(hour=_extract_hour(time_str, 9), minute=0, second=0, microsecond=0)

        # "N分钟后" / "N分钟之后" / "一分钟后"
        m = re.search(r"(\d+|[一二三四五六七八九十]+)\s*分钟[后之]", time_str)
        if m:
            raw = m.group(1)
            minutes = _cn_num(raw)
            return now + timedelta(minutes=minutes)

        # "半小时后" / "半个小时后"
        if re.search(r"半[个]?小时[后之]", time_str):
            return now + timedelta(minutes=30)

        # "N小时后" / "N个小时后" / "一小时后"
        m = re.search(r"(\d+|[一二三四五六七八九十]+)[个]?\s*小时[后之]", time_str)
        if m:
            raw = m.group(1)
            hours = _cn_num(raw)
            return now + timedelta(hours=hours)

        # "N天后" / "N天以后"
        m = re.search(r"(\d+)\s*天[后以]", time_str)
        if m:
            result = now + timedelta(days=int(m.group(1)))
            return result.replace(hour=_extract_hour(time_str, 9), minute=0, second=0, microsecond=0)

        # "下个月X号"
        m = re.search(r"下个?月(\d{1,2})[号日]?", time_str)
        if m:
            day = int(m.group(1))
            month = now.month + 1
            year = now.year
            if month > 12:
                month = 1
                year += 1
            try:
                result = now.replace(year=year, month=month, day=day, hour=_extract_hour(time_str, 9), minute=0, second=0, microsecond=0)
                return result
            except ValueError:
                pass

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
        remind_time = self._calculate_remind_time(
            event_time,
            moment_data.get("importance", "mid"),
            moment_data.get("type", "event"),
            moment_data.get("suggested_timing"),
        )

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

        now = datetime.now(timezone.utc)
        moment_doc = {
            "moment_id": str(uuid.uuid4()),
            "user_id": user_id,
            "conversation_id": conv_id,
            "event_time": event_time,
            "remind_time": remind_time,
            "created_at": now,
            "updated_at": now,
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
        return self._to_response(moment_in_db)

    def _calculate_remind_time(
        self,
        event_time: datetime,
        importance: str,
        moment_type: str,
        suggested_timing: Optional[str] = None,
    ) -> datetime:
        """计算提醒时间。

        核心设计：suggested_timing 是 LLM 的"何时提醒"判断，优先级最高。
        - on_time: 准时提醒 → remind_time = event_time（"3分钟后提醒我买菜"）
        - before_event: 提前通知 → remind_time = event_time - advance（"明天有面试"）
        - after_event / None: 按类型默认策略

        Good Taste：
        - on_time 直接返回 event_time，不做任何减法，精确兑现用户期望
        - before_event 才走 advance 窗口，且 max(candidate, now) 防止跑到过去
        """
        now = datetime.now(timezone.utc)
        timing = (suggested_timing or "").strip().lower()

        # ---- on_time: 用户明确说"N分钟后提醒我"，event_time 就是 remind_time ----
        if timing == "on_time":
            return event_time

        # ---- before_event: "明天有面试" → 提前通知 ----
        if moment_type == "event" and timing != "after_event":
            if importance == "high":
                advance = timedelta(minutes=30)
            elif importance == "mid":
                advance = timedelta(hours=1)
            else:
                advance = timedelta(hours=2)
            candidate = event_time - advance
            return max(candidate, now)

        if moment_type == "habit":
            return event_time

        # emotion / after_event 类型
        if importance == "high":
            return now + timedelta(minutes=5)
        return event_time + timedelta(days=1)
