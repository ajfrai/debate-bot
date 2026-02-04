"""Terminal UI for parallel prep agents using Rich."""

import asyncio
import time
from typing import TYPE_CHECKING

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from debate.prep.base_agent import BaseAgent
    from debate.prep.session import PrepSession


def format_time_remaining(seconds: float) -> str:
    """Format seconds as MM:SS."""
    if seconds <= 0:
        return "0:00"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


def get_status_color(status: str) -> str:
    """Get color for agent status."""
    colors = {
        "working": "green",
        "checking": "yellow",
        "waiting": "blue",
        "idle": "dim",
        "stopped": "red",
        "starting": "cyan",
    }
    return colors.get(status, "white")


def get_status_symbol(status: str) -> str:
    """Get symbol for agent status."""
    symbols = {
        "working": "●",
        "checking": "○",
        "waiting": "◌",
        "idle": "○",
        "stopped": "■",
        "starting": "◐",
    }
    return symbols.get(status, "○")


def create_agent_panel(
    agent: "BaseAgent", width: int = 60, show_details: bool = False, session: "PrepSession | None" = None
) -> Panel:
    """Create a Rich panel for an agent's status.

    Args:
        agent: The agent to display
        width: Panel width
        show_details: If True, show more details (for single-agent view)
        session: PrepSession for getting task stats (optional)
    """
    state = agent.state

    # Status line
    status_color = get_status_color(state.status)
    status_symbol = get_status_symbol(state.status)

    # Build content
    lines = []

    # Show current research direction if available (for strategy agent)
    if state.current_direction:
        direction_text = state.current_direction
        if len(direction_text) > width - 6:
            direction_text = direction_text[: width - 9] + "..."
        lines.append(f"[bold cyan]🔍 Researching:[/bold cyan] {direction_text}")
        lines.append("")  # Blank line for separation

    # Show search agent top status section
    if agent.name == "search" and show_details:
        # Show current argument being researched
        if state.current_argument:
            arg_text = state.current_argument
            if len(arg_text) > width - 15:
                arg_text = arg_text[: width - 18] + "..."
            lines.append(f"[bold cyan]🎯 Argument:[/bold cyan] {arg_text}")

        # Show current query
        if state.current_query:
            query_text = state.current_query
            if len(query_text) > width - 10:
                query_text = query_text[: width - 13] + "..."
            lines.append(f"[bold yellow]🔎 Query:[/bold yellow] {query_text}")

        # Show current fetch target
        if state.current_source:
            source_text = state.current_source
            if len(source_text) > width - 10:
                source_text = source_text[: width - 13] + "..."
            lines.append(f"[bold blue]📄 Fetching:[/bold blue] {source_text}")

        # Blank line for separation before kanban
        if state.current_argument or state.current_query or state.current_source:
            lines.append("")

    # Kanban board for search agent
    if agent.name == "search" and state.task_stages:
        # Group tasks by stage
        stages = {"queued": [], "query": [], "search": [], "fetch": [], "done": [], "error": []}
        for task_id, stage in state.task_stages.items():
            if stage in stages:
                stages[stage].append(task_id)

        # Build kanban header with fixed width columns
        col_width = 8
        headers = [
            ("[yellow]", "Queue", "[/yellow]"),
            ("[cyan]", "Query", "[/cyan]"),
            ("[blue]", "Search", "[/blue]"),
            ("[magenta]", "Fetch", "[/magenta]"),
            ("[green]", "Done", "[/green]"),
            ("[red]", "Error", "[/red]"),
        ]
        header_parts = []
        for start_tag, text, end_tag in headers:
            padded = f"{text:<{col_width}}"
            header_parts.append(f"{start_tag}{padded}{end_tag}")
        lines.append(f"  {' | '.join(header_parts)}")

        # Build kanban rows (show up to 3 tasks per column)
        max_rows = 3
        for i in range(max_rows):
            row_parts = []
            for stage in ["queued", "query", "search", "fetch", "done", "error"]:
                tasks = stages[stage]
                if i < len(tasks):
                    task_id = tasks[i]
                    # For error column, show error reason if available
                    if stage == "error" and task_id in state.task_errors:
                        error_msg = state.task_errors[task_id]
                        # Truncate error message to fit
                        display = f"{task_id[:4]}:{error_msg[:3]}"[:col_width]
                        row_parts.append(f"[red]{display:<{col_width}}[/red]")
                    else:
                        task_display = task_id[:col_width]  # Truncate to col_width
                        row_parts.append(f"{task_display:<{col_width}}")
                else:
                    row_parts.append(" " * col_width)
            lines.append(f"  {' | '.join(row_parts)}")

        # Show overflow counts if needed
        overflow = []
        for stage, color in [
            ("queued", "yellow"),
            ("query", "cyan"),
            ("search", "blue"),
            ("fetch", "magenta"),
            ("done", "green"),
            ("error", "red"),
        ]:
            count = len(stages[stage])
            if count > max_rows:
                overflow.append(f"[{color}]+{count - max_rows} {stage}[/{color}]")

        if overflow:
            lines.append(f"  {', '.join(overflow)}")

        lines.append("")  # Blank line for separation

    # Show status if no content
    if not lines:
        lines.append(f"  {status_symbol} {state.status}")

    # Stats line
    stats = f"Processed: {state.items_processed} | Created: {state.items_created}"
    lines.append(f"  [{stats}]")

    content = "\n".join(lines)

    # Panel with colored border based on status
    return Panel(
        content,
        title=f"[bold]{state.name.title()} Agent[/bold]",
        border_style=status_color,
        width=width,
    )


