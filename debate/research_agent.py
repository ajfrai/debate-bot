"""Research agent for finding and cutting evidence cards.

This module provides cost-effective evidence research by:
1. Using Brave Search to find relevant sources
2. Using Claude Haiku to extract and format evidence cards
3. Organizing cards into debate files by strategic value
"""

import asyncio
import datetime
import json
import os
import re
import time
from pathlib import Path

import anthropic
import requests

from debate.article_fetcher import FetchedArticle, fetch_all_sources_async, fetch_source
from debate.config import Config
from debate.models import (
    Card,
    DebateFile,
    EvidenceBucket,
    EvidenceType,
    FlatDebateFile,
    PrepState,
    QueryStrategy,
    SectionType,
    Side,
)


def load_prompt_template(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", f"{name}.md")
    with open(prompt_path) as f:
        return f.read()


def load_lessons(*lesson_names: str) -> str:
    """Load lesson files from the lessons directory.

    The lessons directory contains accumulated knowledge that agents
    should consult before performing tasks. This enables continuous
    improvement as lessons are added over time.

    Args:
        *lesson_names: Names of lesson files to load (without .md extension)

    Returns:
        Combined lessons as a formatted string, or empty string if none found
    """
    lessons_dir = os.path.join(os.path.dirname(__file__), "..", "lessons")
    lessons = []

    for name in lesson_names:
        lesson_path = os.path.join(lessons_dir, f"{name}.md")
        if os.path.exists(lesson_path):
            with open(lesson_path) as f:
                lessons.append(f.read())

    if not lessons:
        return ""

    return "\n\n---\n\n".join(lessons)


def _brave_search(
    query: str, num_results: int = 20, retry_on_rate_limit: bool = True, quiet: bool = False
) -> str | None:
    """Search Brave for relevant sources with rate limiting support.

    Args:
        query: Search query
        num_results: Number of results to fetch (default 20, max 20)
        retry_on_rate_limit: Whether to retry on 429 rate limit (default True)
        quiet: If True, suppress print output (useful for parallel UI)

    Returns:
        Formatted search results as a string, or None if search fails
    """
    api_key = os.environ.get("BRAVE_API_KEY")

    if not api_key:
        return None

    max_retries = 2  # Retry up to 2 times on rate limit
    retry_count = 0

    while retry_count <= max_retries:
        try:
            headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}
            params = {"q": query, "count": num_results}

            response = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params=params,
                timeout=10,
            )

            # Handle rate limiting (429)
            if response.status_code == 429 and retry_on_rate_limit and retry_count < max_retries:
                if not quiet:
                    print("  Rate limited (429), waiting 10s before retry...")
                time.sleep(10)
                retry_count += 1
                continue

            if response.status_code != 200:
                if not quiet:
                    print(f"Warning: Brave Search returned status {response.status_code}")
                return None

            data = response.json()
            results = data.get("web", {}).get("results", [])

            if not results:
                return None

            # Format results for the prompt
            formatted = ["## Search Results\n"]
            for i, result in enumerate(results, 1):
                formatted.append(f"{i}. **{result.get('title', 'No title')}**")
                formatted.append(f"   URL: {result.get('url', 'No URL')}")
                formatted.append(f"   Description: {result.get('description', 'No description')}")
                formatted.append("")

            return "\n".join(formatted)

        except Exception as e:
            if not quiet:
                print(f"Warning: Brave Search failed: {e}")
            return None

    # If we exhausted retries
    if not quiet:
        print("  Rate limit retries exhausted")
    return None


def _extract_urls_from_search_results(search_results: str) -> list[str]:
    """Extract URLs from formatted search results.

    Args:
        search_results: Formatted markdown search results from _brave_search

    Returns:
        List of URLs found in the search results
    """
    urls = []
    # Match lines like "   URL: https://example.com"
    pattern = r"URL:\s*(https?://[^\s]+)"
    matches = re.finditer(pattern, search_results)
    for match in matches:
        urls.append(match.group(1))
    return urls


def _fetch_articles_from_search(
    search_results: str,
    max_articles: int = 2,
    brave_api_key: str | None = None,
) -> list[FetchedArticle]:
    """Fetch full article text from search result URLs (legacy sync version).

    Args:
        search_results: Formatted search results from _brave_search
        max_articles: Maximum number of articles to fetch
        brave_api_key: Brave API key for paywall retry

    Returns:
        List of successfully fetched articles
    """
    urls = _extract_urls_from_search_results(search_results)
    fetched_articles = []

    for url in urls[:max_articles]:
        article = fetch_source(url, retry_on_paywall=True, brave_api_key=brave_api_key)
        if article:
            fetched_articles.append(article)
            # Brief pause between fetches
            time.sleep(2)

        # Stop if we have enough articles
        if len(fetched_articles) >= max_articles:
            break

    return fetched_articles


