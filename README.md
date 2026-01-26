# 初醒 (Chuxing) - 情绪陪伴与关键时刻兑现系统

从 0 到 1 构建的生产级 LLM 交互系统，支持多用户、多 Agent、多会话对话。

**核心理念**：通过轻目的陪聊采集用户行为数据，自动识别关键时刻，并在合适时间完成情绪兑现。

## 技术栈

- **语言**: Python 3.10+
- **包管理**: uv
- **Web 框架**: FastAPI（异步）
- **数据库**: MongoDB + motor
- **LLM SDK**: OpenAI 官方 Python SDK
- **CLI 框架**: typer + rich
- **配置管理**: pydantic-settings
- **Token 计算**: tiktoken

## 快速开始

### 1. 环境准备

```bash
# 保证 mongdb

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入以下内容：
# OPENAI_API_KEY=sk-your-key-here
```

### 2. 安装依赖

```bash
uv sync
```

### 3. 启动后端

```bash
uv run uvicorn backend.main:app --reload --port 8000
```

访问 http://localhost:8000/docs 查看 API 文档

### 4. 使用 CLI

```bash
# 创建用户
uv run cli user create --username alice

# 创建 Agent
uv run cli agent create \
  --name "Python专家" \
  --system-prompt "你是一个精通Python的资深工程师，善于解释复杂概念" \
  --model "gpt-4o-mini"

# 列出所有用户和 Agent，获取 user_id 和 agent_id
uv run cli user list
uv run cli agent list

# 启动对话（替换为实际的 ID）
uv run cli chat start --user-id <user_id> --agent-id <agent_id>
```

## 项目结构

```
chuxing/
├── backend/                 # FastAPI 后端
│   ├── core/                # 核心配置（config, database, exceptions）
│   ├── models/              # Pydantic 数据模型
│   ├── repositories/        # 数据访问层（MongoDB CRUD）
│   ├── services/            # 业务逻辑层（含 LLM 上下文管理）
│   ├── routers/             # API 路由层
│   └── main.py              # FastAPI 应用入口
│
└── cli/                     # Typer CLI 客户端
    ├── commands/            # 子命令（user, agent, chat）
    ├── client.py            # HTTP 客户端封装
    └── main.py              # CLI 入口
```

## 产品架构

本系统采用四层架构设计：

1. **陪聊层** - 轻目的对话与行为数据采集
2. **关键时刻识别引擎** - 自动识别关键时刻（LLM 层）
3. **存储系统** - 结构化存储关键时刻
4. **兑现系统** - 在合适时间完成情绪兑现

详见 [技术架构文档](./docs/ARCHITECTURE.md) 和 [产品需求文档](./docs/PRD.md)。

## 核心特性

### 1. 单向数据流架构

```
Router → Service → Repository → MongoDB
         ↓
    LLMService → OpenAI API
```

- 上层依赖下层，下层不知上层
- 任何反向依赖都是设计错误

### 2. LLM 上下文管理

**核心逻辑**：`backend/services/llm.py`

**滑动窗口裁剪策略**：
1. 保留 system_prompt（agent 人格稳定）
2. 保留最新 user 消息（用户意图）
3. 删除中间历史消息，直到满足 token 限制

**消除特殊情况**：
- 空历史、首条消息、token 超限用统一逻辑处理
- 代码自证正确：`[system] + [] + [user]` 自然成立

### 3. 分层异常处理

- **Repository 层**：`RepositoryError` → 500
- **Service 层**：`BusinessError` → 400/404
- **LLM 层**：`LLMError` → 502
- **Router 层**：统一转换为 HTTP 状态码

### 4. 上下文压缩

当对话历史超过阈值时，自动将早期消息压缩为摘要，节省约 65% 的 token 消耗。

配置参数：
```bash
ENABLE_CONTEXT_COMPRESSION=false  # 是否启用
COMPRESSION_THRESHOLD=30          # 触发阈值
COMPRESSION_TARGET=10             # 保留消息数
```

详见 [上下文压缩说明](./docs/CONTEXT_COMPRESSION.md)。

### 5. GEB 分形文档系统

- **L1**：项目宪法（/CLAUDE.md）
- **L2**：模块地图（backend/CLAUDE.md, cli/CLAUDE.md 等）
- **L3**：文件头部契约（INPUT/OUTPUT/POS）

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
- `POST /api/conversations/{conv_id}/chat` - 发送消息并获取回复
- `GET /api/conversations/{conv_id}/messages` - 获取对话历史

## CLI 命令

### 用户管理
```bash
uv run cli user create --username <name>
uv run cli user list
```

### Agent 管理
```bash
uv run cli agent create --name <name> --system-prompt <prompt> --model <model>
uv run cli agent list
```

### 交互式对话
```bash
uv run cli chat start --user-id <id> --agent-id <id>
```

## 设计哲学

**核心信念**：让数据如河流般单向流动，让上下文成为计算结果而非存储状态

**关键原则**：
1. 单向依赖流 - 上层依赖下层，下层不知上层
2. 上下文即计算 - LLM 上下文是运行时计算的结果
3. 错误边界清晰 - 每层抛出不同异常类型
4. 消除特殊情况 - 通过设计让边界自然融入常规

**Good Taste 体现**：
- LLM 上下文裁剪统一处理空历史、首条消息、token 超限
- Repository 返回 `Optional[T]`，Service 处理 None
- 代码自证正确，无需注释即可理解意图

## 开发状态

### 已完成 ✅

- 陪聊层基础功能（对话生成、上下文管理）
- LLM 服务（OpenAI API 调用、上下文压缩）
- 用户管理、Agent 管理、会话管理
- 消息存储与查询
- CLI 交互式对话客户端

### 开发中 🚧

- 行为标签提取
- 情绪识别
- 关键时刻识别引擎（规则层 + LLM 层）
- 关键时刻存储系统
- 兑现调度引擎
- 多渠道触达（电话 / 消息）

## 未来扩展路径

1. **流式响应** - LLMService.generate_response_stream() + FastAPI StreamingResponse
2. **多 Agent 协作** - 新增 orchestration_strategy（sequential/parallel/voting）
3. **JWT 认证** - /api/auth/login + 路由依赖注入 verify_token
4. **对话分支** - Message 表新增 parent_message_id，支持 Tree-of-Thought
5. **语音识别** - 集成语音输入支持（暂缓）

## 相关文档

- [技术架构文档](./docs/ARCHITECTURE.md) - 详细的技术架构设计
- [产品需求文档](./docs/PRD.md) - 产品功能与需求说明
- [上下文压缩说明](./docs/CONTEXT_COMPRESSION.md) - 上下文压缩机制详解

## 许可证

MIT License
