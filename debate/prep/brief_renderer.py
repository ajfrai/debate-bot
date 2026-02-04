"""Renders brief JSON to markdown and saves to evidence storage."""

import json
from pathlib import Path
from typing import Any

from debate.evidence_storage import (
    get_or_create_flat_debate_file,
    save_flat_debate_file,
)
from debate.models import ArgumentFile, Card, FlatDebateFile, SemanticGroup, Side


def render_brief_to_markdown(brief: dict[str, Any]) -> str:
    """Render brief JSON to readable markdown.

    Args:
        brief: The brief JSON structure

    Returns:
        Formatted markdown string
    """
    lines = [
        f"# {brief.get('resolution', 'Debate Brief')}",
        f"**Side:** {brief.get('side', '').upper()}",
        "",
    ]

    # Render arguments
    arguments = brief.get("arguments", {})
    if arguments:
        lines.append("## Arguments")
        lines.append("")

        for arg_name, arg_data in arguments.items():
            lines.append(f"### {arg_data.get('name', arg_name)}")
            lines.append("")

            for group_key, group_data in arg_data.get("semantic_groups", {}).items():
                claim = group_data.get("claim", group_key)
                lines.append(f"#### {claim}")
                lines.append("")

                for i, card in enumerate(group_data.get("cards", []), 1):
                    author = card.get("author", "Unknown")
                    year = card.get("year", "")
                    tag = card.get("tag", "")

                    lines.append(f"**{i}. {author} '{year[-2:] if len(year) >= 2 else year}**")
                    lines.append("")
                    lines.append(f"*{tag}*")
                    lines.append("")

                    # Citation
                    lines.append(f"**{author}**")
                    if card.get("source_name"):
                        lines.append(f"*{card['source_name']}*, {year}")
                    if card.get("url"):
                        lines.append(f"[Source]({card['url']})")
                    lines.append("")

                    # Card text
                    text = card.get("text", "")
                    lines.append(text)
                    lines.append("")
                    lines.append("---")
                    lines.append(f"*Card ID: {card.get('id', '')}*")
                    lines.append("")

    # Render answers
    answers = brief.get("answers", {})
    if answers:
        lines.append("## Answers (AT)")
        lines.append("")

        for arg_name, arg_data in answers.items():
            lines.append(f"### AT: {arg_data.get('name', arg_name)}")
            lines.append("")

            for group_key, group_data in arg_data.get("semantic_groups", {}).items():
                claim = group_data.get("claim", group_key)
                lines.append(f"#### {claim}")
                lines.append("")

                for i, card in enumerate(group_data.get("cards", []), 1):
                    author = card.get("author", "Unknown")
                    year = card.get("year", "")
                    tag = card.get("tag", "")

                    lines.append(f"**{i}. {author} '{year[-2:] if len(year) >= 2 else year}**")
                    lines.append("")
                    lines.append(f"*{tag}*")
                    lines.append("")

                    lines.append(f"**{author}**")
                    if card.get("source_name"):
                        lines.append(f"*{card['source_name']}*, {year}")
                    if card.get("url"):
                        lines.append(f"[Source]({card['url']})")
                    lines.append("")

                    text = card.get("text", "")
                    lines.append(text)
                    lines.append("")
                    lines.append("---")
                    lines.append(f"*Card ID: {card.get('id', '')}*")
                    lines.append("")

    return "\n".join(lines)


