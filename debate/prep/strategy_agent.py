"""StrategyAgent: Maintains argument queue and decides what to research."""

import asyncio
import os
import random
from typing import Any

import anthropic

from debate.config import Config
from debate.prep.base_agent import BaseAgent
from debate.prep.research_vocabulary import ALL_TERMS
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
        # Initialize phase tracking for kanban UI
        self.state.phase_task_counts = {phase: 0 for phase in self._phases}
        self.state.current_phase = ""

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
            task_id = self.session.write_task(task)

            # Skip if duplicate
            if not task_id:
                self.log(f"duplicate_from_{feedback_type}", {"argument": message[:40]})
                return

            # Track in kanban (feedback stage)
            self.state.task_stages[task_id] = "feedback"
            self.state.items_created += 1

            self.log(f"task_from_{feedback_type}", {"argument": task["argument"][:40], "task_id": task_id})
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
        side_label = self.session.side.value.upper()
        if evidence_type == "support":
            direction = f"📌 Generating {side_label} arguments"
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

Generate 40-50 NEW argument TAGS to research.

CRITICAL RULES:
- AVOID semantic duplicates - each tag must be MEANINGFULLY DIFFERENT
- Do NOT rephrase the same idea in different words
- Each tag should explore a DISTINCT argument or angle
- Skip any tag that is too similar to existing arguments above
- Each tag is exactly 5-12 words

GOOD (diverse angles):
1. TikTok ban eliminates creator economy jobs
2. Chinese government can access user data
3. Data collection violates privacy rights

