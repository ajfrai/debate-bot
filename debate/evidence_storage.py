"""Storage system for evidence buckets.

Manages saving and loading evidence buckets as JSON files,
organized by resolution and topic.
"""

import json
import os
from pathlib import Path
from typing import Optional

from debate.models import EvidenceBucket, Side


def get_evidence_dir() -> Path:
    """Get the evidence storage directory, creating it if needed."""
    # Store evidence in a local evidence/ directory
    evidence_dir = Path("evidence")
    evidence_dir.mkdir(exist_ok=True)
    return evidence_dir


def sanitize_filename(text: str) -> str:
    """Convert text to a safe filename."""
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


def save_evidence_bucket(bucket: EvidenceBucket) -> str:
    """Save an evidence bucket to a JSON file.

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
