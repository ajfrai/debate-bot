"""
Synthesis Agent

Enables bidirectional flow between evidence and arguments:
1. Evidence → Arguments (synthesize arguments from evidence)
2. Arguments → Evidence (identify evidence needs)
3. Iterative refinement (identify gaps and iterate)
"""

import anthropic
import os
from typing import List, Optional, Dict
from dataclasses import dataclass

from debate.models import DebateFile, Case, Contention, Side, Card


@dataclass
class EvidenceTheme:
    """A theme or topic identified in evidence"""
    name: str  # Theme name (e.g., "Economic impacts on creators")
    card_ids: List[str]  # Card IDs supporting this theme
    strength: str  # weak | moderate | strong
    suggested_claim: str  # What this theme could prove


@dataclass
class ArgumentGap:
    """Identifies a gap between arguments and evidence"""
    gap_type: str  # missing_evidence | unused_evidence | weak_support
    description: str  # Human-readable description
    contention_title: Optional[str] = None  # Which contention (if applicable)
    suggested_action: str = ""  # What to do about it
    card_ids: List[str] = None  # Related cards (if any)

    def __post_init__(self):
        if self.card_ids is None:
            self.card_ids = []


@dataclass
class EvidenceAnalysis:
    """Analysis of evidence and argument-evidence alignment"""
    themes: List[EvidenceTheme]  # Themes identified in evidence
    gaps: List[ArgumentGap]  # Gaps in argument-evidence alignment
    coverage_summary: str  # Overall summary of evidence coverage
    synthesized_contentions: List[Contention]  # Contentions built from evidence


