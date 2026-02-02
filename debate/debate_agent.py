"""A generally capable debate agent that can research, generate cases, and deliver speeches."""

import json
from datetime import datetime
from pathlib import Path

import anthropic

from debate.case_generator import generate_case as _generate_case
from debate.evidence_storage import load_debate_file
from debate.models import (
    AnalysisResult,
    AnalysisType,
    ArgumentPrep,
    Case,
    DebateFile,
    PrepFile,
    ResearchEntry,
    RoundState,
    SectionType,
    Side,
)
from debate.research_agent import research_evidence as _research_evidence


def load_prompt_template(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompts_dir = Path(__file__).parent / "prompts"
    template_path = prompts_dir / f"{name}.md"
    return template_path.read_text()


class DebateAgent:
    """A debate agent capable of research, case generation, and delivering speeches.

    This agent orchestrates all debate activities:
    - Research evidence using web search
    - Generate opening cases
    - Deliver speeches (rebuttal, summary, final focus) based on goals
    - Answer crossfire questions
    """

    def __init__(self, side: Side, resolution: str):
        """Initialize the debate agent.

        Args:
            side: Which side the agent is debating (PRO or CON)
            resolution: The debate resolution
        """
        self.side = side
        self.resolution = resolution
        self.client = anthropic.Anthropic()
        self.prep_file: PrepFile | None = None

    def research(
        self,
        topic: str,
        num_cards: int = 3,
        section_type: str = "support",
        stream: bool = True,
    ) -> DebateFile:
        """Research evidence cards for a specific topic.

        Args:
            topic: The specific argument or topic to research
            num_cards: Number of evidence cards to cut (1-5)
            section_type: Strategic value (support, answer, extension, impact)
            stream: Whether to stream tokens as they're generated

        Returns:
            DebateFile with researched evidence
        """
        from debate.research_agent import research_evidence

        return research_evidence(
            resolution=self.resolution,
            side=self.side,
            topic=topic,
            num_cards=num_cards,
            stream=stream,
        )

    def generate_case(
        self,
        debate_file: DebateFile | None = None,
        stream: bool = True,
    ) -> Case:
        """Generate an opening case.

        Args:
            debate_file: Optional debate file with researched evidence
            stream: Whether to stream tokens as they're generated

        Returns:
            A Case with 2-3 contentions
        """
        evidence_buckets = None
        if debate_file:
            # Convert debate file sections to evidence buckets for compatibility
            from debate.models import EvidenceBucket

            sections = debate_file.get_sections_for_side(self.side)
            evidence_buckets = []
            for section in sections:
                cards = [debate_file.get_card(card_id) for card_id in section.card_ids]
                bucket = EvidenceBucket(
                    topic=section.argument,
                    resolution=self.resolution,
                    side=self.side,
                    cards=[c for c in cards if c is not None],
                )
                evidence_buckets.append(bucket)

        return _generate_case(
            resolution=self.resolution,
            side=self.side,
            evidence_buckets=evidence_buckets,
            stream=stream,
        )

    def generate_speech(
        self,
        goal: str,
        round_state: RoundState,
        time_limit_seconds: int,
        debate_file: DebateFile | None = None,
        stream: bool = True,
    ) -> str:
        """Generate a speech based on the goal and current round state.

        Args:
            goal: The purpose of this speech (e.g., "Rebuttal: attack opponent's contentions and defend our case")
            round_state: Current state of the debate round with all speeches so far
            time_limit_seconds: Time limit for this speech
            debate_file: Optional debate file with available evidence
            stream: Whether to stream tokens as they're generated

        Returns:
            The full text of the speech
        """
        template = load_prompt_template("speech_generation")

        # Format round context
        context_lines = []

        # Add our case
        if self.side == round_state.team_a_side:
            our_case = round_state.team_a_case
            opponent_case = round_state.team_b_case
            our_team = "Team A"
            opponent_team = "Team B"
        else:
            our_case = round_state.team_b_case
            opponent_case = round_state.team_a_case
            our_team = "Team B"
            opponent_team = "Team A"

        if our_case:
            context_lines.append(f"## Our Case ({our_team} - {self.side.value.upper()})\n")
            context_lines.append(our_case.format())
            context_lines.append("")

        if opponent_case:
            context_lines.append(f"## Opponent's Case ({opponent_team} - {self.side.opposite.value.upper()})\n")
            context_lines.append(opponent_case.format())
            context_lines.append("")

        # Add previous speeches
        if round_state.speeches:
            context_lines.append("## Previous Speeches\n")
            for i, speech in enumerate(round_state.speeches, 1):
                speaker = our_team if speech.side == self.side else opponent_team
                context_lines.append(f"### Speech {i}: {speaker} {speech.speech_type.value.title()}\n")
                context_lines.append(speech.content)
                context_lines.append("")

        round_context = "\n".join(context_lines)

        # Format available evidence
        evidence_section = ""
        if debate_file:
            evidence_section = self._format_available_evidence(debate_file)

        # Calculate approximate word limit (assuming ~150 words per minute speaking rate)
        words_per_minute = 150
        word_limit = int((time_limit_seconds / 60) * words_per_minute)

        prompt = template.format(
            resolution=self.resolution,
            side=self.side.value.upper(),
            goal=goal,
            round_context=round_context,
            available_evidence=evidence_section,
            time_limit_seconds=time_limit_seconds,
            word_limit=word_limit,
        )

        if stream:
            response_text = ""
            with self.client.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            ) as stream_response:
                for text in stream_response.text_stream:
                    print(text, end="", flush=True)
                    response_text += text
            print()
        else:
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            first_block = message.content[0]
            response_text = first_block.text if hasattr(first_block, "text") else ""

        return response_text

    def _format_available_evidence(self, debate_file: DebateFile) -> str:
        """Format available evidence for inclusion in speech prompts."""
        lines = ["## Available Evidence\n"]

        sections = debate_file.get_sections_for_side(self.side)
        if not sections:
            return ""

        for section in sections:
            lines.append(f"### {section.get_heading()}\n")
            for card_id in section.card_ids:
                card = debate_file.get_card(card_id)
                if card:
                    last_name = card.author.split()[-1]
                    lines.append(f"- **{card.tag}** ({last_name} {card.year}) `[{card_id}]`")
                    lines.append(f"  - {card.text[:200]}...")
                    lines.append("")

        return "\n".join(lines)

    def answer_crossfire_question(
        self,
        question: str,
        round_state: RoundState,
        stream: bool = True,
    ) -> str:
        """Answer a crossfire question from the opponent.

        Args:
            question: The opponent's question
            round_state: Current state of the debate round
            stream: Whether to stream tokens as they're generated

        Returns:
            The answer to the question
        """
        # Format context about the round
        our_case = round_state.team_a_case if self.side == round_state.team_a_side else round_state.team_b_case
        opponent_case = round_state.team_b_case if self.side == round_state.team_a_side else round_state.team_a_case

        context = f"""You are debating {self.side.value.upper()} on: {self.resolution}

Your case:
{our_case.format() if our_case else "(No case yet)"}

Opponent's case:
{opponent_case.format() if opponent_case else "(No case yet)"}

Question from opponent: {question}

Provide a concise, strategic answer (1-3 sentences). Be confident but don't concede key points."""

        if stream:
            response_text = ""
            with self.client.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                messages=[{"role": "user", "content": context}],
            ) as stream_response:
                for text in stream_response.text_stream:
                    print(text, end="", flush=True)
                    response_text += text
            print()
        else:
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                messages=[{"role": "user", "content": context}],
            )
            first_block = message.content[0]
            response_text = first_block.text if hasattr(first_block, "text") else ""

        return response_text

    def ask_crossfire_question(
        self,
        round_state: RoundState,
        stream: bool = True,
    ) -> str:
        """Generate a crossfire question to ask the opponent.

        Args:
            round_state: Current state of the debate round
            stream: Whether to stream tokens as they're generated

        Returns:
            A strategic question to ask the opponent
        """
        our_case = round_state.team_a_case if self.side == round_state.team_a_side else round_state.team_b_case
        opponent_case = round_state.team_b_case if self.side == round_state.team_a_side else round_state.team_a_case

        context = f"""You are debating {self.side.value.upper()} on: {self.resolution}

Your case:
{our_case.format() if our_case else "(No case yet)"}

Opponent's case:
{opponent_case.format() if opponent_case else "(No case yet)"}

Generate a strategic crossfire question (1-2 sentences) that:
- Exposes a weakness in their case
- Sets up a future argument
- Forces them to concede something helpful to your side"""

        if stream:
            response_text = ""
            with self.client.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=256,
                messages=[{"role": "user", "content": context}],
            ) as stream_response:
                for text in stream_response.text_stream:
                    print(text, end="", flush=True)
                    response_text += text
            print()
        else:
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=256,
                messages=[{"role": "user", "content": context}],
            )
            first_block = message.content[0]
            response_text = first_block.text if hasattr(first_block, "text") else ""

        return response_text

    # ========== Autonomous Prep Methods ==========

    def prep(self, max_turns: int = 10, stream: bool = True) -> PrepFile:
        """Run autonomous prep workflow using skill orchestration.

        The agent autonomously:
        - Analyzes strategic aspects (enumerate arguments, map clash, etc.)
        - Researches evidence (checks backfiles first, then web)
        - Organizes findings incrementally into PrepFile

        Args:
            max_turns: Maximum tool calls (default 10 for cost control)
            stream: Whether to stream agent thinking

        Returns:
            Completed PrepFile with strategic prep
        """
        # Initialize or load existing prep file
        self.prep_file = PrepFile(resolution=self.resolution, side=self.side)

        # Define tools for agent
        tools = [
            {
                "name": "analyze",
                "description": "Run systematic analysis processes to produce structured outputs that inform research and strategy.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "analysis_type": {
                            "type": "string",
                            "enum": [
                                "enumerate_arguments",
                                "brainstorm_rebuttals",
                                "analyze_source",
                                "map_clash",
                                "identify_framework",
                                "synthesize_evidence",
                            ],
                            "description": "Type of systematic analysis to perform",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Subject of analysis (e.g., card ID, opponent claim). Optional for some types.",
                        },
                    },
                    "required": ["analysis_type"],
                },
            },
            {
                "name": "research",
                "description": "Research evidence (searches backfiles first, then web if needed). Automatically organizes findings into prep. Returns sources and citations that you can follow up on.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "What to research (can be based on analysis, previous findings, or citations)",
                        },
                        "purpose": {
                            "type": "string",
                            "enum": ["support", "answer", "extension", "impact"],
                            "description": "Strategic purpose of this evidence",
                        },
                        "num_cards": {
                            "type": "integer",
                            "default": 3,
                            "description": "Number of cards to find/cut (default 3)",
                        },
                    },
                    "required": ["topic", "purpose"],
                },
            },
            {
                "name": "read_prep",
                "description": "View current prep state to see what you've built and identify gaps. Use to avoid redundant research.",
                "input_schema": {"type": "object", "properties": {}},
            },
        ]

        # Load system prompt
        template = load_prompt_template("prep_orchestration")
        system_prompt = template.format(
            resolution=self.resolution,
            side=self.side.value.upper(),
            max_turns=max_turns,
        )

        messages = []
        current_turn = 0

        print(f"\n{'=' * 60}")
        print(f"AUTONOMOUS PREP: {self.side.value.upper()} on {self.resolution}")
        print(f"Budget: {max_turns} turns")
        print(f"{'=' * 60}\n")

        while current_turn < max_turns:
            current_turn += 1
            print(f"\n--- Turn {current_turn}/{max_turns} ---\n")

            # Add turn tracking to the first message
            if not messages:
                initial_msg = f"Begin prep. Current turn: {current_turn}/{max_turns}"
                messages.append({"role": "user", "content": initial_msg})

            # Call Claude with tools
            response = self.client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
                tools=tools,
            )

            # Add assistant response to messages (content must be list of blocks for tool use)
            messages.append({"role": "assistant", "content": list(response.content)})  # type: ignore[dict-item]

            # Display thinking
            for block in response.content:
                if block.type == "text":
                    print(block.text)
                    print()

            # Handle tool use
            if response.stop_reason == "tool_use":
                tool_results = []

                for block in response.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input

                        print(f"[Calling {tool_name}...]")

                        # Execute tool
                        if tool_name == "analyze":
                            result = self._analyze_skill(
                                analysis_type=tool_input["analysis_type"],
                                subject=tool_input.get("subject"),
                            )
                        elif tool_name == "research":
                            result = self._research_skill(
                                topic=tool_input["topic"],
                                purpose=tool_input["purpose"],
                                num_cards=tool_input.get("num_cards", 3),
                                stream=stream,
                            )
                        elif tool_name == "read_prep":
                            result = self._read_prep_skill()
                        else:
                            result = {"error": f"Unknown tool: {tool_name}"}

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(result, indent=2),
                            }
                        )

                        print(f"[{tool_name} complete]\n")

                # Add tool results to messages (must be list of tool result blocks)
                messages.append({"role": "user", "content": tool_results})  # type: ignore[dict-item]

            elif response.stop_reason == "end_turn":
                # Agent decided to stop
                print("\n[Agent concluded prep]\n")
                break

        print(f"\n{'=' * 60}")
        print("PREP COMPLETE")
        print(f"Turns used: {current_turn}/{max_turns}")
        print(f"Arguments: {len(self.prep_file.arguments)}")
        print(f"Total cards: {sum(len(arg.card_ids) for arg in self.prep_file.arguments)}")
        print(f"Analyses: {len(self.prep_file.analyses)}")
        print(f"{'=' * 60}\n")

        return self.prep_file

    def _analyze_skill(self, analysis_type: str, subject: str | None = None) -> dict:
        """Execute an analysis skill."""
        analysis_enum = AnalysisType(analysis_type)

        # TODO: Implement each analysis type with specific prompts
        # For now, return placeholder
        output = f"[Analysis of type {analysis_type} would be performed here]"

        if analysis_type == "enumerate_arguments":
            output = self._enumerate_arguments()
        # Add other analysis types...

        result = AnalysisResult(
            analysis_type=analysis_enum,
            subject=subject,
            output=output,
            timestamp=datetime.now().isoformat(),
        )

        if self.prep_file:
            self.prep_file.add_analysis(result)

        return {
            "analysis_type": analysis_type,
            "output": output,
            "status": "completed",
        }

    def _enumerate_arguments(self) -> str:
        """Systematically enumerate all possible arguments."""
        # TODO: Load prompt template and call LLM
        # For now, return placeholder
        return "PRO arguments: 1. Security, 2. Privacy, 3. Democracy\nCON arguments: 1. Economy, 2. Free speech, 3. Innovation"

    def _research_skill(self, topic: str, purpose: str, num_cards: int = 3, stream: bool = True) -> dict:
        """Execute research skill: backfiles first, then web search, organize immediately."""
        purpose_enum = SectionType(purpose)

        # Step 1: Check backfiles for existing evidence
        debate_file = load_debate_file(self.resolution)
        existing_cards = []
        sources_used = []

        if debate_file:
            existing_cards = debate_file.find_cards_by_tag(topic)
            print(f"  Found {len(existing_cards)} cards in backfiles")

        # Step 2: Calculate how many more cards we need
        cards_needed = max(0, num_cards - len(existing_cards))
        new_cards = []

        if cards_needed > 0:
            print(f"  Researching {cards_needed} more cards from web...")
            # Use existing research agent (returns DebateFile)
            updated_debate_file = _research_evidence(
                resolution=self.resolution,
                side=self.side,
                topic=topic,
                num_cards=cards_needed,
                stream=stream,
            )

            # Extract newly added cards from the debate file
            # The research agent adds cards to sections, so get them from the appropriate side
            sections = updated_debate_file.get_sections_for_side(self.side)
            for section in sections:
                if topic.lower() in section.argument.lower():
                    for card_id in section.card_ids:
                        card = updated_debate_file.get_card(card_id)
                        if card and card not in existing_cards:
                            new_cards.append(card)

            # Extract sources from cards
            sources_used = list(set(card.source for card in new_cards if hasattr(card, "source")))

        # Step 3: Organize into PrepFile immediately
        all_card_ids = []
        for card in existing_cards + new_cards:
            if hasattr(card, "id"):
                all_card_ids.append(card.id)

        argument = ArgumentPrep(
            claim=topic,
            purpose=purpose_enum,
            card_ids=all_card_ids,
            source_summary=f"{len(existing_cards)} from backfiles, {len(new_cards)} cut from web",
            strategic_notes=f"Evidence for {purpose}",
        )

        if self.prep_file:
            self.prep_file.add_argument(argument)

        # Log research
        entry = ResearchEntry(
            topic=topic,
            purpose=purpose_enum,
            cards_from_backfiles=len(existing_cards),
            cards_cut_from_web=len(new_cards),
            sources_used=sources_used,
            citations_found=[],  # TODO: Extract citations from card text
            timestamp=datetime.now().isoformat(),
        )

        if self.prep_file:
            self.prep_file.log_research(entry)

        return {
            "topic": topic,
            "cards_from_backfiles": len(existing_cards),
            "cards_cut_from_web": len(new_cards),
            "total_cards": len(all_card_ids),
            "sources_used": sources_used[:3],  # Limit for readability
            "organized": True,
        }

    def _read_prep_skill(self) -> dict:
        """Return current prep state summary."""
        if self.prep_file:
            return self.prep_file.get_summary()
        return {"error": "No prep file available"}
