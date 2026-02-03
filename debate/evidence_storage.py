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
from pathlib import Path

from debate.models import (
    ArgumentFile,
    Card,
    ClaimCards,
    DebateFile,
    EvidenceBucket,
    EvidenceType,
    FlatDebateFile,
    SectionType,
    Side,
)


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
        lines.extend(
            [
                f"**Purpose:** {card.purpose}",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "",
            f"**{card.author}**, {card.credentials}",
            f"*{card.source}*, {card.year}",
        ]
    )

    if card.url:
        lines.append(f"[Source]({card.url})")

    lines.extend(
        [
            "",
            "---",
            "",
            card.text,
            "",
            "---",
            f"*Card ID: {card.id}*",
        ]
    )

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
        f'grep -r "keyword" {resolution_dir}/pro/   # Search PRO evidence',
        f'grep -r "keyword" {resolution_dir}/con/   # Search CON evidence',
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


def load_debate_file(resolution: str) -> DebateFile | None:
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

    with open(meta_path) as f:
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
    """List all debate files (both old and new flat format).

    Returns:
        List of dicts with resolution info
    """
    evidence_dir = get_evidence_dir()
    files = []

    for dir_path in evidence_dir.iterdir():
        if not dir_path.is_dir():
            continue

        # Check for old format (.debate_meta.json)
        old_meta_path = dir_path / ".debate_meta.json"
        flat_meta_path = dir_path / ".flat_meta.json"

        if old_meta_path.exists():
            # Old format
            try:
                debate_file = load_debate_file(dir_path.name)
                if debate_file:
                    files.append(
                        {
                            "resolution": debate_file.resolution,
                            "dir_path": str(dir_path),
                            "num_cards": len(debate_file.cards),
                            "num_pro_sections": len(debate_file.pro_sections),
                            "num_con_sections": len(debate_file.con_sections),
                            "format": "old",
                        }
                    )
            except Exception:
                continue
        elif flat_meta_path.exists():
            # New flat format
            try:
                flat_file = load_flat_debate_file(dir_path.name)
                if flat_file:
                    # Count total cards across all arguments
                    total_cards = 0
                    for arg in flat_file.pro_arguments + flat_file.con_arguments:
                        for claim in arg.claims:
                            total_cards += len(claim.cards)

                    files.append(
                        {
                            "resolution": flat_file.resolution,
                            "dir_path": str(dir_path),
                            "num_cards": total_cards,
                            "num_pro_sections": len(flat_file.pro_arguments),
                            "num_con_sections": len(flat_file.con_arguments),
                            "format": "flat",
                        }
                    )
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
    with open(filepath) as f:
        data = json.load(f)
    return EvidenceBucket.model_validate(data)


def find_evidence_bucket(
    resolution: str,
    side: Side,
    topic: str,
) -> EvidenceBucket | None:
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


def list_evidence_buckets(resolution: str | None = None) -> list[dict]:
    """List all evidence buckets, optionally filtered by resolution."""
    evidence_dir = get_evidence_dir()
    buckets = []

    for filepath in evidence_dir.glob("*.json"):
        try:
            bucket = load_evidence_bucket(str(filepath))

            if resolution and bucket.resolution != resolution:
                continue

            buckets.append(
                {
                    "filepath": str(filepath),
                    "resolution": bucket.resolution,
                    "side": bucket.side.value,
                    "topic": bucket.topic,
                    "num_cards": len(bucket.cards),
                }
            )
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


# ========== Flat Evidence Structure ==========


