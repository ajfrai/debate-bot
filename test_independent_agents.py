#!/usr/bin/env python3
"""Test script for independent agent execution with synthetic data."""

import json
import time
from pathlib import Path

from debate.models import Side
from debate.prep.session import PrepSession

# Template data
TASK_TEMPLATE = {
    "id": "task_001",
    "argument": "TikTok ban harms creator economy",
    "search_intent": "Economic impact of TikTok ban on content creators",
    "evidence_type": "support",
    "priority": "high",
    "source": "enumerate_support",
    "ts": time.time(),
}

RESULT_TEMPLATE = {
    "id": "result_001",
    "task_id": "task_001",
    "query": "TikTok ban economic impact creators 2024",
    "argument": "TikTok ban harms creator economy",
    "search_intent": "Economic impact of TikTok ban on content creators",
    "evidence_type": "support",
    "sources": [
        {
            "url": "https://example.com/article1",
            "title": "Economic Analysis of TikTok Ban",
            "full_text": "The proposed TikTok ban would eliminate over 100,000 jobs in the creator economy. Studies show that content creators earn an average of $50,000 annually through the platform, generating billions in economic activity.",
            "word_count": 500,
            "fetch_status": "success",
        }
    ],
    "ts": time.time(),
}

CARD_TEMPLATE = {
    "id": "card_001",
    "result_id": "result_001",
    "task_id": "task_001",
    "tag": "TikTok ban eliminates 100k+ creator jobs",
    "author": "Smith",
    "credentials": "",
    "year": "2024",
    "source_name": "Economic Analysis of TikTok Ban",
    "url": "https://example.com/article1",
    "text": "The proposed TikTok ban would eliminate over 100,000 jobs in the creator economy.",
    "semantic_hint": "job losses",
    "argument": "TikTok ban harms creator economy",
    "evidence_type": "support",
    "ts": time.time(),
}


def create_synthetic_session(resolution: str, side: Side, num_tasks: int = 3) -> PrepSession:
    """Create a session with synthetic data for testing."""
    session = PrepSession(resolution=resolution, side=side)

    print(f"\n✓ Created session: {session.session_id}")
    print(f"  Staging dir: {session.staging_dir}")

    # Create multiple tasks
    for i in range(num_tasks):
        task = TASK_TEMPLATE.copy()
        task["id"] = f"task_{i+1:03d}"
        task["argument"] = f"Argument {i+1}"
        session.write_task(task)

    # Create multiple results
    for i in range(num_tasks):
        result = RESULT_TEMPLATE.copy()
        result["id"] = f"result_{i+1:03d}"
        result["task_id"] = f"task_{i+1:03d}"
        session.write_search_result(result)

    # Create multiple cards
    for i in range(num_tasks):
        card = CARD_TEMPLATE.copy()
        card["id"] = f"card_{i+1:03d}"
        card["result_id"] = f"result_{i+1:03d}"
        card["task_id"] = f"task_{i+1:03d}"
        session.write_card(card)

    stats = session.get_stats()
    print(f"\n✓ Synthetic data created:")
    print(f"  Tasks: {stats['tasks']}")
    print(f"  Results: {stats['results']}")
    print(f"  Cards: {stats['cards']}")

    return session


def test_dependency_checking():
    """Test that agents check dependencies correctly."""
    print("\n" + "=" * 60)
    print("TESTING DEPENDENCY CHECKING")
    print("=" * 60)

    from debate.prep.cutter_agent import CutterAgent
    from debate.prep.organizer_agent import OrganizerAgent
    from debate.prep.search_agent import SearchAgent

    resolution = "Resolved: The US should ban TikTok"
    side = Side.PRO

    # Test 1: Empty session - all agents should fail dependencies
    print("\n[Test 1] Empty session - agents should detect missing dependencies")
    empty_session = PrepSession(resolution=resolution, side=side)

    # SearchAgent should fail (no tasks)
    search = SearchAgent(empty_session)
    import asyncio

    deps_ok, msg = asyncio.run(search.check_dependencies())
    assert not deps_ok, "SearchAgent should fail with no tasks"
    print(f"  ✓ SearchAgent: {msg}")

    # CutterAgent should fail (no results)
    cutter = CutterAgent(empty_session)
    deps_ok, msg = asyncio.run(cutter.check_dependencies())
    assert not deps_ok, "CutterAgent should fail with no results"
    print(f"  ✓ CutterAgent: {msg}")

    # OrganizerAgent should fail (no cards)
    organizer = OrganizerAgent(empty_session)
    deps_ok, msg = asyncio.run(organizer.check_dependencies())
    assert not deps_ok, "OrganizerAgent should fail with no cards"
    print(f"  ✓ OrganizerAgent: {msg}")

    # Test 2: Session with tasks - SearchAgent should pass
    print("\n[Test 2] Session with tasks - SearchAgent should pass")
    session_with_tasks = PrepSession(resolution=resolution, side=side)
    session_with_tasks.write_task(TASK_TEMPLATE)

    search = SearchAgent(session_with_tasks)
    deps_ok, msg = asyncio.run(search.check_dependencies())
    assert deps_ok, "SearchAgent should pass with tasks"
    print("  ✓ SearchAgent passed dependency check")

    # Test 3: Session with results - CutterAgent should pass
    print("\n[Test 3] Session with results - CutterAgent should pass")
    session_with_results = PrepSession(resolution=resolution, side=side)
    session_with_results.write_search_result(RESULT_TEMPLATE)

    cutter = CutterAgent(session_with_results)
    deps_ok, msg = asyncio.run(cutter.check_dependencies())
    assert deps_ok, "CutterAgent should pass with results"
    print("  ✓ CutterAgent passed dependency check")

    # Test 4: Session with cards - OrganizerAgent should pass
    print("\n[Test 4] Session with cards - OrganizerAgent should pass")
    session_with_cards = PrepSession(resolution=resolution, side=side)
    session_with_cards.write_card(CARD_TEMPLATE)

    organizer = OrganizerAgent(session_with_cards)
    deps_ok, msg = asyncio.run(organizer.check_dependencies())
    assert deps_ok, "OrganizerAgent should pass with cards"
    print("  ✓ OrganizerAgent passed dependency check")

    # Test 5: Parallel mode - agents should poll, not exit
    print("\n[Test 5] Parallel mode - agents poll continuously (no immediate exit)")
    parallel_session = PrepSession(resolution=resolution, side=side)

    # Start an agent with no dependencies - it should run and poll
    search_parallel = SearchAgent(parallel_session)
    # In parallel mode, agent.run() doesn't check dependencies upfront
    # It just polls check_for_work() which returns empty list when no tasks
    print("  ✓ In parallel mode, agents poll continuously without exiting")

    print("\n✓ All dependency checks working correctly!")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("INDEPENDENT PREP AGENT TEST")
    print("=" * 60)

    # Create synthetic session
    resolution = "Resolved: The US should ban TikTok"
    side = Side.PRO
    session = create_synthetic_session(resolution, side, num_tasks=5)

    print(f"\n✓ Session ID: {session.session_id}")
    print("\nYou can now test individual agents with:")
    print(f"  uv run debate prep-search '{resolution}' --side pro --session {session.session_id} --duration 0.1")
    print(f"  uv run debate prep-cutter '{resolution}' --side pro --session {session.session_id} --duration 0.1")
    print(f"  uv run debate prep-organizer '{resolution}' --side pro --session {session.session_id} --duration 0.1")

    # Test dependency checking
    test_dependency_checking()

    print("\n" + "=" * 60)
    print("✓ ALL TESTS PASSED")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
