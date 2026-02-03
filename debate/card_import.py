"""Card import tool for processing marked-up temp files into evidence cards.

This module implements the token-efficient card workflow:
1. Raw sources are saved with Bash cat > temp/raw_source_XXX.txt
2. Edit tool marks up the text with metadata and bolding
3. This script imports the marked-up file into the evidence directory
"""

import re
from pathlib import Path
from typing import Any

from debate.evidence_storage import get_resolution_dir
from debate.models import SectionType, Side


def parse_metadata(content: str) -> dict[str, Any]:
    """Parse metadata from marked-up file.

    Expected format:
    TAG: Card tag line
    CITE: Short citation
    AUTHOR: Full author name
    YEAR: Publication year
    SECTION: support/answer/extension/impact (can be comma-separated for multiple)
    ARGUMENT: Specific argument this addresses
    URL: Source URL
    """
    metadata: dict[str, Any] = {}

    # Extract single-line metadata
    patterns = {
        "tag": r"TAG:\s*(.+?)(?:\n|$)",
        "cite": r"CITE:\s*(.+?)(?:\n|$)",
        "author": r"AUTHOR:\s*(.+?)(?:\n|$)",
        "year": r"YEAR:\s*(\d{4})",
        "url": r"URL:\s*(.+?)(?:\n|$)",
        "argument": r"ARGUMENT:\s*(.+?)(?:\n|$)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            metadata[key] = match.group(1).strip()

    # Extract SECTION (can be comma-separated)
    section_match = re.search(r"SECTION:\s*(.+?)(?:\n|$)", content, re.MULTILINE)
    if section_match:
        sections_str = section_match.group(1).strip()
        # Split by comma and clean up
        metadata["sections"] = [s.strip() for s in sections_str.split(",")]
    else:
        metadata["sections"] = []

    return metadata


def extract_card_text(content: str) -> str | None:
    """Extract text between >>> START and <<< END markers.

    Returns None if markers not found.
    """
    start_match = re.search(r">>> START\s*\n", content)
    end_match = re.search(r"\n<<< END", content)

    if not start_match or not end_match:
        return None

    start_idx = start_match.end()
    end_idx = end_match.start()

    return content[start_idx:end_idx].strip()


def generate_card_markdown(metadata: dict[str, Any], card_text: str) -> str:
    """Generate proper card markdown format.

    Returns the formatted card content for a .md file.
    """
    lines = []

    # Tag as header
    lines.append(f"# {metadata.get('tag', 'Untitled Card')}")
    lines.append("")

    # Metadata
    lines.append("**Citation:**")
    lines.append(f"{metadata.get('cite', 'Unknown')}")
    lines.append("")

    lines.append("**Author:** " + metadata.get("author", "Unknown"))
    lines.append("")

    lines.append("**Year:** " + metadata.get("year", "Unknown"))
    lines.append("")

    if "url" in metadata:
        lines.append(f"**Source:** {metadata['url']}")
        lines.append("")

    # Card text
    lines.append("**Text:**")
    lines.append("")
    lines.append(card_text)
    lines.append("")

    return "\n".join(lines)


def generate_filename(tag: str) -> str:
    """Generate a filename from the card tag.

    Converts to lowercase, replaces spaces with underscores, removes special chars.
    """
    # Convert to lowercase
    filename = tag.lower()

    # Replace spaces with underscores
    filename = filename.replace(" ", "_")

    # Remove special characters (keep only alphanumeric and underscores)
    filename = re.sub(r"[^a-z0-9_]", "", filename)

    # Truncate if too long
    if len(filename) > 60:
        filename = filename[:60]

    return f"{filename}.md"


def import_card(
    temp_file_path: str,
    resolution: str,
    side: Side,
    copy_to: list[str] | None = None,
) -> list[str]:
    """Import a marked-up temp file as an evidence card.

    Args:
        temp_file_path: Path to marked-up temp file
        resolution: Debate resolution
        side: Which side (PRO/CON)
        copy_to: Optional list of additional sections to copy card to

    Returns:
        List of file paths where card was placed

    Raises:
        ValueError: If metadata is missing or invalid
        FileNotFoundError: If temp file doesn't exist
    """
    # Read temp file
    temp_path = Path(temp_file_path)
    if not temp_path.exists():
        raise FileNotFoundError(f"Temp file not found: {temp_file_path}")

    content = temp_path.read_text()

    # Parse metadata
    metadata = parse_metadata(content)

    # Validate required fields
    required = ["tag", "cite", "author", "year", "argument"]
    missing = [field for field in required if field not in metadata]
    if missing:
        raise ValueError(f"Missing required metadata fields: {', '.join(missing)}")

    # Extract card text
    card_text = extract_card_text(content)
    if not card_text:
        raise ValueError("Card text not found. Use >>> START and <<< END markers.")

    # Generate card markdown
    card_md = generate_card_markdown(metadata, card_text)

    # Determine sections to place card
    sections = metadata.get("sections", [])
    if copy_to:
        sections.extend(copy_to)

    if not sections:
        raise ValueError("No SECTION specified. Use SECTION: support/answer/extension/impact")

    # Validate sections
    valid_sections = {st.value for st in SectionType}
    invalid = [s for s in sections if s not in valid_sections]
    if invalid:
        raise ValueError(f"Invalid sections: {', '.join(invalid)}. Must be: {', '.join(valid_sections)}")

    # Get debate file directory
    debate_dir = get_resolution_dir(resolution)

    # Generate filename from tag
    filename = generate_filename(metadata["tag"])

    # Place card in each section
    placed_paths = []
    for section in sections:
        # Construct path: evidence/resolved_.../pro/support/card.md
        section_dir = debate_dir / side.value / section
        section_dir.mkdir(parents=True, exist_ok=True)

        card_path = section_dir / filename
        card_path.write_text(card_md)
        placed_paths.append(str(card_path))

    return placed_paths


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Usage: python -m debate.card_import <temp_file> <resolution> <side> [--copy-to section1,section2]")
        sys.exit(1)

    temp_file = sys.argv[1]
    resolution = sys.argv[2]
    side_str = sys.argv[3]
    side = Side.PRO if side_str.lower() == "pro" else Side.CON

    copy_to = None
    if "--copy-to" in sys.argv:
        idx = sys.argv.index("--copy-to")
        if idx + 1 < len(sys.argv):
            copy_to = [s.strip() for s in sys.argv[idx + 1].split(",")]

    try:
        paths = import_card(temp_file, resolution, side, copy_to)
        print("\n✓ Card imported successfully:")
        for path in paths:
            print(f"  - {path}")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
