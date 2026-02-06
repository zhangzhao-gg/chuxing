# 初醒 (Chuxing) - 情绪陪伴与关键时刻兑现系统
Python 3.10+ + FastAPI + MongoDB(motor) + PostgreSQL(asyncpg) + OpenAI SDK + typer + rich

**核心理念**: 用“薄陪聊”采集行为与情绪线索，自动识别关键时刻（moment），并在合适时间完成情绪兑现。

---

## AGENTS 索引（统一入口）

- [agents.md](./agents.md) - Agent 协作约束与角色清单（所有模块文档都必须指向这里）

---

## 目录结构

```
<directory>
backend/ - FastAPI 后端服务（5子目录: core, models, repositories, services, routers）
cli/ - Typer CLI 客户端（2子目录: commands）
docs/ - 项目文档（PRD, ARCHITECTURE, CONTEXT_COMPRESSION）
sql/ - PostgreSQL 结构/数据快照（用于本地调试与迁移校验）
.cursor/ - Cursor 规则与提示词（仅开发辅助）
</directory>
```

---

## 配置文件

```
<config>
pyproject.toml - uv 依赖管理（FastAPI/motor/asyncpg/openai/typer/rich 等）
uv.lock - 依赖锁文件（保证可复现）
.env.example - 环境变量模板（MongoDB/PostgreSQL/OpenAI/上下文压缩）
README.md - 项目概览与快速开始
</config>
```

---

## 架构设计

### 产品架构（四层）
1. **陪聊层** - 轻目的对话与行为数据采集
2. **关键时刻识别** - 从对话中提取 moment（当前主要在 `MomentService` 做规则/去重/时间解析）
3. **存储系统** - MongoDB（用户/会话/消息） + PostgreSQL（moments）
4. **兑现系统** - 未来由调度器扫描 `scheduled` moments 并触达（电话/消息）

详见 [技术架构文档](./docs/ARCHITECTURE.md) 和 [产品需求文档](./docs/PRD.md)。

### 技术架构（单向数据流）

```
CLI Client → HTTP → Router → Service → Repository → (MongoDB / PostgreSQL)
                                 ↓
                            LLMService → OpenAI API
```

### 关键设计决策
1. **单向依赖流**: Router → Service → Repository → DB，任何反向依赖都是设计错误
2. **上下文即计算**: LLM 上下文是运行时计算的结果，不回写数据库
3. **错误边界清晰**: Repository/Service/LLM 各自抛出不同异常，由 Router 做 HTTP 映射
4. **消除特殊情况**: 上下文裁剪用统一逻辑处理空历史/首条消息/token 超限

---

## 存储模型（现状）

### MongoDB Collections（motor）
- **users**: user_id(unique), username(unique), created_at
- **agents**: agent_id(unique), name, system_prompt, model, created_at
- **conversations**: conversation_id(unique), user_id, agent_id, title, created_at, updated_at
- **messages**: message_id(unique), conversation_id, role, content, token_count, created_at

### PostgreSQL Tables（asyncpg）
- **moments**: 关键时刻主表（`moment_id` 主键，`remind_time/status/confirmed/context_messages(jsonb)` 等字段）

> 注：代码里仍保留 MongoDB 的 `moments` 索引创建（`backend/core/database.py`），但实际读写 moments 走 PostgreSQL（`backend/repositories/moment.py`）。文档以“实际读写路径”为准。

---

## 核心接口

- `POST /api/conversations/{conv_id}/chat` - 发送消息并获取回复（系统核心价值所在）
- `GET /api/conversations/{conv_id}/messages` - 获取对话历史
- `POST /api/moments/{moment_id}/confirm` - 确认关键时刻并进入调度态（scheduled）

---

## 上下文压缩

当对话历史超过阈值时，可选地将早期消息压缩为摘要，降低 token 消耗。
详见 [上下文压缩说明](./docs/CONTEXT_COMPRESSION.md)。

---

## 启动方式

### 环境准备

```bash
# MongoDB
docker run -d -p 27017:27017 --name mongo mongo:7

# PostgreSQL（注意端口与代码默认一致：55432）
docker run -d --name pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=llm_chat \
  -p 55432:5432 \
  postgres:16

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY
```

### 启动后端

```bash
uv sync  # 安装依赖
uv run uvicorn backend.main:app --reload --port 8000
```

### 使用 CLI

```bash
uv run cli user create --username alice
uv run cli agent create --name "Python专家" --persona "你是一个精通Python的资深工程师" --model "gpt-4o-mini"
uv run cli chat start --user-id <user_id> --agent-id <agent_id>
```

---

## 相关文档

- [agents.md](./agents.md) - Agent 协作约束与角色清单
- [README.md](./README.md) - 项目概览与快速开始
- [技术架构文档](./docs/ARCHITECTURE.md) - 详细的技术架构设计
- [产品需求文档](./docs/PRD.md) - 产品功能与需求说明
- [上下文压缩说明](./docs/CONTEXT_COMPRESSION.md) - 上下文压缩机制详解

---

[PROTOCOL]: 变更时更新此头部，然后检查子模块 CLAUDE.md
[LAST_UPDATED]: 2026-02-06
