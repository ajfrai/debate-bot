#!/usr/bin/env python3
"""Reproduction script for prep agent UI bug.

This script demonstrates that individual prep agents don't show UI progress.
Uses mocked API responses to avoid spending credits.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from debate.models import Side
from debate.prep.runner import run_prep, run_strategy_agent


class MockAnthropicResponse:
    """Mock Anthropic API response."""

    def __init__(self, text: str):
        self.content = [MagicMock(text=text)]


def create_mock_anthropic():
    """Create mock Anthropic client with synthetic responses."""

    def create_message_mock(*args, **kwargs):
        """Generate synthetic responses based on prompt."""
        messages = kwargs.get("messages", [])
        if not messages:
            return MockAnthropicResponse("[]")

        prompt = messages[0].get("content", "")

        # Strategy agent - enumerate arguments
        if "Generate 2-3 NEW arguments" in prompt:
            response = json.dumps(
                [
                    {
                        "argument": "TikTok ban eliminates 100k+ creator jobs",
                        "search_intent": "economic impact creator economy job losses",
                        "priority": "high",
                    },
                    {
                        "argument": "National security threat from data access",
                        "search_intent": "Chinese government data collection surveillance",
                        "priority": "high",
                    },
                ]
            )
            return MockAnthropicResponse(response)

        # Impact chains
        if "IMPACT CHAINS" in prompt:
            response = json.dumps(
                [
                    {
                        "argument": "Impact: Economic decline causes poverty",
                        "search_intent": "economic recession unemployment poverty rates",
                        "priority": "medium",
                    }
                ]
            )
            return MockAnthropicResponse(response)

        # Answers
        if "ANSWER arguments" in prompt:
            response = json.dumps(
                [
                    {
                        "argument": "AT: Privacy protections sufficient",
                        "search_intent": "privacy violations data breaches",
                        "priority": "high",
                    }
                ]
            )
            return MockAnthropicResponse(response)

        # Default empty response
        return MockAnthropicResponse("[]")

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = create_message_mock
    return mock_client


async def test_individual_agent():
    """Test individual strategy agent - should show NO UI (bug)."""
    print("\n" + "=" * 70)
    print("TEST 1: Running individual StrategyAgent (BUGGY - no UI)")
    print("=" * 70)
    print("\nExpected: Rich UI with agent status, countdown timer")
    print("Actual:   No UI, just prints at the end\n")

    resolution = "Resolved: The US should ban TikTok"
    side = Side.PRO

    with patch("anthropic.Anthropic", return_value=create_mock_anthropic()):
        result = await run_strategy_agent(
            resolution=resolution,
            side=side,
            session_id=None,
            duration_minutes=0.05,  # 3 seconds
        )

    print(f"\n✓ Completed: {result['tasks_created']} tasks created")
    print(f"Session ID: {result['session_id']}")


async def test_parallel_prep():
    """Test parallel prep - DOES show UI (working)."""
    print("\n" + "=" * 70)
    print("TEST 2: Running parallel prep (WORKING - has UI)")
    print("=" * 70)
    print("\nExpected: Rich UI with all 4 agents, countdown timer")
    print("Actual:   (see below)\n")

    resolution = "Resolved: The US should ban TikTok"
    side = Side.PRO

    # Mock both Anthropic and the other agents' work checks
    with patch("anthropic.Anthropic", return_value=create_mock_anthropic()):
        # Mock search/cutter/organizer to return no work (so they idle)
        with patch("debate.prep.search_agent.SearchAgent.check_for_work", return_value=[]):
            with patch("debate.prep.cutter_agent.CutterAgent.check_for_work", return_value=[]):
                with patch("debate.prep.organizer_agent.OrganizerAgent.check_for_work", return_value=[]):
                    result = await run_prep(
                        resolution=resolution,
                        side=side,
                        duration_minutes=0.05,  # 3 seconds
                        show_ui=True,
                    )

    print(f"\n✓ Completed")


async def main():
    """Run reproduction tests."""
    print("\n🐛 Prep Agent UI Bug Reproduction")
    print("=" * 70)
    print("\nThis demonstrates that individual prep agents don't show UI.")
    print("Using mocked API responses - no credits used.")

    # Set dummy API key
    os.environ.setdefault("ANTHROPIC_API_KEY", "mock-key-for-testing")

    # Test 1: Individual agent (buggy)
    await test_individual_agent()

    # Brief pause
    await asyncio.sleep(1)

    # Test 2: Parallel prep (working)
    await test_parallel_prep()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("\n❌ BUG: Individual agents don't show Rich UI during execution")
    print("✓  Expected: Live UI like parallel prep")
    print("✓  Actual: Only terminal output after completion\n")


if __name__ == "__main__":
    asyncio.run(main())
