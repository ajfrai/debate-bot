"""Article fetching with paywall detection and retry logic.

This module provides robust article fetching from URLs with support for:
- Web articles (HTML extraction via trafilatura)
- PDF documents
- Paywall detection and retry with alternative sources
- In-memory caching of fetched articles
"""

import hashlib
import io
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import pypdf
import requests
import trafilatura


@dataclass
class FetchedArticle:
    """A fetched article with full text and metadata."""

    fetch_id: str
    url: str
    title: str | None
    full_text: str
    preview: str  # First ~500 chars for preview
    content_type: str  # "web" or "pdf"
    word_count: int
    is_paywalled: bool


# In-memory cache of fetched articles (fetch_id -> FetchedArticle)
_ARTICLE_CACHE: dict[str, FetchedArticle] = {}


# Common paywall indicators
PAYWALL_INDICATORS = [
    "subscribe to read",
    "sign in to continue",
    "this article is for subscribers",
    "create a free account",
    "premium content",
    "paywall",
    "members only",
    "subscribe now",
    "log in to read",
    "subscription required",
]

# Known paywall domains (partial matches)
PAYWALL_DOMAINS = [
    "nytimes.com",
    "wsj.com",
    "washingtonpost.com",
    "ft.com",
    "economist.com",
    "bloomberg.com",
    "thetimes.co.uk",
]


def _generate_fetch_id(url: str) -> str:
    """Generate a short unique ID for a URL."""
    return hashlib.md5(url.encode()).hexdigest()[:8]


def _is_pdf_url(url: str) -> bool:
    """Check if URL points to a PDF."""
    parsed = urlparse(url)
    return parsed.path.lower().endswith(".pdf")


def _detect_paywall(text: str, url: str) -> bool:
    """Detect if content is behind a paywall.

    Args:
        text: The extracted text content
        url: The source URL

    Returns:
        True if paywall detected, False otherwise
    """
    # Check if text is suspiciously short (< 200 chars suggests paywall)
    if len(text.strip()) < 200:
        return True

    # Check for paywall indicators in text (case-insensitive)
    text_lower = text.lower()
    for indicator in PAYWALL_INDICATORS:
        if indicator in text_lower:
            return True

    # Check if URL is from known paywall domain
    url_lower = url.lower()
    for domain in PAYWALL_DOMAINS:
        if domain in url_lower:
            # If from paywall domain and short text, likely paywalled
            if len(text.strip()) < 1000:
                return True

    return False


def _fetch_web_article(url: str, timeout: int = 15) -> tuple[str, str | None]:
    """Fetch and extract text from a web article.

    Args:
        url: The URL to fetch
        timeout: Request timeout in seconds

    Returns:
        Tuple of (extracted_text, title)

    Raises:
        Exception: If fetch fails
    """
    # Fetch the page
    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        },
    )
    response.raise_for_status()

    # Extract text and metadata using trafilatura
    downloaded = response.content
    text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)

    if not text:
        raise ValueError("Could not extract text from URL")

    # Try to get title
    metadata = trafilatura.extract_metadata(downloaded)
    title = metadata.title if metadata else None

    return text, title


def _fetch_pdf(url: str, timeout: int = 15) -> tuple[str, str | None]:
    """Fetch and extract text from a PDF.

    Args:
        url: The PDF URL to fetch
        timeout: Request timeout in seconds

    Returns:
        Tuple of (extracted_text, title)

    Raises:
        Exception: If fetch fails
    """
    # Download the PDF
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()

    # Extract text from PDF
    pdf_file = io.BytesIO(response.content)
    reader = pypdf.PdfReader(pdf_file)

    # Extract text from all pages
    text_parts = []
    for page in reader.pages:
        text_parts.append(page.extract_text())

    text = "\n\n".join(text_parts)

    if not text.strip():
        raise ValueError("PDF appears to be empty or text could not be extracted")

    # Try to get title from PDF metadata
    title = None
    if reader.metadata:
        title = reader.metadata.get("/Title")

    return text, title


