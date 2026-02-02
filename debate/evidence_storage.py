"""Storage system for debate files and evidence.

Manages saving and loading debate files as directory trees,
optimized for quick searching during rounds.

Directory structure:
    evidence/
        {resolution_slug}/
            INDEX.md                    # Master table of contents
            pro/
                support/
                    {tag_slug}.md       # Individual card files
                answer/
                    {tag_slug}.md
                extension/
                    {tag_slug}.md
                impact/
                    {tag_slug}.md
            con/
                support/
                answer/
                extension/
                impact/

This structure allows:
    - `ls pro/answer/` to see all answers
    - `grep -r "billion" pro/` to find cards fast
    - Direct file access for any card
"""

import json
import os
from pathlib import Path
from typing import Optional

from debate.models import Card, DebateFile, EvidenceBucket, SectionType, Side


def get_evidence_dir() -> Path:
    """Get the evidence storage directory, creating it if needed."""
    evidence_dir = Path("evidence")
    evidence_dir.mkdir(exist_ok=True)
    return evidence_dir


def sanitize_filename(text: str, max_length: int = 60) -> str:
    """Convert text to a safe filename/directory name."""
    safe = text.lower()
    safe = safe.replace(" ", "_")
    safe = safe.replace(":", "")
    safe = safe.replace("/", "_")
    safe = safe.replace("\\", "_")
    safe = safe.replace("'", "")
    safe = safe.replace('"', "")
    safe = safe.replace(".", "")
    safe = safe.replace(",", "")
    # Keep only alphanumeric, underscore, hyphen
    safe = "".join(c for c in safe if c.isalnum() or c in "_-")
    # Remove consecutive underscores
    while "__" in safe:
        safe = safe.replace("__", "_")
    # Strip leading/trailing underscores
    safe = safe.strip("_")
    return safe[:max_length]


def get_resolution_dir(resolution: str) -> Path:
    """Get the directory for a resolution, creating it if needed."""
    evidence_dir = get_evidence_dir()
    resolution_slug = sanitize_filename(resolution, max_length=80)
    resolution_dir = evidence_dir / resolution_slug
    resolution_dir.mkdir(exist_ok=True)
    return resolution_dir


def get_section_type_dir(section_type: SectionType) -> str:
    """Get directory name for a section type."""
    return section_type.value  # support, answer, extension, impact


def render_card_markdown(card: Card) -> str:
    """Render a card as a standalone markdown file."""
    lines = [
        f"# {card.tag}",
        "",
    ]

    if card.purpose:
        lines.extend([
            f"**Purpose:** {card.purpose}",
            "",
        ])

    lines.extend([
        "---",
        "",
        f"**{card.author}**, {card.credentials}",
        f"*{card.source}*, {card.year}",
    ])

    if card.url:
        lines.append(f"[Source]({card.url})")

    lines.extend([
        "",
        "---",
        "",
        card.text,
        "",
        "---",
        f"*Card ID: {card.id}*",
    ])

    return "\n".join(lines)