def _fetch_all_articles_async(
    search_results_list: list[str],
    brave_api_key: str | None = None,
) -> list[FetchedArticle]:
    """Fetch ALL article URLs from multiple search results in parallel.

    Collects all URLs from all search results, deduplicates, and fetches in parallel.

    Args:
        search_results_list: List of formatted search results from _brave_search
        brave_api_key: Brave API key for paywall retry

    Returns:
        List of successfully fetched articles (deduplicated)
    """
    # Collect all URLs from all search results
    all_urls = []
    for search_results in search_results_list:
        urls = _extract_urls_from_search_results(search_results)
        all_urls.extend(urls)

    if not all_urls:
        return []

    # Fetch all URLs in parallel (with automatic deduplication)
    return asyncio.run(fetch_all_sources_async(all_urls, brave_api_key=brave_api_key, quiet=False))


def _format_fetched_articles_for_prompt(articles: list[FetchedArticle]) -> str:
    """Format fetched articles for inclusion in Claude prompt.

    Args:
        articles: List of fetched articles

    Returns:
        Formatted markdown string with article contents
    """
    if not articles:
        return ""

    sections = ["## Full Article Text\n"]
    for i, article in enumerate(articles, 1):
        sections.append(f"### Article {i}: {article.title or 'Untitled'}")
        sections.append(f"**Source:** {article.url}")
        sections.append(f"**Type:** {article.content_type.upper()}")
        sections.append(f"**Word Count:** {article.word_count}")
        sections.append("")
        sections.append(article.full_text)
        sections.append("\n---\n")

    return "\n".join(sections)


def _extract_json_from_text(text: str) -> dict:
    """Extract JSON from text that might be wrapped in markdown code blocks."""
    text = text.strip()

    # Try to find JSON in markdown code blocks
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        text = text[start:end].strip()

    return json.loads(text)


def _parse_section_type(section_str: str) -> SectionType:
    """Parse section type string to SectionType enum."""
    section_map = {
        "support": SectionType.SUPPORT,
        "answer": SectionType.ANSWER,
        "extension": SectionType.EXTENSION,
        "impact": SectionType.IMPACT,
    }
    return section_map.get(section_str.lower(), SectionType.SUPPORT)


def _parse_evidence_type(type_str: str | None) -> EvidenceType | None:
    """Parse evidence type string to EvidenceType enum."""
    if not type_str:
        return None
    type_map = {
        "statistical": EvidenceType.STATISTICAL,
        "analytical": EvidenceType.ANALYTICAL,
        "consensus": EvidenceType.CONSENSUS,
        "empirical": EvidenceType.EMPIRICAL,
        "predictive": EvidenceType.PREDICTIVE,
    }
    return type_map.get(type_str.lower())


# ========== Multi-Strategy Query Generation ==========

# Known credible sources for different evidence types
CREDIBLE_SOURCES = {
    "think_tanks": ["brookings.edu", "cfr.org", "rand.org", "cato.org", "heritage.org", "aei.org"],
    "academic": ["nature.com", "science.org", "jstor.org", "scholar.google.com"],
    "news": ["nytimes.com", "wsj.com", "washingtonpost.com", "economist.com", "reuters.com"],
    "government": ["gao.gov", "cbo.gov", "state.gov", "whitehouse.gov"],
}