def _find_free_version(original_url: str, title: str | None, brave_api_key: str | None) -> str | None:
    """Try to find a free version of a paywalled article.

    Args:
        original_url: The paywalled URL
        title: Article title (if known)
        brave_api_key: Brave Search API key

    Returns:
        Alternative URL if found, None otherwise
    """
    if not brave_api_key or not title:
        return None

    # Search for alternative sources using title
    search_query = f'"{title}" article'

    try:
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": brave_api_key, "Accept": "application/json"},
            params={"q": search_query, "count": 5},
            timeout=10,
        )

        if response.status_code != 200:
            return None

        data = response.json()
        results = data.get("web", {}).get("results", [])

        # Look for alternative URLs (not from the same domain)
        original_domain = urlparse(original_url).netloc
        for result in results:
            url = result.get("url", "")
            result_domain = urlparse(url).netloc

            # Skip if same domain as original
            if result_domain == original_domain:
                continue

            # Skip known paywall domains
            if any(paywall_domain in url.lower() for paywall_domain in PAYWALL_DOMAINS):
                continue

            # Found a potential alternative
            return url

    except Exception:
        # If search fails, just return None
        pass

    return None


def fetch_source(
    url: str,
    retry_on_paywall: bool = True,
    brave_api_key: str | None = None,
    quiet: bool = False,
) -> FetchedArticle | None:
    """Fetch full text from a URL with paywall detection and retry.

    This function:
    1. Fetches the URL (supports both web articles and PDFs)
    2. Detects paywalls using heuristics
    3. If paywalled and retry_on_paywall=True, searches for a free version
    4. Caches the result for future access
    5. Returns a FetchedArticle with fetch_id for reference

    Args:
        url: The URL to fetch
        retry_on_paywall: If True, try to find a free version when paywall detected
        brave_api_key: Brave Search API key for finding alternative sources
        quiet: If True, suppress print output (useful for parallel UI)

    Returns:
        FetchedArticle if successful, None if failed or paywall with no alternative
    """
    # Check cache first
    fetch_id = _generate_fetch_id(url)
    if fetch_id in _ARTICLE_CACHE:
        return _ARTICLE_CACHE[fetch_id]

    if not quiet:
        print(f"  Fetching: {url[:80]}...")

    try:
        # Determine if PDF or web article
        is_pdf = _is_pdf_url(url)

        # Fetch the content
        if is_pdf:
            text, title = _fetch_pdf(url)
            content_type = "pdf"
        else:
            text, title = _fetch_web_article(url)
            content_type = "web"

        # Check for paywall
        is_paywalled = _detect_paywall(text, url)

        if is_paywalled:
            if not quiet:
                print("  ⚠ Paywall detected")

            # Try to find a free version if requested
            if retry_on_paywall:
                if not quiet:
                    print("  Searching for free version...")
                time.sleep(3)  # Rate limit pause

                alternative_url = _find_free_version(url, title, brave_api_key)

                if alternative_url:
                    if not quiet:
                        print(f"  ✓ Found alternative: {alternative_url[:80]}...")
                    time.sleep(2)  # Brief pause before fetching alternative

                    # Recursively fetch the alternative (but don't retry again)
                    return fetch_source(
                        alternative_url,
                        retry_on_paywall=False,  # Don't retry again
                        brave_api_key=brave_api_key,
                        quiet=quiet,
                    )
                else:
                    if not quiet:
                        print("  ✗ No free version found, skipping")
                    return None
            else:
                # Already retried once, give up
                return None

        # Success! Create FetchedArticle
        word_count = len(text.split())
        preview = text[:500] + "..." if len(text) > 500 else text

        article = FetchedArticle(
            fetch_id=fetch_id,
            url=url,
            title=title,
            full_text=text,
            preview=preview,
            content_type=content_type,
            word_count=word_count,
            is_paywalled=False,
        )

        # Cache it
        _ARTICLE_CACHE[fetch_id] = article

        if not quiet:
            print(f"  ✓ Fetched {word_count} words from {content_type}")
        return article

    except Exception as e:
        if not quiet:
            print(f"  ✗ Failed to fetch: {str(e)[:100]}")
        return None


def get_cached_article(fetch_id: str) -> FetchedArticle | None:
    """Retrieve a previously fetched article from cache.

    Args:
        fetch_id: The fetch ID returned by fetch_source()

    Returns:
        FetchedArticle if found in cache, None otherwise
    """
    return _ARTICLE_CACHE.get(fetch_id)


def clear_cache() -> None:
    """Clear the article cache."""
    _ARTICLE_CACHE.clear()


def get_cache_stats() -> dict:
    """Get statistics about the article cache.

    Returns:
        Dict with cache statistics (size, total_words, etc.)
    """
    total_words = sum(article.word_count for article in _ARTICLE_CACHE.values())
    return {
        "cached_articles": len(_ARTICLE_CACHE),
        "total_words": total_words,
        "fetch_ids": list(_ARTICLE_CACHE.keys()),
    }
