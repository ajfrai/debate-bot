"""PrepSession manages the staging directory and shared state for prep agents."""

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from debate.models import Side


@dataclass
class PrepSession:
    """Manages staging directories and coordination between prep agents.

    Directory structure:
        staging/{session_id}/
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
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    staging_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        """Initialize staging directories."""
        self.staging_dir = Path("staging") / self.session_id
        self._setup_directories()
        self._read_log: dict[str, dict[str, float]] = {}
        self._load_read_log()

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

    def write_task(self, task: dict[str, Any]) -> str:
        """Write a research task. Returns task ID."""
        task_id = task.get("id", str(uuid.uuid4())[:8])
        task["id"] = task_id
        task["ts"] = time.time()

        task_path = self.staging_dir / "strategy" / "tasks" / f"task_{task_id}.json"
        task_path.write_text(json.dumps(task, indent=2))

        self.log_event("strategy", "enqueue", {"task_id": task_id, "argument": task.get("argument", "")})
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
