"""Test streaming numbered list parser for strategy agent."""

import pytest


def parse_numbered_list_streaming(text_chunks: list[str]) -> list[str]:
    """Parse numbered list format as text arrives in chunks.

    Simulates streaming by processing text incrementally.
    Returns tags as they become complete.

    Args:
        text_chunks: List of text chunks simulating streaming response

    Yields:
        Complete tags as they're parsed from the stream
    """
    buffer = ""
    tags = []

    for chunk in text_chunks:
        buffer += chunk

        # Try to extract complete lines (tags)
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()

            if not line:
                continue

            # Match "N. tag" format where N is a number
            if line and line[0].isdigit():
                period_idx = line.find(".")
                if period_idx > 0:
                    tag = line[period_idx + 1:].strip()
                    if tag:
                        tags.append(tag)
                        yield tag

    # Process any remaining buffer
    if buffer.strip():
        line = buffer.strip()
        if line and line[0].isdigit():
            period_idx = line.find(".")
            if period_idx > 0:
                tag = line[period_idx + 1:].strip()
                if tag:
                    tags.append(tag)
                    yield tag


def test_streaming_parser_complete_lines():
    """Test that complete lines are parsed immediately."""
    chunks = [
        "1. TikTok ban eliminates creator jobs\n",
        "2. Chinese government ",
        "surveillance threatens data\n",
        "3. Platform dependency creates monopoly\n",
    ]

    tags = list(parse_numbered_list_streaming(chunks))

    assert len(tags) == 3
    assert tags[0] == "TikTok ban eliminates creator jobs"
    assert tags[1] == "Chinese government surveillance threatens data"
    assert tags[2] == "Platform dependency creates monopoly"


def test_streaming_parser_incremental():
    """Test that tags are yielded as they complete, not all at once."""
    chunks = [
        "1. First tag\n",
        "2. Second tag\n",
        "3. Third tag\n",
    ]

    tags_received = []
    for tag in parse_numbered_list_streaming(chunks):
        tags_received.append(tag)
        # Verify we get tags one at a time
        if len(tags_received) == 1:
            assert tag == "First tag"
        elif len(tags_received) == 2:
            assert tag == "Second tag"
        elif len(tags_received) == 3:
            assert tag == "Third tag"

    assert len(tags_received) == 3


def test_streaming_parser_incomplete_last_line():
    """Test that incomplete final line is still parsed."""
    chunks = [
        "1. Complete line\n",
        "2. Incomplete line without newline",
    ]

    tags = list(parse_numbered_list_streaming(chunks))

    assert len(tags) == 2
    assert tags[0] == "Complete line"
    assert tags[1] == "Incomplete line without newline"


def test_streaming_parser_split_across_chunks():
    """Test that tags split across multiple chunks are handled."""
    chunks = [
        "1. This is a very long tag that ",
        "spans multiple chunks and should ",
        "be parsed correctly\n",
        "2. Second tag\n",
    ]

    tags = list(parse_numbered_list_streaming(chunks))

    assert len(tags) == 2
    assert tags[0] == "This is a very long tag that spans multiple chunks and should be parsed correctly"
    assert tags[1] == "Second tag"


def test_streaming_parser_empty_lines():
    """Test that empty lines are ignored."""
    chunks = [
        "1. First tag\n",
        "\n",
        "\n",
        "2. Second tag\n",
        "\n",
        "3. Third tag\n",
    ]

    tags = list(parse_numbered_list_streaming(chunks))

    assert len(tags) == 3
    assert tags == ["First tag", "Second tag", "Third tag"]


def test_streaming_parser_large_batch():
    """Test parsing a large batch of 50 tags."""
    # Simulate 50 tags in various chunk sizes
    chunks = []
    for i in range(1, 51):
        chunks.append(f"{i}. Tag number {i}\n")

    tags = list(parse_numbered_list_streaming(chunks))

    assert len(tags) == 50
    assert tags[0] == "Tag number 1"
    assert tags[24] == "Tag number 25"
    assert tags[49] == "Tag number 50"


def test_streaming_parser_with_prefix_suffix():
    """Test parsing when response has prefix/suffix text."""
    chunks = [
        "Here are the tags:\n",
        "1. First tag\n",
        "2. Second tag\n",
        "3. Third tag\n",
        "That's all!\n",
    ]

    tags = list(parse_numbered_list_streaming(chunks))

    # Should extract only the numbered items
    assert len(tags) == 3
    assert tags == ["First tag", "Second tag", "Third tag"]