def generate_research_queries(
    resolution: str,
    topic: str,
    side: Side,
    existing_cards: list[Card] | None = None,
) -> list[dict]:
    """Generate diverse query strategies for comprehensive research.

    Combines:
    - Exploratory: broad topic discovery
    - Spearfish: specific claim targeting
    - Source-targeted: known credible sources
    - Expert: find authoritative voices
    - Verbatim: exact phrase matching from existing cards

    Args:
        resolution: The debate resolution
        topic: The argument/topic to research
        side: Which side (PRO/CON)
        existing_cards: Cards we already have (for verbatim queries)

    Returns:
        List of query dicts with 'strategy', 'query', 'purpose'
    """
    queries = []
    side_term = "benefits" if side == Side.PRO else "concerns"

    # 1. Exploratory - broad discovery
    queries.append(
        {
            "strategy": QueryStrategy.EXPLORATORY,
            "query": f"{topic} research analysis {side_term}",
            "purpose": "Discover broad landscape of evidence",
        }
    )

    # 2. Spearfish - specific claim with year
    queries.append(
        {
            "strategy": QueryStrategy.SPEARFISH,
            "query": f'"{topic}" study findings 2024 OR 2025',
            "purpose": "Find recent specific studies",
        }
    )

    # 3. Source-targeted - credible institutions
    think_tanks = " OR ".join(f"site:{s}" for s in CREDIBLE_SOURCES["think_tanks"][:3])
    queries.append(
        {
            "strategy": QueryStrategy.SOURCE_TARGETED,
            "query": f"{topic} ({think_tanks})",
            "purpose": "Find think tank/policy analysis",
        }
    )

    # 4. Expert - find authorities
    queries.append(
        {
            "strategy": QueryStrategy.EXPERT,
            "query": f"{topic} professor expert analysis opinion",
            "purpose": "Find expert voices with credentials",
        }
    )

    # 5. Verbatim - if we have existing cards, find related evidence
    if existing_cards:
        # Extract a key phrase from an existing card
        for card in existing_cards[:2]:
            # Find a quotable phrase from the bolded text
            import re

            bolded = re.findall(r"\*\*(.+?)\*\*", card.text)
            if bolded:
                phrase = bolded[0][:50]  # First 50 chars of first bold
                queries.append(
                    {
                        "strategy": QueryStrategy.VERBATIM,
                        "query": f'"{phrase}"',
                        "purpose": f"Find sources citing similar evidence to {card.tag[:30]}",
                    }
                )
                break

    # 6. Statistical focus
    queries.append(
        {
            "strategy": QueryStrategy.SPEARFISH,
            "query": f"{topic} statistics data numbers percent",
            "purpose": "Find quantitative evidence",
        }
    )

    return queries


def analyze_existing_coverage(
    debate_file: DebateFile | FlatDebateFile | None,
    topic: str,
    side: Side,
) -> dict:
    """Analyze what evidence already exists for a topic.

    Returns coverage report with:
    - claims_covered: list of existing claims/tags
    - evidence_types: set of evidence types present
    - gaps: identified gaps in coverage
    - suggestion: research guidance

    Args:
        debate_file: Existing debate file (old or new format)
        topic: Topic to analyze
        side: Which side

    Returns:
        Coverage report dict
    """
    if not debate_file:
        return {
            "claims_covered": [],
            "evidence_types": set(),
            "card_count": 0,
            "gaps": ["No existing evidence - explore broadly"],
            "suggestion": "Start with exploratory research to discover the landscape",
        }

    # Find existing cards matching topic
    existing_cards: list[Card] = []

    if isinstance(debate_file, FlatDebateFile):
        # New flat structure
        args = debate_file.get_arguments_for_side(side)
        for arg in args:
            if topic.lower() in arg.title.lower():
                existing_cards.extend(arg.get_all_cards())
    else:
        # Old structure
        existing_cards = debate_file.find_cards_by_tag(topic)

    if not existing_cards:
        return {
            "claims_covered": [],
            "evidence_types": set(),
            "card_count": 0,
            "gaps": [f"No evidence yet for '{topic}'"],
            "suggestion": "Start with exploratory research",
        }

    # Analyze what we have
    claims = [card.tag for card in existing_cards]
    evidence_types = {card.evidence_type for card in existing_cards if card.evidence_type}

    # Identify gaps
    gaps = []
    all_types = set(EvidenceType)
    missing_types = all_types - evidence_types

    if EvidenceType.STATISTICAL not in evidence_types:
        gaps.append("Missing statistical evidence (numbers, data)")
    if EvidenceType.ANALYTICAL not in evidence_types:
        gaps.append("Missing analytical evidence (expert reasoning)")
    if EvidenceType.CONSENSUS not in evidence_types:
        gaps.append("Missing consensus evidence (institutional agreement)")

    # Generate suggestion
    if len(existing_cards) >= 5:
        suggestion = "Good coverage. Focus on filling evidence type gaps."
    elif len(existing_cards) >= 3:
        suggestion = "Moderate coverage. Consider different angles or evidence types."
    else:
        suggestion = "Thin coverage. Research more sources for this topic."

    return {
        "claims_covered": claims,
        "evidence_types": evidence_types,
        "card_count": len(existing_cards),
        "gaps": gaps,
        "missing_types": list(missing_types),
        "suggestion": suggestion,
    }


