# backend/services/
> L2 | 父级: backend/CLAUDE.md

---

## AGENTS 索引（统一入口）

- [agents.md](../../agents.md) - Agent 协作约束与角色清单

---

## 成员清单

**user.py**: UserService，用户 CRUD 业务逻辑，create_user 校验用户名唯一性（DuplicateKeyError），delete_user 抛出 ResourceNotFoundError

**agent.py**: AgentService，Agent CRUD 业务逻辑，create_agent 生成 uuid，update_agent 支持配置更新，校验存在性

**conversation.py**: ConversationService，会话管理业务逻辑，create_conversation 校验 user 和 agent 存在性，update_conversation_timestamp 在新消息时更新时间戳

**message.py**: MessageService，消息持久化与查询，create_message 自动计算 token_count（tiktoken），get_conversation_messages 按时间升序返回

**llm.py**: **核心** LLMService，LLM 调用与上下文编排；增强 system prompt **注入当前时间（北京时间+UTC）**，让 LLM 能精确推算相对时间；要求 LLM 返回 JSON（chat_response/emotion_tags/emotion_level/moment/moment_updates）；方法参数名 `open_moments`，提示词注入时使用 `existing_moments` 术语（面向 LLM 更直觉）；系统提示词解释 status_label 语义（pending/scheduled/completed/cancelled），moment_updates 仅可针对 pending/scheduled，去重检查覆盖 ALL 包括 completed/cancelled；moment.time 要求 ISO 8601 **带时区**格式；新 moment 需输出 needs_user_confirm（是否需要用户确认）；**修改规则**：用户要求改时间/推迟/提前时，LLM 必须同时 cancel 旧 moment（via moment_updates）+ 创建新 moment（via moment 字段），去重规则对修改场景豁免

**context_compression.py**: ContextCompressionService，上下文压缩服务，compress_messages 通过 OpenAI 生成摘要（失败降级为简单摘要），受 ENABLE_CONTEXT_COMPRESSION 控制

**moment.py**: MomentService，关键时刻创建/手动创建/查询/确认/取消；confirm_moment 前置校验 `conversation_id` 非空（无投递目标拒绝确认）；**所有 datetime 统一为 timezone-aware UTC**（`_ensure_utc` 规范化：naive→假定北京时间→转 UTC，aware→直接转 UTC）；时间解析三层策略（ISO 8601 优先 → dateparser → 中文相对时间手动解析：**N分钟后/N小时后/半小时后**/下周X/这周X/每周X/明天/后天/N天后/下个月X号）；`_calculate_remind_time` **以 suggested_timing 为决策入口**（`on_time` → remind_time=event_time 精确兑现，`before_event` → advance 减法+max(now)保护）；服务端不做相似度去重，去重由对话时注入的 get_dedup_moments() 驱动（LLM 重复则 moment=null）；get_dedup_moments() 合并活跃 moments（status=1 且 executed_at IS NULL）与近期关闭（7 天内 completed/cancelled），返回 List[Dict] 含 status_label；创建新 moment 时 `confirmed` 由 LLM 的 needs_user_confirm 决策（不需要确认→直接进入调度态）

**notification.py**: NotificationService，兑现发送服务（当前实现：站内 system 消息），被 `backend/moment_worker.py` 消费；未来扩展短信/Push/电话时保持 Service 边界不变

---

## 核心模块：llm.py

### 职责
1. 加载历史消息（最近 50 条）
2. 检查是否需要压缩上下文（可选功能）
3. 构建上下文：[system_prompt] + history + [user_message]
4. 裁剪上下文（滑动窗口策略，保留 system + 最新 user）
5. 调用 OpenAI API（优先使用 response_format=json_object，取决于模型名）
6. 解析 JSON 响应：chat_response/emotion_tags/emotion_level/moment/moment_updates

### 裁剪策略
- 计算总 token 数（tiktoken cl100k_base 编码器）
- 如果超出 MAX_CONTEXT_TOKENS（默认 4096）：
  - 保留 messages[0]（system prompt，固定前置）
  - 保留 messages[-1]（最新 user 消息，必须响应）
  - 从 messages[1:-1]（历史对话）开头开始删除，直到满足 token 限制

### Good Taste 体现
- 消除特殊情况：空历史、首条消息、token 超限用统一逻辑处理
- 系统提示词始终存在，保证 agent 人格稳定
- 代码自证正确：`[system] + [] + [user]` 自然成立

---

## 上下文压缩：context_compression.py

### 职责
当对话历史超过阈值时（COMPRESSION_THRESHOLD），自动压缩早期消息为摘要，节省 token 消耗。

### 压缩策略
1. 检查消息数是否超过 COMPRESSION_THRESHOLD（默认 30）
2. 保留最近 COMPRESSION_TARGET 条消息（默认 10）
3. 将早期消息通过 LLM 压缩为简洁摘要
4. 用压缩后的摘要替换早期消息

### 配置参数
- `ENABLE_CONTEXT_COMPRESSION`: 是否启用（默认 false）
- `COMPRESSION_THRESHOLD`: 触发阈值（默认 30）
- `COMPRESSION_TARGET`: 保留消息数（默认 10）

### 效果
节省约 65% 的 token 消耗，同时保留对话的核心信息。

---

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
[LAST_UPDATED]: 2026-02-12
