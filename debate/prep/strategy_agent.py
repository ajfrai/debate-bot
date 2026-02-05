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

    def __init__(self, session: PrepSession, generate_blocks: bool = False) -> None:
        super().__init__(session, poll_interval=5.0)
        self._client: anthropic.Anthropic | None = None
        self._generate_blocks = generate_blocks
        self._phase = 0  # Track which phase of strategy generation we're in
        # Build phases list - optionally include opponent_answers phase
        self._phases: list[str] = [
            "initial_arguments",
            "impact_chains",
            "deep_dive",
        ]
        # Insert opponent_answers phase after initial_arguments if generate_blocks is True
        if generate_blocks:
            self._phases.insert(1, "opponent_answers")
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
            # Feedback tasks are treated as stock since they address identified gaps
            task = {
                "argument": message,
                "search_intent": feedback.get("suggested_intent", message),
                "evidence_type": "support" if feedback_type != "link_chain" else "impact",
                "arg_type": "stock",
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

Generate 40-50 NEW argument TAGS to research. Use a MIX of these 5 strategy types (20% each):

1. STOCK - Conventional, predictable arguments (direct claims about the resolution)
2. CREATIVE - Outside the box, counterintuitive link chains
3. NICHE - Academic terms of art, specialized theory
4. OPPORTUNISTIC - Start with impact scenario, work backwards
5. SECOND_ORDER - Extensions that take existing argument conclusions as premises
   - Format: "[Existing conclusion] leads to [downstream effect]"
   - Can chain on other SECOND_ORDER args (build deep causal chains)
   - Examples: "Job elimination leads to reduced spending", "Reduced spending leads to recession"

EXAMPLES by type:

STOCK: "TikTok ban eliminates creator economy jobs"
CREATIVE: "Platform ban accelerates decentralized social media adoption"
NICHE: "Digital sovereignty theory supports data localization mandates"
OPPORTUNISTIC: "Democratic backsliding from authoritarian tech influence"
SECOND_ORDER: "Creator job elimination leads to reduced consumer spending"
SECOND_ORDER (chained): "Reduced consumer spending leads to local business closures"

CRITICAL RULES:
- AVOID semantic duplicates - each tag must be MEANINGFULLY DIFFERENT
- Do NOT rephrase the same idea in different words
- SECOND_ORDER args should reference existing arguments OR other SECOND_ORDER args
- Each tag is exactly 5-12 words
- Skip tags too similar to existing arguments

Output as numbered list. Generate the tag first, then classify it.
Format: N. tag | TYPE (where TYPE is STOCK, CREATIVE, NICHE, OPPORTUNISTIC, or SECOND_ORDER)

1. TikTok ban eliminates creator economy jobs | STOCK
2. Platform ban accelerates decentralized social media adoption | CREATIVE
3. Creator job elimination leads to reduced consumer spending | SECOND_ORDER
4. Digital sovereignty theory supports data localization mandates | NICHE
...etc"""
        else:  # answer
            prompt = f"""You are a debate strategist preparing ANSWERS to opponent arguments.

Resolution: {self.session.resolution}
Your side: {self.session.side.value.upper()}
Opponent side: {"CON" if self.session.side.value == "pro" else "PRO"}

Already prepared answers: {existing_answers if existing_answers else "(none yet)"}

Generate 40-50 ANSWER TAGS (responding to likely opponent claims). Use a MIX of these 5 types (20% each):

1. STOCK - Conventional responses to predictable arguments
2. CREATIVE - Outside the box turns, counterintuitive defenses
3. NICHE - Academic frameworks to reframe opponent claims
4. OPPORTUNISTIC - Concede and turn opponent impact scenarios
5. SECOND_ORDER - Chain opponent's argument to show it leads to worse outcome for them
   - Format: "AT: [Their claim] leads to [bad consequence for them]"
   - Can chain on other answers (build deep refutation chains)

EXAMPLES by type:

STOCK:
- AT: Economic costs outweighed by national security benefits
- AT: Privacy already protected by existing regulations

CREATIVE:
- AT: Ban proves government overreach their impact claims warn against
- AT: Censorship attempt validates slippery slope to authoritarianism

NICHE:
- AT: Coase theorem suggests market solutions superior to ban
- AT: Securitization theory explains overblown threat perception

OPPORTUNISTIC (concede and turn):
- AT: Job losses real but creative destruction accelerates innovation
- AT: Privacy violations exist but ban sets worse precedent

SECOND_ORDER (chain their argument):
- AT: Their privacy concern leads to broader surveillance precedent
- AT: Economic harm claim leads to protectionist spiral

CRITICAL RULES:
- AVOID semantic duplicates - each answer must respond to a MEANINGFULLY DIFFERENT opponent claim
- Do NOT rephrase the same response in different words
- Mix all 5 types roughly equally (20% each)
- Skip any tag too similar to existing answers above
- Each tag starts with "AT:" and is 5-12 words

Output as numbered list. Generate the tag first, then classify it.
Format: N. AT: tag | TYPE (where TYPE is STOCK, CREATIVE, NICHE, OPPORTUNISTIC, or SECOND_ORDER)

1. AT: Economic costs outweighed by national security benefits | STOCK
2. AT: Ban proves government overreach their impact claims warn against | CREATIVE
3. AT: Coase theorem suggests market solutions superior to ban | NICHE
4. AT: Job losses real but creative destruction accelerates innovation | OPPORTUNISTIC
5. AT: Their privacy concern leads to broader surveillance precedent | SECOND_ORDER
...etc"""

        # Show current phase in UI
        self.state.current_phase = self._phases[self._phase]

        try:
            # Stream API call to get tags as they're generated
            tags_created = 0
            async for tag, arg_type in self._stream_tags(model, prompt):
                if not tag:
                    continue

                # Create base task with arg_type for prioritization
                task = {
                    "argument": tag,
                    "evidence_type": evidence_type,
                    "arg_type": arg_type,
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

                # Log base tag to UI with arg_type indicator
                type_emoji = {
                    "stock": "📌",
                    "creative": "💡",
                    "niche": "🎓",
                    "opportunistic": "🎯",
                    "second_order": "🔗",
                }.get(arg_type, "📍")
                tag_snippet = tag[:50] + "..." if len(tag) > 50 else tag
                self.log(
                    f"{type_emoji} {tag_snippet}",
                    {"type": evidence_type, "arg_type": arg_type, "task_id": task_id, "count": tags_created},
                )

                # Create 2 combinatorial variants for broader search coverage
                # Variants inherit arg_type from parent but are marked as variants
                variants = self._expand_tag_with_vocabulary(tag, num_variants=2)
                for variant in variants:
                    variant_task = {
                        "argument": variant,
                        "evidence_type": evidence_type,
                        "arg_type": arg_type,
                        "is_variant": True,
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
                        {"type": f"{evidence_type}_variant", "arg_type": arg_type, "task_id": variant_id},
                    )

        except Exception as e:
            error_msg = f"Error enumerating arguments: {str(e)[:40]}"
            self.log(error_msg, {"error_type": "exception"})
            self.state.current_direction = f"❌ {error_msg}"

    async def _generate_impact_chains(self) -> None:
        """Generate mixed impact evidence: intermediate, second-order, and terminal impacts.

        Creates a mix of three impact types to build full causal chains:
        - Intermediate impacts (25%): Starting points like "reduced voter turnout"
        - Second-order impacts (25%): Chains like "reduced turnout leads to gridlock"
        - Terminal impacts (50%): End-state consequences like "democratic collapse"

        Full chain example: Electoral college → small state power → ethanol subsidies → climate damage
        """
        # Update UI with current research direction
        direction = "⚡ Building impact chains (mixed types)"
        self.state.current_direction = direction
        self.log(direction, {"phase": "starting"})

        config = Config()
        model = config.get_agent_model("prep_strategy")

        brief = self.session.read_brief()
        existing_args = list(brief.get("arguments", {}).keys())

        prompt = f"""You are building IMPACT EVIDENCE for debate arguments.

Resolution: {self.session.resolution}
Side: {self.session.side.value.upper()}

Current arguments: {existing_args if existing_args else "(none yet)"}

Generate 40-50 IMPACT TAGS using a MIX of these 5 types (20% each):

1. STOCK - Conventional, predictable terminal impacts (war, recession, job loss)
2. CREATIVE - Unexpected, counterintuitive impact cascades
3. NICHE - Impacts grounded in specialized academic theory
4. OPPORTUNISTIC - High-magnitude impact scenarios (extinction, collapse)
5. SECOND_ORDER - Causal chains: "[Effect] leads to [Consequence]"
   - Can chain on other SECOND_ORDER impacts (build deep impact chains)
   - Examples: "Turnout decline leads to gridlock", "Gridlock leads to democratic erosion"

EXAMPLES by type:

STOCK: "Impact: Economic recession ensues"
STOCK: "Impact: Unemployment skyrockets"
CREATIVE: "Impact: Innovation ecosystem collapses"
CREATIVE: "Impact: Institutional trust evaporates"
NICHE: "Impact: Authoritarian diffusion undermines democracies"
NICHE: "Impact: Systemic risk cascades through markets"
OPPORTUNISTIC: "Impact: Great power war erupts"
OPPORTUNISTIC: "Impact: Existential catastrophe risk increases"
SECOND_ORDER: "Impact: Reduced turnout leads to policy gridlock"
SECOND_ORDER: "Impact: Policy gridlock leads to democratic erosion"

CRITICAL RULES:
- AVOID semantic duplicates - each tag must be MEANINGFULLY DIFFERENT
- Do NOT create variants of the same impact
- SECOND_ORDER impacts should build chains (reference existing impacts or other SECOND_ORDER)
- Each tag starts with "Impact:" and is 5-12 words

Output as numbered list. Generate the tag first, then classify it.
Format: N. Impact: tag | TYPE (where TYPE is STOCK, CREATIVE, NICHE, OPPORTUNISTIC, or SECOND_ORDER)

1. Impact: Economic recession ensues | STOCK
2. Impact: Innovation ecosystem collapses | CREATIVE
3. Impact: Reduced turnout leads to policy gridlock | SECOND_ORDER
4. Impact: Authoritarian diffusion undermines democracies | NICHE
...etc"""

        # Show current phase in UI
        self.state.current_phase = self._phases[self._phase]

        try:
            # Stream API call to get tags as they're generated
            tags_created = 0
            async for tag, arg_type in self._stream_tags(model, prompt):
                if not tag:
                    continue

                # Create base task with arg_type for prioritization
                task = {
                    "argument": tag,
                    "evidence_type": "impact",
                    "arg_type": arg_type,
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

                # Log base tag to UI with arg_type indicator
                type_emoji = {
                    "stock": "⚡",
                    "creative": "💡",
                    "niche": "🎓",
                    "opportunistic": "🎯",
                    "second_order": "🔗",
                }.get(arg_type, "⚡")
                tag_snippet = tag[:50] + "..." if len(tag) > 50 else tag
                self.log(
                    f"{type_emoji} {tag_snippet}",
                    {"type": "impact", "arg_type": arg_type, "task_id": task_id, "count": tags_created},
                )

                # Create 2 combinatorial variants for broader search coverage
                # Variants inherit arg_type from parent but are marked as variants
                variants = self._expand_tag_with_vocabulary(tag, num_variants=2)
                for variant in variants:
                    variant_task = {
                        "argument": variant,
                        "evidence_type": "impact",
                        "arg_type": arg_type,
                        "is_variant": True,
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
                        {"type": "impact_variant", "arg_type": arg_type, "task_id": variant_id},
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

                # Deep dive tasks are stock since they strengthen existing arguments
                task = {
                    "argument": arg_name,
                    "search_intent": f"Find additional evidence for: {arg_name}",
                    "evidence_type": "support",
                    "arg_type": "stock",
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

    def _parse_tag_line(self, line: str) -> tuple[str, str] | None:
        """Parse a single line in format 'N. tag | TYPE'.

        Args:
            line: Line to parse (e.g., "1. TikTok ban eliminates jobs | STOCK")

        Returns:
            Tuple of (tag, arg_type) or None if line doesn't match format.
            arg_type is lowercased (stock, creative, niche, opportunistic).
        """
        line = line.strip()
        if not line or not line[0].isdigit():
            return None

        # Find the period after the number
        period_idx = line.find(".")
        if period_idx <= 0:
            return None

        content = line[period_idx + 1 :].strip()
        if not content:
            return None

        # Parse "tag | TYPE" format
        if " | " in content:
            tag, arg_type = content.rsplit(" | ", 1)
            arg_type = arg_type.strip().lower()
            # Validate arg_type
            if arg_type not in ("stock", "creative", "niche", "opportunistic", "second_order"):
                arg_type = "stock"  # Default fallback
            return (tag.strip(), arg_type)
        else:
            # No type specified, default to stock
            return (content, "stock")

    async def _stream_tags(self, model: str, prompt: str):
        """Stream tags from API call, yielding each tag as it's parsed.

        Uses streaming API to get response incrementally, parsing numbered list
        format and yielding complete tags immediately as chunks arrive.

        CRITICAL: No list() call - this ensures TRUE streaming, not batch processing.

        Args:
            model: Model to use for generation
            prompt: Prompt to send to model

        Yields:
            Tuples of (tag, arg_type) as they're parsed from the stream.
            arg_type is one of: stock, creative, niche, opportunistic
        """
        buffer = ""
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def _feed_queue():
            """Run sync stream in thread and feed chunks to queue."""

            def _sync_stream_to_queue():
                """Run streaming API call synchronously and feed queue.

                CRITICAL: The iteration must happen INSIDE the thread to avoid
                blocking the main event loop. We use thread-safe queue operations.
                """
                with self._get_client().messages.stream(
                    model=model,
                    max_tokens=2048,
                    messages=[{"role": "user", "content": prompt}],
                ) as stream:
                    # Iterate in thread, feed chunks via thread-safe call
                    for chunk in stream.text_stream:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)

            loop = asyncio.get_running_loop()
            try:
                # This blocks in the thread, not the main event loop
                await asyncio.to_thread(_sync_stream_to_queue)
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
                    parsed = self._parse_tag_line(line)
                    if parsed:
                        yield parsed

            # Process any remaining buffer after stream ends
            if buffer.strip():
                parsed = self._parse_tag_line(buffer)
                if parsed:
                    yield parsed
        finally:
            await feeder_task
