"""
Evidence Validator

Validates that speeches only cite evidence backed by evidence files.

Acceptable:
- Arguments using logic/reasoning/common knowledge (no evidence)
- Arguments using quoted evidence with backing in evidence files

Borderline:
- Arguments using paraphrased evidence with backing in evidence files

Unacceptable:
- Citing evidence not backed in evidence files
"""

import re
from dataclasses import dataclass

from debate.models import Card, DebateFile


@dataclass
class CitationMatch:
    """Represents a citation found in speech text"""

    text: str  # Full citation text (e.g., "[Author Year] explains, ...")
    author_last: str  # Last name extracted
    year: str  # Year extracted
    quoted_text: str | None  # Any quoted portion that follows
    position: int  # Character position in speech
    matched_card: Card | None = None  # Matched card from debate file


@dataclass
class ValidationResult:
    """Results from validating a speech"""

    is_valid: bool
    citations: list[CitationMatch]
    errors: list[str]  # Unacceptable: citations without backing
    warnings: list[str]  # Borderline: paraphrased without quotes
    info: list[str]  # General information


class EvidenceValidator:
    """Validates evidence citations in speeches"""

    # Patterns to detect evidence citations
    CITATION_PATTERNS = [
        # [Author Year] explains/found/argues/states that...
        r"\[([A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+)?)\s+(\d{4})\]\s+(?:explains?|found|argues?|states?|says?|claims?|reports?|shows?|demonstrates?|concludes?)",
        # Author Year explains/found/argues (without brackets)
        r"(?:^|[.\s])([A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+)?)\s+(\d{4})\s+(?:explains?|found|argues?|states?|says?|claims?|reports?|shows?|demonstrates?|concludes?)",
        # According to Author Year,
        r"According to ([A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+)?)\s+(\d{4})",
        # Author (Year) format
        r"([A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+)?)\s+\((\d{4})\)",
    ]

    # Pattern to extract quoted text following a citation
    QUOTE_PATTERN = r'[,\s]+["\u201c]([^"\u201d]+)["\u201d]'

    def __init__(self, debate_file: DebateFile | None = None):
        """
        Initialize validator with optional debate file

        Args:
            debate_file: DebateFile containing evidence cards to validate against
        """
        self.debate_file = debate_file

    def validate_speech(self, speech_text: str, side: str) -> ValidationResult:
        """
        Validate a speech against available evidence

        Args:
            speech_text: The speech text to validate
            side: "PRO" or "CON" - which side is speaking

        Returns:
            ValidationResult with validation status and details
        """
        errors = []
        warnings = []
        info = []
        citations = self._extract_citations(speech_text)

        # If no debate file provided, we can't validate evidence
        if not self.debate_file:
            if citations:
                warnings.append(f"Found {len(citations)} citation(s) but no evidence file available for validation")
            return ValidationResult(
                is_valid=True,  # Can't invalidate without evidence file
                citations=citations,
                errors=errors,
                warnings=warnings,
                info=info,
            )

        # Match citations against available cards
        available_cards = self._get_cards_for_side(side)

        for citation in citations:
            matched_card = self._find_matching_card(citation, available_cards)

            if matched_card:
                citation.matched_card = matched_card

                # Check if quoted text matches bolded portions
                if citation.quoted_text:
                    if self._verify_quote_match(citation.quoted_text, matched_card):
                        info.append(
                            f"✓ Citation '{citation.author_last} {citation.year}' matches evidence and quote verified"
                        )
                    else:
                        warnings.append(
                            f"⚠ Citation '{citation.author_last} {citation.year}' "
                            f"has quoted text that doesn't match evidence bolded portions. "
                            f"Quote may be paraphrased."
                        )
                else:
                    # Citation without quotes - could be paraphrased
                    warnings.append(
                        f"⚠ Citation '{citation.author_last} {citation.year}' "
                        f"found in evidence but no quoted text provided. "
                        f"Consider using direct quotes from bolded portions."
                    )
            else:
                # UNACCEPTABLE: Citation without backing
                errors.append(
                    f"✗ Citation '{citation.author_last} {citation.year}' "
                    f"not found in evidence file. This citation is not backed by evidence."
                )

        # Summary info
        if citations:
            info.append(f"Found {len(citations)} citation(s) in speech")
            matched_count = sum(1 for c in citations if c.matched_card)
            info.append(f"{matched_count}/{len(citations)} citation(s) matched to evidence")

        is_valid = len(errors) == 0

        return ValidationResult(is_valid=is_valid, citations=citations, errors=errors, warnings=warnings, info=info)

    def _extract_citations(self, text: str) -> list[CitationMatch]:
        """Extract all citations from speech text"""
        citations = []
        seen_positions = set()

        for pattern in self.CITATION_PATTERNS:
            for match in re.finditer(pattern, text, re.MULTILINE):
                position = match.start()

                # Skip if we already found a citation at this position
                if position in seen_positions:
                    continue

                seen_positions.add(position)

                author_last = match.group(1).strip()
                year = match.group(2).strip()

                # Extract any quoted text following the citation
                quoted_text = None
                remaining_text = text[match.end() :]
                quote_match = re.match(self.QUOTE_PATTERN, remaining_text)
                if quote_match:
                    quoted_text = quote_match.group(1).strip()

                citations.append(
                    CitationMatch(
                        text=match.group(0),
                        author_last=author_last,
                        year=year,
                        quoted_text=quoted_text,
                        position=position,
                    )
                )

        # Sort by position in text
        citations.sort(key=lambda c: c.position)
        return citations

    def _get_cards_for_side(self, side: str) -> list[Card]:
        """Get all cards available for the given side"""
        if not self.debate_file:
            return []

        sections = self.debate_file.get_sections_for_side(side)
        cards = []

        for section in sections:
            for card_id in section.card_ids:
                card = self.debate_file.get_card(card_id)
                if card:
                    cards.append(card)

        return cards

    def _find_matching_card(self, citation: CitationMatch, available_cards: list[Card]) -> Card | None:
        """
        Find a card that matches the citation

        Matches on:
        1. Author last name (case-insensitive)
        2. Year (exact match)
        """
        for card in available_cards:
            # Extract last name from card author (e.g., "Jane Smith, Professor" -> "Smith")
            card_author = card.author.split(",")[0].strip()  # Remove credentials
            card_last_names = card_author.split()[-1].lower()  # Get last name

            # Check for "and" in citations (e.g., "Smith and Jones")
            citation_last_lower = citation.author_last.lower()

            # Simple match on last name and year
            if card_last_names in citation_last_lower and card.year == citation.year:
                return card

            # Also check if citation last name is in card author
            if citation.author_last.lower() in card_author.lower() and card.year == citation.year:
                return card

        return None

    def _verify_quote_match(self, quoted_text: str, card: Card) -> bool:
        """
        Verify that quoted text appears in the card's bolded portions

        Args:
            quoted_text: The quoted text from the speech
            card: The evidence card to check against

        Returns:
            True if the quote matches bolded portions (with some flexibility)
        """
        # Extract bolded portions from card text
        bolded_pattern = r"\*\*([^*]+)\*\*"
        bolded_portions = re.findall(bolded_pattern, card.text)

        if not bolded_portions:
            # No bolded text, check against full card text
            return self._fuzzy_match(quoted_text, card.text)

        # Check if quoted text appears in any bolded portion
        for bolded in bolded_portions:
            if self._fuzzy_match(quoted_text, bolded):
                return True

        return False

    def _fuzzy_match(self, quote: str, source: str, threshold: float = 0.8) -> bool:
        """
        Check if quote approximately matches source text

        Uses simple word-overlap matching with threshold.
        More sophisticated matching (e.g., Levenshtein distance) could be added.

        Args:
            quote: The quoted text
            source: The source text to match against
            threshold: Minimum ratio of matching words (0.0 to 1.0)

        Returns:
            True if quote matches source above threshold
        """
        # Normalize text for comparison
        quote_words = set(re.findall(r"\b\w+\b", quote.lower()))
        source_words = set(re.findall(r"\b\w+\b", source.lower()))

        if not quote_words:
            return False

        # Calculate overlap
        matching_words = quote_words.intersection(source_words)
        overlap_ratio = len(matching_words) / len(quote_words)

        return overlap_ratio >= threshold


def validate_speech_evidence(speech_text: str, side: str, debate_file: DebateFile | None = None) -> ValidationResult:
    """
    Convenience function to validate a speech

    Args:
        speech_text: The speech text to validate
        side: "PRO" or "CON"
        debate_file: Optional DebateFile with evidence cards

    Returns:
        ValidationResult
    """
    validator = EvidenceValidator(debate_file)
    return validator.validate_speech(speech_text, side)
