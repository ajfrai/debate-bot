"""Pydantic models for debate round state and content."""

import uuid
from enum import Enum

from pydantic import BaseModel, Field


class Side(str, Enum):
    """Debate side (Pro affirms the resolution, Con negates)."""

    PRO = "pro"
    CON = "con"

    @property
    def opposite(self) -> "Side":
        """Return the opposing side."""
        return Side.CON if self == Side.PRO else Side.PRO


class SpeechType(str, Enum):
    """Types of speeches in Public Forum debate."""

    CONSTRUCTIVE = "constructive"
    REBUTTAL = "rebuttal"
    SUMMARY = "summary"
    FINAL_FOCUS = "final_focus"
    CROSSFIRE = "crossfire"


class SectionType(str, Enum):
    """Types of argument sections in a debate file."""

    SUPPORT = "support"  # Supporting evidence for an argument
    ANSWER = "answer"  # Answer/response to an argument
    EXTENSION = "extension"  # Extension/additional warrants
    IMPACT = "impact"  # Impact calculus evidence


class Card(BaseModel):
    """An evidence card with full citation, credentials, and bolded sections.

    Like real policy debate evidence cards, includes:
    - Unique ID for cross-referencing across sections
    - Full author credentials
    - Complete citation information
    - Direct quote with bolded sections (using **text** for what to read aloud)
    - Source URL for verification
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], description="Unique card ID")
    tag: str = Field(description="Brief label summarizing the card's argument")
    author: str = Field(description="Author's full name (e.g., 'John Smith')")
    credentials: str = Field(description="Author's qualifications (e.g., 'Professor of Economics at MIT')")
    year: str = Field(description="Publication year")
    source: str = Field(description="Publication name (e.g., 'New York Times', 'Nature')")
    url: str | None = Field(default=None, description="URL to source for verification")
    text: str = Field(description="Full quoted text with **bolded sections** marking what should be read aloud")
    purpose: str = Field(default="", description="Strategic purpose of this card (e.g., 'proves economic harm')")

    def format_for_reading(self) -> str:
        """Format the card for reading aloud in a speech (only bolded portions)."""
        import re

        # Extract only bolded text
        bolded_parts = re.findall(r"\*\*(.+?)\*\*", self.text)
        reading_text = " ".join(bolded_parts)

        last_name = self.author.split()[-1]
        return f"{last_name} {self.year} explains, {reading_text}"

    def format_full(self) -> str:
        """Format the full card with citation and credentials for reference."""
        last_name = self.author.split()[-1]
        return (
            f"[{last_name} {self.year}]\n"
            f"{self.author}, {self.credentials}\n"
            f"{self.source}, {self.year}\n"
            f"{self.url or '(no URL)'}\n\n"
            f"{self.text}"
        )


class ArgumentSection(BaseModel):
    """A section organizing cards for a specific strategic purpose.

    Cards are grouped by their strategic value:
    - Supporting evidence for <argument>
    - Answer to <argument>
    - Extensions for <argument>
    - Impact evidence for <argument>
    """

    section_type: SectionType = Field(description="Type of section (support, answer, extension, impact)")
    argument: str = Field(description="The specific argument this section addresses")
    card_ids: list[str] = Field(default_factory=list, description="IDs of cards in this section")
    notes: str = Field(default="", description="Strategic notes for using this section")

    def get_heading(self) -> str:
        """Get the markdown heading for this section."""
        type_labels = {
            SectionType.SUPPORT: "Supporting evidence for",
            SectionType.ANSWER: "Answer to",
            SectionType.EXTENSION: "Extensions for",
            SectionType.IMPACT: "Impact evidence for",
        }
        return f"{type_labels[self.section_type]} {self.argument}"


class DebateFile(BaseModel):
    """A debate file organizing all evidence for one resolution.

    Acts like a directory structure with:
    - A master list of all cards (each with unique ID)
    - Sections organizing cards by strategic value
    - Cards can appear in multiple sections (cross-referenced by ID)
    - A markdown table of contents for navigation
    """

    resolution: str = Field(description="The debate resolution")
    cards: dict[str, Card] = Field(default_factory=dict, description="All cards keyed by ID")
    pro_sections: list[ArgumentSection] = Field(default_factory=list, description="Pro-side sections")
    con_sections: list[ArgumentSection] = Field(default_factory=list, description="Con-side sections")

    def add_card(self, card: Card) -> str:
        """Add a card to the master list. Returns the card ID."""
        self.cards[card.id] = card
        return card.id

    def get_card(self, card_id: str) -> Card | None:
        """Get a card by ID."""
        return self.cards.get(card_id)

    def add_to_section(
        self,
        side: Side,
        section_type: SectionType,
        argument: str,
        card_id: str,
        notes: str = "",
    ) -> None:
        """Add a card to a section, creating the section if needed."""
        sections = self.pro_sections if side == Side.PRO else self.con_sections

        # Find or create section
        section = None
        for s in sections:
            if s.section_type == section_type and s.argument.lower() == argument.lower():
                section = s
                break

        if not section:
            section = ArgumentSection(
                section_type=section_type,
                argument=argument,
                card_ids=[],
                notes=notes,
            )
            sections.append(section)

        # Add card if not already present
        if card_id not in section.card_ids:
            section.card_ids.append(card_id)

    def get_table_of_contents(self) -> str:
        """Generate a markdown table of contents for navigation."""
        lines = [
            f"# {self.resolution}",
            "",
            "## Table of Contents",
            "",
        ]

        # Pro sections
        if self.pro_sections:
            lines.append("### PRO")
            lines.append("")
            for section in self.pro_sections:
                heading = section.get_heading()
                anchor = heading.lower().replace(" ", "-").replace("<", "").replace(">", "")
                lines.append(f"- [{heading}](#{anchor})")
                for card_id in section.card_ids:
                    card = self.cards.get(card_id)
                    if card:
                        last_name = card.author.split()[-1]
                        lines.append(f"  - {card.tag} ({last_name} {card.year}) `[{card_id}]`")
            lines.append("")

        # Con sections
        if self.con_sections:
            lines.append("### CON")
            lines.append("")
            for section in self.con_sections:
                heading = section.get_heading()
                anchor = heading.lower().replace(" ", "-").replace("<", "").replace(">", "")
                lines.append(f"- [{heading}](#{anchor})")
                for card_id in section.card_ids:
                    card = self.cards.get(card_id)
                    if card:
                        last_name = card.author.split()[-1]
                        lines.append(f"  - {card.tag} ({last_name} {card.year}) `[{card_id}]`")
            lines.append("")

        return "\n".join(lines)

    def render_full_file(self) -> str:
        """Render the complete debate file as markdown."""
        lines = [self.get_table_of_contents(), "---", ""]

        def render_sections(sections: list[ArgumentSection], side_label: str):
            if not sections:
                return
            lines.append(f"# {side_label}")
            lines.append("")
            for section in sections:
                lines.append(f"## {section.get_heading()}")
                lines.append("")
                if section.notes:
                    lines.append(f"*{section.notes}*")
                    lines.append("")
                for i, card_id in enumerate(section.card_ids, 1):
                    card = self.cards.get(card_id)
                    if card:
                        lines.append(f"### {i}. {card.tag} `[{card_id}]`")
                        lines.append("")
                        if card.purpose:
                            lines.append(f"**Purpose:** {card.purpose}")
                            lines.append("")
                        lines.append(card.format_full())
                        lines.append("")
                lines.append("---")
                lines.append("")

        render_sections(self.pro_sections, "PRO")
        render_sections(self.con_sections, "CON")

        return "\n".join(lines)

    def find_cards_by_tag(self, search_term: str) -> list[Card]:
        """Find cards whose tags contain the search term."""
        search_lower = search_term.lower()
        return [card for card in self.cards.values() if search_lower in card.tag.lower()]

    def get_sections_for_side(self, side: Side) -> list[ArgumentSection]:
        """Get all sections for a given side."""
        return self.pro_sections if side == Side.PRO else self.con_sections


# Keep EvidenceBucket for backwards compatibility
class EvidenceBucket(BaseModel):
    """A collection of evidence cards organized by argument/topic.

    Like policy debaters' tubs of evidence, stores cards for specific arguments
    with a table of contents for quick reference.

    Note: This is maintained for backwards compatibility. New code should use DebateFile.
    """

    topic: str = Field(description="The argument or topic this bucket covers")
    resolution: str = Field(description="The debate resolution this evidence supports")
    side: Side = Field(description="Which side this evidence supports")
    cards: list[Card] = Field(default_factory=list, description="Evidence cards in this bucket")

    def add_card(self, card: Card) -> None:
        """Add a card to the bucket."""
        self.cards.append(card)

    def get_table_of_contents(self) -> str:
        """Generate a table of contents listing all card tags."""
        lines = [f"Evidence Bucket: {self.topic}", "=" * 60, ""]
        for i, card in enumerate(self.cards, 1):
            last_name = card.author.split()[-1]
            lines.append(f"{i}. {card.tag} ({last_name} {card.year})")
        return "\n".join(lines)

    def find_cards_by_tag(self, search_term: str) -> list[Card]:
        """Find cards whose tags contain the search term."""
        search_lower = search_term.lower()
        return [card for card in self.cards if search_lower in card.tag.lower()]


class Contention(BaseModel):
    """A contention is a 100-500 word argument that may contain evidence cards.

    Contentions should read like real debate cases with natural integration
    of evidence - cards are woven into prose, not listed separately.
    """

    title: str = Field(description="Contention label, e.g., 'Contention 1: Economic Growth'")
    content: str = Field(
        description="100-500 word argument mixing claims, warrants, and evidence",
    )


class Case(BaseModel):
    """A debate case with 2-3 contentions for one side of a resolution."""

    resolution: str = Field(description="The debate resolution")
    side: Side = Field(description="Pro or Con")
    contentions: list[Contention] = Field(
        description="2-3 contentions supporting the side's position",
        min_length=2,
        max_length=3,
    )

    def format(self) -> str:
        """Format the full case for display."""
        side_label = "AFFIRMATIVE" if self.side == Side.PRO else "NEGATIVE"
        lines = [
            f"{'=' * 60}",
            f"{side_label} CASE",
            f"Resolution: {self.resolution}",
            f"{'=' * 60}",
            "",
        ]

        for contention in self.contentions:
            lines.append(contention.title)
            lines.append("-" * 40)
            lines.append(contention.content)
            lines.append("")

        return "\n".join(lines)


class Speech(BaseModel):
    """A speech delivered during the debate round."""

    speech_type: SpeechType = Field(description="Type of speech")
    side: Side = Field(description="Which side delivered this speech")
    speaker_number: int = Field(description="1 for first speaker, 2 for second speaker", ge=1, le=2)
    content: str = Field(description="The full text of the speech")
    time_limit_seconds: int = Field(description="Time limit for this speech in seconds")


class CrossfireExchange(BaseModel):
    """A single question-answer exchange in crossfire."""

    questioner_side: Side
    question: str
    answer: str


class Crossfire(BaseModel):
    """A crossfire period with Q&A exchanges."""

    crossfire_type: str = Field(description="first, second, or grand")
    exchanges: list[CrossfireExchange] = Field(default_factory=list)
    time_limit_seconds: int = Field(default=180, description="3 minutes")


class RoundState(BaseModel):
    """Current state of a debate round."""

    resolution: str
    team_a_side: Side = Field(description="Which side Team A (user) is on")
    team_b_side: Side = Field(description="Which side Team B (AI) is on")
    team_a_case: Case | None = None
    team_b_case: Case | None = None
    speeches: list[Speech] = Field(default_factory=list)
    crossfires: list[Crossfire] = Field(default_factory=list)
    current_speech_index: int = Field(default=0, description="Index in speech order")


class JudgeDecision(BaseModel):
    """The judge's decision and reasoning after the round."""

    winner: Side
    winning_team: str = Field(description="'Team A' or 'Team B'")
    voting_issues: list[str] = Field(description="Key issues that decided the round")
    rfd: str = Field(description="Full reason for decision")
    feedback: list[str] = Field(description="1-2 pieces of constructive feedback")


