"""
[INPUT]: 依赖 typer 的 Typer/Option，依赖 rich.console 的 Console，依赖 cli.client 的 APIClient
[OUTPUT]: 对外提供 Agent 管理命令（create/list）
[POS]: cli/commands 的 Agent 管理命令，被 cli/main.py 注册
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from ..client import APIClient

app = typer.Typer()
console = Console()

DEFAULT_MOMENT_DEFINITION = """关键时刻（moment）定义（非常重要）：
- 你认为这件事你会有后续的动作和反应，例如在这件事发生之后打算给用户发个消息问问。
- 情绪波动严重的时候（例如强烈焦虑、恐惧、兴奋、悲伤等）需要给他打电话。
- 用户提到需要持续提醒/坚持的习惯（例如每天早起、每周跑步、戒糖等）

当且仅当你判断这是“值得被记录并在合适时间触达”的时刻，才在结构化输出的 moment 字段给出 is_moment=true；否则 moment=null。"""


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _compose_system_prompt(
    name: str,
    moment_definition: str,
    persona_constraints: Optional[str],
    base_prompt: Optional[str],
) -> str:
    parts = []
    
    if persona_constraints:
        parts.append(persona_constraints.strip())
    parts.append(moment_definition.strip())
    if base_prompt:
        parts.append(base_prompt.strip())
    return "\n\n".join([p for p in parts if p])


@app.command("create")
def create_agent(
    name: str = typer.Option(..., "--name", "-n", help="Agent 名称"),
    system_prompt: Optional[str] = typer.Option(
        None, "--system-prompt", "-s", help="补充提示词（可选；与 --system-prompt-file 二选一）"
    ),
    system_prompt_file: Optional[Path] = typer.Option(
        None,
        "--system-prompt-file",
        help="从文件读取补充提示词（UTF-8；与 --system-prompt 二选一）",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    moment_definition: Optional[str] = typer.Option(
        None,
        "--moment-definition",
        help="关键时刻定义（默认内置；与 --moment-definition-file 二选一）",
    ),
    moment_definition_file: Optional[Path] = typer.Option(
        None,
        "--moment-definition-file",
        help="从文件读取关键时刻定义（UTF-8；与 --moment-definition 二选一）",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    persona_constraints: Optional[str] = typer.Option(
        None,
        "--persona",
        help="人设约束（可选；与 --persona-file 二选一）",
    ),
    persona_file: Optional[Path] = typer.Option(
        None,
        "--persona-file",
        help="从文件读取人设约束（UTF-8；与 --persona 二选一）",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="OpenAI 模型名"),
    api_url: str = typer.Option("http://localhost:8000", "--api-url", help="API 地址"),
):
    """创建 Agent"""
    client = APIClient(api_url)
    try:
        # -------------------- 参数互斥校验 --------------------
        if system_prompt and system_prompt_file:
            raise ValueError("--system-prompt 与 --system-prompt-file 只能二选一")
        if moment_definition and moment_definition_file:
            raise ValueError("--moment-definition 与 --moment-definition-file 只能二选一")
        if persona_constraints and persona_file:
            raise ValueError("--persona 与 --persona-file 只能二选一")

        # -------------------- 读取文本块 --------------------
        base_prompt_text = (
            _read_text_file(system_prompt_file)
            if system_prompt_file
            else (system_prompt.strip() if system_prompt else None)
        )
        persona_text = (
            _read_text_file(persona_file)
            if persona_file
            else (persona_constraints.strip() if persona_constraints else None)
        )

        if moment_definition_file:
            moment_def_text = _read_text_file(moment_definition_file)
        elif moment_definition:
            moment_def_text = moment_definition.strip()
        else:
            moment_def_text = DEFAULT_MOMENT_DEFINITION

        # -------------------- 组合 system_prompt --------------------
        if not persona_text and not base_prompt_text:
            raise ValueError(
                "必须提供 --persona/--persona-file 或 --system-prompt/--system-prompt-file 至少一个"
            )

        final_prompt = _compose_system_prompt(
            moment_definition=moment_def_text,
            persona_constraints=persona_text,
            base_prompt=base_prompt_text,
        )

        agent = client.create_agent(name, final_prompt, model)
        console.print("[green][OK][/green] Agent 创建成功")
        console.print(f"  agent_id: {agent['agent_id']}")
        console.print(f"  name: {agent['name']}")
        console.print(f"  model: {agent['model']}")
    except Exception as e:
        console.print(f"[red][ERR][/red] 创建失败: {e}")
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
        console.print(f"[red][ERR][/red] 查询失败: {e}")
        raise typer.Exit(1)
    finally:
        client.close()
