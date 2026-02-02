"""Pydantic models for debate round state and content."""

from enum import Enum
from typing import Optional

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


class Card(BaseModel):
    """An evidence card with full citation, credentials, and bolded sections.

    Like real policy debate evidence cards, includes:
    - Full author credentials
    - Complete citation information
    - Direct quote with bolded sections (using **text** for what to read aloud)
    - Source URL for verification
    """

    tag: str = Field(description="Brief label summarizing the card's argument")
    author: str = Field(description="Author's full name (e.g., 'John Smith')")
    credentials: str = Field(
        description="Author's qualifications (e.g., 'Professor of Economics at MIT')"
    )
    year: str = Field(description="Publication year")
    source: str = Field(description="Publication name (e.g., 'New York Times', 'Nature')")
    url: Optional[str] = Field(default=None, description="URL to source for verification")
    text: str = Field(
        description="Full quoted text with **bolded sections** marking what should be read aloud"
    )

    def format_for_reading(self) -> str:
        """Format the card for reading aloud in a speech (only bolded portions)."""
        import re

        # Extract only bolded text
        bolded_parts = re.findall(r'\*\*(.+?)\*\*', self.text)
        reading_text = ' '.join(bolded_parts)

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


class EvidenceBucket(BaseModel):
    """A collection of evidence cards organized by argument/topic.

    Like policy debaters' tubs of evidence, stores cards for specific arguments
    with a table of contents for quick reference.
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
    team_a_case: Optional[Case] = None
    team_b_case: Optional[Case] = None
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