class AnalysisType(str, Enum):
    """Types of systematic analysis processes available during prep."""

    ENUMERATE_ARGUMENTS = "enumerate_arguments"  # List all possible PRO and CON arguments
    BRAINSTORM_REBUTTALS = "brainstorm_rebuttals"  # Generate multiple answers to a claim
    ANALYZE_SOURCE = "analyze_source"  # Line-by-line breakdown of evidence
    MAP_CLASH = "map_clash"  # Identify debate clash points
    IDENTIFY_FRAMEWORK = "identify_framework"  # Determine weighing criteria
    SYNTHESIZE_EVIDENCE = "synthesize_evidence"  # Connect cards into narrative


class AnalysisResult(BaseModel):
    """Result of a systematic analysis process."""

    analysis_type: AnalysisType
    subject: str | None = Field(default=None, description="Subject of analysis (e.g., card ID, claim)")
    output: str = Field(description="Structured output from the analysis")
    timestamp: str = Field(description="When this analysis was performed")


class ArgumentPrep(BaseModel):
    """An argument with organized evidence for prep."""

    claim: str = Field(description="What we're arguing")
    purpose: SectionType = Field(description="Strategic purpose: support, answer, extension, impact")
    card_ids: list[str] = Field(default_factory=list, description="Cards backing this argument")
    source_summary: str = Field(
        default="",
        description="Where cards came from (e.g., '2 from backfiles, 1 cut from web')",
    )
    strategic_notes: str = Field(default="", description="When to use, what it sets up")


