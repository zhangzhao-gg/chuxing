# backend/repositories/
> L2 | 父级: backend/CLAUDE.md

---

## AGENTS 索引（统一入口）

- [agents.md](../../agents.md) - Agent 协作约束与角色清单

---

## 成员清单

**base.py**: BaseRepository 抽象类，定义通用 CRUD 方法（create/find_one/find_many/update/delete/count），泛型设计支持类型安全，抽象方法 _to_model 由子类实现

**user.py**: UserRepository，继承 BaseRepository[UserInDB]，操作 db.users 集合，实现 _to_model 转换逻辑

**agent.py**: AgentRepository，继承 BaseRepository[AgentInDB]，操作 db.agents 集合，实现 _to_model 转换逻辑

**conversation.py**: ConversationRepository，继承 BaseRepository[ConversationInDB]，操作 db.conversations 集合，实现 _to_model 转换逻辑

**message.py**: MessageRepository，继承 BaseRepository[MessageInDB]，操作 db.messages 集合，实现 _to_model 转换逻辑

**moment.py**: MomentRepository（PostgreSQL），操作 moments 表；find_user_open_moments 使用 status=1 AND executed_at IS NULL；find_user_recent_closed_moments（N 天内 completed/cancelled 记录，供 LLM dedup 上下文）；find_latest_user_pending_moment/find_pending_moments 等查询；claim_due_moments/mark_delivered/mark_delivery_failed 用于 worker 兑现调度（抢锁+重试），claim_due_moments 过滤 `conversation_id IS NOT NULL`（无投递目标的 moment 不领取）；jsonb 字段做序列化兜底

---

## 设计原则

**BaseRepository 抽象**: 封装 MongoDB 操作细节，提供类型安全的查询接口，消除重复代码

**异构存储（Good Taste）**: moments 走 PostgreSQL 是“按访问模式选存储”，不强行塞进 BaseRepository，避免抽象污染与特殊分支膨胀

**返回 Optional[T]**: find_one 返回 None 表示不存在，让上层处理 None 情况，代码自证正确

**统一接口**: 所有 Repository 继承 BaseRepository，保持接口一致，降低认知负担

---

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
[LAST_UPDATED]: 2026-02-12
