# backend/models/
> L2 | 父级: backend/CLAUDE.md

---

## AGENTS 索引（统一入口）

- [agents.md](../../agents.md) - Agent 协作约束与角色清单

---

## 成员清单

**user.py**: UserCreate/UserResponse/UserInDB，用户数据模型，username 字段校验（1-50字符）

**agent.py**: AgentCreate/AgentResponse/AgentInDB，Agent 数据模型，system_prompt 必填，model 默认 gpt-4o-mini

**conversation.py**: ConversationCreate/ConversationResponse/ConversationInDB，会话数据模型，title 可选（最长200字符）

**message.py**: MessageCreate/MessageResponse/MessageInDB，消息数据模型，role 为 Literal["user", "assistant", "system"]，token_count 可选

**moment.py**: MomentCreate/MomentResponse/MomentInDB，关键时刻数据模型（importance/status/type 等枚举字段，context_messages 可选）

---

## 设计原则

**三层模型设计**:
- Create: API 请求体，用于接收外部输入
- Response: API 响应体，对外暴露数据
- InDB: 数据库模型，内部使用，与 MongoDB 文档结构对应

**字段验证**: 使用 Pydantic Field 进行类型校验、长度校验、默认值设置

---

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
