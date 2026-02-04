#!/usr/bin/env python3
"""Verify that UI shows immediately and updates continuously."""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from debate.models import Side
from debate.prep.runner import run_strategy_agent


class MockAnthropicResponse:
    """Mock Anthropic API response with delay."""

    def __init__(self, text: str):
        self.content = [MagicMock(text=text)]


def create_mock_anthropic_with_delay():
    """Create mock Anthropic client that simulates API latency."""
    call_count = [0]

    async def async_sleep():
        # Simulate API call taking 1 second
        await asyncio.sleep(1)

    def create_message_mock(*args, **kwargs):
        """Generate synthetic responses with simulated delay."""
        call_count[0] += 1

        messages = kwargs.get("messages", [])
        if not messages:
            return MockAnthropicResponse("[]")

        prompt = messages[0].get("content", "")

        # Simulate API delay (sync version - blocks)
        import time

        time.sleep(0.5)  # Half second delay

        # Cycle through different response types
        cycle = call_count[0] % 4

        if cycle == 1:  # First call - support arguments
            response = json.dumps(
                [
                    {
                        "argument": "Economic harm from TikTok ban",
                        "search_intent": "economic impact studies",
                        "priority": "high",
                    },
                    {
                        "argument": "National security threat",
                        "search_intent": "data security surveillance",
                        "priority": "high",
                    },
                ]
            )
        elif cycle == 2:  # Second call - answer arguments
            response = json.dumps(
                [
                    {
                        "argument": "AT: Privacy already protected",
                        "search_intent": "privacy violations",
                        "priority": "high",
                    }
                ]
            )
        elif cycle == 3:  # Third call - impact chains
            response = json.dumps(
                [
                    {
                        "argument": "Impact: Economic decline causes poverty",
                        "search_intent": "recession unemployment poverty",
                        "priority": "medium",
                    }
                ]
            )
        else:  # Fourth call - deep dive
            response = json.dumps([])

        return MockAnthropicResponse(response)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = create_message_mock
    return mock_client


async def test_continuous_ui():
    """Test that UI appears immediately and updates continuously."""
    print("\n" + "=" * 70)
    print("VERIFYING CONTINUOUS UI UPDATES")
    print("=" * 70)
    print("\nThis test will run for ~6 seconds.")
    print("Watch for:")
    print("  ✓ UI appears IMMEDIATELY (not after 6 seconds)")
    print("  ✓ Countdown timer decrements continuously")
    print("  ✓ New research directions appear as they're generated")
    print("  ✓ Agent status updates in real-time\n")

    input("Press Enter to start the test...")

    resolution = "Resolved: The US should ban TikTok"
    side = Side.PRO

    with patch("anthropic.Anthropic", return_value=create_mock_anthropic_with_delay()):
        result = await run_strategy_agent(
            resolution=resolution,
            side=side,
            session_id=None,
            duration_minutes=0.1,  # 6 seconds
            show_ui=True,
        )

    print(f"\n✓ Test completed: {result['tasks_created']} tasks created")
    print(f"Session ID: {result['session_id']}\n")


async def main():
    """Run verification test."""
    print("\n🔍 Continuous UI Update Verification")
    print("=" * 70)
    print("\nThis test verifies that:")
    print("1. UI appears immediately when agent starts")
    print("2. UI updates continuously during execution")
    print("3. Research directions appear in real-time")
    print("4. Countdown timer decrements smoothly")

    # Set dummy API key
    os.environ.setdefault("ANTHROPIC_API_KEY", "mock-key-for-testing")

    await test_continuous_ui()

    print("=" * 70)
    print("\nDid you observe:")
    print("  ✅ UI appeared immediately (not just at the end)?")
    print("  ✅ Countdown timer updated continuously?")
    print("  ✅ New research directions appeared as generated?")
    print("\nIf YES to all → BUG IS FIXED! ✅")
    print("If NO to any → Further investigation needed ❌\n")


if __name__ == "__main__":
    asyncio.run(main())
