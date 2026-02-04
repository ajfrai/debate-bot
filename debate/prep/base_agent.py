"""Base class for specialized prep agents."""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from debate.prep.session import PrepSession


@dataclass
class AgentState:
    """Tracks agent activity for UI display."""

    name: str
    status: str = "idle"  # idle, working, waiting
    last_action: str = ""
    last_action_time: float = 0.0
    items_processed: int = 0
    items_created: int = 0
    recent_actions: list[str] = field(default_factory=list)
    current_direction: str = ""  # Current research direction being pursued
    current_query: str = ""  # Current search query
    current_source: str = ""  # Current source URL being fetched
    current_snippet: str = ""  # Current content snippet
    current_task_id: str = ""  # Current task being processed
    current_task_progress: str = ""  # Current stage (e.g., "query", "searching", "fetch 1/2")
    current_argument: str = ""  # Current argument being researched
    # Kanban board: task_id -> stage mapping
    task_stages: dict[str, str] = field(default_factory=dict)  # stage: queued, query, search, fetch, done, error
    # Error tracking
    task_errors: dict[str, str] = field(default_factory=dict)  # task_id -> error reason
    task_retries: dict[str, int] = field(default_factory=dict)  # task_id -> retry count
    task_urls_tried: dict[str, list[str]] = field(default_factory=dict)  # task_id -> URLs already attempted

    def update(self, action: str, status: str = "working") -> None:
        """Update agent state with a new action."""
        self.status = status
        self.last_action = action
        self.last_action_time = time.time()
        self.recent_actions.append(action)
        # Keep only last 5 actions
        if len(self.recent_actions) > 5:
            self.recent_actions = self.recent_actions[-5:]


class BaseAgent(ABC):
    """Base class for all prep agents.

    Provides:
    - Async run loop with deadline
    - Session access for reading/writing staged files
    - State tracking for UI display
    - Abstract methods for agent-specific logic
    """

    def __init__(self, session: PrepSession, poll_interval: float = 2.0) -> None:
        """Initialize the agent.

        Args:
            session: The shared prep session
            poll_interval: Seconds between polling for new work
        """
        self.session = session
        self.poll_interval = poll_interval
        self.state = AgentState(name=self.name)
        self._running = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name for logging and UI."""
        pass

    @abstractmethod
    async def check_for_work(self) -> list[Any]:
        """Check for new work items. Returns list of items to process."""
        pass

    @abstractmethod
    async def process_item(self, item: Any) -> None:
        """Process a single work item."""
        pass

    async def on_start(self) -> None:  # noqa: B027
        """Called when agent starts. Override for initialization."""
        pass

    async def on_stop(self) -> None:  # noqa: B027
        """Called when agent stops. Override for cleanup."""
        pass

    async def check_dependencies(self) -> tuple[bool, str]:
        """Check if this agent's dependencies are met.

        Returns:
            (satisfied, message) - True if dependencies met, False otherwise
        """
        return (True, "")  # Default: no dependencies

    def log(self, action: str, details: dict[str, Any] | None = None) -> None:
        """Log an action to the session event log."""
        self.session.log_event(self.name, action, details)
        self.state.update(action)

    async def run(self, deadline: float) -> None:
        """Run the agent until the deadline.

        Args:
            deadline: Unix timestamp when to stop
        """
        self._running = True
        self.state.status = "starting"

        try:
            await self.on_start()

            while time.time() < deadline and self._running:
                self.state.status = "checking"

                # Check for work
                work_items = await self.check_for_work()

                if work_items:
                    self.state.status = "working"
                    for item in work_items:
                        if time.time() >= deadline:
                            break
                        await self.process_item(item)
                        self.state.items_processed += 1
                else:
                    self.state.status = "waiting"

                # Poll interval
                if time.time() < deadline:
                    await asyncio.sleep(self.poll_interval)

        finally:
            self._running = False
            self.state.status = "stopped"
            await self.on_stop()

    def stop(self) -> None:
        """Request the agent to stop."""
        self._running = False