def format_coverage_for_prompt(coverage: dict) -> str:
    """Format coverage analysis for inclusion in research prompt."""
    lines = ["## Existing Coverage (avoid duplication)", ""]

    if coverage["card_count"] == 0:
        lines.append("No existing evidence on this topic. Research freely.")
        return "\n".join(lines)

    lines.append(f"You already have **{coverage['card_count']} cards** on this topic:")
    for claim in coverage["claims_covered"][:5]:  # Limit to 5
        lines.append(f"- {claim}")

    if coverage.get("evidence_types"):
        type_names = [t.value for t in coverage["evidence_types"]]
        lines.append(f"\n**Evidence types present:** {', '.join(type_names)}")

    if coverage.get("gaps"):
        lines.append("\n**Gaps identified:**")
        for gap in coverage["gaps"]:
            lines.append(f"- {gap}")

    lines.append(f"\n**Suggestion:** {coverage['suggestion']}")
    lines.append("\n**Low value:** Cards that repeat existing claims")
    lines.append("**High value:** Cards that fill identified gaps or add new perspectives")

    return "\n".join(lines)


def research_evidence(
    resolution: str,
    side: Side,
    topic: str,
    num_cards: int = 3,
    search_query: str | None = None,
    stream: bool = True,
    use_multi_strategy: bool = True,
) -> FlatDebateFile:
    """Research and cut evidence cards for a specific argument.

    Args:
        resolution: The debate resolution
        side: Which side (PRO/CON) the evidence supports
        topic: The specific argument/topic to research (e.g., "Economic impacts")
        num_cards: How many cards to cut (default 3, max 5 for cost control)
        search_query: Optional custom search query (auto-generated if not provided)
        stream: Whether to stream tokens as they're generated (default True)
        use_multi_strategy: Whether to use multi-strategy query generation (default True)

    Returns:
        FlatDebateFile with researched evidence cards organized by file and semantic categories

    Cost optimization:
        - Uses Haiku (cheapest model) for card cutting
        - Limits to 5 cards max per research session
        - Uses efficient prompts to minimize token usage

    Research improvements:
        - Multi-strategy queries (exploratory, spearfish, source-targeted, expert, verbatim)
        - Duplication detection to avoid redundant research
        - Evidence type diversity tracking
    """
    if num_cards > 5:
        raise ValueError("Maximum 5 cards per research session to control costs")

    # Load or create flat debate file for this resolution
    from debate.evidence_storage import get_or_create_flat_debate_file

    flat_file, is_new = get_or_create_flat_debate_file(resolution)
    if is_new:
        print(f"Creating new debate file for: {resolution}")
    else:
        # Count existing cards
        total_cards = sum(
            len(group.cards)
            for arg in flat_file.pro_arguments + flat_file.con_arguments
            for group in arg.semantic_groups
        )
        print(f"Adding to existing debate file ({total_cards} cards)")

    # Analyze existing coverage to avoid duplication
    coverage = analyze_existing_coverage(flat_file if not is_new else None, topic, side)
    coverage_prompt = format_coverage_for_prompt(coverage)

    if coverage["card_count"] > 0:
        print(f"ℹ Existing coverage: {coverage['card_count']} cards on this topic")
        if coverage.get("gaps"):
            print(f"  Gaps: {', '.join(coverage['gaps'][:2])}")

    # Generate search queries
    if use_multi_strategy and not search_query:
        # Get existing cards for verbatim queries from flat file
        existing_cards: list[Card] = []
        if not is_new:
            args = flat_file.get_arguments_for_side(side)
            for arg in args:
                if topic.lower() in arg.title.lower():
                    existing_cards.extend(arg.get_all_cards())

        # Generate diverse queries
        queries = generate_research_queries(resolution, topic, side, existing_cards)

        # Execute ALL queries serially (respecting Brave rate limits)
        # Then fetch ALL sources from ALL results in parallel
        if queries:
            print(f"Executing {len(queries)} search strategies...")
            all_search_results = []
            search_results_formatted = []

            for i, q in enumerate(queries, 1):
                print(f"  [{i}/{len(queries)}] {q['strategy'].value}: {q['query'][:60]}...")

                # Rate limit: 3-second pause between searches
                if i > 1:
                    time.sleep(3)

                result = _brave_search(q["query"], num_results=20, quiet=False)
                if result:
                    all_search_results.append(result)
                    search_results_formatted.append(f"### {q['strategy'].value.upper()} ({q['purpose']})\n{result}")
                    print("    ✓ Found results")
                else:
                    print("    ⚠ No results")

            # Fetch ALL sources from ALL queries in parallel
            if all_search_results:
                brave_api_key = os.environ.get("BRAVE_API_KEY")
                print(f"\nFetching all sources from {len(all_search_results)} search result(s)...")
                fetched_articles = _fetch_all_articles_async(all_search_results, brave_api_key=brave_api_key)

                # Combine search results and article text
                search_results = "\n\n".join(search_results_formatted)

                if fetched_articles:
                    print(f"✓ Fetched {len(fetched_articles)} unique article(s) with full text")
                    article_text = _format_fetched_articles_for_prompt(fetched_articles)
                    search_results = f"{search_results}\n\n{article_text}"
                else:
                    print("⚠ Could not fetch any articles")
            else:
                print("⚠ No search results from any query, using Claude's knowledge base")
                search_results = "(No search results available - use your knowledge base)"
        else:
            print("⚠ No search queries generated, using Claude's knowledge base")
            search_results = "(No search results available - use your knowledge base)"
    else:
        # Single query mode (legacy)
        if not search_query:
            search_query = f"{resolution} {topic} {side.value}"

        print("Searching Brave for relevant sources...")

        # Add 3-second pause to avoid rate limiting
        time.sleep(3)

        brave_results = _brave_search(search_query, num_results=20)

        if brave_results:
            search_results = brave_results
            print("✓ Found search results from Brave")

            # Fetch ALL article sources from the search results
            brave_api_key = os.environ.get("BRAVE_API_KEY")
            print("Fetching all sources from search results...")
            fetched_articles = _fetch_all_articles_async([brave_results], brave_api_key=brave_api_key)

            if fetched_articles:
                print(f"✓ Fetched {len(fetched_articles)} article(s) with full text")
                article_text = _format_fetched_articles_for_prompt(fetched_articles)
                search_results = f"{search_results}\n\n{article_text}"
            else:
                print("⚠ Could not fetch any articles")
        else:
            search_results = "(No search results available - use your knowledge base)"
            print("⚠ Brave Search unavailable, using Claude's knowledge base")

    # Load lessons for the research agent
    lessons = load_lessons("research", "organization")
    if lessons:
        print("✓ Loaded lessons for research agent")

    # Load the research prompt template
    template = load_prompt_template("card_research")

    # Format the prompt with search_query fallback for template
    query_display = search_query if search_query else "(Multi-strategy queries)"

    # Format the prompt
    side_info = "affirming" if side == Side.PRO else "negating"
    prompt = template.format(
        resolution=resolution,
        side=side_info,
        side_value=side.value.upper(),
        topic=topic,
        num_cards=num_cards,
        search_query=query_display,
        search_results=search_results,
    )

    # Prepend coverage analysis to help avoid duplication
    prompt = f"{coverage_prompt}\n\n---\n\n{prompt}"

    # Prepend lessons to the prompt
    if lessons:
        prompt = f"## Lessons Learned (consult before cutting cards)\n\n{lessons}\n\n---\n\n{prompt}"

    # Call Claude API with configured model
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)

    config = Config()
    model = config.get_agent_model("research")
    max_tokens = config.get_max_tokens()

    if stream:
        # Stream the response
        print("\nCutting evidence cards...\n")
        response_text = ""
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        ) as stream_response:
            for text in stream_response.text_stream:
                print(text, end="", flush=True)
                response_text += text
        print()  # Add newline after streaming
    else:
        # Non-streaming response
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        first_block = response.content[0]
        response_text = first_block.text if hasattr(first_block, "text") else ""

    # Parse the response and add cards to flat debate file
    try:
        from debate.evidence_storage import save_flat_debate_file
        from debate.models import ArgumentFile, SemanticGroup

        data = _extract_json_from_text(response_text)
        cards_data = data.get("cards", [])

        # Track evidence types found for reporting
        evidence_types_found: set[EvidenceType] = set()

        # Group cards by file_category, then by semantic_category
        file_groups: dict[str, dict[str, list[Card]]] = {}

        # Create Card objects and organize them
        for card_data in cards_data:
            # Parse evidence type
            evidence_type = _parse_evidence_type(card_data.get("evidence_type"))
            if evidence_type:
                evidence_types_found.add(evidence_type)

            # Parse the two-level structure
            file_category = card_data.get("file_category", topic)  # Broad category
            semantic_category = card_data.get("semantic_category", card_data.get("argument", topic))  # Medium-specific

            card = Card(
                tag=card_data["tag"],
                author=card_data["author"],
                credentials=card_data["credentials"],
                year=card_data["year"],
                source=card_data["source"],
                url=card_data.get("url"),
                text=card_data["text"],
                purpose=card_data.get("purpose", ""),
                evidence_type=evidence_type,
                semantic_category=semantic_category,  # Store semantic grouping on the card
            )

            # Organize cards by file_category → semantic_category
            if file_category not in file_groups:
                file_groups[file_category] = {}
            if semantic_category not in file_groups[file_category]:
                file_groups[file_category][semantic_category] = []
            file_groups[file_category][semantic_category].append(card)

        # Create or update ArgumentFiles
        for file_category, semantic_groups in file_groups.items():
            # Find existing argument file or create new one
            existing_arg = flat_file.find_argument(side, file_category)

            if existing_arg:
                # Add cards to existing argument file
                for semantic_category, cards in semantic_groups.items():
                    semantic_group = existing_arg.find_or_create_semantic_group(semantic_category)
                    for card in cards:
                        semantic_group.add_card(card)
            else:
                # Create new argument file
                section_type = _parse_section_type(cards_data[0].get("section_type", "support"))
                is_answer = section_type == SectionType.ANSWER

                new_arg = ArgumentFile(
                    title=file_category,
                    is_answer=is_answer,
                    answers_to=file_category if is_answer else None,
                    purpose=f"Evidence for: {file_category}",
                    semantic_groups=[
                        SemanticGroup(semantic_category=sem_cat, cards=cards_list)
                        for sem_cat, cards_list in semantic_groups.items()
                    ],
                )
                flat_file.add_argument(side, new_arg)

        # Report evidence diversity
        if evidence_types_found:
            type_names = [t.value for t in evidence_types_found]
            print(f"✓ Evidence types found: {', '.join(type_names)}")

        # Count cards added
        total_cards = sum(len(cards) for sem_groups in file_groups.values() for cards in sem_groups.values())
        print(f"✓ Added {total_cards} card(s) to {len(file_groups)} argument file(s)")

        # Save the updated flat debate file
        dir_path = save_flat_debate_file(flat_file)
        print(f"\n✓ Saved debate file to: {dir_path}")

        return flat_file

    except (json.JSONDecodeError, KeyError) as e:
        raise ValueError(f"Failed to parse research response: {e}\n\nResponse:\n{response_text}") from e


