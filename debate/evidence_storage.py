"""Storage system for debate files and evidence.

Manages saving and loading debate files as directories,
organized by resolution with markdown index files.

Directory structure:
    evidence/
        {resolution_slug}/
            debate_file.json    # The main DebateFile data
            INDEX.md            # Rendered markdown table of contents
"""

import json
import os
from pathlib import Path
from typing import Optional

from debate.models import DebateFile, EvidenceBucket, Side


def get_evidence_dir() -> Path:
    """Get the evidence storage directory, creating it if needed."""
    # Store evidence in a local evidence/ directory
    evidence_dir = Path("evidence")
    evidence_dir.mkdir(exist_ok=True)
    return evidence_dir


def sanitize_filename(text: str) -> str:
    """Convert text to a safe filename/directory name."""
    # Remove/replace problematic characters
    safe = text.lower()
    safe = safe.replace(" ", "_")
    safe = safe.replace(":", "")
    safe = safe.replace("/", "_")
    safe = safe.replace("\\", "_")
    # Keep only alphanumeric, underscore, hyphen
    safe = "".join(c for c in safe if c.isalnum() or c in "_-")
    # Truncate to reasonable length
    return safe[:100]


def get_resolution_dir(resolution: str) -> Path:
    """Get the directory for a resolution, creating it if needed."""
    evidence_dir = get_evidence_dir()
    resolution_slug = sanitize_filename(resolution)
    resolution_dir = evidence_dir / resolution_slug
    resolution_dir.mkdir(exist_ok=True)
    return resolution_dir


def save_debate_file(debate_file: DebateFile) -> str:
    """Save a debate file to its resolution directory.

    Args:
        debate_file: The debate file to save

    Returns:
        Path to the resolution directory

    Creates/updates:
        evidence/{resolution}/debate_file.json
        evidence/{resolution}/INDEX.md
    """
    resolution_dir = get_resolution_dir(debate_file.resolution)

    # Save JSON data
    json_path = resolution_dir / "debate_file.json"
    with open(json_path, "w") as f:
        json.dump(debate_file.model_dump(), f, indent=2)

    # Save markdown index
    index_path = resolution_dir / "INDEX.md"
    with open(index_path, "w") as f:
        f.write(debate_file.render_full_file())

    return str(resolution_dir)


def load_debate_file(resolution: str) -> Optional[DebateFile]:
    """Load a debate file for a resolution.

    Args:
        resolution: The debate resolution

    Returns:
        DebateFile if found, None otherwise
    """
    resolution_dir = get_resolution_dir(resolution)
    json_path = resolution_dir / "debate_file.json"

    if not json_path.exists():
        return None

    with open(json_path, "r") as f:
        data = json.load(f)

    return DebateFile.model_validate(data)


def get_or_create_debate_file(resolution: str) -> tuple[DebateFile, bool]:
    """Get existing debate file or create a new empty one.

    Args:
        resolution: The debate resolution

    Returns:
        Tuple of (DebateFile, is_new)
        is_new is True if a new file was created, False if loaded from disk
    """
    existing = load_debate_file(resolution)

    if existing:
        return existing, False

    # Create new empty debate file
    new_file = DebateFile(resolution=resolution)
    return new_file, True


def list_debate_files() -> list[dict]:
    """List all debate files.

    Returns:
        List of dicts with 'resolution', 'dir_path', 'num_cards', 'num_sections'
    """
    evidence_dir = get_evidence_dir()
    files = []

    for dir_path in evidence_dir.iterdir():
        if not dir_path.is_dir():
            continue

        json_path = dir_path / "debate_file.json"
        if not json_path.exists():
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
    """Save an evidence bucket to a JSON file (legacy format).

    Args:
        bucket: The evidence bucket to save

    Returns:
        Path to the saved file

    File naming: evidence/{resolution}_{side}_{topic}.json
    Example: evidence/us_should_ban_tiktok_pro_economic_impacts.json
    """
    evidence_dir = get_evidence_dir()

    # Create filename
    resolution_slug = sanitize_filename(bucket.resolution)
    side_slug = bucket.side.value
    topic_slug = sanitize_filename(bucket.topic)
    filename = f"{resolution_slug}_{side_slug}_{topic_slug}.json"

    filepath = evidence_dir / filename

    # Save as JSON
    with open(filepath, "w") as f:
        json.dump(bucket.model_dump(), f, indent=2)

    return str(filepath)


def load_evidence_bucket(filepath: str) -> EvidenceBucket:
    """Load an evidence bucket from a JSON file.

    Args:
        filepath: Path to the JSON file

    Returns:
        EvidenceBucket loaded from file
    """
    with open(filepath, "r") as f:
        data = json.load(f)

    return EvidenceBucket.model_validate(data)


def find_evidence_bucket(
    resolution: str,
    side: Side,
    topic: str,
) -> Optional[EvidenceBucket]:
    """Find and load an evidence bucket if it exists.

    Args:
        resolution: The debate resolution
        side: Which side the evidence supports
        topic: The topic/argument

    Returns:
        EvidenceBucket if found, None otherwise
    """
    evidence_dir = get_evidence_dir()

    # Construct expected filename
    resolution_slug = sanitize_filename(resolution)
    side_slug = side.value
    topic_slug = sanitize_filename(topic)
    filename = f"{resolution_slug}_{side_slug}_{topic_slug}.json"

    filepath = evidence_dir / filename

    if filepath.exists():
        return load_evidence_bucket(str(filepath))

    return None


def list_evidence_buckets(resolution: Optional[str] = None) -> list[dict]:
    """List all evidence buckets, optionally filtered by resolution.

    Args:
        resolution: Optional resolution to filter by

    Returns:
        List of dicts with 'filepath', 'resolution', 'side', 'topic', 'num_cards'
    """
    evidence_dir = get_evidence_dir()
    buckets = []

    for filepath in evidence_dir.glob("*.json"):
        try:
            bucket = load_evidence_bucket(str(filepath))

            # Filter by resolution if specified
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
            # Skip invalid files
            continue

    return buckets


def get_or_create_evidence_bucket(
    resolution: str,
    side: Side,
    topic: str,
) -> tuple[EvidenceBucket, bool]:
    """Get existing evidence bucket or create a new empty one.

    Args:
        resolution: The debate resolution
        side: Which side the evidence supports
        topic: The topic/argument

    Returns:
        Tuple of (EvidenceBucket, is_new)
        is_new is True if a new bucket was created, False if loaded from disk
    """
    existing = find_evidence_bucket(resolution, side, topic)

    if existing:
        return existing, False

    # Create new empty bucket
    new_bucket = EvidenceBucket(
        topic=topic,
        resolution=resolution,
        side=side,
        cards=[],
    )

    return new_bucket, True
