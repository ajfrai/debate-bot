"""Runner for parallel prep agents."""

import asyncio
import time
from typing import Any

from debate.models import Side
from debate.prep.brief_renderer import finalize_brief
from debate.prep.cutter_agent import CutterAgent
from debate.prep.organizer_agent import OrganizerAgent
from debate.prep.search_agent import SearchAgent
from debate.prep.session import PrepSession
from debate.prep.strategy_agent import StrategyAgent
from debate.prep.ui import print_summary, render_ui


async def run_prep(
    resolution: str,
    side: Side,
    duration_minutes: float = 5.0,
    show_ui: bool = True,
) -> dict[str, Any]:
    """Run parallel prep agents for the specified duration.

    Args:
        resolution: The debate resolution
        side: Which side to prep
        duration_minutes: How long to run prep
        show_ui: Whether to show the terminal UI

    Returns:
        Summary dict with stats and paths
    """
    # Create session
    session = PrepSession(resolution=resolution, side=side)

    # Create agents
    strategy = StrategyAgent(session)
    search = SearchAgent(session)
    cutter = CutterAgent(session)
    organizer = OrganizerAgent(session)

    agents = [strategy, search, cutter, organizer]

    # Calculate deadline
    deadline = time.time() + (duration_minutes * 60)

    # Run all agents concurrently
    if show_ui:
        # Run agents and UI in parallel
        await asyncio.gather(
            strategy.run(deadline),
            search.run(deadline),
            cutter.run(deadline),
            organizer.run(deadline),
            render_ui(agents, session, deadline),
        )
    else:
        # Run agents without UI
        await asyncio.gather(
            strategy.run(deadline),
            search.run(deadline),
            cutter.run(deadline),
            organizer.run(deadline),
        )

    # Print summary
    print_summary(session, agents)

    # Finalize: save brief to evidence storage
    try:
        evidence_path = finalize_brief(session.staging_dir, resolution, side)
        print(f"\n[bold green]Evidence saved to:[/bold green] {evidence_path}")
    except Exception as e:
        print(f"\n[yellow]Warning: Could not save evidence: {e}[/yellow]")
        evidence_path = None

    # Return summary
    stats = session.get_stats()
    return {
        "session_id": session.session_id,
        "staging_dir": str(session.staging_dir),
        "evidence_path": evidence_path,
        "stats": stats,
        "agent_stats": {
            a.name: {
                "processed": a.state.items_processed,
                "created": a.state.items_created,
            }
            for a in agents
        },
    }


def run_prep_sync(
    resolution: str,
    side: Side,
    duration_minutes: float = 5.0,
    show_ui: bool = True,
) -> dict[str, Any]:
    """Synchronous wrapper for run_prep.

    Args:
        resolution: The debate resolution
        side: Which side to prep
        duration_minutes: How long to run prep
        show_ui: Whether to show the terminal UI

    Returns:
        Summary dict with stats and paths
    """
    return asyncio.run(run_prep(resolution, side, duration_minutes, show_ui))
