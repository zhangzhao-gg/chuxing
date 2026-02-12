# cli/
> L2 | 父级: /CLAUDE.md

---

## AGENTS 索引（统一入口）

- [agents.md](../agents.md) - Agent 协作约束与角色清单

---

## 成员清单

**main.py**: CLI 应用入口，typer.Typer 实例，注册子命令（user/agent/chat/moment/e2e/lifecycle），pyproject.toml 的 [project.scripts] 引用

**client.py**: HTTP 客户端封装，APIClient 类，封装与后端 API 的 HTTP 交互（httpx）；强制 `trust_env=False` 避免 localhost 被代理导致 502；提供用户/Agent/会话/消息/moments 全量 API（`create_user/list_users/create_agent/list_agents/create_conversation/send_message/get_messages/list_moments/get_moment/confirm_moment/cancel_moment/create_moment`）

**commands/user.py**: 用户管理命令，user create 创建用户，user list 列出用户（rich.Table 展示）

**commands/agent.py**: Agent 管理命令。agent create 采用"组合式 system_prompt"：默认注入关键时刻定义（可覆盖），可选叠加人设约束（persona），再拼接补充提示词；agent list 列出 Agent（system_prompt 截断显示）

**commands/agent_old.py**: agent create 的旧版实现（已废弃，保留供参考）

**commands/chat.py**: **核心** 对话命令，chat start 交互式对话（支持 `--watch-reminders` 后台轮询兑现消息自动输出）；chat simulate 多人设批量对话（4 种人设 × N 轮，生成 moment 识别报告到 docs/reports/*.md）

**commands/moment.py**: 兑现端到端测试命令，moment test-delivery 一键创建 user/agent/conv/moment 并确认，等待 worker 到点写入站内消息后校验 moment completed，生成 Markdown 报告到 docs/reports

**commands/e2e_test.py**: 全链路端到端测试命令，e2e test-conversation 模拟 20 轮自然对话（马拉松备赛主题）→ LLM 自动识别关键时刻 → 确认 pending → 调整 remind_time（直连 PostgreSQL）→ 等 worker 兑现 → 生成 Markdown 报告。内置 502 重试机制

**commands/e2e_full_lifecycle.py**: 全生命周期端到端测试命令，lifecycle test-full-lifecycle 两阶段对话（Phase1: 15 轮多主题触发 12+ moments，Phase2: 5 轮取消/修改对话）→ AI 自动取消 + 手动补充 Cancel/Modify → 确认 pending → 加速 remind_time → worker 兑现 → 生成 Markdown 报告。覆盖 pending→scheduled→completed、pending→cancelled、修改（取消旧+创建新）三条状态迁移链路

---

## 核心命令：commands/chat.py

### chat start

**流程**:
1. 创建会话（APIClient.create_conversation）
2. 进入交互循环（while True）
3. 读取用户输入（console.input）
4. 发送消息（APIClient.send_message）
5. 展示回复（rich.Panel + rich.Markdown）
6. 输入 'exit' 或 'quit' 退出

### chat simulate

**用途**:
- 4 种人设 × N 轮对话（并发执行，用于 moment 识别率压测）
- 生成 Markdown 报告到 docs/reports/（对话转录 + 关键时刻分析）

**用户体验**:
- 使用 rich 美化输出（颜色、表格、Markdown 渲染）
- 错误提示清晰（红色 [ERR] 标记）
- 成功提示友好（绿色 [OK] 标记）

---

## 设计原则

**薄客户端**: CLI 不包含业务逻辑，所有操作通过 HTTP API 完成，与后端解耦

**用户体验优先**: 使用 rich 库美化输出，Markdown 渲染 AI 回复，表格展示列表数据

**命令结构清晰**: 子命令分组（user/agent/chat/moment/e2e/lifecycle），参数命名一致（--api-url），帮助文档完整

---

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
[LAST_UPDATED]: 2026-02-12