def research_evidence_efficient(
    resolution: str,
    side: Side,
    topic: str,
    purpose: SectionType,
    argument: str | None = None,
    num_cards: int = 1,
    search_query: str | None = None,
) -> list[str]:
    """Token-efficient research using card_import workflow.

    This workflow:
    1. Searches Brave for sources
    2. Saves raw results to temp file
    3. Asks LLM to mark up (add metadata + bold key warrants)
    4. Uses card_import to place card

    More token-efficient than full card extraction.

    Args:
        resolution: Debate resolution
        side: Which side (PRO/CON)
        topic: Research topic
        purpose: Section type (support, answer, extension, impact)
        argument: Specific argument this card addresses (defaults to topic if not provided)
        num_cards: Number of cards to cut (default 1)
        search_query: Optional custom search query

    Returns:
        List of file paths where cards were placed
    """
    from debate.card_import import import_card
    from debate.evidence_storage import get_or_create_debate_file

    # Default argument to topic if not provided
    if not argument:
        argument = topic

    # Load existing debate file
    debate_file, _is_new = get_or_create_debate_file(resolution)

    # Search Brave
    if not search_query:
        search_query = f"{resolution} {topic} {side.value}"

    print(f"Searching for: {topic}")
    print(f"  Query: {search_query[:70]}...")

    # Add 3-second pause to avoid rate limiting
    time.sleep(3)

    brave_results = _brave_search(search_query, num_results=20)

    if not brave_results:
        print("⚠ No search results available")
        return []

    search_results = brave_results
    print("✓ Found search results")

    # Create temp directory
    temp_dir = Path("evidence/temp")
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Save raw results to temp file
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_file = temp_dir / f"raw_{side.value}_{timestamp}.txt"
    temp_file.write_text(search_results)

    # Ask LLM to mark up the text (smaller task than full extraction)
    print("Marking up evidence...")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)

    config = Config()
    model = config.get_agent_model("research")

    markup_prompt = f"""You are marking up a source document for debate evidence.

**Task**: Add metadata and bold key warrants in the text below.

**Resolution**: {resolution}
**Side**: {side.value.upper()}
**Topic**: {topic}
**Purpose**: {purpose.value}
**Argument**: {argument}

**Source Text**:
{search_results}

**Instructions**:
1. Choose the BEST 1-2 paragraph excerpt that supports "{argument}"
2. Add metadata header:
   TAG: [what the card proves, 5-10 words]
   CITE: [author last name year, credentials]
   AUTHOR: [full author name]
   YEAR: [publication year]
   SECTION: {purpose.value}
   ARGUMENT: {argument}
   URL: [source URL]

3. Add >>> START before the excerpt
4. Bold key warrants using **text**
5. Add <<< END after the excerpt

**Output Format**:
TAG: Card tag line
CITE: Author '24, Credentials
AUTHOR: Full Author Name
YEAR: 2024
SECTION: {purpose.value}
ARGUMENT: {argument}
URL: https://...

>>> START
Excerpt text with **key warrants bolded** like this. The **most important claims** should be **bolded** for emphasis.
<<< END

Output ONLY the marked-up card. Do not include explanations."""

    # Get markup from LLM (streaming)
    print("  Extracting and marking up...")
    response_text = ""
    with client.messages.stream(
        model=model,
        max_tokens=1024,  # Smaller than full extraction
        messages=[{"role": "user", "content": markup_prompt}],
    ) as stream:
        for text in stream.text_stream:
            response_text += text

    # Save marked-up text
    temp_file.write_text(response_text)
    print(f"  Saved to {temp_file}")

    # Import using card_import
    try:
        paths = import_card(
            temp_file_path=str(temp_file),
            resolution=resolution,
            side=side,
        )

        print(f"✓ Imported {len(paths)} card(s):")
        for path in paths:
            print(f"  - {Path(path).relative_to('evidence')}")

        return paths

    except Exception as e:
        print(f"✗ Failed to import card: {e}")
        print(f"  Marked-up file saved at: {temp_file}")
        print("  You can manually review and fix the format, then run:")
        print(f'  uv run debate card-import {temp_file} "{resolution}" --side {side.value}')
        return []


