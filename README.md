# 初醒 (Chuxing) - 情绪陪伴与关键时刻兑现系统

用"薄陪聊"采集行为与情绪线索，自动识别关键时刻（moment），并在合适时间完成情绪兑现。

## 技术栈

- **语言**: Python 3.10+
- **包管理**: uv
- **Web 框架**: FastAPI（异步）
- **数据库**: MongoDB（motor） + PostgreSQL（asyncpg）
- **LLM SDK**: OpenAI 官方 Python SDK（兼容 DeepSeek 等 OpenAI 协议服务）
- **CLI 框架**: typer + rich
- **配置管理**: pydantic-settings
- **Token 计算**: tiktoken
- **时间解析**: dateparser + 中文相对时间手动解析

## 快速开始

### 1. 环境准备

```bash
# MongoDB
docker run -d -p 27017:27017 --name mongo mongo:7

# PostgreSQL（moments 存储）
docker run -d --name pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=llm_chat \
  -p 5432:5432 \
  postgres:16

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY（或 DeepSeek API Key + OPENAI_BASE_URL）
```

### 2. 安装依赖

```bash
uv sync
```

### 3. 启动后端

```bash
# Linux / macOS
uv run uvicorn backend.main:app --reload --port 8000

# Windows（推荐，避免 asyncpg 事件循环问题）
uv run uvicorn backend.win_entrypoint:app --reload --port 8000
```

访问 http://localhost:8000/docs 查看 API 文档

### 4. 启动兑现 Worker（独立进程）

```bash
uv run python -m backend.moment_worker
```

Worker 轮询领取到期 moments 并发送站内兑现消息，与 Web 进程解耦。

### 5. 使用 CLI

```bash
# 创建用户
uv run cli user create --username alice

# 创建 Agent（内置关键时刻定义，可选叠加人设）
uv run cli agent create \
  --name "陪伴助手" \
  --persona "你是一个温暖的情绪陪伴者" \
  --model "deepseek-chat"

# 列出用户和 Agent，获取 ID
uv run cli user list
uv run cli agent list

# 启动交互式对话（支持 --watch-reminders 后台接收兑现消息）
uv run cli chat start --user-id <user_id> --agent-id <agent_id>

```

## 项目结构

```
chuxing/
├── backend/                  # FastAPI 后端
│   ├── core/                 # 核心基础设施（config, database, postgres, exceptions）
│   ├── models/               # Pydantic 数据模型
│   ├── repositories/         # 数据访问层（MongoDB CRUD + PostgreSQL moments）
│   ├── services/             # 业务逻辑层（LLM/moment/notification/上下文压缩）
│   ├── routers/              # API 路由层
│   ├── main.py               # FastAPI 应用入口
│   ├── win_entrypoint.py     # Windows 兼容入口点
│   └── moment_worker.py      # 兑现调度 Worker（独立进程）
│
├── cli/                      # Typer CLI 客户端
│   ├── commands/             # 子命令（user/agent/chat/moment）
│   ├── client.py             # HTTP 客户端封装
│   └── main.py               # CLI 入口
│
├── docs/                     # 项目文档
│
└── sql/                      # PostgreSQL 结构/数据快照
```

## 产品架构

```
┌─────────────────────────────────────────────┐
│  陪聊层        轻目的对话 + 行为数据采集      │
├─────────────────────────────────────────────┤
│  识别层        LLM 自动识别关键时刻           │
├─────────────────────────────────────────────┤
│  存储层        MongoDB(用户/会话/消息)         │
│               PostgreSQL(moments)            │
├─────────────────────────────────────────────┤
│  兑现层        Worker 轮询 + 站内消息兑现      │
└─────────────────────────────────────────────┘
```

详见 [技术架构文档](./docs/ARCHITECTURE.md) 和 [产品需求文档](./docs/PRD.md)。

## 核心特性

### 1. 单向数据流架构

```
CLI Client → HTTP → Router → Service → Repository → MongoDB / PostgreSQL
                      ↓
                 LLMService → OpenAI API
```

- 上层依赖下层，下层不知上层
- 任何反向依赖都是设计错误

### 2. 关键时刻全生命周期

**识别**: LLM 对话中自动识别关键时刻，返回结构化 JSON（类型/时间/情绪/描述）

**去重**: 注入用户全量 moments（含已完成/已取消）供 LLM 判断重复

**时间解析**: 三层策略（ISO 8601 优先 → dateparser → 中文相对时间手动解析）

