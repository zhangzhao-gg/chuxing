# backend/services/
> L2 | 父级: backend/CLAUDE.md

---

## 成员清单

**user.py**: UserService，用户 CRUD 业务逻辑，create_user 校验用户名唯一性（DuplicateKeyError），delete_user 抛出 ResourceNotFoundError

**agent.py**: AgentService，Agent CRUD 业务逻辑，create_agent 生成 uuid，update_agent 支持配置更新，校验存在性

**conversation.py**: ConversationService，会话管理业务逻辑，create_conversation 校验 user 和 agent 存在性，update_conversation_timestamp 在新消息时更新时间戳

**message.py**: MessageService，消息持久化与查询，create_message 自动计算 token_count（tiktoken），get_conversation_messages 按时间升序返回

**llm.py**: **核心** LLMService，LLM 调用与上下文编排，generate_response 核心方法，_build_context 拼接上下文，_trim_context 滑动窗口裁剪

---

## 核心模块：llm.py

### 职责
1. 加载历史消息（最近 50 条）
2. 构建上下文：[system_prompt] + history + [user_message]
3. 裁剪上下文（滑动窗口策略，保留 system + 最新 user）
4. 调用 OpenAI API
5. 返回 assistant 回复

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

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
