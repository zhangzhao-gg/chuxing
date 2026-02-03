# backend/core/
> L2 | 父级: backend/CLAUDE.md

---

## AGENTS 索引（统一入口）

- [agents.md](../../agents.md) - Agent 协作约束与角色清单

---

## 成员清单

**config.py**: Pydantic Settings 配置管理，环境变量加载（MongoDB/PostgreSQL/OpenAI/上下文压缩/服务器端口），提供全局 settings 实例

**database.py**: MongoDB 连接池管理，connect_to_mongo 创建连接 + 索引，close_mongo_connection 关闭连接，提供全局 db 实例

**postgres.py**: PostgreSQL 连接池管理，connect_to_postgres 创建连接池 + 幂等建表（moments），close_postgres_connection 关闭连接池

**exceptions.py**: 自定义异常类型，分层设计（RepositoryError/BusinessError/LLMError/OpenAIAPIError），Router 层根据异常类型转换 HTTP 状态码

---

## 设计原则

**配置管理**: 所有配置通过环境变量注入，支持 .env 文件，Pydantic 自动验证类型

**数据库连接**: 应用启动时建立连接池，关闭时销毁，索引创建幂等（重复创建不报错）

**异常分层**: Repository 层抛出 RepositoryError，Service 层抛出 BusinessError，LLM 层抛出 LLMError，Router 层统一处理

---

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