**状态流转**: `pending` → `scheduled`（确认后）→ `completed`（兑现后）/ `cancelled`

**兑现**: 独立 Worker 进程轮询到期 moments，写入站内系统消息，支持并发抢锁与失败重试

### 3. LLM 上下文管理

**滑动窗口裁剪**：
1. 保留 system_prompt（agent 人格 + 关键时刻定义 + 当前 moments 列表）
2. 保留最新 user 消息（用户意图）
3. 删除中间历史消息，直到满足 token 限制

**消除特殊情况**：空历史、首条消息、token 超限用统一逻辑处理

### 4. 分层异常处理

- **Repository 层**：`RepositoryError` → 500
- **Service 层**：`BusinessError` → 400/404
- **LLM 层**：`LLMError` → 502
- **Router 层**：统一转换为 HTTP 状态码

### 5. 上下文压缩（可选）

当对话历史超过阈值时，自动将早期消息压缩为摘要，节省约 65% 的 token 消耗。

```bash
ENABLE_CONTEXT_COMPRESSION=false  # 是否启用
COMPRESSION_THRESHOLD=30          # 触发阈值
COMPRESSION_TARGET=10             # 保留消息数
```

详见 [上下文压缩说明](./docs/CONTEXT_COMPRESSION.md)。

## API 接口

### 用户管理
- `POST /api/users` - 创建用户
- `GET /api/users` - 列出所有用户
- `GET /api/users/{user_id}` - 获取用户详情
- `DELETE /api/users/{user_id}` - 删除用户

### Agent 管理
- `POST /api/agents` - 创建 Agent
- `GET /api/agents` - 列出所有 Agent
- `GET /api/agents/{agent_id}` - 获取 Agent 详情
- `PUT /api/agents/{agent_id}` - 更新 Agent 配置
- `DELETE /api/agents/{agent_id}` - 删除 Agent

### 会话管理
- `POST /api/conversations` - 创建会话
- `GET /api/conversations?user_id=xxx` - 列出用户会话
- `GET /api/conversations/{conv_id}` - 获取会话详情
- `DELETE /api/conversations/{conv_id}` - 删除会话

### 核心对话接口
- `POST /api/conversations/{conv_id}/chat` - 发送消息并获取回复（含 moment 自动识别）
- `GET /api/conversations/{conv_id}/messages` - 获取对话历史

### 关键时刻管理
- `POST /api/moments` - 手动创建关键时刻
- `GET /api/moments` - 列出关键时刻（支持 user_id/conversation_id 过滤）
- `GET /api/moments/{moment_id}` - 获取关键时刻详情
- `POST /api/moments/{moment_id}/confirm` - 确认关键时刻（pending → scheduled）
- `POST /api/moments/{moment_id}/cancel` - 取消关键时刻

## CLI 命令

### 用户管理
```bash
uv run cli user create --username <name>
uv run cli user list
```

### Agent 管理
```bash
uv run cli agent create --name <name> --persona <persona> --model <model>
# 可选：自定义关键时刻定义文件
uv run cli agent create --name <name> --persona <persona> --moment-definition-file moment.txt --model <model>
uv run cli agent list
```

### 交互式对话
```bash
uv run cli chat start --user-id <id> --agent-id <id>
# 附带后台兑现消息监听
uv run cli chat start --user-id <id> --agent-id <id> --watch-reminders
```

## 存储模型

### MongoDB Collections
- **users**: 用户信息
- **agents**: Agent 配置（含 system_prompt）
- **conversations**: 会话元数据
- **messages**: 对话消息（含 token_count）

### PostgreSQL Tables
- **moments**: 关键时刻主表（状态/时间/情绪/兑现调度/抢锁/重试）

## 设计哲学

**核心信念**：让数据如河流般单向流动，让上下文成为计算结果而非存储状态

**关键原则**：
1. **单向依赖流** - 上层依赖下层，下层不知上层
2. **上下文即计算** - LLM 上下文是运行时计算的结果，不回写数据库
3. **错误边界清晰** - 每层抛出不同异常类型
4. **消除特殊情况** - 通过设计让边界自然融入常规
5. **异构存储** - MongoDB 存对话流（文档模型），PostgreSQL 存 moments（关系模型），按访问模式选存储

## 相关文档

- [技术架构文档](./docs/ARCHITECTURE.md) - 详细的技术架构设计
- [产品需求文档](./docs/PRD.md) - 产品功能与需求说明
- [上下文压缩说明](./docs/CONTEXT_COMPRESSION.md) - 上下文压缩机制详解

## 许可证

MIT License