class ResearchEntry(BaseModel):
    """Record of a research session during prep."""

    topic: str
    purpose: SectionType
    cards_from_backfiles: int = 0
    cards_cut_from_web: int = 0
    sources_used: list[str] = Field(default_factory=list)
    citations_found: list[str] = Field(default_factory=list, description="Citations that could be followed up")
    timestamp: str


class PrepFile(BaseModel):
    """Strategic prep that grows incrementally during autonomous prep.

    This is a living document that the agent builds through:
    - Systematic analysis (enumerate arguments, map clash, etc.)
    - Iterative research (backfiles + web search)
    - Incremental organization (updates after each research cycle)
    """

    resolution: str
    side: Side

    # Strategic analyses (updated by analyze())
    analyses: dict[str, AnalysisResult] = Field(
        default_factory=dict,
        description="Analysis results keyed by type (e.g., 'enumerate_arguments')",
    )

    # Arguments (grow as research happens)
    arguments: list[ArgumentPrep] = Field(default_factory=list, description="Arguments with organized evidence")

    # Research history (tracks what's been researched)
    research_log: list[ResearchEntry] = Field(default_factory=list, description="Log of all research sessions")

    def add_analysis(self, result: AnalysisResult) -> None:
        """Add an analysis result."""
        self.analyses[result.analysis_type.value] = result

    def add_argument(self, argument: ArgumentPrep) -> None:
        """Add a new argument to prep."""
        self.arguments.append(argument)

    def log_research(self, entry: ResearchEntry) -> None:
        """Log a research session."""
        self.research_log.append(entry)

    def get_summary(self) -> dict:
        """Get a summary of current prep state for the agent."""
        return {
            "resolution": self.resolution,
            "side": self.side.value,
            "analyses_completed": list(self.analyses.keys()),
            "num_arguments": len(self.arguments),
            "total_cards": sum(len(arg.card_ids) for arg in self.arguments),
            "research_sessions": len(self.research_log),
            "arguments_by_purpose": {
                "support": len([a for a in self.arguments if a.purpose == SectionType.SUPPORT]),
                "answer": len([a for a in self.arguments if a.purpose == SectionType.ANSWER]),
                "extension": len([a for a in self.arguments if a.purpose == SectionType.EXTENSION]),
                "impact": len([a for a in self.arguments if a.purpose == SectionType.IMPACT]),
            },
        }