def create_stats_panel(session: "PrepSession", time_remaining: float) -> Panel:
    """Create a panel showing session statistics."""
    stats = session.get_stats()

    table = Table.grid(padding=(0, 2))
    table.add_column(justify="left")
    table.add_column(justify="right")

    table.add_row("Tasks:", str(stats["tasks"]))
    table.add_row("Search Results:", str(stats["results"]))
    table.add_row("Cards Cut:", str(stats["cards"]))
    table.add_row("Feedback:", str(stats["feedback"]))

    time_str = format_time_remaining(time_remaining)

    return Panel(
        table,
        title=f"[bold]Prep Session[/bold] | {time_str} remaining",
        border_style="cyan",
    )


def create_layout(
    agents: list["BaseAgent"],
    session: "PrepSession",
    time_remaining: float,
) -> Layout:
    """Create the full terminal layout."""
    layout = Layout()

    # Top row: Strategy and Search
    # Bottom row: Cutter and Organizer
    # Footer: Stats

    layout.split_column(
        Layout(name="top", ratio=2),
        Layout(name="bottom", ratio=2),
        Layout(name="footer", ratio=1),
    )

    layout["top"].split_row(
        Layout(name="strategy"),
        Layout(name="search"),
    )

    layout["bottom"].split_row(
        Layout(name="cutter"),
        Layout(name="organizer"),
    )

    # Assign panels
    agent_by_name = {a.name: a for a in agents}

    if "strategy" in agent_by_name:
        layout["strategy"].update(create_agent_panel(agent_by_name["strategy"], session=session))
    if "search" in agent_by_name:
        layout["search"].update(create_agent_panel(agent_by_name["search"], session=session))
    if "cutter" in agent_by_name:
        layout["cutter"].update(create_agent_panel(agent_by_name["cutter"], session=session))
    if "organizer" in agent_by_name:
        layout["organizer"].update(create_agent_panel(agent_by_name["organizer"], session=session))

    layout["footer"].update(create_stats_panel(session, time_remaining))

    return layout