def research_evidence_legacy(
    resolution: str,
    side: Side,
    topic: str,
    num_cards: int = 3,
    search_query: str | None = None,
    stream: bool = True,
) -> EvidenceBucket:
    """Research and cut evidence cards (legacy format returning EvidenceBucket).

    This is maintained for backwards compatibility. New code should use research_evidence().
    """
    flat_file = research_evidence(resolution, side, topic, num_cards, search_query, stream)

    # Convert to legacy EvidenceBucket format
    cards = flat_file.get_all_cards()
    bucket = EvidenceBucket(
        topic=topic,
        resolution=resolution,
        side=side,
        cards=cards,
    )
    return bucket


def research_case_evidence(
    resolution: str,
    side: Side,
    contentions: list[dict],
    cards_per_contention: int = 2,
) -> dict[str, EvidenceBucket]:
    """Research evidence for multiple contentions in a case.

    Args:
        resolution: The debate resolution
        side: Which side the case is on
        contentions: List of dicts with 'title' and 'topic' keys
        cards_per_contention: Cards to research per contention (default 2)

    Returns:
        Dictionary mapping contention titles to EvidenceBuckets

    Example:
        contentions = [
            {"title": "C1: Economic Growth", "topic": "economic impacts"},
            {"title": "C2: National Security", "topic": "security concerns"}
        ]
        buckets = research_case_evidence(resolution, Side.PRO, contentions)
    """
    buckets = {}

    for contention in contentions:
        title = contention["title"]
        topic = contention["topic"]

        flat_file = research_evidence(
            resolution=resolution,
            side=side,
            topic=topic,
            num_cards=cards_per_contention,
        )

        # Convert to EvidenceBucket for legacy compatibility
        cards = flat_file.get_all_cards()
        bucket = EvidenceBucket(
            topic=topic,
            resolution=resolution,
            side=side,
            cards=cards,
        )

        buckets[title] = bucket

    return buckets


