#!/usr/bin/env python3
"""Debug script to check when UI actually displays."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from debate.models import Side
from debate.prep.runner import run_strategy_agent


class MockAnthropicResponse:
    """Mock Anthropic API response with intentional delay."""

    def __init__(self, text: str):
        self.content = [MagicMock(text=text)]


def create_mock_anthropic():
    """Create mock that simulates slow API calls."""

    def create_message_mock(*args, **kwargs):
        # Print when API is called
        print(f"[DEBUG {time.time():.2f}] API call started", flush=True)

        # Simulate slow API (2 seconds)
        time.sleep(2)

        print(f"[DEBUG {time.time():.2f}] API call finished", flush=True)

        response = json.dumps([
            {
                "argument": "Test argument 1",
                "search_intent": "test search",
                "priority": "high",
            }
        ])
        return MockAnthropicResponse(response)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = create_message_mock
    return mock_client


async def test_ui_timing():
    """Test when UI actually appears."""
    print("\n" + "=" * 70)
    print("UI TIMING DEBUG TEST")
    print("=" * 70)
    print("\nThis test runs for 10 seconds with slow API calls.")
    print("Watch for:")
    print("  1. When does the UI first appear?")
    print("  2. Does it update during execution or only at end?")
    print("  3. When do DEBUG messages appear?\n")

    print(f"[DEBUG {time.time():.2f}] Starting test", flush=True)

    os.environ.setdefault("ANTHROPIC_API_KEY", "mock-key")

    resolution = "Resolved: The US should ban TikTok"
    side = Side.PRO

    start_time = time.time()
    print(f"[DEBUG {start_time:.2f}] Calling run_strategy_agent", flush=True)

    with patch("anthropic.Anthropic", return_value=create_mock_anthropic()):
        result = await run_strategy_agent(
            resolution=resolution,
            side=side,
            session_id=None,
            duration_minutes=0.17,  # ~10 seconds
            show_ui=True,
        )

    end_time = time.time()
    print(f"\n[DEBUG {end_time:.2f}] Test completed after {end_time - start_time:.1f}s", flush=True)
    print(f"Tasks created: {result['tasks_created']}")


if __name__ == "__main__":
    print("\n🔍 Debugging UI Display Timing")
    print("\nIf UI appears immediately and updates during execution → WORKING")
    print("If UI only appears at the end → STILL BUGGY\n")

    input("Press Enter to start 10-second test...")

    asyncio.run(test_ui_timing())

    print("\n" + "=" * 70)
    print("QUESTION: Did you see the UI updating DURING the test?")
    print("Or did everything appear only AFTER the test finished?")
    print("=" * 70 + "\n")
