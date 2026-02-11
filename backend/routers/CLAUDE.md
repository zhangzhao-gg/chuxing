# backend/routers/
> L2 | 父级: backend/CLAUDE.md

---

## AGENTS 索引（统一入口）

- [agents.md](../../agents.md) - Agent 协作约束与角色清单

---

## 成员清单

**users.py**: 用户管理 REST API，POST 创建用户，GET 列表/详情，DELETE 删除用户，捕获 DuplicateKeyError → 400

**agents.py**: Agent 管理 REST API，POST 创建 Agent，GET 列表/详情，PUT 更新配置，DELETE 删除 Agent

**conversations.py**: 会话管理 REST API，POST 创建会话，GET 列表（可按 user_id 过滤），DELETE 删除会话，捕获 ResourceNotFoundError → 404

**messages.py**: **核心** 对话接口，POST /api/conversations/{conv_id}/chat 发送消息并获取回复，GET /api/conversations/{conv_id}/messages 获取对话历史

**moments.py**: 关键时刻管理 REST API，POST/GET /api/moments，GET /api/moments/{moment_id}，POST confirm/cancel

---

## 核心接口：messages.py

### POST /conversations/{conv_id}/chat

**数据流**:
1. 保存 user message（MessageService.create_message）
2. 注入“当前用户所有未完成且未取消的关键时刻（open moments）”（status!=2 且 status!=3）
3. 调用 LLMService.generate_response 生成回复（返回 JSON：chat_response/emotion_tags/emotion_level/moment/moment_updates）
4. 按 moment_updates 更新对应 moment 状态（confirm/cancel/complete；失败不影响对话）
5. 保存 assistant message
6. 更新会话时间戳（ConversationService.update_conversation_timestamp）
7. 如果识别到 moment，则创建关键时刻记录（MomentService.create_moment_from_llm_response；失败不影响对话）
8. 返回 assistant 回复

**错误处理**:
- ResourceNotFoundError（会话/Agent 不存在）→ 404
- LLMError（OpenAI 调用失败）→ 502
- Exception（未知错误）→ 500 + 日志记录

---

## 设计原则

**统一错误处理**: 所有路由捕获业务异常，转换为 HTTP 状态码，保持 API 响应一致性

**依赖注入**: 每个 Router 初始化对应的 Service 实例，实现单向依赖

**RESTful 风格**: 路径命名清晰，方法语义明确（POST 创建，GET 查询，PUT 更新，DELETE 删除）

---

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
