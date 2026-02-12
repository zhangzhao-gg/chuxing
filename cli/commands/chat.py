"""
[INPUT]: 依赖 typer 的 Typer/Option，依赖 rich 的 Console/Markdown/Panel/Table，依赖 cli.client 的 APIClient，依赖 commands.agent 的 DEFAULT_MOMENT_DEFINITION，依赖标准库 threading/time/datetime
[OUTPUT]: 对外提供交互式对话命令（start）与批量对话压测命令（simulate）
[POS]: cli/commands 的核心对话命令，被 cli/main.py 注册；start 用于人工对话，simulate 用于多人设 moment 识别测试
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import typer
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple
import threading
import time

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from ..client import APIClient
from .agent import DEFAULT_MOMENT_DEFINITION

app = typer.Typer()
console = Console()
BJ_TZ = timezone(timedelta(hours=8))


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        s = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _fmt_bj(value: Any) -> str:
    dt = _parse_dt(value)
    if not dt:
        return ""
    # 仅用于展示：北京时间（UTC+8）
    return dt.astimezone(BJ_TZ).strftime("%Y-%m-%d %H:%M:%S")


@app.command("start")
def start_chat(
    user_id: str = typer.Option(..., "--user-id", "-u", help="用户 ID"),
    agent_id: str = typer.Option(..., "--agent-id", "-a", help="Agent ID"),
    api_url: str = typer.Option("http://localhost:8000", "--api-url", help="API 地址"),
    watch_reminders: bool = typer.Option(
        True,
        "--watch-reminders/--no-watch-reminders",
        help="是否后台监听新消息（用于到点兑现提醒自动输出）",
    ),
):
    """启动交互式对话

    用法示例：
        uv run cli chat start --user-id <user_id> --agent-id <agent_id>

    输入 'exit' 或 'quit' 退出对话
    """
    client = APIClient(api_url)
    stop_event = threading.Event()
    seen_lock = threading.Lock()
    seen_message_ids: set[str] = set()

    try:
        # 创建会话
        console.print("[cyan]正在创建会话...[/cyan]")
        conv = client.create_conversation(user_id, agent_id)
        conv_id = conv["conversation_id"]
        console.print(f"[green]✓[/green] 会话已创建: {conv_id}")
        console.print()

        def _watch_new_messages() -> None:
            """后台监听会话新消息（用于兑现提醒）。

            备注：
            - 单独创建 APIClient，避免跨线程复用 httpx.Client
            - 仅打印 role=assistant 且未展示过的消息（去重基于 message_id）
            """
            watcher = APIClient(api_url)
            try:
                # 初始化：把现有消息标记为已读，避免一启动就刷屏
                try:
                    initial = watcher.get_messages(conv_id, limit=200)
                except Exception:
                    initial = []
                with seen_lock:
                    for m in initial:
                        mid = m.get("message_id")
                        if mid:
                            seen_message_ids.add(str(mid))

                while not stop_event.is_set():
                    try:
                        msgs = watcher.get_messages(conv_id, limit=50)
                        new_msgs: List[Dict[str, Any]] = []
                        with seen_lock:
                            for m in msgs:
                                if m.get("role") != "assistant":
                                    continue
                                mid = m.get("message_id")
                                if not mid:
                                    continue
                                mid_s = str(mid)
                                if mid_s in seen_message_ids:
                                    continue
                                seen_message_ids.add(mid_s)
                                new_msgs.append(m)

                        # 统一输出（避免一条条刷）
                        for m in new_msgs:
                            content = m.get("content") or ""
                            if not str(content).strip():
                                continue
                            bj = _fmt_bj(m.get("created_at"))
                            title = (
                                "[bold magenta]Reminder[/bold magenta]"
                                if not bj
                                else f"[bold magenta]Reminder（北京时间 {bj}）[/bold magenta]"
                            )
                            console.print()
                            console.print(
                                Panel(
                                    Markdown(str(content)),
                                    title=title,
                                    border_style="magenta",
                                )
                            )
                            console.print()
                    except Exception:
                        # 监听失败不影响主对话：静默退避
                        pass

                    time.sleep(1.0)
            finally:
                watcher.close()

        watcher_thread: Optional[threading.Thread] = None
        if watch_reminders:
            watcher_thread = threading.Thread(
                target=_watch_new_messages, name="chat_message_watcher", daemon=True
            )
            watcher_thread.start()

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

                # 去重：主线程打印的 assistant 回复也加入 seen，避免 watcher 重复输出
                with seen_lock:
                    mid = response.get("message_id")
                    if mid:
                        seen_message_ids.add(str(mid))

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
        stop_event.set()
        client.close()


def _compose_system_prompt(name: str, persona_constraints: str) -> str:
    parts: List[str] = []
    agent_name = name.strip()
    if agent_name:
        parts.append(f"你的名字是：{agent_name}")
    parts.append(persona_constraints.strip())
    parts.append(DEFAULT_MOMENT_DEFINITION.strip())
    return "\n\n".join([p for p in parts if p])


def _build_benchmark_messages(turns: int) -> List[str]:
    """构造固定的 50+ 轮用户消息，用于比较不同人设的 moment 产出差异。"""
    base: List[str] = [
        # --- event: 明确时间/地点 ---
        "明天早上8点我要去体检，有点紧张。",
        "下周三下午3点要做项目评审，我怕讲不好。",
        "今晚9点我想去跑步，但我现在有点懒。",
        "后天中午和朋友吃饭，我有点社恐。",
        "周五晚上我爸妈来我家，我要准备一顿饭。",
        "明天晚上我有个面试，感觉压力很大。",
        "下个月初我要搬家，事情很多很乱。",
        "这周六早上10点要去银行办点事，别迟到。",
        "明天我准备把简历改完投出去。",
        "今晚我想早点睡，明天要早起。",
        # --- habit: 习惯/坚持 ---
        "我想从今天开始每天睡前写10分钟日记。",
        "我想每周至少跑步3次，坚持一个月。",
        "我准备戒糖，但总是忍不住。",
        "我想每天早上起床后冥想5分钟。",
        "我想每天晚上11点前睡觉。",
        "我想每天喝够两升水，但经常忘。",
        "我想把刷短视频控制在每天30分钟以内。",
        "我打算每周末整理一次房间。",
        "我想每天背20个英语单词，坚持下去。",
        "我想每天下班后散步20分钟。",
        # --- emotion: 强情绪但不一定有事件 ---
        "我今天突然很烦躁，什么都不想做。",
        "我有点焦虑，感觉自己一直在原地打转。",
        "我刚刚特别沮丧，觉得自己很失败。",
        "我今天很开心，事情都顺了很多。",
        "我有点害怕明天会出问题。",
        "我突然很委屈，但又说不出来为什么。",
        "我现在心跳有点快，可能是紧张。",
        "我今天很兴奋，想做点大事。",
        "我有点难过，想一个人待会儿。",
        "我觉得自己快要崩溃了。",
        # --- neutral: 降噪，避免每句都可做 moment ---
        "你觉得我这种状态正常吗？",
        "我想听你说说我应该怎么调整。",
        "我现在只想有人陪我聊聊。",
        "我不确定自己到底在怕什么。",
        "我今天工作挺忙的，脑子一团浆糊。",
        "你能用更具体的步骤帮我吗？",
        "我想先把今天熬过去。",
        "你觉得我需要休息吗？",
        "我想让自己更自律一点。",
        "你可以问我几个问题，帮我理清思路吗？",
        # --- mixed: 事件+情绪/行动 ---
        "明天开会前我想练一遍发言稿，你能陪我过一下吗？",
        "今晚我想把待办列出来，但我总是拖延。",
        "下周要交付，我想每天晚上复盘一下进度。",
        "我想在周末把房间收拾好，给自己一个更好的开始。",
        "明天早上我想6点起床，但我怕起不来。",
        "我担心我会在面试时脑子空白。",
        "我想请你明天提醒我别忘了体检的注意事项。",
        "我想坚持跑步，但我每次都半途而废。",
        "我想在情绪上来时先停下来呼吸10次。",
        "如果我明天还是很焦虑，你能主动问问我吗？",
    ]

    if turns <= len(base):
        return base[:turns]

    out: List[str] = []
    for i in range(turns):
        msg = base[i % len(base)]
        out.append(f"[Round {i+1}] {msg}")
    return out


def _moment_stats(moments: List[Dict[str, Any]]) -> Dict[str, Counter]:
    return {
        "type": Counter([m.get("type") or "unknown" for m in moments]),
        "importance": Counter([m.get("importance") or "unknown" for m in moments]),
        "suggested_action": Counter(
            [m.get("suggested_action") or "unknown" for m in moments]
        ),
        "suggested_timing": Counter(
            [m.get("suggested_timing") or "unknown" for m in moments]
        ),
    }


def _md_escape_cell(value: Any, max_len: int = 60) -> str:
    s = "" if value is None else str(value)
    s = s.replace("\n", " ").replace("|", "\\|").strip()
    if len(s) > max_len:
        s = s[:max_len] + "…"
    return s


def _append_persona_section(
    md_lines: List[str],
    persona_name: str,
    persona_constraints: str,
    expected_range: Tuple[int, int],
    user_id: str,
    agent_id: str,
    conv_id: str,
    turns: int,
    transcript: List[Tuple[str, str]],
    moments: List[Dict[str, Any]],
) -> None:
    stats = _moment_stats(moments)
    moment_count = len(moments)
    freq = moment_count / max(turns, 1)
    pass_fail = "PASS" if (expected_range[0] <= moment_count <= expected_range[1]) else "FAIL"

    md_lines.append(f"## 人设：{persona_name}")
    md_lines.append("")
    md_lines.append(f"- user_id: `{user_id}`")
    md_lines.append(f"- agent_id: `{agent_id}`")
    md_lines.append(f"- conversation_id: `{conv_id}`")
    md_lines.append(f"- turns: **{turns}**")
    md_lines.append(f"- moments: **{moment_count}**（频率 {freq:.1%}）")
    md_lines.append(
        f"- 期望范围: **[{expected_range[0]}, {expected_range[1]}]** / {turns} 轮 → **{pass_fail}**"
    )
    md_lines.append("")
    md_lines.append("### 人设约束")
    md_lines.append("")
    md_lines.append("```")
    md_lines.append(persona_constraints.strip())
    md_lines.append("```")
    md_lines.append("")
    md_lines.append("### 统计概览")
    md_lines.append("")
    md_lines.append(f"- type: {dict(stats['type'])}")
    md_lines.append(f"- importance: {dict(stats['importance'])}")
    md_lines.append(f"- suggested_action: {dict(stats['suggested_action'])}")
    md_lines.append(f"- suggested_timing: {dict(stats['suggested_timing'])}")
    md_lines.append("")
    md_lines.append("### Moments 列表（按 event_time）")
    md_lines.append("")
    md_lines.append("| # | event_time | type | importance | action | timing | description | reason |")
    md_lines.append("|---:|---|---|---|---|---|---|---|")
    for idx, m in enumerate(moments, start=1):
        md_lines.append(
            f"| {idx} | {_md_escape_cell(str(m.get('event_time',''))[:19].replace('T',' '), 40)}"
            f" | {_md_escape_cell(m.get('type'))}"
            f" | {_md_escape_cell(m.get('importance'))}"
            f" | {_md_escape_cell(m.get('suggested_action'))}"
            f" | {_md_escape_cell(m.get('suggested_timing'))}"
            f" | {_md_escape_cell(m.get('event_description'))}"
            f" | {_md_escape_cell(m.get('reason'))} |"
        )
    md_lines.append("")
    md_lines.append("### 对话转录（前10轮）")
    md_lines.append("")
    for i, (u, a) in enumerate(transcript[:10], start=1):
        md_lines.append(f"#### Round {i}")
        md_lines.append("")
        md_lines.append(f"**User**: {u}")
        md_lines.append("")
        md_lines.append(f"**Assistant**: {a}")
        md_lines.append("")


@app.command("simulate")
def simulate_chat(
    turns: int = typer.Option(50, "--turns", "-t", help="每个人设对话轮数（>=50）"),
    api_url: str = typer.Option("http://localhost:8000", "--api-url", help="API 地址"),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="Agent 模型名"),
    out_dir: Path = typer.Option(
        Path("docs/reports"),
        "--out-dir",
        help="报告输出目录（默认 docs/reports）",
        dir_okay=True,
        file_okay=False,
        readable=False,
        writable=True,
    ),
    out_md: Optional[Path] = typer.Option(
        None,
        "--out-md",
        help="可选：指定单个 Markdown 报告路径（默认写入 --out-dir 并带时间戳）",
        dir_okay=False,
        file_okay=True,
        readable=False,
        writable=True,
    ),
    user_id: Optional[str] = typer.Option(
        None,
        "--user-id",
        help="可选：复用既有 user_id；不传则自动创建 benchmark 用户",
    ),
):
    """批量对话压测 + 单文件关键时刻报告（4种人设，各>=50轮）"""
    if turns < 50:
        console.print("[red][ERR][/red] --turns 必须 >= 50")
        raise typer.Exit(1)

    client = APIClient(api_url)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_md or (out_dir / f"moment_benchmark_{run_id}.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    personas: List[Dict[str, Any]] = [
        {
            "name": "佛系朋友（极低频）",
            "expected": (0, max(1, turns // 50)),
            "persona": """
