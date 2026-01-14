"""
[INPUT]: 依赖 typer 的 Typer/Option，依赖 rich.console 的 Console/Markdown，依赖 cli.client 的 APIClient
[OUTPUT]: 对外提供交互式对话命令（start）
[POS]: cli/commands 的核心对话命令，被 cli/main.py 注册
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from ..client import APIClient

app = typer.Typer()
console = Console()


@app.command("start")
def start_chat(
    user_id: str = typer.Option(..., "--user-id", "-u", help="用户 ID"),
    agent_id: str = typer.Option(..., "--agent-id", "-a", help="Agent ID"),
    api_url: str = typer.Option("http://localhost:8000", "--api-url", help="API 地址"),
):
    """启动交互式对话

    用法示例：
        uv run cli chat start --user-id <user_id> --agent-id <agent_id>

    输入 'exit' 或 'quit' 退出对话
    """
    client = APIClient(api_url)

    try:
        # 创建会话
        console.print("[cyan]正在创建会话...[/cyan]")
        conv = client.create_conversation(user_id, agent_id)
        conv_id = conv["conversation_id"]
        console.print(f"[green]✓[/green] 会话已创建: {conv_id}")
        console.print()

        # 交互循环
        console.print("[yellow]开始对话（输入 'exit' 或 'quit' 退出）[/yellow]")
        console.print("─" * 60)
        console.print()

        while True:
            # 读取用户输入
            user_input = console.input("[bold blue]You:[/bold blue] ")

            if user_input.strip().lower() in ["exit", "quit", "q"]:
                console.print("[yellow]再见![/yellow]")
                break

            if not user_input.strip():
                continue

            # 发送消息
            try:
                console.print("[dim]等待回复...[/dim]")
                response = client.send_message(conv_id, user_input)

                # 展示回复（使用 Markdown 渲染）
                console.print()
                console.print(
                    Panel(
                        Markdown(response["content"]),
                        title="[bold green]Assistant[/bold green]",
                        border_style="green",
                    )
                )
                console.print()

            except Exception as e:
                console.print(f"[red]✗[/red] 消息发送失败: {e}")
                console.print()

    except Exception as e:
        console.print(f"[red]✗[/red] 会话创建失败: {e}")
        raise typer.Exit(1)

    finally:
        client.close()
