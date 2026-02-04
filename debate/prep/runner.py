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
from debate.prep.ui import print_summary, render_single_agent_ui, render_ui


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


async def run_strategy_agent(
    resolution: str,
    side: Side,
    session_id: str | None = None,
    duration_minutes: float = 5.0,
    show_ui: bool = True,
) -> dict[str, Any]:
    """Run only the StrategyAgent independently.

    Args:
        resolution: The debate resolution
        side: Which side to prep
        session_id: Existing session ID to continue, or None for new session
        duration_minutes: How long to run
        show_ui: Whether to show the terminal UI

    Returns:
        Summary dict with stats and paths
    """
    # Create or load session
    if session_id:
        from pathlib import Path

        staging_dir = Path("staging") / session_id
        if not staging_dir.exists():
            raise ValueError(f"Session {session_id} not found")
        session = PrepSession(resolution=resolution, side=side)
        session.session_id = session_id
        session.staging_dir = staging_dir
    else:
        session = PrepSession(resolution=resolution, side=side)

    # Create and run strategy agent
    strategy = StrategyAgent(session)
    deadline = time.time() + (duration_minutes * 60)

    # Run with or without UI
    if show_ui:
        # Start UI rendering first, then agent
        # This ensures UI displays before any blocking operations
        ui_task = asyncio.create_task(render_single_agent_ui(strategy, session, deadline))
        # Brief delay to let UI initialize
        await asyncio.sleep(0.1)
        # Now run agent
        agent_task = asyncio.create_task(strategy.run(deadline))
        # Wait for both to complete
        await asyncio.gather(ui_task, agent_task)
    else:
        await strategy.run(deadline)

    # Print summary
    print_summary(session, [strategy])

    return {
        "session_id": session.session_id,
        "staging_dir": str(session.staging_dir),
        "stats": session.get_stats(),
        "agent": "strategy",
        "tasks_created": strategy.state.items_created,
    }


async def run_search_agent(
    resolution: str,
    side: Side,
    session_id: str,
    duration_minutes: float = 5.0,
    show_ui: bool = True,
) -> dict[str, Any]:
    """Run only the SearchAgent independently.

    Args:
        resolution: The debate resolution
        side: Which side to prep
        session_id: Existing session ID with tasks to process
        duration_minutes: How long to run
        show_ui: Whether to show the terminal UI

    Returns:
        Summary dict with stats and paths
    """
    # Load existing session
    from pathlib import Path

    staging_dir = Path("staging") / session_id
    if not staging_dir.exists():
        raise ValueError(f"Session {session_id} not found")

    session = PrepSession(resolution=resolution, side=side)
    session.session_id = session_id
    session.staging_dir = staging_dir

    # Create search agent and check dependencies
    search = SearchAgent(session)
    deps_satisfied, deps_message = await search.check_dependencies()
    if not deps_satisfied:
        print(f"\n[SEARCH] {deps_message}\n")
        raise ValueError(deps_message)

    # Run the agent
    deadline = time.time() + (duration_minutes * 60)

    # Run with or without UI
    if show_ui:
        # Start UI rendering first, then agent
        ui_task = asyncio.create_task(render_single_agent_ui(search, session, deadline))
        await asyncio.sleep(0.1)
        agent_task = asyncio.create_task(search.run(deadline))
        await asyncio.gather(ui_task, agent_task)
    else:
        await search.run(deadline)

    # Print summary
    print_summary(session, [search])

    return {
        "session_id": session.session_id,
        "staging_dir": str(session.staging_dir),
        "stats": session.get_stats(),
        "agent": "search",
        "results_created": search.state.items_created,
    }


async def run_cutter_agent(
    resolution: str,
    side: Side,
    session_id: str,
    duration_minutes: float = 5.0,
    show_ui: bool = True,
) -> dict[str, Any]:
    """Run only the CutterAgent independently.

    Args:
        resolution: The debate resolution
        side: Which side to prep
        session_id: Existing session ID with search results to process
        duration_minutes: How long to run
        show_ui: Whether to show the terminal UI

    Returns:
        Summary dict with stats and paths
    """
    # Load existing session
    from pathlib import Path

    staging_dir = Path("staging") / session_id
    if not staging_dir.exists():
        raise ValueError(f"Session {session_id} not found")

    session = PrepSession(resolution=resolution, side=side)
    session.session_id = session_id
    session.staging_dir = staging_dir

    # Create cutter agent and check dependencies
    cutter = CutterAgent(session)
    deps_satisfied, deps_message = await cutter.check_dependencies()
    if not deps_satisfied:
        print(f"\n[CUTTER] {deps_message}\n")
        raise ValueError(deps_message)

    # Run the agent
    deadline = time.time() + (duration_minutes * 60)

    # Run with or without UI
    if show_ui:
        # Start UI rendering first, then agent
        ui_task = asyncio.create_task(render_single_agent_ui(cutter, session, deadline))
        await asyncio.sleep(0.1)
        agent_task = asyncio.create_task(cutter.run(deadline))
        await asyncio.gather(ui_task, agent_task)
    else:
        await cutter.run(deadline)

    # Print summary
    print_summary(session, [cutter])

    return {
        "session_id": session.session_id,
        "staging_dir": str(session.staging_dir),
        "stats": session.get_stats(),
        "agent": "cutter",
        "cards_created": cutter.state.items_created,
    }


async def run_organizer_agent(
    resolution: str,
    side: Side,
    session_id: str,
    duration_minutes: float = 5.0,
    show_ui: bool = True,
) -> dict[str, Any]:
    """Run only the OrganizerAgent independently.

    Args:
        resolution: The debate resolution
        side: Which side to prep
        session_id: Existing session ID with cards to organize
        duration_minutes: How long to run
        show_ui: Whether to show the terminal UI

    Returns:
        Summary dict with stats and paths
    """
    # Load existing session
    from pathlib import Path

    staging_dir = Path("staging") / session_id
    if not staging_dir.exists():
        raise ValueError(f"Session {session_id} not found")

    session = PrepSession(resolution=resolution, side=side)
    session.session_id = session_id
    session.staging_dir = staging_dir

    # Create organizer agent and check dependencies
    organizer = OrganizerAgent(session)
    deps_satisfied, deps_message = await organizer.check_dependencies()
    if not deps_satisfied:
        print(f"\n[ORGANIZER] {deps_message}\n")
        raise ValueError(deps_message)

    # Run the agent
    deadline = time.time() + (duration_minutes * 60)

    # Run with or without UI
    if show_ui:
        # Start UI rendering first, then agent
        ui_task = asyncio.create_task(render_single_agent_ui(organizer, session, deadline))
        await asyncio.sleep(0.1)
        agent_task = asyncio.create_task(organizer.run(deadline))
        await asyncio.gather(ui_task, agent_task)
    else:
        await organizer.run(deadline)

    # Print summary
    print_summary(session, [organizer])

    return {
        "session_id": session.session_id,
        "staging_dir": str(session.staging_dir),
        "stats": session.get_stats(),
        "agent": "organizer",
        "cards_organized": organizer.state.items_created,
    }
