"""Simple test of fixture mocking."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.fixtures import enable_fixtures, mock_generate_query, mock_brave_search, mock_fetch_source


def test_fixtures():
    """Test that fixture mocks work correctly."""
    enable_fixtures()

    print("\n" + "=" * 60)
    print("TESTING FIXTURE MOCKS")
    print("=" * 60 + "\n")

    # Test query generation
    print("1. Testing mock_generate_query:")
    query = mock_generate_query({"argument": "Test", "search_intent": "Test intent"})
    print(f"   Generated: {query}\n")

    # Test search
    print("2. Testing mock_brave_search:")
    results = mock_brave_search(query)
    print(f"   Results: {results[:100]}...\n")

    # Verify markdown format with URL: prefix
    assert "## Search Results" in results, "Should have markdown header"
    assert "URL: " in results, "Should have URL: prefix for extraction"

    # Extract URLs using the same pattern as _extract_urls_from_search_results
    urls = re.findall(r"URL:\s*(https?://[^\s]+)", results)
    assert len(urls) > 0, f"Should extract URLs from markdown, got: {results[:200]}"
    print(f"   Extracted {len(urls)} URLs\n")

    # Test fetch
    print("3. Testing mock_fetch_source:")
    url = urls[0]
    article = mock_fetch_source(url)
    if article:  # May be None due to simulated errors
        print(f"   Title: {article.title}")
        print(f"   Content preview: {article.full_text[:100]}...")
        print(f"   Word count: {article.word_count}\n")
    else:
        print("   (Simulated fetch failure - this is expected sometimes)\n")
        # Try again to get a successful fetch
        article = mock_fetch_source(url)
        if article:
            print(f"   Retry succeeded: {article.title}")

    print("=" * 60)
    print("All fixture mocks working!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    test_fixtures()
