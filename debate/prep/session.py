"""PrepSession manages the staging directory and shared state for prep agents."""

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from debate.models import Side


@dataclass
class PrepSession:
    """Manages staging directories and coordination between prep agents.

    Directory structure:
        staging/
            MANIFEST.json         - Maps timestamps to resolutions
            {timestamp}/
                strategy/tasks/       - Research tasks from StrategyAgent
                search/results/       - Search results from SearchAgent
                cutter/cards/         - Cut cards from CutterAgent
                organizer/brief.json  - Current brief state
                organizer/feedback/   - Feedback for StrategyAgent
                _read_log.json        - Tracks what each agent has processed
                _event_log.jsonl      - Unified event stream for UI
    """

    resolution: str
    side: Side
    session_id: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    staging_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        """Initialize staging directories."""
        self.staging_dir = Path("staging") / self.session_id
        self._setup_directories()
        self._read_log: dict[str, dict[str, float]] = {}
        self._load_read_log()
        # Track normalized task arguments for deduplication
        self._task_signatures: set[str] = set()
        # Register this session in the manifest
        self._write_manifest()

    def _setup_directories(self) -> None:
        """Create the staging directory structure."""
        dirs = [
            self.staging_dir / "strategy" / "tasks",
            self.staging_dir / "search" / "results",
            self.staging_dir / "cutter" / "cards",
            self.staging_dir / "organizer" / "feedback",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

        # Initialize empty brief
        brief_path = self.staging_dir / "organizer" / "brief.json"
        if not brief_path.exists():
            initial_brief = {
                "resolution": self.resolution,
                "side": self.side.value,
                "updated_at": time.time(),
                "arguments": {},
                "answers": {},
            }
            brief_path.write_text(json.dumps(initial_brief, indent=2))

    def _load_read_log(self) -> None:
        """Load the read log from disk."""
        log_path = self.staging_dir / "_read_log.json"
        if log_path.exists():
            self._read_log = json.loads(log_path.read_text())
        else:
            self._read_log = {}

    def _save_read_log(self) -> None:
        """Save the read log to disk."""
        log_path = self.staging_dir / "_read_log.json"
        log_path.write_text(json.dumps(self._read_log, indent=2))

    def _read_manifest(self) -> dict[str, dict[str, Any]]:
        """Read the staging manifest.

        Returns:
            Dict mapping timestamp -> {resolution, side, created_at}
        """
        manifest_path = Path("staging") / "MANIFEST.json"
        if not manifest_path.exists():
            return {}
        return json.loads(manifest_path.read_text())

    def _write_manifest(self) -> None:
        """Write this session to the staging manifest."""
        Path("staging").mkdir(exist_ok=True)
        manifest_path = Path("staging") / "MANIFEST.json"

        # Read existing manifest
        manifest = self._read_manifest()

        # Add/update this session
        manifest[self.session_id] = {
            "resolution": self.resolution,
            "side": self.side.value,
            "created_at": time.time(),
        }

        # Write back
        manifest_path.write_text(json.dumps(manifest, indent=2))

    def log_event(self, agent: str, action: str, details: dict[str, Any] | None = None) -> None:
        """Log an event to the unified event stream."""
        event = {
            "ts": time.time(),
            "agent": agent,
            "action": action,
            **(details or {}),
        }
        log_path = self.staging_dir / "_event_log.jsonl"
        with open(log_path, "a") as f:
            f.write(json.dumps(event) + "\n")

    def mark_processed(self, agent: str, file_path: str) -> None:
        """Mark a file as processed by an agent."""
        if agent not in self._read_log:
            self._read_log[agent] = {}
        self._read_log[agent][file_path] = time.time()
        self._save_read_log()

    def is_processed(self, agent: str, file_path: str) -> bool:
        """Check if a file has been processed by an agent."""
        return file_path in self._read_log.get(agent, {})

    def get_unprocessed_files(self, agent: str, directory: Path) -> list[Path]:
        """Get files in a directory that haven't been processed by this agent."""
        if not directory.exists():
            return []

        unprocessed = []
        for f in sorted(directory.glob("*.json")):
            if not self.is_processed(agent, str(f)):
                unprocessed.append(f)
        return unprocessed

    # === Strategy Agent Interface ===

    @staticmethod
    def _normalize_argument(text: str) -> str:
        """Normalize argument text for aggressive deduplication.

        Keeps only key nouns and entities by removing:
        - Common filler words
        - Action verbs (eliminates, destroys, causes, etc.)
        - Adjectives and descriptors
        - Variant markers
        """
        # Lowercase and strip
        text = text.lower().strip()

        # Remove "AT:" prefix for answer arguments
        text = re.sub(r"^at:\s*", "", text)

        # Remove "Impact:" prefix
        text = re.sub(r"^impact:\s*", "", text)

        # Remove variant markers (e.g., "+ term")
        text = re.sub(r"\s*\+\s*[^+]*$", "", text)

        # AGGRESSIVE filtering - keep only key nouns and entities
        # Remove action verbs, adjectives, prepositions, descriptors
        stop_words = {
            # Prepositions and articles
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            # Action verbs - these vary but don't change the core argument
            "eliminates",
            "destroyed",
            "destroys",
            "loses",
            "lost",
            "creates",
            "causes",
            "leads",
            "harms",
            "impacts",
            "affects",
            "threatens",
            "violates",
            "requires",
            "needed",
            "harm",
            "impact",
            "affect",
            "threat",
            "violation",
            "requirement",
            # Adjectives/descriptors
            "economic",
            "economically",
            "new",
            "large",
            "significant",
            # Other variants
            "opportunity",
            "opportunities",
            "employment",
            "employed",
            "due",
            "able",
            "more",
            "most",
        }
        words = text.split()
        words = [w for w in words if w not in stop_words and len(w) > 2]

        # Remove punctuation and normalize whitespace
        text = " ".join(words)
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def is_duplicate_task(self, argument: str) -> bool:
        """Check if a task with similar argument already exists.

        Args:
            argument: The task argument to check

        Returns:
            True if a duplicate or near-duplicate exists
        """
        normalized = self._normalize_argument(argument)

        # Exact match check
        if normalized in self._task_signatures:
            return True

        # Similarity check - check if any existing signature is very similar
        # Two normalized arguments are duplicates if they share >65% of core words
        norm_words = set(normalized.split())
        if not norm_words:
            return False

        for existing_sig in self._task_signatures:
            existing_words = set(existing_sig.split())
            if not existing_words:
                continue

            # Calculate Jaccard similarity on normalized (key words only)
            intersection = len(norm_words & existing_words)
            union = len(norm_words | existing_words)
            similarity = intersection / union if union > 0 else 0

            # Lower threshold to catch semantic duplicates
            # Examples:
            # - "tiktok ban jobs" vs "tiktok ban creator jobs" = 3/5 = 0.60 ✓ duplicate
            # - "tiktok ban" vs "tiktok ban creator jobs" = 2/5 = 0.40 ✗ different arg
            # - "tiktok ban jobs" vs "chinese gov data" = 0/6 = 0.00 ✗ different
            if similarity > 0.55:
                return True

        return False

    def write_task(self, task: dict[str, Any]) -> str:
        """Write a research task. Returns task ID.

        Performs deduplication check before writing.
        """
        argument = task.get("argument", "")

        # Check for duplicates
        if self.is_duplicate_task(argument):
            # Return empty string to signal duplicate
            return ""

        # Track this task signature
        normalized = self._normalize_argument(argument)
        self._task_signatures.add(normalized)

        task_id = task.get("id", str(uuid.uuid4())[:8])
        task["id"] = task_id
        task["ts"] = time.time()

        task_path = self.staging_dir / "strategy" / "tasks" / f"task_{task_id}.json"
        task_path.write_text(json.dumps(task, indent=2))

        self.log_event("strategy", "enqueue", {"task_id": task_id, "argument": argument})
        return task_id

    def get_pending_tasks(self) -> list[dict[str, Any]]:
        """Get all unprocessed tasks for SearchAgent."""
        tasks_dir = self.staging_dir / "strategy" / "tasks"
        unprocessed = self.get_unprocessed_files("search", tasks_dir)

        tasks = []
        for f in unprocessed:
            tasks.append(json.loads(f.read_text()))
        return tasks

    # === Search Agent Interface ===

    def write_search_result(self, result: dict[str, Any]) -> str:
        """Write a search result. Returns result ID."""
        result_id = result.get("id", str(uuid.uuid4())[:8])
        result["id"] = result_id
        result["ts"] = time.time()

        result_path = self.staging_dir / "search" / "results" / f"result_{result_id}.json"
        result_path.write_text(json.dumps(result, indent=2))

        self.log_event(
            "search",
            "staged",
            {
                "result_id": result_id,
                "task_id": result.get("task_id", ""),
                "query": result.get("query", "")[:50],
            },
        )
        return result_id

    def get_pending_results(self) -> list[dict[str, Any]]:
        """Get all unprocessed search results for CutterAgent."""
        results_dir = self.staging_dir / "search" / "results"
        unprocessed = self.get_unprocessed_files("cutter", results_dir)

        results = []
        for f in unprocessed:
            results.append(json.loads(f.read_text()))
        return results

    # === Cutter Agent Interface ===

    def write_card(self, card: dict[str, Any]) -> str:
        """Write a cut card. Returns card ID."""
        card_id = card.get("id", str(uuid.uuid4())[:8])
        card["id"] = card_id
        card["ts"] = time.time()

        card_path = self.staging_dir / "cutter" / "cards" / f"card_{card_id}.json"
        card_path.write_text(json.dumps(card, indent=2))

        self.log_event(
            "cutter",
            "cut",
            {
                "card_id": card_id,
                "tag": card.get("tag", "")[:40],
            },
        )
        return card_id

    def get_pending_cards(self) -> list[dict[str, Any]]:
        """Get all unprocessed cards for OrganizerAgent."""
        cards_dir = self.staging_dir / "cutter" / "cards"
        unprocessed = self.get_unprocessed_files("organizer", cards_dir)

        cards = []
        for f in unprocessed:
            cards.append(json.loads(f.read_text()))
        return cards

    # === Organizer Agent Interface ===

    def read_brief(self) -> dict[str, Any]:
        """Read the current brief state."""
        brief_path = self.staging_dir / "organizer" / "brief.json"
        return json.loads(brief_path.read_text())

    def write_brief(self, brief: dict[str, Any]) -> None:
        """Update the brief state."""
        brief["updated_at"] = time.time()
        brief_path = self.staging_dir / "organizer" / "brief.json"
        brief_path.write_text(json.dumps(brief, indent=2))

        self.log_event(
            "organizer",
            "updated_brief",
            {
                "num_arguments": len(brief.get("arguments", {})),
            },
        )

    def write_feedback(self, feedback: dict[str, Any]) -> str:
        """Write feedback for StrategyAgent. Returns feedback ID."""
        feedback_id = feedback.get("id", str(uuid.uuid4())[:8])
        feedback["id"] = feedback_id
        feedback["ts"] = time.time()

        feedback_path = self.staging_dir / "organizer" / "feedback" / f"feedback_{feedback_id}.json"
        feedback_path.write_text(json.dumps(feedback, indent=2))

        self.log_event(
            "organizer",
            "feedback",
            {
                "feedback_id": feedback_id,
                "type": feedback.get("type", ""),
                "message": feedback.get("message", "")[:50],
            },
        )
        return feedback_id

    def get_pending_feedback(self) -> list[dict[str, Any]]:
        """Get all unprocessed feedback for StrategyAgent."""
        feedback_dir = self.staging_dir / "organizer" / "feedback"
        unprocessed = self.get_unprocessed_files("strategy", feedback_dir)

        feedback = []
        for f in unprocessed:
            feedback.append(json.loads(f.read_text()))
        return feedback

    # === Stats ===

    def get_stats(self) -> dict[str, int]:
        """Get current session statistics."""
        tasks_dir = self.staging_dir / "strategy" / "tasks"
        results_dir = self.staging_dir / "search" / "results"
        cards_dir = self.staging_dir / "cutter" / "cards"
        feedback_dir = self.staging_dir / "organizer" / "feedback"

        return {
            "tasks": len(list(tasks_dir.glob("*.json"))) if tasks_dir.exists() else 0,
            "results": len(list(results_dir.glob("*.json"))) if results_dir.exists() else 0,
            "cards": len(list(cards_dir.glob("*.json"))) if cards_dir.exists() else 0,
            "feedback": len(list(feedback_dir.glob("*.json"))) if feedback_dir.exists() else 0,
        }

    def get_task_stats(self) -> dict[str, int]:
        """Get search task statistics from event log.

        Returns:
            Dict with: total, completed, failed counts
        """
        events = self.get_event_log(limit=1000)

        enqueued_tasks = set()
        completed_tasks = set()
        failed_tasks = set()

        for event in events:
            if event.get("action") == "enqueue" and event.get("agent") == "strategy":
                enqueued_tasks.add(event.get("task_id", ""))
            elif event.get("action") == "staged_result" and event.get("agent") == "search":
                completed_tasks.add(event.get("task_id", ""))
            elif event.get("action") in ("query_failed", "search_failed") and event.get("agent") == "search":
                failed_tasks.add(event.get("task_id", ""))

        total = len(enqueued_tasks)
        completed = len(completed_tasks)
        failed = len(failed_tasks)
        pending = total - completed - failed

        return {
            "total": total,
            "pending": pending,
            "completed": completed,
            "failed": failed,
        }

    def get_event_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent events from the event log."""
        log_path = self.staging_dir / "_event_log.jsonl"
        if not log_path.exists():
            return []

        events = []
        with open(log_path) as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))

        return events[-limit:]

    @classmethod
    def load_from_session_id(cls, session_id: str) -> "PrepSession":
        """Load an existing session from its session ID.

        Args:
            session_id: The session ID to load

        Returns:
            PrepSession instance loaded from disk

        Raises:
            ValueError: If session not found or brief.json is invalid
        """
        staging_dir = Path("staging") / session_id
        if not staging_dir.exists():
            raise ValueError(f"Session {session_id} not found at {staging_dir}")

        brief_path = staging_dir / "organizer" / "brief.json"
        if not brief_path.exists():
            raise ValueError(f"Session {session_id} is missing brief.json")

        brief = json.loads(brief_path.read_text())
        resolution = brief.get("resolution")
        side_str = brief.get("side")

        if not resolution or not side_str:
            raise ValueError(f"Session {session_id} has invalid brief.json (missing resolution or side)")

        side = Side.PRO if side_str.lower() == "pro" else Side.CON

        # Create session with loaded metadata
        session = cls(resolution=resolution, side=side)
        session.session_id = session_id
        session.staging_dir = staging_dir
        session._load_read_log()

        return session

    @classmethod
    def get_most_recent_session(cls) -> str | None:
        """Get the most recently created session ID from manifest.

        Returns:
            Session ID (timestamp) string, or None if no sessions found
        """
        manifest_path = Path("staging") / "MANIFEST.json"

        # Try manifest first (fast lookup)
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            if not manifest:
                return None

            # Sort by created_at timestamp (most recent first)
            sessions = [(ts, info["created_at"]) for ts, info in manifest.items()]
            sessions.sort(key=lambda x: x[1], reverse=True)
            return sessions[0][0]

        # Fallback to directory scanning
        staging_root = Path("staging")
        if not staging_root.exists():
            return None

        session_dirs = []
        for item in staging_root.iterdir():
            if item.is_dir() and item.name != "MANIFEST.json":
                # Validate it's a real session by checking for brief.json
                brief_path = item / "organizer" / "brief.json"
                if brief_path.exists():
                    session_dirs.append((item.name, item.stat().st_mtime))

        if not session_dirs:
            return None

        # Sort by modification time (most recent first)
        session_dirs.sort(key=lambda x: x[1], reverse=True)
        return session_dirs[0][0]
