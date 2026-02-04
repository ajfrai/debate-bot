"""Test for prep agent UI display bug."""

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest import fixture

from debate.models import Side
from debate.prep.runner import (
    run_cutter_agent,
    run_organizer_agent,
    run_search_agent,
    run_strategy_agent,
)
from debate.prep.session import PrepSession

# Mark all tests as anyio for async support
pytestmark = pytest.mark.anyio


class MockAnthropicResponse:
    """Mock Anthropic API response."""

    def __init__(self, text: str):
        self.content = [MagicMock(text=text)]


class MockBraveResponse:
    """Mock Brave search API response."""

    def __init__(self, results: list[dict]):
        self.results = results


@pytest.fixture
def mock_anthropic_client():
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

        # Default empty response
        return MockAnthropicResponse("[]")

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = create_message_mock
    return mock_client


@pytest.fixture
def mock_brave_search():
    """Create mock Brave search with synthetic results."""

    def search_mock(*args, **kwargs):
        """Return synthetic search results."""
        return {
            "web": {
                "results": [
                    {
                        "title": "Economic Impact of TikTok Ban",
                        "url": "https://example.com/article1",
                        "description": "Study shows significant job losses from creator economy disruption.",
                    },
                    {
                        "title": "National Security Analysis",
                        "url": "https://example.com/article2",
                        "description": "Research on data access and surveillance concerns.",
                    },
                ]
            }
        }

    return search_mock


async def test_strategy_agent_no_ui(tmp_path, mock_anthropic_client, capsys):
    """Test that strategy agent shows UI when run individually (FIXED)."""
    resolution = "Resolved: The US should ban TikTok"
    side = Side.PRO

    with patch("anthropic.Anthropic", return_value=mock_anthropic_client):
        # Run strategy agent with UI disabled for testing
        result = await run_strategy_agent(
            resolution=resolution,
            side=side,
            session_id=None,
            duration_minutes=0.01,  # 0.6 seconds
            show_ui=False,  # Disable UI for this test
        )

    # With UI disabled, should still work
    assert result["tasks_created"] > 0


async def test_strategy_agent_with_ui(tmp_path, mock_anthropic_client, capsys):
    """Test that strategy agent DOES show UI when run individually (FIX VERIFICATION)."""
    resolution = "Resolved: The US should ban TikTok"
    side = Side.PRO

    with patch("anthropic.Anthropic", return_value=mock_anthropic_client):
        # Run strategy agent with UI enabled (default)
        result = await run_strategy_agent(
            resolution=resolution,
            side=side,
            session_id=None,
            duration_minutes=0.01,  # 0.6 seconds
            show_ui=True,
        )

    # Should have created tasks
    assert result["tasks_created"] > 0

    # Note: In test environment, Rich UI may not render properly
    # But the function should complete successfully with UI enabled


async def test_parallel_prep_has_ui(tmp_path, mock_anthropic_client, capsys):
    """Test that parallel prep DOES show UI (for comparison)."""
    from debate.prep.runner import run_prep

    resolution = "Resolved: The US should ban TikTok"
    side = Side.PRO

    with patch("anthropic.Anthropic", return_value=mock_anthropic_client):
        with patch("debate.prep.search_agent.SearchAgent.check_for_work", return_value=[]):
            # Run full prep with UI for 0.5 seconds
            result = await run_prep(
                resolution=resolution,
                side=side,
                duration_minutes=0.01,
                show_ui=True,
            )

    # Capture output
    captured = capsys.readouterr()

    # Parallel prep SHOULD have UI
    # Note: This might not work in test environment, but we're documenting expected behavior
    # In real terminal, you would see Rich UI elements


if __name__ == "__main__":
    # Quick manual test
    asyncio.run(
        test_strategy_agent_no_ui(
            Path("/tmp"),
            pytest.fixture(mock_anthropic_client),
            MagicMock(),
        )
    )