def brief_to_flat_debate_file(brief: dict[str, Any]) -> FlatDebateFile:
    """Convert brief JSON to FlatDebateFile model.

    Args:
        brief: The brief JSON structure

    Returns:
        FlatDebateFile model
    """
    resolution = brief.get("resolution", "")
    side_str = brief.get("side", "pro")
    side = Side.PRO if side_str.lower() == "pro" else Side.CON

    flat_file = FlatDebateFile(resolution=resolution)

    # Convert arguments
    for arg_name, arg_data in brief.get("arguments", {}).items():
        semantic_groups = []

        for group_key, group_data in arg_data.get("semantic_groups", {}).items():
            cards = []
            for card_data in group_data.get("cards", []):
                card = Card(
                    id=card_data.get("id", ""),
                    tag=card_data.get("tag", ""),
                    author=card_data.get("author", "Unknown"),
                    credentials="",
                    year=card_data.get("year", "2024"),
                    source=card_data.get("source_name", ""),
                    url=card_data.get("url"),
                    text=card_data.get("text", ""),
                    semantic_category=group_data.get("claim", group_key),
                )
                cards.append(card)

            if cards:
                semantic_groups.append(
                    SemanticGroup(
                        semantic_category=group_data.get("claim", group_key),
                        cards=cards,
                    )
                )

        if semantic_groups:
            arg_file = ArgumentFile(
                title=arg_data.get("name", arg_name),
                is_answer=False,
                purpose=f"Evidence for: {arg_name}",
                semantic_groups=semantic_groups,
            )
            flat_file.add_argument(side, arg_file)

    # Convert answers
    for arg_name, arg_data in brief.get("answers", {}).items():
        semantic_groups = []

        for group_key, group_data in arg_data.get("semantic_groups", {}).items():
            cards = []
            for card_data in group_data.get("cards", []):
                card = Card(
                    id=card_data.get("id", ""),
                    tag=card_data.get("tag", ""),
                    author=card_data.get("author", "Unknown"),
                    credentials="",
                    year=card_data.get("year", "2024"),
                    source=card_data.get("source_name", ""),
                    url=card_data.get("url"),
                    text=card_data.get("text", ""),
                    semantic_category=group_data.get("claim", group_key),
                )
                cards.append(card)

            if cards:
                semantic_groups.append(
                    SemanticGroup(
                        semantic_category=group_data.get("claim", group_key),
                        cards=cards,
                    )
                )

        if semantic_groups:
            arg_file = ArgumentFile(
                title=arg_data.get("name", arg_name),
                is_answer=True,
                answers_to=arg_name,
                purpose=f"Answer to: {arg_name}",
                semantic_groups=semantic_groups,
            )
            flat_file.add_argument(side, arg_file)

    return flat_file


def save_brief_to_evidence(brief: dict[str, Any]) -> str:
    """Save brief to the evidence storage system.

    Merges with existing evidence if present.

    Args:
        brief: The brief JSON structure

    Returns:
        Path to saved evidence directory
    """
    resolution = brief.get("resolution", "")
    side_str = brief.get("side", "pro")
    side = Side.PRO if side_str.lower() == "pro" else Side.CON

    # Load or create existing file
    existing_file, is_new = get_or_create_flat_debate_file(resolution)

    # Convert brief to FlatDebateFile
    new_file = brief_to_flat_debate_file(brief)

    # Merge: add new arguments/cards to existing
    for new_arg in new_file.get_arguments_for_side(side):
        existing_arg = existing_file.find_argument(side, new_arg.title)

        if existing_arg:
            # Merge semantic groups
            for new_group in new_arg.semantic_groups:
                existing_group = existing_arg.find_or_create_semantic_group(new_group.semantic_category)
                # Add cards that don't already exist
                existing_ids = {c.id for c in existing_group.cards}
                for card in new_group.cards:
                    if card.id not in existing_ids:
                        existing_group.cards.append(card)
        else:
            # Add new argument
            existing_file.add_argument(side, new_arg)

    # Save
    return save_flat_debate_file(existing_file)


def finalize_brief(staging_dir: Path, resolution: str, side: Side) -> str:
    """Finalize prep session by saving brief to evidence storage.

    Args:
        staging_dir: Path to staging directory
        resolution: The debate resolution
        side: Which side

    Returns:
        Path to saved evidence directory
    """
    brief_path = staging_dir / "organizer" / "brief.json"

    if not brief_path.exists():
        raise FileNotFoundError(f"Brief not found at {brief_path}")

    brief = json.loads(brief_path.read_text())
    brief["resolution"] = resolution
    brief["side"] = side.value

    return save_brief_to_evidence(brief)
