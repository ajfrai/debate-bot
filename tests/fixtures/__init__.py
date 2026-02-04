"""Test fixtures for mocking external API calls."""

import json
import os
import random
from pathlib import Path
from typing import Any

# Path to fixtures directory
FIXTURES_DIR = Path(__file__).parent

# Fixture mode tracking
_FIXTURE_MODE = False


def load_fixture(name: str) -> dict[str, Any]:
    """Load a fixture JSON file."""
    fixture_path = FIXTURES_DIR / f"{name}.json"
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_path}")
    return json.loads(fixture_path.read_text())


# Load all fixtures at module level
SAMPLE_QUERIES = load_fixture("queries/sample_queries")["queries"]
SAMPLE_RESULTS = load_fixture("search_results/sample_results")["results"]
SAMPLE_ARTICLES = load_fixture("articles/sample_articles")["articles"]

# Track state across mock calls
_query_index = 0
_result_index = 0


def is_fixture_mode() -> bool:
    """Check if fixture mode is enabled."""
    return os.environ.get("DEBATE_FIXTURES") == "1"


def enable_fixtures():
    """Enable fixture mode via environment variable."""
    os.environ["DEBATE_FIXTURES"] = "1"
    print("[FIXTURE] API mocking enabled - using synthetic data only")


def disable_fixtures():
    """Disable fixture mode."""
    os.environ["DEBATE_FIXTURES"] = ""


def mock_generate_query(task: dict[str, Any]) -> str:
    """Mock query generation without calling Anthropic API."""
    global _query_index
    query = SAMPLE_QUERIES[_query_index % len(SAMPLE_QUERIES)]
    _query_index += 1
    print(f"  [FIXTURE] Generated query: {query[:50]}...")
    return query


def mock_brave_search(query: str, num_results: int = 5, quiet: bool = True) -> str:
    """Mock Brave search without calling API."""
    global _result_index

    print(f"  [FIXTURE] Brave search for: {query[:50]}...")

    # Find matching results or use next in sequence
    matching_results = None
    for result in SAMPLE_RESULTS:
        if result["query"].lower() in query.lower() or query.lower() in result["query"].lower():
            matching_results = result
            break

    if not matching_results:
        matching_results = SAMPLE_RESULTS[_result_index % len(SAMPLE_RESULTS)]
        _result_index += 1

    # Format as JSON like Brave API would return
    urls = matching_results["urls"][:num_results]
    results = [
        {
            "url": url,
            "title": f"Result for {query}",
            "description": f"Search result from {url}",
        }
        for url in urls
    ]
    print(f"    Found {len(results)} results")
    return json.dumps({"results": results})


def mock_fetch_source(url: str, **kwargs) -> Any:
    """Mock article fetching without calling the real URL."""
    print(f"  [FIXTURE] Fetching: {url[:60]}...")

    # Find matching article or return random
    article = None
    for a in SAMPLE_ARTICLES:
        if a["url"] == url:
            article = a
            break

    if not article:
        # Use random article
        article = random.choice(SAMPLE_ARTICLES)

    # Create a mock Article object
    class MockArticle:
        def __init__(self, url: str, title: str, content: str):
            self.url = url
            self.title = title
            self.full_text = content
            self.word_count = len(content.split())

    print(f"    Got: {article['title'][:40]}... ({len(article['content'].split())} words)")
    return MockArticle(
        url=article["url"], title=article["title"], content=article["content"]
    )
