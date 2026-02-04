#!/usr/bin/env python3
"""Verify UI appears DURING execution, not just at end."""

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
    call_count = [0]

    def create_message_mock(*args, **kwargs):
        call_count[0] += 1
        call_num = call_count[0]

        # Simulate slow API (1.5 seconds per call)
        # This gives UI time to render before call completes
        time.sleep(1.5)

        # Return different responses based on call number
        if call_num == 1:
            response = json.dumps([
                {
                    "argument": "Economic harm from TikTok ban",
                    "search_intent": "economic impact studies",
                    "priority": "high",
                },
                {
                    "argument": "National security threat from data access",
                    "search_intent": "data security surveillance",
                    "priority": "high",
                },
            ])
        elif call_num == 2:
            response = json.dumps([
                {
                    "argument": "AT: Privacy already protected",
                    "search_intent": "privacy violations",
                    "priority": "high",
                }
            ])
        else:
            response = json.dumps([])

        return MockAnthropicResponse(response)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = create_message_mock
    return mock_client


async def test_live_ui():
    """Test that UI appears and updates during execution."""
    print("\n" + "=" * 70)
    print("LIVE UI VERIFICATION TEST")
    print("=" * 70)
    print("\nThis test runs for ~10 seconds with slow API calls (1.5s each).")
    print("\n✅ EXPECTED BEHAVIOR:")
    print("  1. UI appears within 0.5 seconds")
    print("  2. Countdown timer updates continuously (10 → 9 → 8...)")
    print("  3. Agent status changes: starting → checking → working")
    print("  4. New research directions appear as they're generated")
    print("  5. UI updates WHILE API calls are running (not frozen)")
    print("\n❌ BUG SYMPTOMS:")
    print("  - Blank screen for 10 seconds, then everything appears at once")
    print("  - UI frozen during API calls")
    print("  - Only final state shown")
    print()

    os.environ.setdefault("ANTHROPIC_API_KEY", "mock-key")

    resolution = "Resolved: The US should ban TikTok"
    side = Side.PRO

    print("Starting in 3 seconds...")
    await asyncio.sleep(1)
    print("2...")
    await asyncio.sleep(1)
    print("1...")
    await asyncio.sleep(1)
    print("\n👀 WATCH FOR IMMEDIATE UI DISPLAY:\n")

    with patch("anthropic.Anthropic", return_value=create_mock_anthropic()):
        result = await run_strategy_agent(
            resolution=resolution,
            side=side,
            session_id=None,
            duration_minutes=0.17,  # ~10 seconds
            show_ui=True,
        )

    print(f"\n✓ Test completed: {result['tasks_created']} tasks created")


async def main():
    """Run verification test."""
    print("\n🔍 Live UI Verification Test")
    print("=" * 70)
    print("\nThis test verifies that UI appears DURING execution.")
    print("Uses mocked API responses - no credits used.")

    await test_live_ui()

    print("\n" + "=" * 70)
    print("VERIFICATION CHECKLIST:")
    print("=" * 70)
    print("\n❓ Did you observe:")
    print("  [ ] UI appeared immediately (< 1 second)")
    print("  [ ] Countdown timer updated continuously")
    print("  [ ] Agent status changed in real-time")
    print("  [ ] New research directions appeared as generated")
    print("  [ ] UI kept updating even during slow API calls")
    print("\n✅ If all checked → BUG IS FIXED!")
    print("❌ If any unchecked → Still has timing issues\n")


if __name__ == "__main__":
    asyncio.run(main())
