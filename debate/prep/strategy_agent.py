"""StrategyAgent: Maintains argument queue and decides what to research."""

import os
from typing import Any

import anthropic

from debate.config import Config
from debate.prep.base_agent import BaseAgent
from debate.prep.session import PrepSession


class StrategyAgent(BaseAgent):
    """Plans research strategy and creates targeted research tasks.

    Responsibilities:
    - Start cold with just the resolution
    - Enumerate initial arguments for the side
    - Create targeted research tasks (not exploratory)
    - Read organizer feedback to identify gaps
    - Follow research trails when sources reveal new arguments
    - Opportunistically add link chain tasks for impact scenarios
    """

    def __init__(self, session: PrepSession) -> None:
        super().__init__(session, poll_interval=3.0)
        self._initialized = False
        self._client: anthropic.Anthropic | None = None

    @property
    def name(self) -> str:
        return "strategy"

    def _get_client(self) -> anthropic.Anthropic:
        """Get or create Anthropic client."""
        if self._client is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not set")
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    async def on_start(self) -> None:
        """Initialize with argument enumeration."""
        if not self._initialized:
            self.log("initializing", {"resolution": self.session.resolution})
            await self._enumerate_initial_arguments()
            self._initialized = True

    async def check_for_work(self) -> list[Any]:
        """Check for feedback from organizer."""
        feedback = self.session.get_pending_feedback()
        return feedback

    async def process_item(self, feedback: dict[str, Any]) -> None:
        """Process feedback and potentially create new tasks."""
        feedback_path = str(self.session.staging_dir / "organizer" / "feedback" / f"feedback_{feedback['id']}.json")
        self.session.mark_processed("strategy", feedback_path)

        self.log(
            "processing_feedback",
            {
                "feedback_id": feedback["id"],
                "type": feedback.get("type", ""),
            },
        )

        # Generate new tasks based on feedback
        await self._respond_to_feedback(feedback)
        self.state.items_created += 1

    async def _enumerate_initial_arguments(self) -> None:
        """Use LLM to enumerate initial arguments for the resolution."""
        config = Config()
        model = config.get_agent_model("prep_strategy")

        prompt = f"""You are a debate strategist preparing for Public Forum debate.

Resolution: {self.session.resolution}
Side: {self.session.side.value.upper()}

Your task: Enumerate 4-6 strong arguments for this side. For each argument, provide:
1. A clear claim (what you're arguing)
2. What evidence would prove it (be specific about the type of source needed)
3. Priority (high/medium/low)

Focus on arguments that:
- Have strong empirical backing (can find real studies, data, expert quotes)
- Lead to clear impacts (harms or benefits)
- Are likely to win in debate

Output JSON array:
[
  {{
    "argument": "The specific claim to prove",
    "search_intent": "What evidence to look for (be specific)",
    "evidence_type": "support",
    "priority": "high"
  }}
]

Only output the JSON array, nothing else."""

        response = self._get_client().messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse response and create tasks
        response_text = "[]"
        if response.content:
            first_block = response.content[0]
            if hasattr(first_block, "text"):
                response_text = first_block.text

        import json

        try:
            # Extract JSON from response
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()

            arguments = json.loads(response_text)

            for arg in arguments:
                task = {
                    "argument": arg.get("argument", ""),
                    "search_intent": arg.get("search_intent", ""),
                    "evidence_type": arg.get("evidence_type", "support"),
                    "priority": arg.get("priority", "medium"),
                }
                self.session.write_task(task)
                self.state.items_created += 1
                self.log("created_task", {"argument": task["argument"][:40]})

        except json.JSONDecodeError:
            # Fallback: create a generic research task
            task = {
                "argument": f"Core arguments for {self.session.side.value.upper()}",
                "search_intent": f"Find evidence supporting {self.session.side.value} side of {self.session.resolution}",
                "evidence_type": "support",
                "priority": "high",
            }
            self.session.write_task(task)
            self.state.items_created += 1

    async def _respond_to_feedback(self, feedback: dict[str, Any]) -> None:
        """Generate new tasks based on organizer feedback."""
        feedback_type = feedback.get("type", "")

        if feedback_type == "gap":
            # Create task to fill the gap
            task = {
                "argument": feedback.get("message", ""),
                "search_intent": feedback.get("suggested_intent", feedback.get("message", "")),
                "evidence_type": "support",
                "priority": "high",
            }
            self.session.write_task(task)
            self.log("created_task_from_gap", {"argument": task["argument"][:40]})

        elif feedback_type == "opportunity":
            # New argument discovered - research it
            task = {
                "argument": feedback.get("message", ""),
                "search_intent": feedback.get("suggested_intent", ""),
                "evidence_type": "support",
                "priority": "medium",
            }
            self.session.write_task(task)
            self.log("created_task_from_opportunity", {"argument": task["argument"][:40]})

        elif feedback_type == "link_chain":
            # Build impact link chain
            task = {
                "argument": feedback.get("message", ""),
                "search_intent": feedback.get("suggested_intent", ""),
                "evidence_type": "impact",
                "priority": "medium",
            }
            self.session.write_task(task)
            self.log("created_link_chain_task", {"argument": task["argument"][:40]})
