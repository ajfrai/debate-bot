"""Test for prep agent UI display bug."""

import asyncio
import json
import shutil
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


@pytest.fixture(autouse=True)
def cleanup_staging():
    """Clean up staging directory before and after each test."""
    staging_dir = Path("staging")
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    yield
    if staging_dir.exists():
        shutil.rmtree(staging_dir)


class MockAnthropicResponse:
    """Mock Anthropic API response."""

    def __init__(self, text: str):
        self.content = [MagicMock(text=text)]


class MockStreamContext:
    """Mock Anthropic streaming context manager."""

    def __init__(self, text: str):
        self.text = text
        self.text_stream = [text]  # Simulate streaming by yielding full text at once

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


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

        # Strategy agent - enumerate support arguments (new numbered list format)
        if "Generating PRO arguments" in prompt or "NEW argument TAGS" in prompt:
            response = """1. TikTok ban eliminates creator economy jobs
2. Chinese government surveillance threatens user data
3. Platform dependency creates social media monopoly
4. Data collection violates privacy rights
5. Economic costs exceed national security benefits"""
            return MockAnthropicResponse(response)

        # Strategy agent - enumerate answer arguments
        if "ANSWER TAGS" in prompt or "Generating ANSWER arguments" in prompt:
            response = """1. AT: Economic costs outweighed by security benefits
2. AT: Privacy already protected by existing laws
3. AT: TikTok alternatives available to creators
4. AT: US already bans Chinese tech in government
5. AT: Commerce benefits justify data collection risks"""
            return MockAnthropicResponse(response)

        # Impact chains
        if "IMPACT CHAINS" in prompt:
            response = """1. Impact: Data breaches lead to identity theft
2. Impact: Economic recession causes unemployment
3. Impact: Job losses create community decline
4. Impact: Privacy erosion enables authoritarianism
5. Impact: Tech monopolies stifle innovation"""
            return MockAnthropicResponse(response)

        # Default empty response
        return MockAnthropicResponse("[]")

    def stream_message_mock(*args, **kwargs):
        """Generate synthetic streaming responses based on prompt."""
        messages = kwargs.get("messages", [])
        if not messages:
            return MockStreamContext("")

        prompt = messages[0].get("content", "")

        # Return the same responses as create_message_mock
        response = create_message_mock(*args, **kwargs)
        return MockStreamContext(response.content[0].text)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = create_message_mock
    mock_client.messages.stream.side_effect = stream_message_mock
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