def save_debate_file(debate_file: DebateFile) -> str:
    """Save a debate file as a directory tree.

    Args:
        debate_file: The debate file to save

    Returns:
        Path to the resolution directory

    Creates:
        evidence/{resolution}/INDEX.md
        evidence/{resolution}/pro/{section_type}/{tag}.md
        evidence/{resolution}/con/{section_type}/{tag}.md
    """
    resolution_dir = get_resolution_dir(debate_file.resolution)

    # Create side directories
    for side in ["pro", "con"]:
        side_dir = resolution_dir / side
        side_dir.mkdir(exist_ok=True)
        for section_type in SectionType:
            (side_dir / section_type.value).mkdir(exist_ok=True)

    # Save cards to their section directories
    saved_cards = set()  # Track which cards we've saved

    def save_sections(sections, side_name: str):
        for section in sections:
            section_dir = resolution_dir / side_name / section.section_type.value

            for card_id in section.card_ids:
                card = debate_file.cards.get(card_id)
                if not card:
                    continue

                # Create filename from the section's specific argument + card tag
                # This makes files more specific and searchable
                filename = sanitize_filename(card.tag) + ".md"
                filepath = section_dir / filename

                # Write the card file
                with open(filepath, "w") as f:
                    f.write(render_card_markdown(card))

                saved_cards.add(card_id)

    save_sections(debate_file.pro_sections, "pro")
    save_sections(debate_file.con_sections, "con")

    # Generate and save INDEX.md
    index_content = generate_index_markdown(debate_file, resolution_dir)
    index_path = resolution_dir / "INDEX.md"
    with open(index_path, "w") as f:
        f.write(index_content)

    # Also save a minimal JSON for programmatic loading
    # (just metadata, cards are in the markdown files)
    meta_path = resolution_dir / ".debate_meta.json"
    meta = {
        "resolution": debate_file.resolution,
        "cards": {cid: card.model_dump() for cid, card in debate_file.cards.items()},
        "pro_sections": [s.model_dump() for s in debate_file.pro_sections],
        "con_sections": [s.model_dump() for s in debate_file.con_sections],
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    return str(resolution_dir)


def generate_index_markdown(debate_file: DebateFile, resolution_dir: Path) -> str:
    """Generate the INDEX.md table of contents."""
    lines = [
        f"# {debate_file.resolution}",
        "",
        "## Quick Navigation",
        "",
        "```",
        f"grep -r \"keyword\" {resolution_dir}/pro/   # Search PRO evidence",
        f"grep -r \"keyword\" {resolution_dir}/con/   # Search CON evidence",
        f"ls {resolution_dir}/pro/answer/             # List all PRO answers",
        "```",
        "",
    ]

    def render_side(sections, side_name: str, side_label: str):
        if not sections:
            return

        lines.append(f"## {side_label}")
        lines.append("")

        # Group by section type
        by_type = {}
        for section in sections:
            if section.section_type not in by_type:
                by_type[section.section_type] = []
            by_type[section.section_type].append(section)

        type_labels = {
            SectionType.SUPPORT: "Supporting Evidence",
            SectionType.ANSWER: "Answers",
            SectionType.EXTENSION: "Extensions",
            SectionType.IMPACT: "Impact Evidence",
        }

        for section_type in SectionType:
            if section_type not in by_type:
                continue

            lines.append(f"### {type_labels[section_type]}")
            lines.append(f"*`{side_name}/{section_type.value}/`*")
            lines.append("")

            for section in by_type[section_type]:
                lines.append(f"**{section.argument}**")
                for card_id in section.card_ids:
                    card = debate_file.cards.get(card_id)
                    if card:
                        filename = sanitize_filename(card.tag) + ".md"
                        filepath = f"{side_name}/{section_type.value}/{filename}"
                        last_name = card.author.split()[-1]
                        lines.append(f"- [{card.tag}]({filepath}) ({last_name} {card.year})")
                lines.append("")

    render_side(debate_file.pro_sections, "pro", "PRO")
    render_side(debate_file.con_sections, "con", "CON")

    return "\n".join(lines)


def load_debate_file(resolution: str) -> Optional[DebateFile]:
    """Load a debate file from its directory.

    Args:
        resolution: The debate resolution

    Returns:
        DebateFile if found, None otherwise
    """
    resolution_dir = get_resolution_dir(resolution)
    meta_path = resolution_dir / ".debate_meta.json"

    if not meta_path.exists():
        return None

    with open(meta_path, "r") as f:
        meta = json.load(f)

    return DebateFile.model_validate(meta)


def get_or_create_debate_file(resolution: str) -> tuple[DebateFile, bool]:
    """Get existing debate file or create a new empty one.

    Args:
        resolution: The debate resolution

    Returns:
        Tuple of (DebateFile, is_new)
    """
    existing = load_debate_file(resolution)

    if existing:
        return existing, False

    new_file = DebateFile(resolution=resolution)
    return new_file, True


def list_debate_files() -> list[dict]:
    """List all debate files.

    Returns:
        List of dicts with resolution info
    """
    evidence_dir = get_evidence_dir()
    files = []

    for dir_path in evidence_dir.iterdir():
        if not dir_path.is_dir():
            continue

        meta_path = dir_path / ".debate_meta.json"
        if not meta_path.exists():
            continue

        try:
            debate_file = load_debate_file(dir_path.name)
            if debate_file:
                files.append({
                    "resolution": debate_file.resolution,
                    "dir_path": str(dir_path),
                    "num_cards": len(debate_file.cards),
                    "num_pro_sections": len(debate_file.pro_sections),
                    "num_con_sections": len(debate_file.con_sections),
                })
        except Exception:
            continue

    return files


# --- Backwards compatibility functions for EvidenceBucket ---


def save_evidence_bucket(bucket: EvidenceBucket) -> str:
    """Save an evidence bucket to a JSON file (legacy format)."""
    evidence_dir = get_evidence_dir()

    resolution_slug = sanitize_filename(bucket.resolution)
    side_slug = bucket.side.value
    topic_slug = sanitize_filename(bucket.topic)
    filename = f"{resolution_slug}_{side_slug}_{topic_slug}.json"

    filepath = evidence_dir / filename

    with open(filepath, "w") as f:
        json.dump(bucket.model_dump(), f, indent=2)

    return str(filepath)


def load_evidence_bucket(filepath: str) -> EvidenceBucket:
    """Load an evidence bucket from a JSON file."""
    with open(filepath, "r") as f:
        data = json.load(f)
    return EvidenceBucket.model_validate(data)


def find_evidence_bucket(
    resolution: str,
    side: Side,
    topic: str,
) -> Optional[EvidenceBucket]:
    """Find and load an evidence bucket if it exists."""
    evidence_dir = get_evidence_dir()

    resolution_slug = sanitize_filename(resolution)
    side_slug = side.value
    topic_slug = sanitize_filename(topic)
    filename = f"{resolution_slug}_{side_slug}_{topic_slug}.json"

    filepath = evidence_dir / filename

    if filepath.exists():
        return load_evidence_bucket(str(filepath))

    return None


def list_evidence_buckets(resolution: Optional[str] = None) -> list[dict]:
    """List all evidence buckets, optionally filtered by resolution."""
    evidence_dir = get_evidence_dir()
    buckets = []

    for filepath in evidence_dir.glob("*.json"):
        try:
            bucket = load_evidence_bucket(str(filepath))

            if resolution and bucket.resolution != resolution:
                continue

            buckets.append({
                "filepath": str(filepath),
                "resolution": bucket.resolution,
                "side": bucket.side.value,
                "topic": bucket.topic,
                "num_cards": len(bucket.cards),
            })
        except Exception:
            continue

    return buckets


def get_or_create_evidence_bucket(
    resolution: str,
    side: Side,
    topic: str,
) -> tuple[EvidenceBucket, bool]:
    """Get existing evidence bucket or create a new empty one."""
    existing = find_evidence_bucket(resolution, side, topic)

    if existing:
        return existing, False

    new_bucket = EvidenceBucket(
        topic=topic,
        resolution=resolution,
        side=side,
        cards=[],
    )

    return new_bucket, True
