"""Simple test of fixture mocking."""

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

    # Test fetch
    print("3. Testing mock_fetch_source:")
    import json

    results_obj = json.loads(results)
    if results_obj.get("results"):
        url = results_obj["results"][0]["url"]
        article = mock_fetch_source(url)
        print(f"   Title: {article.title}")
        print(f"   Content preview: {article.full_text[:100]}...")
        print(f"   Word count: {article.word_count}\n")

    print("=" * 60)
    print("✓ All fixture mocks working!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    test_fixtures()
