# 初醒 (Chuxing) - 情绪陪伴与关键时刻兑现系统
Python 3.10+ + FastAPI + MongoDB + motor + OpenAI SDK + typer + rich

**核心理念**: 通过轻目的陪聊采集用户行为数据，自动识别关键时刻，并在合适时间完成情绪兑现。

---

## 目录结构

```
<directory>
backend/ - FastAPI 后端服务（5子目录: core, models, repositories, services, routers）
cli/ - Typer CLI 客户端（2子目录: commands）
docs/ - 项目文档（PRD, ARCHITECTURE, CONTEXT_COMPRESSION）
</directory>
```

---

## 配置文件

```
<config>
pyproject.toml - uv 依赖管理，定义项目元数据与依赖
.env.example - 环境变量模板（MONGODB_URL, OPENAI_API_KEY, MAX_CONTEXT_TOKENS）
</config>
```

---

## 架构设计

### 产品架构（四层设计）
1. **陪聊层** - 轻目的对话与行为数据采集
2. **关键时刻识别引擎** - 自动识别关键时刻（规则层 + LLM 层）
3. **存储系统** - 结构化存储关键时刻
4. **兑现系统** - 在合适时间完成情绪兑现

详见 [技术架构文档](./docs/ARCHITECTURE.md) 和 [产品需求文档](./docs/PRD.md)。

### 技术架构（单向数据流）

### 核心价值
单向数据流架构 + LLM 上下文管理 + 多用户/多Agent/多会话

### 数据流向
```
CLI Client → HTTP → Router → Service → Repository → MongoDB
                                 ↓
                            LLMService → OpenAI API
```

### 关键设计决策
1. **单向依赖流**: Router → Service → Repository → DB，任何反向依赖都是设计错误
2. **上下文即计算**: LLM 上下文是运行时计算的结果，不存储到数据库
3. **错误边界清晰**: 每层抛出不同异常类型（RepositoryError/BusinessError/LLMError）
4. **消除特殊情况**: 滑动窗口裁剪统一处理空历史、首条消息、token 超限

### MongoDB Schema
- **users**: user_id (unique), username (unique), created_at
- **agents**: agent_id (unique), name, system_prompt, model, created_at
- **conversations**: conversation_id (unique), user_id, agent_id, title, created_at, updated_at
- **messages**: message_id (unique), conversation_id, role, content, token_count, created_at

### 核心接口
- `POST /api/conversations/{conv_id}/chat` - 发送消息并获取回复（系统核心价值所在）
- `GET /api/conversations/{conv_id}/messages` - 获取对话历史

### 上下文压缩
当对话历史超过阈值时，自动将早期消息压缩为摘要，节省约 65% 的 token 消耗。
详见 [上下文压缩说明](./docs/CONTEXT_COMPRESSION.md)。

---

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

---

## 启动方式

### 环境准备
```bash
# 启动 MongoDB
docker run -d -p 27017:27017 --name mongo mongo:7

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY
```

### 启动后端
```bash
uv sync  # 安装依赖
uv run uvicorn backend.main:app --reload --port 8000
# 访问 http://localhost:8000/docs 查看 API 文档
```

### 使用 CLI
```bash
# 创建用户
uv run cli user create --username alice

# 创建 Agent
uv run cli agent create \
  --name "Python专家" \
  --system-prompt "你是一个精通Python的资深工程师" \
  --model "gpt-4o-mini"

# 启动对话
uv run cli chat start --user-id <user_id> --agent-id <agent_id>
```

---

## 设计哲学

**核心信念**: 让数据如河流般单向流动，让上下文成为计算结果而非存储状态

**关键原则**:
1. 单向依赖流 - 上层依赖下层，下层不知上层
2. 上下文即计算 - LLM 上下文是运行时计算的结果
3. 错误边界清晰 - 每层抛出不同异常类型
4. 消除特殊情况 - 通过设计让边界自然融入常规

**Good Taste 体现**:
- LLM 上下文裁剪：统一处理空历史、首条消息、token 超限，无需特殊分支
- Repository 返回 Optional[T]，Service 处理 None，Router 永不崩溃
- 代码自证正确，无需注释即可理解意图

---

## 未来扩展路径

1. **流式响应**: LLMService.generate_response_stream() + FastAPI StreamingResponse
2. **多 Agent 协作**: 新增 orchestration_strategy（sequential/parallel/voting）
3. **JWT 认证**: /api/auth/login + 路由依赖注入 verify_token
4. **对话分支**: Message 表新增 parent_message_id，支持 Tree-of-Thought
5. **语音识别**: 集成语音输入支持（暂缓）

---

## 相关文档

- [README.md](./README.md) - 项目概览与快速开始
- [技术架构文档](./docs/ARCHITECTURE.md) - 详细的技术架构设计
- [产品需求文档](./docs/PRD.md) - 产品功能与需求说明
- [上下文压缩说明](./docs/CONTEXT_COMPRESSION.md) - 上下文压缩机制详解

---

[PROTOCOL]: 变更时更新此头部，然后检查子模块 CLAUDE.md
[LAST_UPDATED]: 2026-01-20
