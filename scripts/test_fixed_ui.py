#!/usr/bin/env python3
"""Test script to verify UI fix for individual prep agents."""

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


async def test_fixed_ui():
    """Test that individual strategy agent now shows UI."""
    print("\n" + "=" * 70)
    print("TESTING FIXED UI - Individual StrategyAgent")
    print("=" * 70)
    print("\nExpected: Rich UI appears immediately and updates continuously")
    print("          Shows new research directions as they're generated")
    print("          Displays countdown timer\n")

    resolution = "Resolved: The US should ban TikTok"
    side = Side.PRO

    with patch("anthropic.Anthropic", return_value=create_mock_anthropic()):
        result = await run_strategy_agent(
            resolution=resolution,
            side=side,
            session_id=None,
            duration_minutes=0.1,  # 6 seconds
            show_ui=True,
        )

    print(f"\n✓ Completed: {result['tasks_created']} tasks created")
    print(f"Session ID: {result['session_id']}\n")


async def main():
    """Run test."""
    print("\n✅ Testing Fixed Prep Agent UI")
    print("=" * 70)
    print("\nUsing mocked API responses - no credits used.")

    # Set dummy API key
    os.environ.setdefault("ANTHROPIC_API_KEY", "mock-key-for-testing")

    await test_fixed_ui()

    print("=" * 70)
    print("\n✅ If you saw a live UI with countdown timer above, the bug is FIXED!")
    print("❌ If you only saw output at the end, there's still an issue.\n")


if __name__ == "__main__":
    asyncio.run(main())
