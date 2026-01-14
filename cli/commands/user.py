"""
[INPUT]: 依赖 typer 的 Typer/Option，依赖 rich.console 的 Console，依赖 cli.client 的 APIClient
[OUTPUT]: 对外提供用户管理命令（create/list）
[POS]: cli/commands 的用户管理命令，被 cli/main.py 注册
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import typer
from rich.console import Console
from rich.table import Table
from ..client import APIClient

app = typer.Typer()
console = Console()


@app.command("create")
def create_user(
    username: str = typer.Option(..., "--username", "-u", help="用户名"),
    api_url: str = typer.Option("http://localhost:8000", "--api-url", help="API 地址"),
):
    """创建用户"""
    client = APIClient(api_url)
    try:
        user = client.create_user(username)
        console.print(f"[green]✓[/green] 用户创建成功")
        console.print(f"  user_id: {user['user_id']}")
        console.print(f"  username: {user['username']}")
    except Exception as e:
        console.print(f"[red]✗[/red] 创建失败: {e}")
        raise typer.Exit(1)
    finally:
        client.close()


@app.command("list")
def list_users(
    api_url: str = typer.Option("http://localhost:8000", "--api-url", help="API 地址"),
):
    """列出所有用户"""
    client = APIClient(api_url)
    try:
        users = client.list_users()

        if not users:
            console.print("[yellow]暂无用户[/yellow]")
            return

        table = Table(title="用户列表")
        table.add_column("User ID", style="cyan")
        table.add_column("Username", style="green")
        table.add_column("Created At", style="magenta")

        for user in users:
            table.add_row(
                user["user_id"], user["username"], user["created_at"][:19]
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]✗[/red] 查询失败: {e}")
        raise typer.Exit(1)
    finally:
        client.close()
