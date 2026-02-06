# cli/
> L2 | 父级: /CLAUDE.md

---

## AGENTS 索引（统一入口）

- [agents.md](../agents.md) - Agent 协作约束与角色清单

---

## 成员清单

**main.py**: CLI 应用入口，typer.Typer 实例，注册子命令（user/agent/chat），pyproject.toml 的 [project.scripts] 引用

**client.py**: HTTP 客户端封装，APIClient 类，封装与后端 API 的 HTTP 交互（httpx）；强制 `trust_env=False` 避免 localhost 被代理导致 502；提供 moments 拉取（`list_moments`）供测试报告生成

**commands/user.py**: 用户管理命令，user create 创建用户，user list 列出用户（rich.Table 展示）

**commands/agent.py**: Agent 管理命令。agent create 采用“组合式 system_prompt”：默认注入关键时刻定义（可覆盖），可选叠加人设约束（persona），再拼接补充提示词；agent list 列出 Agent（system_prompt 截断显示）

**commands/chat.py**: **核心** 对话命令，chat start 交互式对话；chat simulate 非交互式批量对话（用于关键时刻识别测试），输出“对话转录 + moment 报告”到 txt

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
- 生成 N 轮对话（>=50 用于压测/观测）
- 落盘 `txt`：对话转录 + 关键时刻分析报告（从 `/api/moments` 拉取并按 `conversation_id` 过滤）

**用户体验**:
- 使用 rich 美化输出（颜色、表格、Markdown 渲染）
- 错误提示清晰（红色 [ERR] 标记，避免 Windows GBK 控制台编码问题）
- 成功提示友好（绿色 [OK] 标记，避免 Windows GBK 控制台编码问题）

---

## 设计原则

**薄客户端**: CLI 不包含业务逻辑，所有操作通过 HTTP API 完成，与后端解耦

**用户体验优先**: 使用 rich 库美化输出，Markdown 渲染 AI 回复，表格展示列表数据

**命令结构清晰**: 子命令分组（user/agent/chat），参数命名一致（--api-url），帮助文档完整

---

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
[LAST_UPDATED]: 2026-02-06
