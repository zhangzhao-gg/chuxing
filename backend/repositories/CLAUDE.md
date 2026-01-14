# backend/repositories/
> L2 | 父级: backend/CLAUDE.md

---

## 成员清单

**base.py**: BaseRepository 抽象类，定义通用 CRUD 方法（create/find_one/find_many/update/delete/count），泛型设计支持类型安全，抽象方法 _to_model 由子类实现

**user.py**: UserRepository，继承 BaseRepository[UserInDB]，操作 db.users 集合，实现 _to_model 转换逻辑

**agent.py**: AgentRepository，继承 BaseRepository[AgentInDB]，操作 db.agents 集合，实现 _to_model 转换逻辑

**conversation.py**: ConversationRepository，继承 BaseRepository[ConversationInDB]，操作 db.conversations 集合，实现 _to_model 转换逻辑

**message.py**: MessageRepository，继承 BaseRepository[MessageInDB]，操作 db.messages 集合，实现 _to_model 转换逻辑

---

## 设计原则

**BaseRepository 抽象**: 封装 MongoDB 操作细节，提供类型安全的查询接口，消除重复代码

**返回 Optional[T]**: find_one 返回 None 表示不存在，让上层处理 None 情况，代码自证正确

**统一接口**: 所有 Repository 继承 BaseRepository，保持接口一致，降低认知负担

---

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
