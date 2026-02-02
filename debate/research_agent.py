"""Research agent for finding and cutting evidence cards.

This module provides cost-effective evidence research by:
1. Using web search to find relevant sources
2. Using Claude Haiku to extract and format evidence cards
3. Organizing cards into evidence buckets by argument
"""

import json
import os
from typing import Optional

import anthropic

from debate.models import Card, EvidenceBucket, Side


def load_prompt_template(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", f"{name}.md")
    with open(prompt_path, "r") as f:
        return f.read()


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


def research_evidence(
    resolution: str,
    side: Side,
    topic: str,
    num_cards: int = 3,
    search_query: Optional[str] = None,
) -> EvidenceBucket:
    """Research and cut evidence cards for a specific argument.

    Args:
        resolution: The debate resolution
        side: Which side (PRO/CON) the evidence supports
        topic: The specific argument/topic to research (e.g., "Economic impacts")
        num_cards: How many cards to cut (default 3, max 5 for cost control)
        search_query: Optional custom search query (auto-generated if not provided)

    Returns:
        EvidenceBucket with researched evidence cards

    Cost optimization:
        - Uses Haiku (cheapest model) for card cutting
        - Limits to 5 cards max per research session
        - Uses efficient prompts to minimize token usage
    """
    if num_cards > 5:
        raise ValueError("Maximum 5 cards per research session to control costs")

    # Load the research prompt template
    template = load_prompt_template("card_research")

    # Generate search query if not provided
    if not search_query:
        search_query = f"{resolution} {topic} {side.value}"

    # Format the prompt
    side_info = "affirming" if side == Side.PRO else "negating"
    prompt = template.format(
        resolution=resolution,
        side=side_info,
        side_value=side.value.upper(),
        topic=topic,
        num_cards=num_cards,
        search_query=search_query,
    )

    # Call Claude API with Haiku for cost-effectiveness
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-haiku-4-20250514",  # Most cost-effective model
        max_tokens=4096,  # Limit tokens for cost control
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = response.content[0].text

    # Parse the response
    try:
        data = _extract_json_from_text(response_text)
        cards_data = data.get("cards", [])

        # Create Card objects
        cards = []
        for card_data in cards_data:
            card = Card(
                tag=card_data["tag"],
                author=card_data["author"],
                credentials=card_data["credentials"],
                year=card_data["year"],
                source=card_data["source"],
                url=card_data.get("url"),
                text=card_data["text"],
            )
            cards.append(card)

        # Create evidence bucket
        bucket = EvidenceBucket(
            topic=topic,
            resolution=resolution,
            side=side,
            cards=cards,
        )

        return bucket

    except (json.JSONDecodeError, KeyError) as e:
        raise ValueError(f"Failed to parse research response: {e}\n\nResponse:\n{response_text}")


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
