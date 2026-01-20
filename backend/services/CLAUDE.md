# backend/services/
> L2 | 父级: backend/CLAUDE.md

---

## 成员清单

**user.py**: UserService，用户 CRUD 业务逻辑，create_user 校验用户名唯一性（DuplicateKeyError），delete_user 抛出 ResourceNotFoundError

**agent.py**: AgentService，Agent CRUD 业务逻辑，create_agent 生成 uuid，update_agent 支持配置更新，校验存在性

**conversation.py**: ConversationService，会话管理业务逻辑，create_conversation 校验 user 和 agent 存在性，update_conversation_timestamp 在新消息时更新时间戳

**message.py**: MessageService，消息持久化与查询，create_message 自动计算 token_count（tiktoken），get_conversation_messages 按时间升序返回

**llm.py**: **核心** LLMService，LLM 调用与上下文编排，generate_response 核心方法，_build_context 拼接上下文，_trim_context 滑动窗口裁剪，支持上下文压缩

**context_compression.py**: ContextCompressionService，上下文压缩服务，compress_context 方法，将早期消息压缩为摘要，节省 65% token 消耗

---

## 核心模块：llm.py

### 职责
1. 加载历史消息（最近 50 条）
2. 检查是否需要压缩上下文（可选功能）
3. 构建上下文：[system_prompt] + history + [user_message]
4. 裁剪上下文（滑动窗口策略，保留 system + 最新 user）
5. 调用 OpenAI API
6. 返回 assistant 回复

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
当对话历史超过阈值时，自动压缩早期消息为摘要，节省 token 消耗。

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
[LAST_UPDATED]: 2026-01-20
