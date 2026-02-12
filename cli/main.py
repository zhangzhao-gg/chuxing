"""
[INPUT]: 依赖 typer 的 Typer，依赖 cli.commands 的所有子命令模块
[OUTPUT]: 对外提供 CLI 应用实例 app，供 uv run cli 调用
[POS]: cli 的应用入口，被 pyproject.toml 的 [project.scripts] 引用
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import typer
from .commands import user, agent, chat, moment, e2e_test, e2e_full_lifecycle

app = typer.Typer(
    name="cli",
    help="LLM Chat System CLI - 与 AI 助手对话的命令行工具",
    no_args_is_help=True,
)

# 注册子命令
app.add_typer(user.app, name="user", help="用户管理")
app.add_typer(agent.app, name="agent", help="Agent 管理")
app.add_typer(chat.app, name="chat", help="交互式对话")
app.add_typer(moment.app, name="moment", help="关键时刻/兑现测试")
app.add_typer(e2e_test.app, name="e2e", help="端到端集成测试")
app.add_typer(e2e_full_lifecycle.app, name="lifecycle", help="全生命周期测试（含取消/修改/兑现）")


if __name__ == "__main__":
    app()