你是一个佛系朋友，主要负责陪聊，不主动“记录关键时刻”。
除非用户明确提出“需要提醒/需要你之后主动问我/需要你打电话”这类请求，否则 moment 必须为 null。
即使出现时间/计划/习惯，也优先给建议与共情，不要轻易产出 moment。
""",
        },
        {
            "name": "理性工程师（低频）",
            "expected": (1, max(6, turns // 10)),
            "persona": """
你是理性、克制的工程师型陪伴者：只有“明显会需要后续触达”的情况才记录 moment。
阈值要求：
- emotion_level >= 4 的强烈情绪，且用户需要支持/回访
- 明确的未来事件（有时间点）且重要程度 mid/high
- 明确提出要坚持的习惯，且用户表达“容易忘/坚持不住”
除此之外 moment 必须为 null。
""",
        },
        {
            "name": "温柔教练（中频）",
            "expected": (max(5, turns // 12), max(12, turns // 4)),
            "persona": """
你是温柔的生活教练，愿意帮助用户把“可行动的关键点”记录下来以便后续触达。
规则：
- 用户提到未来事件/时间点、习惯计划、或明显情绪波动时，倾向于产出 moment
- 但要避免每句话都产出：只记录“你认为后续触达真的有价值”的那部分
一般频率控制在大约每 4-10 轮出现 1 个 moment。
""",
        },
        {
            "name": "高敏感守护者（高频）",
            "expected": (max(15, turns // 4), max(30, turns // 2)),
            "persona": """
