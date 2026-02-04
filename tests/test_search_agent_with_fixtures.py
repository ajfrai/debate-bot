"""Test search agent with synthetic fixture data (no real API calls)."""

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.fixtures import enable_fixtures
from debate.prep.session import PrepSession
from debate.prep.search_agent import SearchAgent
from debate.models import Side


@pytest.mark.anyio
async def test_search_agent_with_fixtures():
    """Run search agent using fixture data instead of real APIs."""
    print("\n" + "=" * 60)
    print("SEARCH AGENT TEST - USING SYNTHETIC FIXTURES")
    print("=" * 60)
    print("\n✓ Fixture mode enabled (no real API calls)\n")

    # Enable fixtures to replace API calls
    enable_fixtures()

    # Create a test session
    session = PrepSession(
        resolution="Resolved: The US should pursue military action against Iran",
        side=Side.CON,
    )
    # Note: session_id is auto-generated, we just use it as-is

    # Create mock research tasks
    test_tasks = [
        {
            "id": "task_1",
            "argument": "Iran nuclear advancement threatens regional stability",
            "search_intent": "Find evidence on Iran's nuclear capability growth",
            "evidence_type": "support",
        },
        {
            "id": "task_2",
            "argument": "Military intervention would destabilize the region",
            "search_intent": "Find evidence on military conflict costs and risks",
            "evidence_type": "support",
        },
    ]

    # Write tasks to session
    for task in test_tasks:
        session.write_task(task)

    # Create and run search agent
    search = SearchAgent(session)

    print(f"Session ID: {session.session_id}")
    print(f"Resolution: {session.resolution}")
    print(f"Tasks to process: {len(test_tasks)}\n")

    # Verify tasks are actually in the session
    pending = session.get_pending_tasks()
    print(f"Verified pending tasks: {len(pending)}")
    print(f"Tasks available: {[t['id'] for t in pending]}\n")

    # Run for 30 seconds with agent
    print("Running agent loop for 30 seconds...")
    import time

    deadline = time.time() + 30
    try:
        await search.run(deadline)
    except Exception as e:
        print(f"Error during agent run: {e}")
        import traceback

        traceback.print_exc()

    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Tasks processed: {search.state.items_processed}")
    print(f"Results created: {search.state.items_created}")

    # Show created results
    results_dir = session.staging_dir / "search" / "results"
    if results_dir.exists():
        result_files = list(results_dir.glob("*.json"))
        print(f"Result files created: {len(result_files)}")
        for result_file in result_files:
            print(f"  - {result_file.name}")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(test_search_agent_with_fixtures())
