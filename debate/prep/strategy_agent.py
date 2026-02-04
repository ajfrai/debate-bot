"""StrategyAgent: Maintains argument queue and decides what to research."""

import asyncio
import json
import os
from typing import Any

import anthropic

from debate.config import Config
from debate.prep.base_agent import BaseAgent
from debate.prep.session import PrepSession


class StrategyAgent(BaseAgent):
    """Plans research strategy and creates targeted research tasks.

    Runs continuously, generating new research tasks based on:
    - Initial argument enumeration
    - Feedback from organizer (gaps, opportunities)
    - Periodic reassessment of what's needed
    - Opponent case anticipation
    - Impact link chains
    """

    def __init__(self, session: PrepSession) -> None:
        super().__init__(session, poll_interval=5.0)
        self._client: anthropic.Anthropic | None = None
        self._phase = 0  # Track which phase of strategy generation we're in
        self._phases = [
            "initial_arguments",
            "opponent_answers",
            "impact_chains",
            "deep_dive",
        ]

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

    async def check_for_work(self) -> list[Any]:
        """Always return work - either feedback to process or a signal to generate more."""
        # First, check for feedback from organizer
        feedback = self.session.get_pending_feedback()
        if feedback:
            return [("feedback", f) for f in feedback]

        # Otherwise, signal that we should generate more tasks
        # This ensures the agent never idles
        return [("generate", self._phase)]

    async def process_item(self, item: tuple[str, Any]) -> None:
        """Process either feedback or a generation request."""
        item_type, data = item

        if item_type == "feedback":
            await self._process_feedback(data)
        elif item_type == "generate":
            await self._generate_tasks_for_phase(data)
            # Advance to next phase (cycles through)
            self._phase = (self._phase + 1) % len(self._phases)

    async def _process_feedback(self, feedback: dict[str, Any]) -> None:
        """Process feedback from organizer."""
        try:
            feedback_path = str(self.session.staging_dir / "organizer" / "feedback" / f"feedback_{feedback['id']}.json")
            self.session.mark_processed("strategy", feedback_path)

            feedback_type = feedback.get("type", "")
            message = feedback.get("message", "")

            # Update UI with current direction
            display_msg = message[:20] + "..." if len(message) > 20 else message
            direction = f"📝 Responding: {display_msg}"
            self.state.current_direction = direction

            self.log(direction, {"type": feedback_type, "id": feedback["id"]})

            # Create task based on feedback
            task = {
                "argument": message,
                "search_intent": feedback.get("suggested_intent", message),
                "evidence_type": "support" if feedback_type != "link_chain" else "impact",
                "priority": "high",
                "source": f"feedback_{feedback_type}",
            }
            self.session.write_task(task)
            self.state.items_created += 1
            self.log(f"task_from_{feedback_type}", {"argument": task["argument"][:40]})
        except Exception as e:
            error_msg = f"Error processing feedback: {str(e)[:40]}"
            self.log(error_msg, {"error_type": "feedback_error"})
            self.state.current_direction = f"❌ {error_msg}"

    async def _generate_tasks_for_phase(self, phase_idx: int) -> None:
        """Generate tasks for the current strategy phase."""
        phase = self._phases[phase_idx]
        self.log(f"generating_{phase}", {"phase": phase})

        if phase == "initial_arguments":
            await self._enumerate_arguments("support")
        elif phase == "opponent_answers":
            await self._enumerate_arguments("answer")
        elif phase == "impact_chains":
            await self._generate_impact_chains()
        elif phase == "deep_dive":
            await self._generate_deep_dive()

    async def _enumerate_arguments(self, evidence_type: str) -> None:
        """Enumerate arguments for the given evidence type."""
        # Update UI with current research direction
        if evidence_type == "support":
            direction = "📌 Generating PRO arguments"
        else:
            direction = "🛡️ Generating ANSWER arguments"
        self.state.current_direction = direction
        self.log(direction, {"phase": "starting"})

        config = Config()
        model = config.get_agent_model("prep_strategy")

        # Get current brief state to avoid duplicates
        brief = self.session.read_brief()
        existing_args = list(brief.get("arguments", {}).keys())
        existing_answers = list(brief.get("answers", {}).keys())

        if evidence_type == "support":
            prompt = f"""You are a debate strategist for Public Forum debate.

Resolution: {self.session.resolution}
Side: {self.session.side.value.upper()}

Already researched arguments: {existing_args if existing_args else "(none yet)"}

Generate 2-3 NEW arguments to research (not duplicates of existing).
For each argument, be CONCISE (3-10 words max):
- argument: A specific, provable claim (3-10 words)
- search_intent: What evidence to find (3-10 words)
- priority: high/medium/low

Output JSON array:
[
  {{
    "argument": "Concise specific claim",
    "search_intent": "What evidence to find",
    "priority": "high"
  }}
]

Only output JSON array."""
        else:  # answer
            prompt = f"""You are a debate strategist preparing ANSWERS to opponent arguments.

Resolution: {self.session.resolution}
Your side: {self.session.side.value.upper()}
Opponent side: {"CON" if self.session.side.value == "pro" else "PRO"}

Already prepared answers: {existing_answers if existing_answers else "(none yet)"}

Generate 2-3 ANSWER arguments (responding to likely opponent claims).
Be CONCISE (3-10 words max) for each:
- argument: AT: [Opponent claim] (3-10 words)
- search_intent: Evidence that refutes/mitigates (3-10 words)
- priority: high/medium/low

Output JSON array:
[
  {{
    "argument": "AT: Concise opponent claim",
    "search_intent": "Evidence that refutes this",
    "priority": "high"
  }}
]

Only output JSON array."""

        try:
            # Run sync API call in thread pool to avoid blocking event loop
            response = await asyncio.to_thread(
                self._get_client().messages.create,
                model=model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = "[]"
            if response.content:
                first_block = response.content[0]
                if hasattr(first_block, "text"):
                    response_text = first_block.text

            # Parse JSON
            response_text = self._extract_json(response_text)
            arguments = json.loads(response_text)

            for arg in arguments[:3]:  # Limit to 3
                task = {
                    "argument": arg.get("argument", ""),
                    "search_intent": arg.get("search_intent", ""),
                    "evidence_type": evidence_type,
                    "priority": arg.get("priority", "medium"),
                    "source": f"enumerate_{evidence_type}",
                }
                self.session.write_task(task)
                self.state.items_created += 1

                # Log full argument and search intent to UI
                arg_text = task["argument"]
                search_text = task["search_intent"]
                self.log(f"📍 {arg_text} | 🔍 {search_text}", {"type": evidence_type, "priority": task["priority"]})

        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse JSON response: {str(e)[:40]}"
            self.log(error_msg, {"error_type": "json_decode"})
            self.state.current_direction = f"❌ {error_msg}"
        except Exception as e:
            error_msg = f"Error enumerating arguments: {str(e)[:40]}"
            self.log(error_msg, {"error_type": "exception"})
            self.state.current_direction = f"❌ {error_msg}"

    async def _generate_impact_chains(self) -> None:
        """Generate research tasks for impact link chains."""
        # Update UI with current research direction
        direction = "⚡ Building impact link chains"
        self.state.current_direction = direction
        self.log(direction, {"phase": "starting"})

        config = Config()
        model = config.get_agent_model("prep_strategy")

        brief = self.session.read_brief()
        existing_args = list(brief.get("arguments", {}).keys())

        prompt = f"""You are building IMPACT CHAINS for debate arguments.

Resolution: {self.session.resolution}
Side: {self.session.side.value.upper()}

Current arguments: {existing_args if existing_args else "(none yet)"}

For each existing argument, identify TERMINAL IMPACT evidence needed.
Impact chains: [Internal Link] -> [Impact]

Be CONCISE (3-10 words max):
- argument: Impact: [Terminal impact] (3-10 words)
- search_intent: Evidence that [X] leads to [Y] (3-10 words)
- priority: high/medium

Generate 2 impact research tasks:
[
  {{
    "argument": "Impact: Concise terminal impact",
    "search_intent": "Evidence linking to terminal harm",
    "priority": "medium"
  }}
]

Only output JSON array."""

        try:
            # Run sync API call in thread pool to avoid blocking event loop
            response = await asyncio.to_thread(
                self._get_client().messages.create,
                model=model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = "[]"
            if response.content:
                first_block = response.content[0]
                if hasattr(first_block, "text"):
                    response_text = first_block.text

            response_text = self._extract_json(response_text)
            impacts = json.loads(response_text)

            for impact in impacts[:2]:
                task = {
                    "argument": impact.get("argument", ""),
                    "search_intent": impact.get("search_intent", ""),
                    "evidence_type": "impact",
                    "priority": impact.get("priority", "medium"),
                    "source": "impact_chain",
                }
                self.session.write_task(task)
                self.state.items_created += 1

                # Log full impact and search intent to UI
                arg_text = task["argument"]
                search_text = task["search_intent"]
                self.log(f"⚡ {arg_text} | 🔍 {search_text}", {"type": "impact", "priority": task["priority"]})

        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse impact chain JSON: {str(e)[:35]}"
            self.log(error_msg, {"error_type": "json_decode"})
            self.state.current_direction = f"❌ {error_msg}"
        except Exception as e:
            error_msg = f"Error generating impact chains: {str(e)[:35]}"
            self.log(error_msg, {"error_type": "exception"})
            self.state.current_direction = f"❌ {error_msg}"

    async def _generate_deep_dive(self) -> None:
        """Generate deep-dive tasks for arguments that need more evidence."""
        # Update UI with current research direction
        direction = "🔎 Deepening existing arguments"
        self.state.current_direction = direction
        self.log(direction, {"phase": "deep_dive"})

        brief = self.session.read_brief()

        # Find arguments with few cards
        for arg_name, arg_data in brief.get("arguments", {}).items():
            total_cards = sum(len(g.get("cards", [])) for g in arg_data.get("semantic_groups", {}).values())
            if total_cards < 3:
                # Need more evidence for this argument
                # Condense argument name if needed
                display_arg = arg_name[:30] + "..." if len(arg_name) > 30 else arg_name
                direction = f"📚 Deepening: {display_arg}"
                self.state.current_direction = direction

                task = {
                    "argument": arg_name,
                    "search_intent": f"Find additional evidence for: {arg_name}",
                    "evidence_type": "support",
                    "priority": "medium",
                    "source": "deep_dive",
                }
                self.session.write_task(task)
                self.state.items_created += 1

                # Log with brief argument and card count
                self.log(f"{direction} ({total_cards} cards)", {"cards": total_cards})
                return  # One at a time

        # If no arguments need deep dive, explore new angles
        direction = "✨ Exploring new strategic angles"
        self.state.current_direction = direction
        self.log(direction, {})

    def _extract_json(self, text: str) -> str:
        """Extract JSON from response text."""
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            return text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            return text[start:end].strip()
        return text.strip()