你是高敏感的守护者，会积极捕捉值得后续触达的关键时刻。
只要用户提到：未来事件（哪怕较小）、想坚持的习惯、或明显情绪变化，你都更倾向于产出 moment。
注意：moment 必须有清晰的 time 与 event_description，reason 写清楚“为什么值得后续触达”。
""",
        },
    ]

    try:
        if not user_id:
            username = f"benchmark_{run_id}"
            console.print(f"[cyan]创建 benchmark 用户: {username}[/cyan]")
            user = client.create_user(username)
            user_id = user["user_id"]
        console.print(f"[green][OK][/green] user_id={user_id}")

        dataset = _build_benchmark_messages(turns)

        md_lines: List[str] = []
        md_lines.append("# 关键时刻识别基准测试（单文件报告）")
        md_lines.append("")
        md_lines.append(f"- run_id: `{run_id}`")
        md_lines.append(f"- api_url: `{api_url}`")
        md_lines.append(f"- model: `{model}`")
        md_lines.append(f"- turns_per_persona: **{turns}**")
        md_lines.append(f"- user_id: `{user_id}`")
        md_lines.append("")
        md_lines.append("## 测试数据（用户消息序列）")
        md_lines.append("")
        for i, msg in enumerate(dataset, start=1):
            md_lines.append(f"{i}. {msg}")
        md_lines.append("")

        summary_rows: List[Tuple[str, str, str, int, str]] = []

        for p in personas:
            persona_name: str = p["name"]
            persona_constraints: str = p["persona"]
            expected: Tuple[int, int] = p["expected"]

            agent_name = f"BENCH_{persona_name}"
            system_prompt = _compose_system_prompt(agent_name, persona_constraints)
            console.print(f"\n[yellow]=== {persona_name} ===[/yellow]")

            agent = client.create_agent(agent_name, system_prompt, model=model)
            agent_id = agent["agent_id"]
            conv = client.create_conversation(
                user_id, agent_id, title=f"moment_benchmark:{persona_name}:{run_id}"
            )
            conv_id = conv["conversation_id"]
            console.print(f"[green][OK][/green] agent_id={agent_id} conv_id={conv_id}")

            transcript: List[Tuple[str, str]] = []
            for i, msg in enumerate(dataset, start=1):
                console.print(f"[dim]{persona_name} {i}/{turns}[/dim]")
                resp = client.send_message(conv_id, msg)
                transcript.append((msg, resp.get("content", "")))

            all_moments = client.list_moments(user_id, limit=500)
            conv_moments = [
                m for m in all_moments if m.get("conversation_id") == conv_id
            ]
            conv_moments = sorted(conv_moments, key=lambda x: x.get("event_time") or "")

            moment_count = len(conv_moments)
            freq = moment_count / max(turns, 1)
            pass_fail = "PASS" if (expected[0] <= moment_count <= expected[1]) else "FAIL"
            summary_rows.append(
                (persona_name, agent_id, conv_id, moment_count, f"{freq:.1%} {pass_fail}")
            )

            _append_persona_section(
                md_lines=md_lines,
                persona_name=persona_name,
                persona_constraints=persona_constraints,
                expected_range=expected,
                user_id=user_id,
                agent_id=agent_id,
                conv_id=conv_id,
                turns=turns,
                transcript=transcript,
                moments=conv_moments,
            )

        md_lines.append("## 汇总")
        md_lines.append("")
        md_lines.append("| persona | moments | freq/result | agent_id | conversation_id |")
        md_lines.append("|---|---:|---|---|---|")
        for persona_name, agent_id, conv_id, moment_count, freq_result in summary_rows:
            md_lines.append(
                f"| {persona_name} | {moment_count} | {freq_result} | `{agent_id}` | `{conv_id}` |"
            )
        md_lines.append("")

        report_path.write_text("\n".join(md_lines), encoding="utf-8")
        console.print(f"[green][OK][/green] 单文件报告已生成: {report_path.as_posix()}")

        table = Table(title=f"Moment Benchmark Summary ({run_id})")
        table.add_column("Persona", style="cyan")
        table.add_column("Moments", style="yellow", justify="right")
        table.add_column("Freq/Result", style="magenta")
        for persona_name, _, _, moment_count, freq_result in summary_rows:
            table.add_row(persona_name, str(moment_count), freq_result)
        console.print()
        console.print(table)

    except Exception as e:
        console.print(f"[red][ERR][/red] simulate 失败: {e}")
        raise typer.Exit(1)
    finally:
        client.close()
