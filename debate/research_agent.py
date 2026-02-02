"""Research agent for finding and cutting evidence cards.

This module provides cost-effective evidence research by:
1. Using Brave Search to find relevant sources
2. Using Claude Haiku to extract and format evidence cards
3. Organizing cards into debate files by strategic value
"""

import json
import os
from typing import Optional

import anthropic
import requests

from debate.models import Card, DebateFile, EvidenceBucket, SectionType, Side
from debate.evidence_storage import get_or_create_debate_file, save_debate_file


def load_prompt_template(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", f"{name}.md")
    with open(prompt_path, "r") as f:
        return f.read()


def _brave_search(query: str, num_results: int = 5) -> Optional[str]:
    """Search Brave for relevant sources.

    Args:
        query: Search query
        num_results: Number of results to fetch (default 5)

    Returns:
        Formatted search results as a string, or None if search fails
    """
    api_key = os.environ.get("BRAVE_API_KEY")

    if not api_key:
        return None

    try:
        headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}
        params = {"q": query, "count": num_results}

        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers,
            params=params,
            timeout=10,
        )

        if response.status_code != 200:
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
        print(f"Warning: Brave Search failed: {e}")
        return None


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


def research_evidence(
    resolution: str,
    side: Side,
    topic: str,
    num_cards: int = 3,
    search_query: Optional[str] = None,
    stream: bool = True,
) -> DebateFile:
    """Research and cut evidence cards for a specific argument.

    Args:
        resolution: The debate resolution
        side: Which side (PRO/CON) the evidence supports
        topic: The specific argument/topic to research (e.g., "Economic impacts")
        num_cards: How many cards to cut (default 3, max 5 for cost control)
        search_query: Optional custom search query (auto-generated if not provided)
        stream: Whether to stream tokens as they're generated (default True)

    Returns:
        DebateFile with researched evidence cards organized by strategic value

    Cost optimization:
        - Uses Haiku (cheapest model) for card cutting
        - Limits to 5 cards max per research session
        - Uses efficient prompts to minimize token usage
    """
    if num_cards > 5:
        raise ValueError("Maximum 5 cards per research session to control costs")

    # Load or create debate file for this resolution
    debate_file, is_new = get_or_create_debate_file(resolution)
    if is_new:
        print(f"Creating new debate file for: {resolution}")
    else:
        print(f"Adding to existing debate file ({len(debate_file.cards)} cards)")

    # Generate search query if not provided
    if not search_query:
        search_query = f"{resolution} {topic} {side.value}"

    # Perform Brave Search
    print("Searching Brave for relevant sources...")
    search_results = _brave_search(search_query, num_results=5)

    if search_results:
        print("✓ Found search results from Brave")
    else:
        print("⚠ Brave Search unavailable, using Claude's knowledge base")
        search_results = "(No search results available - use your knowledge base)"

    # Load the research prompt template
    template = load_prompt_template("card_research")

    # Format the prompt
    side_info = "affirming" if side == Side.PRO else "negating"
    prompt = template.format(
        resolution=resolution,
        side=side_info,
        side_value=side.value.upper(),
        topic=topic,
        num_cards=num_cards,
        search_query=search_query,
        search_results=search_results,
    )

    # Call Claude API with Haiku for cost-effectiveness
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)

    if stream:
        # Stream the response
        print("\nCutting evidence cards...\n")
        response_text = ""
        with client.messages.stream(
            model="claude-haiku-4-20250514",  # Most cost-effective model
            max_tokens=4096,  # Limit tokens for cost control
            messages=[{"role": "user", "content": prompt}],
        ) as stream_response:
            for text in stream_response.text_stream:
                print(text, end="", flush=True)
                response_text += text
        print()  # Add newline after streaming
    else:
        # Non-streaming response
        response = client.messages.create(
            model="claude-haiku-4-20250514",  # Most cost-effective model
            max_tokens=4096,  # Limit tokens for cost control
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = response.content[0].text

    # Parse the response and add cards to debate file
    try:
        data = _extract_json_from_text(response_text)
        cards_data = data.get("cards", [])

        # Create Card objects and add to debate file
        for card_data in cards_data:
            card = Card(
                tag=card_data["tag"],
                author=card_data["author"],
                credentials=card_data["credentials"],
                year=card_data["year"],
                source=card_data["source"],
                url=card_data.get("url"),
                text=card_data["text"],
                purpose=card_data.get("purpose", ""),
            )

            # Add card to master list
            card_id = debate_file.add_card(card)

            # Add card to appropriate section
            section_type = _parse_section_type(card_data.get("section_type", "support"))
            argument = card_data.get("argument", topic)

            debate_file.add_to_section(
                side=side,
                section_type=section_type,
                argument=argument,
                card_id=card_id,
            )

        # Save the updated debate file
        dir_path = save_debate_file(debate_file)
        print(f"\n✓ Saved debate file to: {dir_path}")

        return debate_file

    except (json.JSONDecodeError, KeyError) as e:
        raise ValueError(f"Failed to parse research response: {e}\n\nResponse:\n{response_text}")


def research_evidence_legacy(
    resolution: str,
    side: Side,
    topic: str,
    num_cards: int = 3,
    search_query: Optional[str] = None,
    stream: bool = True,
) -> EvidenceBucket:
    """Research and cut evidence cards (legacy format returning EvidenceBucket).

    This is maintained for backwards compatibility. New code should use research_evidence().
    """
    debate_file = research_evidence(resolution, side, topic, num_cards, search_query, stream)

    # Convert to legacy EvidenceBucket format
    cards = [debate_file.cards[cid] for cid in debate_file.cards]
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

        bucket = research_evidence(
            resolution=resolution,
            side=side,
            topic=topic,
            num_cards=cards_per_contention,
        )

        buckets[title] = bucket

    return buckets