BAD (semantic duplicates):
1. TikTok ban eliminates creator economy jobs
2. TikTok ban destroys creator employment opportunities  ← DUPLICATE (same as #1)
3. Creator jobs lost due to TikTok ban  ← DUPLICATE (same as #1)

Output as numbered list ONLY. No other text.
1. Tag here exactly 5-12 words
2. Another tag exactly 5-12 words
3. Third tag exactly 5-12 words
...etc"""
        else:  # answer
            prompt = f"""You are a debate strategist preparing ANSWERS to opponent arguments.

Resolution: {self.session.resolution}
Your side: {self.session.side.value.upper()}
Opponent side: {"CON" if self.session.side.value == "pro" else "PRO"}

Already prepared answers: {existing_answers if existing_answers else "(none yet)"}

Generate 40-50 ANSWER TAGS (responding to likely opponent claims).

CRITICAL RULES:
- AVOID semantic duplicates - each answer must respond to a MEANINGFULLY DIFFERENT opponent claim
- Do NOT rephrase the same response in different words
- Each tag should address a DISTINCT opponent argument
- Skip any tag too similar to existing answers above
- Each tag starts with "AT:" and is 5-12 words

GOOD (diverse responses):
1. AT: Economic costs outweighed by national security benefits
2. AT: Privacy already protected by existing regulations
3. AT: Ban creates worse problems than it solves

BAD (semantic duplicates):
1. AT: Economic costs outweighed by national security benefits
2. AT: Security concerns justify the economic harm  ← DUPLICATE (same as #1)
3. AT: National security more important than economy  ← DUPLICATE (same as #1)

Output as numbered list ONLY. No other text.
1. AT: Tag here exactly 5-12 words
2. AT: Another tag exactly 5-12 words
3. AT: Third tag exactly 5-12 words
...etc"""

        # Show current phase in UI
        self.state.current_phase = self._phases[self._phase]

        try:
            # Stream API call to get tags as they're generated
            tags_created = 0
            async for tag in self._stream_tags(model, prompt):
                if not tag:
                    continue

                # Create base task
                task = {
                    "argument": tag,
                    "evidence_type": evidence_type,
                    "source": f"enumerate_{evidence_type}",
                }
                task_id = self.session.write_task(task)

                # Skip if duplicate (write_task returns empty string)
                if not task_id:
                    continue

                # Track in kanban
                self.state.task_stages[task_id] = "created"
                phase_name = self._phases[self._phase]
                self.state.phase_task_counts[phase_name] += 1
                self.state.items_created += 1
                tags_created += 1

                # Log base tag to UI
                tag_snippet = tag[:50] + "..." if len(tag) > 50 else tag
                self.log(
                    f"📍 {tag_snippet}",
                    {"type": evidence_type, "task_id": task_id, "count": tags_created},
                )

                # Create 2 combinatorial variants for broader search coverage
                variants = self._expand_tag_with_vocabulary(tag, num_variants=2)
                for variant in variants:
                    variant_task = {
                        "argument": variant,
                        "evidence_type": evidence_type,
                        "source": f"enumerate_{evidence_type}_variant",
                    }
                    variant_id = self.session.write_task(variant_task)

                    # Skip if duplicate
                    if not variant_id:
                        continue

                    # Track variant in kanban
                    self.state.task_stages[variant_id] = "created"
                    self.state.phase_task_counts[phase_name] += 1
                    self.state.items_created += 1
                    tags_created += 1

                    # Log variant (condensed to save UI space)
                    variant_snippet = variant[:45] + "..." if len(variant) > 45 else variant
                    self.log(
                        f"  ↳ {variant_snippet}",
                        {"type": f"{evidence_type}_variant", "task_id": variant_id},
                    )

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

Generate 40-50 IMPACT TAGS identifying terminal impact evidence needed.

CRITICAL RULES:
- AVOID semantic duplicates - each impact must be MEANINGFULLY DIFFERENT
- Do NOT rephrase the same impact chain in different words
- Each tag should identify a DISTINCT terminal harm or benefit
- Skip any tag too similar to others in your list
- Each tag starts with "Impact:" and is 5-12 words

GOOD (diverse impacts):
1. Impact: Data breaches lead to identity theft harm
2. Impact: Job loss causes economic recession
3. Impact: Censorship threatens democratic institutions

BAD (semantic duplicates):
1. Impact: Data breaches lead to identity theft harm
2. Impact: Personal information stolen causes identity theft  ← DUPLICATE (same as #1)
3. Impact: Privacy violations result in identity fraud  ← DUPLICATE (same as #1)

Output as numbered list ONLY. No other text.
1. Impact: Tag here exactly 5-12 words
2. Impact: Another tag exactly 5-12 words
3. Impact: Third tag exactly 5-12 words
...etc"""

        # Show current phase in UI
        self.state.current_phase = self._phases[self._phase]

        try:
            # Stream API call to get tags as they're generated
            tags_created = 0
            async for tag in self._stream_tags(model, prompt):
                if not tag:
                    continue

                # Create base task
                task = {
                    "argument": tag,
                    "evidence_type": "impact",
                    "source": "impact_chain",
                }
                task_id = self.session.write_task(task)

                # Skip if duplicate
                if not task_id:
                    continue

                # Track in kanban
                self.state.task_stages[task_id] = "created"
                phase_name = self._phases[self._phase]
                self.state.phase_task_counts[phase_name] += 1
                self.state.items_created += 1
                tags_created += 1

                # Log base tag to UI
                tag_snippet = tag[:50] + "..." if len(tag) > 50 else tag
                self.log(
                    f"⚡ {tag_snippet}",
                    {"type": "impact", "task_id": task_id, "count": tags_created},
                )

                # Create 2 combinatorial variants for broader search coverage
                variants = self._expand_tag_with_vocabulary(tag, num_variants=2)
                for variant in variants:
                    variant_task = {
                        "argument": variant,
                        "evidence_type": "impact",
                        "source": "impact_chain_variant",
                    }
                    variant_id = self.session.write_task(variant_task)

                    # Skip if duplicate
                    if not variant_id:
                        continue

                    # Track variant in kanban
                    self.state.task_stages[variant_id] = "created"
                    self.state.phase_task_counts[phase_name] += 1
                    self.state.items_created += 1
                    tags_created += 1

                    # Log variant (condensed to save UI space)
                    variant_snippet = variant[:45] + "..." if len(variant) > 45 else variant
                    self.log(
                        f"  ↳ {variant_snippet}",
                        {"type": "impact_variant", "task_id": variant_id},
                    )

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

        # Show current phase in UI
        self.state.current_phase = self._phases[self._phase]

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
                task_id = self.session.write_task(task)

                # Skip if duplicate
                if not task_id:
                    continue

                # Track in kanban
                self.state.task_stages[task_id] = "created"
                phase_name = self._phases[self._phase]
                self.state.phase_task_counts[phase_name] += 1
                self.state.items_created += 1

                # Log with brief argument and card count
                self.log(f"{direction} ({total_cards} cards)", {"cards": total_cards, "task_id": task_id})
                return  # One at a time

        # If no arguments need deep dive, explore new angles
        direction = "✨ Exploring new strategic angles"
        self.state.current_direction = direction
        self.log(direction, {})

    def _expand_tag_with_vocabulary(self, base_tag: str, num_variants: int = 2) -> list[str]:
        """Create variants of a base tag by combining with vocabulary terms.

        Args:
            base_tag: The base research tag to expand
            num_variants: Number of variants to create (default 2)

        Returns:
            List of variant tags (does not include base tag)
        """
        variants = []
        # Sample random terms from vocabulary without replacement
        sampled_terms = random.sample(ALL_TERMS, min(num_variants, len(ALL_TERMS)))

        for term in sampled_terms:
            variant = f"{base_tag} + {term}"
            variants.append(variant)

        return variants

    def _parse_numbered_list(self, text: str) -> list[str]:
        """Parse numbered list format: '1. tag here', '2. tag here', etc.

        Returns list of tags extracted from the numbered list.
        """
        tags = []
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # Match "N. tag" format where N is a number
            if line and line[0].isdigit():
                # Find the period and extract everything after it
                period_idx = line.find(".")
                if period_idx > 0:
                    tag = line[period_idx + 1 :].strip()
                    if tag:
                        tags.append(tag)
        return tags

    async def _stream_tags(self, model: str, prompt: str):
        """Stream tags from API call, yielding each tag as it's parsed.

        Uses streaming API to get response incrementally, parsing numbered list
        format and yielding complete tags immediately as chunks arrive.

        CRITICAL: No list() call - this ensures TRUE streaming, not batch processing.

        Args:
            model: Model to use for generation
            prompt: Prompt to send to model

        Yields:
            Complete tags as they're parsed from the stream
        """
        buffer = ""
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def _feed_queue():
            """Run sync stream in thread and feed chunks to queue."""

            def _sync_stream():
                """Run streaming API call synchronously."""
                with self._get_client().messages.stream(
                    model=model,
                    max_tokens=2048,
                    messages=[{"role": "user", "content": prompt}],
                ) as stream:
                    yield from stream.text_stream

            try:
                for chunk in await asyncio.to_thread(_sync_stream):
                    await queue.put(chunk)
            finally:
                await queue.put(None)  # Signal end of stream

        # Start the queue feeder task
        feeder_task = asyncio.create_task(_feed_queue())

        try:
            # Process chunks as they arrive - no batching, no list() call
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break  # End of stream

                buffer += chunk

                # Try to extract complete lines (tags) from buffer
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if not line:
                        continue

                    # Match "N. tag" format where N is a number
                    if line and line[0].isdigit():
                        period_idx = line.find(".")
                        if period_idx > 0:
                            tag = line[period_idx + 1 :].strip()
                            if tag:
                                yield tag

            # Process any remaining buffer after stream ends
            if buffer.strip():
                line = buffer.strip()
                if line and line[0].isdigit():
                    period_idx = line.find(".")
                    if period_idx > 0:
                        tag = line[period_idx + 1 :].strip()
                        if tag:
                            yield tag
        finally:
            await feeder_task
