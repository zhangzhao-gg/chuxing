# backend/
> L2 | 父级: /CLAUDE.md

---

## AGENTS 索引（统一入口）

- [agents.md](../agents.md) - Agent 协作约束与角色清单

---

## 成员清单

**main.py**: FastAPI 应用入口，生命周期管理（lifespan），路由注册，日志配置

**core/**: 核心配置与基础设施模块
- config.py: Pydantic Settings，环境变量加载（MongoDB/PostgreSQL/OpenAI/上下文压缩等）
- database.py: MongoDB 连接池管理（connect_to_mongo/close_mongo_connection），索引创建（包含 moments 的 Mongo 索引：历史遗留）
- postgres.py: PostgreSQL 连接池管理（connect_to_postgres/close_postgres_connection），moments 表结构幂等创建
- exceptions.py: 自定义异常类型（RepositoryError/BusinessError/LLMError/OpenAIAPIError），分层异常设计

**models/**: Pydantic 数据模型模块
- user.py: UserCreate/UserResponse/UserInDB，用户数据模型
- agent.py: AgentCreate/AgentResponse/AgentInDB，Agent 数据模型
- conversation.py: ConversationCreate/ConversationResponse/ConversationInDB，会话数据模型
- message.py: MessageCreate/MessageResponse/MessageInDB，消息数据模型
- moment.py: MomentCreate/MomentResponse/MomentInDB，关键时刻数据模型

**repositories/**: 数据访问层模块（MongoDB CRUD）
- base.py: BaseRepository 抽象类，定义通用 CRUD 方法（create/find_one/find_many/update/delete）
- user.py: UserRepository，继承 BaseRepository，实现 _to_model
- agent.py: AgentRepository，继承 BaseRepository，实现 _to_model
- conversation.py: ConversationRepository，继承 BaseRepository，实现 _to_model
- message.py: MessageRepository，继承 BaseRepository，实现 _to_model
- moment.py: MomentRepository（**PostgreSQL**），关键时刻 moments 的 CRUD/去重查询（与 BaseRepository 分离）

**services/**: 业务逻辑层模块
- user.py: UserService，用户 CRUD，校验用户名唯一性
- agent.py: AgentService，Agent CRUD，支持更新配置
- conversation.py: ConversationService，会话管理，校验 user/agent 存在性
- message.py: MessageService，消息持久化，token 计算（tiktoken）
- llm.py: **核心** LLMService，上下文拼接 + 滑动窗口裁剪 + OpenAI 调用；要求返回 JSON（对话回复 + 情绪 + moment）
- context_compression.py: ContextCompressionService，上下文压缩（调用 OpenAI 生成摘要，失败则降级）
- moment.py: MomentService，关键时刻创建/时间解析（dateparser）/去重/确认/取消

**routers/**: API 路由层模块
- users.py: 用户管理 REST API（POST/GET/DELETE /api/users）
- agents.py: Agent 管理 REST API（POST/GET/PUT/DELETE /api/agents）
- conversations.py: 会话管理 REST API（POST/GET/DELETE /api/conversations）
- messages.py: **核心** 对话接口（POST /api/conversations/{conv_id}/chat），数据流汇聚点（包含 moment 识别后的创建）
- moments.py: 关键时刻管理 API（/api/moments，含 confirm/cancel）

---

## 架构分层

```
Router（HTTP 请求/响应）
  ↓ 调用 Service
Service（业务逻辑）
  ↓ 调用 Repository
Repository（数据访问）
  ↓ 操作 MongoDB / PostgreSQL
```

**单向依赖**: 上层依赖下层，下层不知上层，任何反向依赖都是设计错误

---

## 核心模块

### services/llm.py - 系统核心价值
**职责**: LLM 调用与上下文编排
**关键方法**: generate_response(conv_id, user_message) → str
**裁剪策略**: 滑动窗口，保留 system_prompt（agent 人格）+ 最新 user（用户意图），删除中间历史
**上下文压缩**: 当消息数超过阈值时，自动压缩早期消息为摘要（可选功能）

### services/context_compression.py - 上下文压缩
**职责**: 压缩长对话历史，节省 token 消耗
**关键方法**: compress_context(messages, threshold, target) → compressed_messages
**压缩策略**: 保留最近 N 条消息，将早期消息通过 LLM 压缩为摘要
**效果**: 节省约 65% 的 token 消耗

### routers/messages.py - 数据流汇聚点
**职责**: 核心对话接口
**数据流**: 保存 user → LLM 返回（chat_response/emotion/moment）→ 保存 assistant → 更新会话时间戳 → 如有 moment 则创建关键时刻 → 返回 assistant
**错误处理**: ResourceNotFoundError → 404，LLMError → 502，Exception → 500（关键时刻创建失败不影响对话流程）

---

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
[LAST_UPDATED]: 2026-02-03
