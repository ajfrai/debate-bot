"""A generally capable debate agent that can research, generate cases, and deliver speeches."""

from pathlib import Path
from typing import Optional

import anthropic

from debate.case_generator import generate_case as _generate_case
from debate.models import Case, DebateFile, RoundState, Side, Speech, SpeechType
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

    def research(
        self,
        topic: str,
        num_cards: int = 3,
        section_type: str = "support",
        stream: bool = True,
    ) -> list:
        """Research evidence cards for a specific topic.

        Args:
            topic: The specific argument or topic to research
            num_cards: Number of evidence cards to cut (1-5)
            section_type: Strategic value (support, answer, extension, impact)
            stream: Whether to stream tokens as they're generated

        Returns:
            List of evidence cards
        """
        from debate.research_agent import research_evidence

        return research_evidence(
            resolution=self.resolution,
            side=self.side,
            topic=topic,
            num_cards=num_cards,
            section_type=section_type,
            stream=stream,
        )

    def generate_case(
        self,
        debate_file: Optional[DebateFile] = None,
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
                bucket = EvidenceBucket(
                    topic=section.argument,
                    resolution=self.resolution,
                    side=self.side,
                    cards=[debate_file.get_card(card_id) for card_id in section.card_ids if debate_file.get_card(card_id)]
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
        debate_file: Optional[DebateFile] = None,
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
            response_text = message.content[0].text

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
            response_text = message.content[0].text

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
            response_text = message.content[0].text

        return response_text
