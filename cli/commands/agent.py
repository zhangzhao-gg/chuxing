"""
[INPUT]: 依赖 typer 的 Typer/Option，依赖 rich.console 的 Console，依赖 cli.client 的 APIClient
[OUTPUT]: 对外提供 Agent 管理命令（create/list）
[POS]: cli/commands 的 Agent 管理命令，被 cli/main.py 注册
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import typer
from rich.console import Console
from rich.table import Table
from ..client import APIClient

app = typer.Typer()
console = Console()


@app.command("create")
def create_agent(
    name: str = typer.Option(..., "--name", "-n", help="Agent 名称"),
    system_prompt: str = typer.Option(..., "--system-prompt", "-s", help="系统提示词"),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="OpenAI 模型名"),
    api_url: str = typer.Option("http://localhost:8000", "--api-url", help="API 地址"),
):
    """创建 Agent"""
    client = APIClient(api_url)
    try:
        agent = client.create_agent(name, system_prompt, model)
        console.print(f"[green]✓[/green] Agent 创建成功")
        console.print(f"  agent_id: {agent['agent_id']}")
        console.print(f"  name: {agent['name']}")
        console.print(f"  model: {agent['model']}")
    except Exception as e:
        console.print(f"[red]✗[/red] 创建失败: {e}")
        raise typer.Exit(1)
    finally:
        client.close()


@app.command("list")
def list_agents(
    api_url: str = typer.Option("http://localhost:8000", "--api-url", help="API 地址"),
):
    """列出所有 Agent"""
    client = APIClient(api_url)
    try:
        agents = client.list_agents()

        if not agents:
            console.print("[yellow]暂无 Agent[/yellow]")
            return

        table = Table(title="Agent 列表")
        table.add_column("Agent ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Model", style="yellow")
        table.add_column("System Prompt", style="magenta", no_wrap=False)

        for agent in agents:
            prompt_preview = agent["system_prompt"][:50] + "..." if len(agent["system_prompt"]) > 50 else agent["system_prompt"]
            table.add_row(
                agent["agent_id"],
                agent["name"],
                agent["model"],
                prompt_preview,
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]✗[/red] 查询失败: {e}")
        raise typer.Exit(1)
    finally:
        client.close()
