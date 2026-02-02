"""Generate debate cases using the Anthropic API."""

import json
import sys
from pathlib import Path
from typing import Optional

import anthropic

from debate.config import Config
from debate.models import Case, Contention, EvidenceBucket, Side, DebateFile


def load_prompt_template(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompts_dir = Path(__file__).parent / "prompts"
    template_path = prompts_dir / f"{name}.md"
    return template_path.read_text()


def generate_case(
    resolution: str,
    side: Side,
    evidence_buckets: list[EvidenceBucket] | None = None,
    stream: bool = True,
) -> Case:
    """Generate a debate case for the given resolution and side.

    Args:
        resolution: The debate resolution text
        side: Which side to generate (PRO or CON)
        evidence_buckets: Optional list of evidence buckets to use for the case.
                         If provided, the case will use real evidence cards.
                         If None, the case will use fabricated evidence.
        stream: Whether to stream tokens as they're generated (default True)

    Returns:
        A Case object with 2-3 contentions
    """
    client = anthropic.Anthropic()
    config = Config()

    # Choose template based on whether we have evidence
    if evidence_buckets:
        template = load_prompt_template("case_generation_with_evidence")
    else:
        template = load_prompt_template("case_generation")

    side_description = "affirms the resolution" if side == Side.PRO else "negates the resolution"
    side_instruction = (
        "Argue that the resolution is true and should be affirmed"
        if side == Side.PRO
        else "Argue that the resolution is false and should be negated"
    )

    # Format evidence buckets if provided
    evidence_section = ""
    if evidence_buckets:
        evidence_section = _format_evidence_buckets(evidence_buckets)

    # Get word limits from config
    min_words, max_words = config.get_case_word_limits()

    prompt = template.format(
        resolution=resolution,
        side=side.value.upper(),
        side_description=side_description,
        side_instruction=side_instruction,
        evidence_buckets=evidence_section,
        min_words=min_words,
        max_words=max_words,
    )

    model = config.get_agent_model("case_generator")
    max_tokens = config.get_max_tokens()

    if stream:
        # Stream the response
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
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text

    # Extract JSON from the response
    contentions = _parse_case_response(response_text)

    return Case(
        resolution=resolution,
        side=side,
        contentions=contentions,
    )


def _format_evidence_buckets(buckets: list[EvidenceBucket]) -> str:
    """Format evidence buckets for inclusion in the prompt."""
    lines = ["## Available Evidence\n"]

    for bucket in buckets:
        lines.append(f"### {bucket.topic}\n")

        for i, card in enumerate(bucket.cards, 1):
            last_name = card.author.split()[-1]
            lines.append(f"{i}. **{card.tag}** ({last_name} {card.year})")
            lines.append(f"   - Author: {card.author}, {card.credentials}")
            lines.append(f"   - Source: {card.source}, {card.year}")
            if card.url:
                lines.append(f"   - URL: {card.url}")
            lines.append(f"   - Text: {card.text}")
            lines.append("")

    return "\n".join(lines)


def _extract_json_from_text(text: str) -> str:
    """Extract JSON object from text, handling markdown code blocks."""
    import re

    # Try to extract JSON from markdown code block first
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if code_block_match:
        potential_json = code_block_match.group(1).strip()
        if potential_json.startswith("{"):
            return potential_json

    # Fall back to finding raw JSON by matching balanced braces
    json_start = text.find("{")
    if json_start == -1:
        raise ValueError("No JSON found in response")

    # Count braces to find the matching closing brace
    depth = 0
    in_string = False
    escape_next = False
    json_end = json_start

    for i, char in enumerate(text[json_start:], start=json_start):
        if escape_next:
            escape_next = False
            continue

        if char == "\\":
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                json_end = i + 1
                break

    if depth != 0:
        raise ValueError("Unbalanced JSON braces in response")

    return text[json_start:json_end]


def _count_words(text: str) -> int:
    """Count the number of words in a text string."""
    return len(text.split())


def _parse_case_response(response_text: str) -> list[Contention]:
    """Parse the LLM response into Contention objects."""
    json_str = _extract_json_from_text(response_text)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        # Show context around the error
        error_pos = e.pos if hasattr(e, "pos") else 0
        context_start = max(0, error_pos - 50)
        context_end = min(len(json_str), error_pos + 50)
        context = json_str[context_start:context_end]
        raise ValueError(f"JSON parse error at position {error_pos}: {e.msg}\nContext: ...{context}...") from e

    contentions = []
    config = Config()
    min_words, max_words = config.get_case_word_limits()

    for i, c in enumerate(data.get("contentions", []), 1):
        content = c["content"]
        word_count = _count_words(content)

        # Warn if word count is outside the configured limits
        if word_count < min_words:
            print(f"⚠️  Warning: Contention {i} has {word_count} words (minimum: {min_words})")
        elif word_count > max_words:
            print(f"⚠️  Warning: Contention {i} has {word_count} words (maximum: {max_words})")

        contentions.append(
            Contention(
                title=c["title"],
                content=content,
            )
        )

    if len(contentions) < 2:
        raise ValueError(f"Expected 2-3 contentions, got {len(contentions)}")

    return contentions


