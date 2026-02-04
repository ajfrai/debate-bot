#!/usr/bin/env python3
"""Demo of detailed research directions in strategy agent UI."""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from debate.models import Side
from debate.prep.runner import run_strategy_agent


class MockAnthropicResponse:
    """Mock Anthropic API response."""

    def __init__(self, text: str):
        self.content = [MagicMock(text=text)]


def create_mock_anthropic():
    """Create mock that shows different research directions."""
    call_count = [0]

    def create_message_mock(*args, **kwargs):
        call_count[0] += 1
        call_num = call_count[0]

        # Simulate realistic delays
        import time

        time.sleep(0.8)

        # Return different responses for different phases
        if call_num == 1:  # Support arguments
            response = json.dumps(
                [
                    {
                        "argument": "TikTok ban eliminates 100k+ creator jobs across digital economy",
                        "search_intent": "creator economy job losses statistics data",
                        "priority": "high",
                    },
                    {
                        "argument": "Small businesses lose critical marketing channel representing 3-5% of ROI",
                        "search_intent": "small business TikTok marketing ROI impact",
                        "priority": "high",
                    },
                ]
            )
        elif call_num == 2:  # Answer arguments
            response = json.dumps(
                [
                    {
                        "argument": "AT: Privacy concerns overstate actual data vulnerabilities",
                        "search_intent": "privacy legislation data protection existing safeguards",
                        "priority": "high",
                    }
                ]
            )
        elif call_num == 3:  # Impact chains
            response = json.dumps(
                [
                    {
                        "argument": "Impact: Economic disruption leads to increased poverty rates",
                        "search_intent": "economic recession unemployment poverty correlation",
                        "priority": "medium",
                    }
                ]
            )
        else:  # Deep dive
            response = json.dumps([])

        return MockAnthropicResponse(response)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = create_message_mock
    return mock_client


async def main():
    """Run demo showing research directions."""
    print("\n" + "=" * 80)
    print("RESEARCH DIRECTIONS UI DEMO")
    print("=" * 80)
    print("\nWatch the UI to see:")
    print("  🔍 Researching: Generating PRO arguments that support the resolution")
    print("  🔍 Researching: Generating ANSWER arguments that refute opponent claims")
    print("  🔍 Researching: Identifying terminal impacts and link chains for arguments")
    print("  ⚡ Deep dive: finding more evidence for '[specific argument]'")
    print("  ✨ Brief well-developed, exploring new angles")
    print("\nEach line shows exactly what the agent is working on RIGHT NOW.")
    print("=" * 80 + "\n")

    input("Press Enter to start 12-second demo...")

    os.environ.setdefault("ANTHROPIC_API_KEY", "mock-key")

    resolution = "Resolved: The US should ban TikTok"
    side = Side.PRO

    with patch("anthropic.Anthropic", return_value=create_mock_anthropic()):
        result = await run_strategy_agent(
            resolution=resolution,
            side=side,
            session_id=None,
            duration_minutes=0.2,  # 12 seconds
            show_ui=True,
        )

    print("\n" + "=" * 80)
    print("COMPLETED")
    print("=" * 80)
    print(f"\n✓ Tasks created: {result['tasks_created']}")
    print(f"✓ Session ID: {result['session_id']}")
    print("\nNotice how the UI showed you:")
    print("  ✅ Each research phase (support args, answer args, impacts, deep dive)")
    print("  ✅ Specific arguments being researched")
    print("  ✅ Progress in real-time (not just at the end)")
    print("  ✅ New research directions as they're generated\n")


if __name__ == "__main__":
    print("\n🔍 Strategy Agent Research Directions Demo")
    print("=" * 80)
    print("\nThis demo shows the enhanced UI that displays exactly what")
    print("research directions the strategy agent is pursuing.\n")

    asyncio.run(main())
