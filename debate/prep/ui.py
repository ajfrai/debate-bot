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


def create_agent_panel(agent: "BaseAgent", width: int = 60) -> Panel:
    """Create a Rich panel for an agent's status."""
    state = agent.state

    # Status line
    status_color = get_status_color(state.status)
    status_symbol = get_status_symbol(state.status)

    # Build content
    lines = []

    # Recent actions (last 3)
    for action in state.recent_actions[-3:]:
        lines.append(f"  {status_symbol} {action[: width - 10]}")

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
        layout["strategy"].update(create_agent_panel(agent_by_name["strategy"]))
    if "search" in agent_by_name:
        layout["search"].update(create_agent_panel(agent_by_name["search"]))
    if "cutter" in agent_by_name:
        layout["cutter"].update(create_agent_panel(agent_by_name["cutter"]))
    if "organizer" in agent_by_name:
        layout["organizer"].update(create_agent_panel(agent_by_name["organizer"]))

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

    with Live(console=console, refresh_per_second=int(1 / refresh_rate)) as live:
        while time.time() < deadline:
            time_remaining = deadline - time.time()
            layout = create_layout(agents, session, time_remaining)
            live.update(layout)
            await asyncio.sleep(refresh_rate)

        # Final update
        layout = create_layout(agents, session, 0)
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