def render_argument_file_markdown(argument: ArgumentFile) -> str:
    """Render an argument file as markdown.

    Format:
        # Argument Title
        Strategic purpose...

        ## Claim 1
        ### 1. Author 2024 - Source
        **Purpose:** ...
        [card content]

        ### 2. Author 2025 - Source
        ...
    """
    lines = []

    # Header
    if argument.is_answer and argument.answers_to:
        lines.append(f"# AT: {argument.answers_to}")
    else:
        lines.append(f"# {argument.title}")
    lines.append("")
    lines.append(argument.purpose)
    lines.append("")

    # Claims with numbered cards
    for claim_cards in argument.claims:
        lines.append(f"## {claim_cards.claim}")
        lines.append("")

        for i, card in enumerate(claim_cards.cards, 1):
            last_name = card.author.split()[-1]
            lines.append(f"### {i}. {last_name} {card.year} - {card.source}")
            lines.append("")

            if card.purpose:
                lines.append(f"**Purpose:** {card.purpose}")
                lines.append("")

            if card.evidence_type:
                lines.append(f"**Type:** {card.evidence_type.value}")
                lines.append("")

            lines.append(f"**{card.author}**, {card.credentials}")
            lines.append(f"*{card.source}*, {card.year}")
            if card.url:
                lines.append(f"[Source]({card.url})")
            lines.append("")
            lines.append("---")
            lines.append("")
            lines.append(card.text)
            lines.append("")
            lines.append("---")
            lines.append(f"*Card ID: {card.id}*")
            lines.append("")

    return "\n".join(lines)