# ========== Explore/Exploit Analysis ==========


def suggest_next_action(
    prep_state: PrepState,
    turn_budget_remaining: int,
) -> dict:
    """Suggest whether to explore or exploit based on prep state.

    Applies RL-inspired explore/exploit logic:
    - Early prep: favor exploration (discover argument space)
    - Thin coverage: exploit (deepen evidence)
    - Diminishing returns: switch to explore elsewhere
    - Low opponent coverage: explore adversarially

    Args:
        prep_state: Current state of prep
        turn_budget_remaining: How many turns left

    Returns:
        Action dict with mode, reason, suggestion, priority
    """
    from debate.models import ExploreExploitMode, PrepAction

    # Early prep: explore the argument space first
    if prep_state.argument_space_coverage < 0.3:
        return PrepAction(
            mode=ExploreExploitMode.EXPLORE,
            reason="Argument space under-explored (<30% coverage)",
            suggestion="Run enumerate_arguments or adversarial_brainstorm to discover arguments",
            priority=0.9,
        ).model_dump()

    # Have arguments but thin evidence: exploit
    weakest = prep_state.get_weakest_argument()
    if prep_state.avg_evidence_depth < 2 and prep_state.argument_space_coverage > 0.5:
        return PrepAction(
            mode=ExploreExploitMode.EXPLOIT,
            reason=f"Arguments identified but evidence thin (avg {prep_state.avg_evidence_depth:.1f} cards)",
            suggestion=f"Research more cards for: {weakest}" if weakest else "Deepen evidence on core arguments",
            priority=0.8,
        ).model_dump()

    # Check for diminishing returns on strongest argument
    strongest = prep_state.get_strongest_argument()
    if strongest and prep_state.arguments.get(strongest):
        arg_state = prep_state.arguments[strongest]
        if arg_state.last_research_yield == 0 and arg_state.times_researched >= 2:
            return PrepAction(
                mode=ExploreExploitMode.EXPLORE,
                reason=f"Diminishing returns on '{strongest}' (0 cards in last research)",
                suggestion="Explore new arguments or opponent weaknesses",
                priority=0.7,
            ).model_dump()

    # Low opponent coverage: explore adversarially
    if prep_state.opponent_coverage < 0.4 and prep_state.opponent_arguments_identified > 0:
        return PrepAction(
            mode=ExploreExploitMode.EXPLORE,
            reason=f"Few answers to opponent args ({prep_state.opponent_coverage:.0%} coverage)",
            suggestion="Brainstorm opponent's best arguments, then research AT cards",
            priority=0.85,
        ).model_dump()

    # Late prep with budget: exploit weakest links
    if turn_budget_remaining <= 3:
        return PrepAction(
            mode=ExploreExploitMode.EXPLOIT,
            reason=f"Limited budget remaining ({turn_budget_remaining} turns)",
            suggestion=f"Shore up weakest argument: {weakest}" if weakest else "Finalize strongest arguments",
            priority=0.75,
        ).model_dump()

    # Default: balanced exploration
    return PrepAction(
        mode=ExploreExploitMode.EXPLORE,
        reason="Balanced prep state - continue building",
        suggestion="Research next priority argument or explore new angles",
        priority=0.5,
    ).model_dump()


