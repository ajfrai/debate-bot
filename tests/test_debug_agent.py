"""Debug search agent behavior with fixtures."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.fixtures import enable_fixtures
from debate.prep.session import PrepSession
from debate.prep.search_agent import SearchAgent
from debate.models import Side


@pytest.mark.anyio
async def test():
    """Debug agent processing."""
    enable_fixtures()

    # Create session and agent
    session = PrepSession(resolution="Test", side=Side.CON)
    search = SearchAgent(session)

    # Create one task
    session.write_task({
        "id": "debug_1",
        "argument": "Test arg",
        "search_intent": "Test intent",
        "evidence_type": "support",
    })

    pending = session.get_pending_tasks()
    print(f"Pending tasks: {len(pending)}\n")

    # Run one iteration manually
    print("=== Manual iteration ===")
    work = await search.check_for_work()
    print(f"Work found: {len(work)}")
    if work:
        print(f"Processing task: {work[0]['id']}")
        await search.process_item(work[0])
        print(f"Done")

    print(f"\nItems processed: {search.state.items_processed}")
    print(f"Items created: {search.state.items_created}")

    # Check what was created
    results_dir = session.staging_dir / "search" / "results"
    if results_dir.exists():
        print(f"Result files: {len(list(results_dir.glob('*.json')))}")


if __name__ == "__main__":
    asyncio.run(test())
