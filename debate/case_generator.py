"""Generate debate cases using the Anthropic API."""

import json
from pathlib import Path

import anthropic

from debate.models import Case, Contention, Side


def load_prompt_template(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompts_dir = Path(__file__).parent / "prompts"
    template_path = prompts_dir / f"{name}.md"
    return template_path.read_text()


def generate_case(resolution: str, side: Side) -> Case:
    """Generate a debate case for the given resolution and side.

    Args:
        resolution: The debate resolution text
        side: Which side to generate (PRO or CON)

    Returns:
        A Case object with 2-3 contentions
    """
    client = anthropic.Anthropic()

    template = load_prompt_template("case_generation")

    side_description = "affirms the resolution" if side == Side.PRO else "negates the resolution"
    side_instruction = (
        "Argue that the resolution is true and should be affirmed"
        if side == Side.PRO
        else "Argue that the resolution is false and should be negated"
    )

    prompt = template.format(
        resolution=resolution,
        side=side.value.upper(),
        side_description=side_description,
        side_instruction=side_instruction,
    )

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
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
    for c in data.get("contentions", []):
        contentions.append(
            Contention(
                title=c["title"],
                content=c["content"],
            )
        )

    if len(contentions) < 2:
        raise ValueError(f"Expected 2-3 contentions, got {len(contentions)}")

    return contentions
