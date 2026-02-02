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
    """An evidence card with citation and content.

    Cards are formatted like real debate cards:
    [Author Last Name, Year] then the warrant text.
    """

    tag: str = Field(description="Brief label summarizing the card's argument")
    cite: str = Field(description="Citation in format: Author Last Name, Year")
    text: str = Field(description="The quoted/paraphrased evidence text")

    def format(self) -> str:
        """Format the card for display in a speech."""
        return f"[{self.cite}] {self.text}"


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