async def render_ui(
    agents: list["BaseAgent"],
    session: "PrepSession",
    deadline: float,
    refresh_rate: float = 0.5,
) -> None:
    """Render the live terminal UI.

    Args:
        agents: List of agents to display
        session: The prep session
        deadline: Unix timestamp when prep ends
        refresh_rate: Seconds between UI updates
    """
    console = Console()

    # Print header
    console.print()
    console.print(f"[bold cyan]Debate Prep: {session.resolution}[/bold cyan]")
    console.print(f"[dim]Side: {session.side.value.upper()} | Session: {session.session_id}[/dim]")
    console.print()

    # Create initial layout BEFORE Live context to show immediately
    time_remaining = deadline - time.time()
    initial_layout = create_layout(agents, session, time_remaining)

    with Live(initial_layout, console=console, refresh_per_second=int(1 / refresh_rate)) as live:
        # Brief pause to ensure terminal is ready
        await asyncio.sleep(0.05)

        # Continuous update loop
        while time.time() < deadline:
            time_remaining = deadline - time.time()
            layout = create_layout(agents, session, time_remaining)
            live.update(layout)
            await asyncio.sleep(refresh_rate)

        # Final update
        layout = create_layout(agents, session, 0)
        live.update(layout)


def create_single_agent_layout(
    agent: "BaseAgent",
    session: "PrepSession",
    time_remaining: float,
) -> Layout:
    """Create a layout for a single agent view.

    Args:
        agent: The agent to display
        session: The prep session
        time_remaining: Seconds remaining

    Returns:
        Layout with agent panel and stats
    """
    layout = Layout()

    # Simple vertical split: agent panel on top, stats on bottom
    layout.split_column(
        Layout(name="agent", ratio=3),
        Layout(name="stats", ratio=1),
    )

    # Agent panel with extra details
    layout["agent"].update(create_agent_panel(agent, width=80, show_details=True, session=session))

    # Stats panel with countdown
    layout["stats"].update(create_stats_panel(session, time_remaining))

    return layout


async def render_single_agent_ui(
    agent: "BaseAgent",
    session: "PrepSession",
    deadline: float,
    refresh_rate: float = 0.5,
) -> None:
    """Render the live terminal UI for a single agent.

    Args:
        agent: The agent to display
        session: The prep session
        deadline: Unix timestamp when prep ends
        refresh_rate: Seconds between UI updates
    """
    console = Console()

    # Print header
    console.print()
    console.print(f"[bold cyan]{agent.state.name.title()} Agent: {session.resolution}[/bold cyan]")
    console.print(f"[dim]Side: {session.side.value.upper()} | Session: {session.session_id}[/dim]")
    console.print()

    # Create initial layout BEFORE Live context to show immediately
    time_remaining = deadline - time.time()
    initial_layout = create_single_agent_layout(agent, session, time_remaining)

    with Live(initial_layout, console=console, refresh_per_second=int(1 / refresh_rate)) as live:
        # Brief pause to ensure terminal is ready
        await asyncio.sleep(0.05)

        # Continuous update loop
        while time.time() < deadline:
            time_remaining = deadline - time.time()
            layout = create_single_agent_layout(agent, session, time_remaining)
            live.update(layout)
            await asyncio.sleep(refresh_rate)

        # Final update
        layout = create_single_agent_layout(agent, session, 0)
        live.update(layout)


def print_summary(session: "PrepSession", agents: list["BaseAgent"]) -> None:
    """Print a summary after prep completes."""
    console = Console()

    console.print()
    console.print("[bold green]Prep Complete![/bold green]")
    console.print()

    # Stats table
    stats = session.get_stats()
    table = Table(title="Session Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")

    table.add_row("Research Tasks", str(stats["tasks"]))
    table.add_row("Search Results", str(stats["results"]))
    table.add_row("Cards Cut", str(stats["cards"]))
    table.add_row("Feedback Generated", str(stats["feedback"]))

    console.print(table)
    console.print()

    # Agent stats
    for agent in agents:
        state = agent.state
        console.print(
            f"[bold]{state.name.title()} Agent:[/bold] {state.items_processed} processed, {state.items_created} created"
        )

    console.print()
    console.print(f"[dim]Staging directory: {session.staging_dir}[/dim]")