def build_prep_state_from_debate_file(
    debate_file: DebateFile | FlatDebateFile | None,
    side: Side,
) -> PrepState:
    """Build PrepState from an existing debate file.

    Analyzes the debate file to track:
    - Arguments and their evidence depth
    - Evidence types per argument
    - Opponent argument coverage (for AT files)

    Args:
        debate_file: Existing debate file
        side: Side we're prepping for

    Returns:
        PrepState with current coverage analysis
    """
    state = PrepState()

    if not debate_file:
        return state

    if isinstance(debate_file, FlatDebateFile):
        # New flat structure
        args = debate_file.get_arguments_for_side(side)
        opponent_args = debate_file.get_arguments_for_side(side.opposite)

        for arg in args:
            cards = arg.get_all_cards()
            evidence_types = set()
            for card in cards:
                if card.evidence_type:
                    evidence_types.add(card.evidence_type)

            state.update_argument(arg.title, len(cards), evidence_types)

            if arg.is_answer:
                state.opponent_arguments_answered += 1

        # Count opponent arguments we might need to answer
        state.opponent_arguments_identified = len([a for a in opponent_args if not a.is_answer])
    else:
        # Old structure
        sections = debate_file.get_sections_for_side(side)
        for section in sections:
            cards = [c for cid in section.card_ids if (c := debate_file.get_card(cid)) is not None]
            evidence_types = {c.evidence_type for c in cards if c.evidence_type}

            state.update_argument(section.argument, len(cards), evidence_types)

            if section.section_type == SectionType.ANSWER:
                state.opponent_arguments_answered += 1

    return state
