# cli/
> L2 | 父级: /CLAUDE.md

---

## 成员清单

**main.py**: CLI 应用入口，typer.Typer 实例，注册子命令（user/agent/chat），pyproject.toml 的 [project.scripts] 引用

**client.py**: HTTP 客户端封装，APIClient 类，封装与后端 API 的 HTTP 交互（httpx），提供 create_user/create_agent/create_conversation/send_message 等方法

**commands/user.py**: 用户管理命令，user create 创建用户，user list 列出用户（rich.Table 展示）

**commands/agent.py**: Agent 管理命令，agent create 创建 Agent，agent list 列出 Agent（system_prompt 截断显示）

**commands/chat.py**: **核心** 交互式对话命令，chat start 启动对话，创建会话后进入循环，读取用户输入，发送消息，使用 rich.Markdown 渲染回复

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

**用户体验**:
- 使用 rich 美化输出（颜色、表格、Markdown 渲染）
- 错误提示清晰（红色 ✗ 标记）
- 成功提示友好（绿色 ✓ 标记）

---

## 设计原则

**薄客户端**: CLI 不包含业务逻辑，所有操作通过 HTTP API 完成，与后端解耦

**用户体验优先**: 使用 rich 库美化输出，Markdown 渲染 AI 回复，表格展示列表数据

**命令结构清晰**: 子命令分组（user/agent/chat），参数命名一致（--api-url），帮助文档完整

---

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
