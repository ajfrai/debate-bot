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
from debate.research_agent import research_evidence_efficient as _research_evidence_efficient


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
                                # Exploration
                                "enumerate_arguments",
                                "adversarial_brainstorm",
                                "find_novel_angles",
                                "identify_uncertainty",
                                # Exploitation
                                "brainstorm_rebuttals",
                                "analyze_source",
                                "extend_argument",
                                "build_block",
                                "synthesize_evidence",
                                # Strategic
                                "map_clash",
                                "identify_framework",
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
                "name": "search",
                "description": "Search for sources on a topic. Returns search results with descriptions. Use fetch_source to get full article text.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query to find sources",
                        },
                        "num_results": {
                            "type": "integer",
                            "default": 5,
                            "description": "Number of search results to return (default 5)",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "fetch_source",
                "description": "Fetch full article text from a URL. Returns the raw text that you can then mark up.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL of the article to fetch",
                        },
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "mark_warrants",
                "description": "Mark key warrants in text by bolding specific phrases. Like using Edit tool on code - you specify which phrases to bold, and the tool adds ** markers programmatically. NEVER rewrite the text, just specify which exact phrases to bold.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The raw text to mark up (from fetch_source)",
                        },
                        "warrant_phrases": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of exact phrases to bold (will add **phrase** markers). Each phrase should be 3-15 words. Aim for 3-6 phrases covering 20-40% of text.",
                        },
                    },
                    "required": ["text", "warrant_phrases"],
                },
            },
            {
                "name": "cut_card",
                "description": "Save a cut card with marked-up text to the debate file. Call this after mark_warrants.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "tag": {
                            "type": "string",
                            "description": "Brief label (5-10 words) stating what the card PROVES",
                        },
                        "argument": {
                            "type": "string",
                            "description": "The SPECIFIC claim this card relates to (NOT a vague topic)",
                        },
                        "purpose": {
                            "type": "string",
                            "enum": ["support", "answer", "extension", "impact"],
                            "description": "Strategic purpose of this card",
                        },
                        "author": {
                            "type": "string",
                            "description": "Author's full name",
                        },
                        "credentials": {
                            "type": "string",
                            "description": "Author's qualifications (e.g., 'Professor of Economics at MIT')",
                        },
                        "year": {
                            "type": "string",
                            "description": "Publication year",
                        },
                        "source": {
                            "type": "string",
                            "description": "Publication name (e.g., 'New York Times')",
                        },
                        "url": {
                            "type": "string",
                            "description": "URL to source",
                        },
                        "text": {
                            "type": "string",
                            "description": "The marked-up text from mark_warrants (already has **bold** markers)",
                        },
                        "evidence_type": {
                            "type": "string",
                            "enum": ["statistical", "analytical", "consensus", "empirical", "predictive"],
                            "description": "Type of evidence",
                        },
                    },
                    "required": ["tag", "argument", "purpose", "author", "credentials", "year", "source", "text"],
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
                        elif tool_name == "search":
                            result = self._search_skill(
                                query=tool_input["query"],
                                num_results=tool_input.get("num_results", 5),
                            )
                        elif tool_name == "fetch_source":
                            result = self._fetch_source_skill(
                                url=tool_input["url"],
                            )
                        elif tool_name == "mark_warrants":
                            result = self._mark_warrants_skill(
                                text=tool_input["text"],
                                warrant_phrases=tool_input["warrant_phrases"],
                            )
                        elif tool_name == "cut_card":
                            result = self._cut_card_skill(
                                tag=tool_input["tag"],
                                argument=tool_input["argument"],
                                purpose=tool_input["purpose"],
                                author=tool_input["author"],
                                credentials=tool_input["credentials"],
                                year=tool_input["year"],
                                source=tool_input["source"],
                                url=tool_input.get("url"),
                                text=tool_input["text"],
                                evidence_type=tool_input.get("evidence_type"),
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

        # Route to specific analysis implementation
        output = self._run_analysis(analysis_type, subject)

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

    def _run_analysis(self, analysis_type: str, subject: str | None = None) -> str:
        """Run breadcrumb analysis using LLM with streaming output.

        Analysis should be CONCISE bullet points showing:
        - Argument links (X -> Y -> Z)
        - Evidence needs
        - Blockers
        - Next research targets
        """
        # Build concise breadcrumb prompts
        prompts = {
            "breadcrumb_initial": f"""Map the ARGUMENT TREE for {self.side.value.upper()} on: {self.resolution}

Think of this as a tree:
- Resolution = ROOT node (top-level action)
- Branches = CAUSES (what leads to what)
- Leaves = IMPACTS (end consequences)

For utilitarian: map cause-effect chains
For rights-based: map rights in tension and frameworks

Format as BRIEF bullet points (mix of links, impacts, blockers as relevant):
∙ resolution -> cause -> impact
∙ resolution -> cause -> impact
∙ Blocker: potential challenge (if relevant)
Need: warrants for each link

Example:
∙ ban -> reduced social media use -> improved grades
∙ ban -> reduced phone use -> mental health
∙ ban -> removes Chinese data collection -> national security
Need: warrants for each link, strong impact evidence

Keep it SHORT (max 10 lines). Map the tree, then identify evidence needs.""",

            "breadcrumb_followup": f"""Based on new evidence{f' about {subject}' if subject else ''}, identify NEW BRANCHES on the argument tree:

Format as brief bullet points:
- What evidence mentions (citations, related cases, follow-up targets)
- New argument branches revealed
- Research gaps

Example:
∙ <card> mentions Supreme Court case X. Research related cases.
∙ <card> mentions Chinese influence. New branch: Russian influence comparison
∙ Gap: no statistical evidence for economic magnitude
Need: quantitative data, expert analysis

Keep it SHORT (max 8 lines). Just new branches and next research targets.""",
        }

        prompt = prompts.get(analysis_type, f"Perform {analysis_type} breadcrumb analysis for {self.resolution}")

        # Stream the response for user feedback
        print(f"\n  Analyzing ({analysis_type})...\n")
        response_text = ""
        with self.client.messages.stream(
            model="claude-sonnet-4-5",
            max_tokens=256,  # Strict limit for breadcrumb analysis (was 1024)
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                response_text += text
        print("\n")

        return response_text

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

    def _search_skill(self, query: str, num_results: int = 5) -> dict:
        """Execute web search and return formatted results."""
        import time
        from debate.research_agent import _brave_search

        print(f"  Searching for: {query[:70]}...")

        # Add 3-second pause to avoid rate limiting
        time.sleep(3)

        search_results = _brave_search(query, num_results=num_results)

        if search_results:
            print("  ✓ Found search results")
            return {
                "status": "success",
                "query": query,
                "results": search_results,
                "message": "Search completed. Use fetch_source to get full article text from a URL.",
            }
        else:
            print("  ⚠ No search results")
            return {
                "status": "no_results",
                "query": query,
                "message": "No search results found. Try a different query or use your knowledge base.",
            }

    def _fetch_source_skill(self, url: str) -> dict:
        """Fetch full article text from a URL using trafilatura."""
        import trafilatura

        print(f"  Fetching: {url[:60]}...")

        try:
            # Download and extract text
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return {
                    "status": "error",
                    "message": f"Failed to download content from {url}",
                }

            # Extract main text content
            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
            )

            if not text:
                return {
                    "status": "error",
                    "message": f"Could not extract text from {url}",
                }

            # Truncate if too long (keep first 3000 chars for token efficiency)
            if len(text) > 3000:
                text = text[:3000] + "\n\n[... truncated for length ...]"

            print(f"  ✓ Fetched {len(text)} characters")

            return {
                "status": "success",
                "url": url,
                "text": text,
                "message": "Article text fetched. Use mark_warrants to bold key phrases.",
            }

        except Exception as e:
            print(f"  ✗ Error: {e}")
            return {
                "status": "error",
                "message": f"Error fetching {url}: {str(e)}",
            }

    def _mark_warrants_skill(self, text: str, warrant_phrases: list[str]) -> dict:
        """Mark key warrants by bolding specific phrases in the text.

        This is like using the Edit tool - we find exact phrases and add ** markers.
        Never regenerate the text, just mark it up programmatically.
        """
        print(f"  Marking {len(warrant_phrases)} warrant phrases...")

        marked_text = text
        marked_count = 0

        # Bold each phrase (in order, to avoid position shifts)
        # We need to be careful about already-bolded text
        for phrase in warrant_phrases:
            if phrase in marked_text:
                # Only bold if not already bolded
                if f"**{phrase}**" not in marked_text:
                    marked_text = marked_text.replace(phrase, f"**{phrase}**", 1)
                    marked_count += 1
                    print(f"    ✓ Bolded: {phrase[:50]}...")
            else:
                print(f"    ⚠ Phrase not found: {phrase[:50]}...")

        if marked_count == 0:
            return {
                "status": "error",
                "message": "No phrases were found in the text. Make sure phrases are exact matches.",
            }

        # Calculate how much is bolded
        bold_chars = sum(len(p) for p in warrant_phrases if p in text)
        total_chars = len(text)
        bold_pct = (bold_chars / total_chars * 100) if total_chars > 0 else 0

        print(f"  ✓ Marked {marked_count}/{len(warrant_phrases)} phrases (~{bold_pct:.0f}% of text)")

        return {
            "status": "success",
            "marked_text": marked_text,
            "phrases_marked": marked_count,
            "bold_percentage": bold_pct,
            "message": f"Marked {marked_count} phrases. Use cut_card to save this card.",
        }

    def _cut_card_skill(
        self,
        tag: str,
        argument: str,
        purpose: str,
        author: str,
        credentials: str,
        year: str,
        source: str,
        text: str,
        url: str | None = None,
        evidence_type: str | None = None,
    ) -> dict:
        """Cut a card and add it to the flat debate file structure."""
        from debate.evidence_storage import get_or_create_flat_debate_file, save_flat_debate_file
        from debate.models import EvidenceType

        # Parse evidence type
        evidence_type_enum = None
        if evidence_type:
            type_map = {
                "statistical": EvidenceType.STATISTICAL,
                "analytical": EvidenceType.ANALYTICAL,
                "consensus": EvidenceType.CONSENSUS,
                "empirical": EvidenceType.EMPIRICAL,
                "predictive": EvidenceType.PREDICTIVE,
            }
            evidence_type_enum = type_map.get(evidence_type.lower())

        # Create card
        card = Card(
            tag=tag,
            author=author,
            credentials=credentials,
            year=year,
            source=source,
            url=url,
            text=text,
            purpose=f"{purpose} - {argument}",
            evidence_type=evidence_type_enum,
        )

        # Get or create flat debate file
        flat_file, is_new = get_or_create_flat_debate_file(self.resolution)

        # Determine if this is an answer based on purpose or argument name
        is_answer = purpose.lower() == "answer" or argument.lower().startswith("at:") or argument.lower().startswith("opponent claim:")
        answers_to = None
        argument_title = argument

        if is_answer:
            # Extract what we're answering
            if argument.lower().startswith("at:"):
                answers_to = argument[3:].strip()
                argument_title = f"AT: {answers_to}"
            elif argument.lower().startswith("opponent claim:"):
                answers_to = argument[15:].strip()
                argument_title = f"AT: {answers_to}"
            else:
                answers_to = argument
                argument_title = f"AT: {argument}"

        # Find or create the argument file
        arguments = flat_file.get_arguments_for_side(self.side)
        arg_file = None

        # Look for existing argument file
        for existing_arg in arguments:
            # Match by title or answers_to
            if is_answer and existing_arg.is_answer:
                if existing_arg.answers_to and answers_to and existing_arg.answers_to.lower() == answers_to.lower():
                    arg_file = existing_arg
                    break
            elif not is_answer and not existing_arg.is_answer:
                if existing_arg.title.lower() == argument_title.lower():
                    arg_file = existing_arg
                    break

        # Create new argument file if not found
        if not arg_file:
            from debate.models import ArgumentFile

            arg_file = ArgumentFile(
                title=argument_title,
                is_answer=is_answer,
                answers_to=answers_to,
                purpose=f"Evidence for {purpose}: {argument}",
            )
            if self.side == Side.PRO:
                flat_file.pro_arguments.append(arg_file)
            else:
                flat_file.con_arguments.append(arg_file)

        # Find or create claim within the argument file
        # For now, use the card tag as the claim
        claim_cards = arg_file.find_or_create_claim(tag)
        claim_cards.cards.append(card)

        # Save the flat debate file
        save_flat_debate_file(flat_file)

        # Add to prep file if available
        if self.prep_file:
            # Check if argument already exists in prep
            existing_arg = None
            for arg in self.prep_file.arguments:
                if arg.claim == argument:
                    existing_arg = arg
                    break

            if existing_arg:
                # Add card ID reference (note: flat structure doesn't use IDs the same way)
                # Just track that we added a card
                existing_arg.source_summary += f", {source} ({year})"
            else:
                # Create new argument in prep
                new_arg = ArgumentPrep(
                    claim=argument,
                    purpose=SectionType(purpose.lower()),
                    card_ids=[card.id],
                    source_summary=f"{source} ({year})",
                    strategic_notes=f"Card: {tag}",
                )
                self.prep_file.add_argument(new_arg)

        print(f"  ✓ Cut card: {tag[:50]}...")

        return {
            "status": "success",
            "tag": tag,
            "argument": argument_title,
            "claim": claim_cards.claim,
            "card_number": len(claim_cards.cards),
            "message": f"Card cut and saved to {arg_file.get_filename()}",
        }