def save_flat_debate_file(debate_file: FlatDebateFile) -> str:
    """Save a flat debate file structure.

    Creates:
        evidence/{resolution}/
            pro/
                {argument}.md
                at_{argument}.md
            con/
                {argument}.md
                at_{argument}.md
            .flat_meta.json
    """
    resolution_dir = get_resolution_dir(debate_file.resolution)

    # Create side directories (flat - no subdirs)
    for side in ["pro", "con"]:
        side_dir = resolution_dir / side
        side_dir.mkdir(exist_ok=True)

    # Save pro arguments
    for arg in debate_file.pro_arguments:
        filepath = resolution_dir / "pro" / arg.get_filename()
        with open(filepath, "w") as f:
            f.write(render_argument_file_markdown(arg))

    # Save con arguments
    for arg in debate_file.con_arguments:
        filepath = resolution_dir / "con" / arg.get_filename()
        with open(filepath, "w") as f:
            f.write(render_argument_file_markdown(arg))

    # Save metadata for programmatic loading
    meta_path = resolution_dir / ".flat_meta.json"
    meta = {
        "resolution": debate_file.resolution,
        "pro_arguments": [_serialize_argument_file(arg) for arg in debate_file.pro_arguments],
        "con_arguments": [_serialize_argument_file(arg) for arg in debate_file.con_arguments],
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    # Generate flat INDEX.md
    index_content = generate_flat_index_markdown(debate_file, resolution_dir)
    index_path = resolution_dir / "INDEX.md"
    with open(index_path, "w") as f:
        f.write(index_content)

    return str(resolution_dir)


def _serialize_argument_file(arg: ArgumentFile) -> dict:
    """Serialize ArgumentFile for JSON storage."""
    return {
        "title": arg.title,
        "is_answer": arg.is_answer,
        "answers_to": arg.answers_to,
        "purpose": arg.purpose,
        "claims": [
            {
                "claim": claim.claim,
                "cards": [card.model_dump() for card in claim.cards],
            }
            for claim in arg.claims
        ],
    }


def _deserialize_argument_file(data: dict) -> ArgumentFile:
    """Deserialize ArgumentFile from JSON."""
    claims = []
    for claim_data in data.get("claims", []):
        cards = []
        for card_data in claim_data.get("cards", []):
            # Handle evidence_type enum
            if card_data.get("evidence_type"):
                card_data["evidence_type"] = EvidenceType(card_data["evidence_type"])
            cards.append(Card(**card_data))
        claims.append(ClaimCards(claim=claim_data["claim"], cards=cards))

    return ArgumentFile(
        title=data["title"],
        is_answer=data.get("is_answer", False),
        answers_to=data.get("answers_to"),
        purpose=data.get("purpose", ""),
        claims=claims,
    )


def generate_flat_index_markdown(debate_file: FlatDebateFile, resolution_dir: Path) -> str:
    """Generate INDEX.md for flat structure."""
    lines = [
        f"# {debate_file.resolution}",
        "",
        "## Quick Navigation",
        "",
        "```bash",
        f"ls {resolution_dir}/pro/      # List PRO arguments",
        f"ls {resolution_dir}/con/      # List CON arguments",
        f'grep -r "keyword" {resolution_dir}/pro/   # Search PRO evidence',
        "```",
        "",
    ]

    def render_side(arguments: list[ArgumentFile], side_name: str, side_label: str):
        if not arguments:
            return

        lines.append(f"## {side_label}")
        lines.append(f"*`{side_name}/`*")
        lines.append("")

        # Separate arguments and AT files
        main_args = [a for a in arguments if not a.is_answer]
        at_args = [a for a in arguments if a.is_answer]

        if main_args:
            lines.append("### Arguments")
            lines.append("")
            for arg in main_args:
                filename = arg.get_filename()
                card_count = sum(len(c.cards) for c in arg.claims)
                lines.append(f"- [{arg.title}]({side_name}/{filename}) ({card_count} cards)")
                for claim in arg.claims:
                    lines.append(f"  - {claim.claim} ({len(claim.cards)} cards)")
            lines.append("")

        if at_args:
            lines.append("### Answers (AT)")
            lines.append("")
            for arg in at_args:
                filename = arg.get_filename()
                card_count = sum(len(c.cards) for c in arg.claims)
                lines.append(f"- [AT: {arg.answers_to}]({side_name}/{filename}) ({card_count} cards)")
            lines.append("")

    render_side(debate_file.pro_arguments, "pro", "PRO")
    render_side(debate_file.con_arguments, "con", "CON")

    return "\n".join(lines)


def load_flat_debate_file(resolution: str) -> FlatDebateFile | None:
    """Load a flat debate file from its directory."""
    resolution_dir = get_resolution_dir(resolution)
    meta_path = resolution_dir / ".flat_meta.json"

    if not meta_path.exists():
        return None

    with open(meta_path) as f:
        meta = json.load(f)

    return FlatDebateFile(
        resolution=meta["resolution"],
        pro_arguments=[_deserialize_argument_file(a) for a in meta.get("pro_arguments", [])],
        con_arguments=[_deserialize_argument_file(a) for a in meta.get("con_arguments", [])],
    )


def get_or_create_flat_debate_file(resolution: str) -> tuple[FlatDebateFile, bool]:
    """Get existing flat debate file or create a new empty one."""
    existing = load_flat_debate_file(resolution)

    if existing:
        return existing, False

    new_file = FlatDebateFile(resolution=resolution)
    return new_file, True


def convert_to_flat_structure(old_file: DebateFile) -> FlatDebateFile:
    """Convert old DebateFile to new FlatDebateFile structure.

    Groups cards by argument, then by claim within each argument.
    """
    flat = FlatDebateFile(resolution=old_file.resolution)

    def convert_sections(sections: list, side: Side):
        # Group sections by argument
        arg_map: dict[str, ArgumentFile] = {}

        for section in sections:
            arg_key = section.argument.lower()
            is_answer = section.section_type == SectionType.ANSWER

            if arg_key not in arg_map:
                arg_map[arg_key] = ArgumentFile(
                    title=section.argument,
                    is_answer=is_answer,
                    answers_to=section.argument if is_answer else None,
                    purpose=section.notes or f"Evidence for: {section.argument}",
                )

            arg_file = arg_map[arg_key]

            # Add cards to claims
            for card_id in section.card_ids:
                card = old_file.get_card(card_id)
                if card:
                    # Use card tag as claim
                    claim = arg_file.find_or_create_claim(card.tag)
                    claim.add_card(card)

        for arg_file in arg_map.values():
            flat.add_argument(side, arg_file)

    convert_sections(old_file.pro_sections, Side.PRO)
    convert_sections(old_file.con_sections, Side.CON)

    return flat