class SynthesisAgent:
    """Agent for bidirectional evidence-argument synthesis"""

    def __init__(self, resolution: str, side: Side):
        """
        Initialize synthesis agent

        Args:
            resolution: The debate resolution
            side: Which side (PRO or CON)
        """
        self.resolution = resolution
        self.side = side
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    def analyze_evidence(
        self,
        debate_file: DebateFile,
        stream: bool = False
    ) -> EvidenceAnalysis:
        """
        Analyze available evidence to identify themes and argument opportunities

        Args:
            debate_file: DebateFile containing evidence cards
            stream: Whether to stream the response

        Returns:
            EvidenceAnalysis with themes and synthesized arguments
        """
        # Get evidence for this side
        sections = debate_file.get_sections_for_side(self.side)

        if not sections:
            return EvidenceAnalysis(
                themes=[],
                gaps=[],
                coverage_summary="No evidence available for this side",
                synthesized_contentions=[]
            )

        # Format evidence for analysis
        evidence_text = self._format_evidence_for_analysis(debate_file, sections)

        # Build prompt
        prompt = self._build_evidence_analysis_prompt(evidence_text)

        # Call Claude
        if stream:
            print("Analyzing evidence for argument opportunities...\n")

        response_text = ""
        with self.client.messages.stream(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        ) as stream_response:
            for text in stream_response.text_stream:
                if stream:
                    print(text, end="", flush=True)
                response_text += text

        if stream:
            print("\n")

        # Parse response
        return self._parse_evidence_analysis(response_text)

    def identify_gaps(
        self,
        case: Case,
        debate_file: Optional[DebateFile],
        stream: bool = False
    ) -> List[ArgumentGap]:
        """
        Identify gaps between arguments and evidence

        Args:
            case: The debate case to analyze
            debate_file: Optional DebateFile with available evidence
            stream: Whether to stream the analysis

        Returns:
            List of ArgumentGap objects
        """
        gaps = []

        # Format case
        case_text = case.format()

        # Format evidence if available
        evidence_text = ""
        if debate_file:
            sections = debate_file.get_sections_for_side(self.side)
            evidence_text = self._format_evidence_for_analysis(debate_file, sections)

        # Build prompt
        prompt = self._build_gap_analysis_prompt(case_text, evidence_text)

        # Call Claude
        if stream:
            print("Identifying gaps between arguments and evidence...\n")

        response_text = ""
        with self.client.messages.stream(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        ) as stream_response:
            for text in stream_response.text_stream:
                if stream:
                    print(text, end="", flush=True)
                response_text += text

        if stream:
            print("\n")

        # Parse gaps from response
        gaps = self._parse_gap_analysis(response_text)

        return gaps

    def synthesize_arguments_from_evidence(
        self,
        debate_file: DebateFile,
        num_contentions: int = 3,
        stream: bool = False
    ) -> List[Contention]:
        """
        Generate argument contentions directly from evidence

        Args:
            debate_file: DebateFile with evidence to build from
            num_contentions: Number of contentions to generate
            stream: Whether to stream the response

        Returns:
            List of Contention objects built from evidence
        """
        # First analyze evidence to identify themes
        analysis = self.analyze_evidence(debate_file, stream=stream)

        # Use synthesized contentions from analysis
        return analysis.synthesized_contentions[:num_contentions]

    def _format_evidence_for_analysis(
        self,
        debate_file: DebateFile,
        sections: List
    ) -> str:
        """Format evidence sections for analysis prompt"""
        output = []

        for section in sections:
            output.append(f"\n## {section.get_heading()}")
            output.append(f"Section Type: {section.section_type}")
            output.append("")

            for card_id in section.card_ids:
                card = debate_file.get_card(card_id)
                if card:
                    output.append(f"### [{card_id}] {card.tag}")
                    output.append(f"**Author:** {card.author}, {card.credentials}")
                    output.append(f"**Year:** {card.year}")
                    output.append(f"**Source:** {card.source}")
                    if card.purpose:
                        output.append(f"**Purpose:** {card.purpose}")
                    output.append("")
                    output.append(card.text)
                    output.append("")

        return "\n".join(output)

    def _build_evidence_analysis_prompt(self, evidence_text: str) -> str:
        """Build prompt for analyzing evidence to find argument themes"""
        return f"""You are a Public Forum debate expert analyzing evidence to identify argument opportunities.

Resolution: {self.resolution}
Side: {self.side.value.upper()}

## Your Task

Analyze the evidence below and:
1. Identify major themes/topics covered by the evidence
2. For each theme, assess the strength of evidence support (weak/moderate/strong)
3. Synthesize 2-3 strong contentions directly from the evidence
4. Ensure contentions are built around what the evidence actually proves

## Evidence Available

{evidence_text}

## Output Format

Please respond with:

### THEMES IDENTIFIED

For each theme:
- Theme: [theme name]
- Cards: [list card IDs]
- Strength: [weak|moderate|strong]
- Could Prove: [what claim this evidence supports]

### SYNTHESIZED CONTENTIONS

For each contention (2-3 total):

**Contention [N]: [Title]**

[200-500 word argument that:
- Is built directly from available evidence
- Cites specific cards by ID using format: [CardID] proves that...
- Weaves evidence naturally into the argument
- Uses bolded warrants from the cards
- Includes logical reasoning that connects evidence to the resolution]

### COVERAGE SUMMARY

[2-3 sentences summarizing what arguments the current evidence supports well vs. what gaps exist]
"""

    def _build_gap_analysis_prompt(self, case_text: str, evidence_text: str) -> str:
        """Build prompt for identifying gaps between arguments and evidence"""
        has_evidence = bool(evidence_text.strip())

        evidence_section = f"""
## Available Evidence

{evidence_text}
""" if has_evidence else """
## Available Evidence

No evidence file available. Analyze the case for claims that need evidence support.
"""

        return f"""You are a Public Forum debate coach reviewing a case for evidence quality.

Resolution: {self.resolution}
Side: {self.side.value.upper()}

## Your Task

Analyze the case below and identify gaps between arguments and evidence:
1. Arguments that cite evidence not in the evidence file (CRITICAL ERROR)
2. Arguments making factual claims without evidence support (needs research)
3. Available evidence that isn't used in arguments (missed opportunity)

## Case to Analyze

{case_text}

{evidence_section}

## Output Format

Please identify gaps in this format:

### MISSING EVIDENCE ERRORS

[List any citations in the case that don't match available evidence]
- Contention: [title]
- Problem: [what citation is unbacked]
- Action: Research evidence for this claim

### UNSUPPORTED CLAIMS

[List factual claims that need evidence]
- Contention: [title]
- Claim: [specific claim needing evidence]
- Action: Research evidence to support this

### UNUSED EVIDENCE

[List evidence that could strengthen arguments but isn't used]
- Card: [card ID and tag]
- Opportunity: [what argument this could support]
- Action: Revise contention to incorporate this evidence

### OVERALL ASSESSMENT

[2-3 sentences on the quality of argument-evidence alignment]
"""

    def _parse_evidence_analysis(self, response_text: str) -> EvidenceAnalysis:
        """Parse the evidence analysis response from Claude"""
        # This is a simplified parser - you could make it more robust
        themes = []
        contentions = []
        coverage_summary = ""

        # Extract themes section
        if "### THEMES IDENTIFIED" in response_text:
            themes_section = response_text.split("### THEMES IDENTIFIED")[1]
            if "### SYNTHESIZED CONTENTIONS" in themes_section:
                themes_section = themes_section.split("### SYNTHESIZED CONTENTIONS")[0]

            # Parse themes (basic parsing - could be enhanced)
            # For now, create a simple theme
            themes.append(EvidenceTheme(
                name="Evidence-based arguments",
                card_ids=[],
                strength="moderate",
                suggested_claim="Multiple claims supported by available evidence"
            ))

        # Extract contentions section
        if "### SYNTHESIZED CONTENTIONS" in response_text:
            contentions_section = response_text.split("### SYNTHESIZED CONTENTIONS")[1]
            if "### COVERAGE SUMMARY" in contentions_section:
                coverage_summary = contentions_section.split("### COVERAGE SUMMARY")[1].strip()
                contentions_section = contentions_section.split("### COVERAGE SUMMARY")[0]

            # Parse contentions
            import re
            contention_pattern = r'\*\*Contention \d+: ([^\*]+)\*\*\s+(.*?)(?=\*\*Contention|\Z)'
            matches = re.findall(contention_pattern, contentions_section, re.DOTALL)

            for title, content in matches:
                contentions.append(Contention(
                    title=title.strip(),
                    content=content.strip()
                ))

        return EvidenceAnalysis(
            themes=themes,
            gaps=[],  # Filled in by identify_gaps()
            coverage_summary=coverage_summary,
            synthesized_contentions=contentions
        )

    def _parse_gap_analysis(self, response_text: str) -> List[ArgumentGap]:
        """Parse gap analysis response from Claude"""
        gaps = []

        # Parse missing evidence errors
        if "### MISSING EVIDENCE ERRORS" in response_text:
            section = response_text.split("### MISSING EVIDENCE ERRORS")[1]
            if "###" in section:
                section = section.split("###")[0]

            # Look for bullet points
            lines = section.strip().split("\n")
            current_gap = None

            for line in lines:
                line = line.strip()
                if line.startswith("- Contention:"):
                    if current_gap:
                        gaps.append(current_gap)
                    current_gap = ArgumentGap(
                        gap_type="missing_evidence",
                        description="",
                        contention_title=line.replace("- Contention:", "").strip()
                    )
                elif line.startswith("- Problem:") and current_gap:
                    current_gap.description = line.replace("- Problem:", "").strip()
                elif line.startswith("- Action:") and current_gap:
                    current_gap.suggested_action = line.replace("- Action:", "").strip()

            if current_gap:
                gaps.append(current_gap)

        # Parse unsupported claims
        if "### UNSUPPORTED CLAIMS" in response_text:
            section = response_text.split("### UNSUPPORTED CLAIMS")[1]
            if "###" in section:
                section = section.split("###")[0]

            lines = section.strip().split("\n")
            current_gap = None

            for line in lines:
                line = line.strip()
                if line.startswith("- Contention:"):
                    if current_gap:
                        gaps.append(current_gap)
                    current_gap = ArgumentGap(
                        gap_type="weak_support",
                        description="",
                        contention_title=line.replace("- Contention:", "").strip()
                    )
                elif line.startswith("- Claim:") and current_gap:
                    current_gap.description = line.replace("- Claim:", "").strip()
                elif line.startswith("- Action:") and current_gap:
                    current_gap.suggested_action = line.replace("- Action:", "").strip()

            if current_gap:
                gaps.append(current_gap)

        # Parse unused evidence
        if "### UNUSED EVIDENCE" in response_text:
            section = response_text.split("### UNUSED EVIDENCE")[1]
            if "###" in section:
                section = section.split("###")[0]

            lines = section.strip().split("\n")
            current_gap = None

            for line in lines:
                line = line.strip()
                if line.startswith("- Card:"):
                    if current_gap:
                        gaps.append(current_gap)
                    current_gap = ArgumentGap(
                        gap_type="unused_evidence",
                        description="",
                    )
                    current_gap.description = line.replace("- Card:", "").strip()
                elif line.startswith("- Opportunity:") and current_gap:
                    current_gap.suggested_action = line.replace("- Opportunity:", "").strip()

            if current_gap:
                gaps.append(current_gap)

        return gaps


def analyze_evidence_for_arguments(
    debate_file: DebateFile,
    resolution: str,
    side: Side,
    stream: bool = False
) -> EvidenceAnalysis:
    """
    Convenience function to analyze evidence and synthesize arguments

    Args:
        debate_file: DebateFile with evidence
        resolution: The debate resolution
        side: Which side
        stream: Whether to stream output

    Returns:
        EvidenceAnalysis with themes and synthesized contentions
    """
    agent = SynthesisAgent(resolution=resolution, side=side)
    return agent.analyze_evidence(debate_file, stream=stream)


def identify_case_gaps(
    case: Case,
    debate_file: Optional[DebateFile],
    resolution: str,
    side: Side,
    stream: bool = False
) -> List[ArgumentGap]:
    """
    Convenience function to identify gaps between case and evidence

    Args:
        case: The debate case
        debate_file: Optional evidence file
        resolution: The debate resolution
        side: Which side
        stream: Whether to stream output

    Returns:
        List of ArgumentGap objects
    """
    agent = SynthesisAgent(resolution=resolution, side=side)
    return agent.identify_gaps(case, debate_file, stream=stream)
