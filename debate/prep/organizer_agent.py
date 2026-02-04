"""OrganizerAgent: Places cut cards into strategic briefs."""

import os
from typing import Any

import anthropic

from debate.config import Config
from debate.prep.base_agent import BaseAgent
from debate.prep.session import PrepSession


class OrganizerAgent(BaseAgent):
    """Organizes cut cards into strategic briefs and provides feedback.

    Responsibilities:
    - Read cut cards from CutterAgent
    - Organize cards into brief JSON structure
    - Group semantically similar cards
    - Identify gaps and opportunities
    - Write feedback for StrategyAgent

    Output:
    - brief.json: Structured brief that renders to markdown
    - feedback/: Gap and opportunity notifications
    """

    def __init__(self, session: PrepSession) -> None:
        super().__init__(session, poll_interval=2.0)
        self._client: anthropic.Anthropic | None = None
        self._cards_since_analysis: int = 0
        self._analysis_threshold: int = 3  # Analyze after every N cards

    @property
    def name(self) -> str:
        return "organizer"

    def _get_client(self) -> anthropic.Anthropic:
        """Get or create Anthropic client."""
        if self._client is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not set")
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    async def check_for_work(self) -> list[Any]:
        """Check for pending cut cards."""
        return self.session.get_pending_cards()

    async def process_item(self, card: dict[str, Any]) -> None:
        """Process a cut card: place in brief, potentially generate feedback."""
        card_id = card["id"]
        card_path = str(self.session.staging_dir / "cutter" / "cards" / f"card_{card_id}.json")
        self.session.mark_processed("organizer", card_path)

        self.log("processing_card", {"card_id": card_id, "tag": card.get("tag", "")[:40]})

        # Place card in brief
        await self._place_card(card)
        self.state.items_created += 1

        # Track for periodic analysis
        self._cards_since_analysis += 1

        # Periodically analyze for gaps/opportunities
        if self._cards_since_analysis >= self._analysis_threshold:
            await self._analyze_brief()
            self._cards_since_analysis = 0

    async def _place_card(self, card: dict[str, Any]) -> None:
        """Place a card in the brief structure."""
        brief = self.session.read_brief()

        # Determine placement
        argument = card.get("argument", "General")
        semantic_hint = card.get("semantic_hint", "")
        evidence_type = card.get("evidence_type", "support")

        # Use evidence_type to determine top-level category
        if evidence_type == "answer":
            category = "answers"
        else:
            category = "arguments"

        # Get or create argument entry
        if argument not in brief[category]:
            brief[category][argument] = {
                "name": argument,
                "semantic_groups": {},
            }

        arg_entry = brief[category][argument]

        # Get or create semantic group
        group_key = semantic_hint if semantic_hint else "general"
        if group_key not in arg_entry["semantic_groups"]:
            arg_entry["semantic_groups"][group_key] = {
                "claim": semantic_hint or argument,
                "card_ids": [],
                "cards": [],
            }

        group = arg_entry["semantic_groups"][group_key]

        # Add card to group
        card_entry = {
            "id": card["id"],
            "tag": card.get("tag", ""),
            "author": card.get("author", ""),
            "year": card.get("year", ""),
            "source_name": card.get("source_name", ""),
            "url": card.get("url", ""),
            "text": card.get("text", ""),
        }

        group["cards"].append(card_entry)
        group["card_ids"].append(card["id"])

        # Save updated brief
        self.session.write_brief(brief)

        self.log(
            "placed_card",
            {
                "card_id": card["id"],
                "argument": argument[:30],
                "group": group_key[:30],
            },
        )

    async def _analyze_brief(self) -> None:
        """Analyze brief for gaps and opportunities."""
        config = Config()
        model = config.get_agent_model("prep_organizer")

        brief = self.session.read_brief()

        # Format brief for analysis
        brief_summary = self._format_brief_summary(brief)

        prompt = f"""Analyze this debate prep brief for gaps and opportunities.

Resolution: {self.session.resolution}
Side: {self.session.side.value.upper()}

CURRENT BRIEF:
{brief_summary}

Identify:
1. GAPS: Arguments that need more evidence
2. OPPORTUNITIES: New arguments suggested by existing evidence
3. LINK CHAINS: Impact scenarios that need connecting evidence

Output JSON array of feedback items:
[
  {{
    "type": "gap",
    "message": "Brief description of the gap",
    "suggested_intent": "What to search for"
  }},
  {{
    "type": "opportunity",
    "message": "New argument to explore",
    "suggested_intent": "What evidence would support it"
  }},
  {{
    "type": "link_chain",
    "message": "Impact scenario to develop",
    "suggested_intent": "What connecting evidence needed"
  }}
]

If the brief is well-covered, output an empty array: []
Only output the JSON array."""

        try:
            response = self._get_client().messages.create(
                model=model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = "[]"
            if response.content:
                first_block = response.content[0]
                if hasattr(first_block, "text"):
                    response_text = first_block.text

            # Parse JSON
            import json

            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()

            feedback_items = json.loads(response_text)

            # Write feedback
            for item in feedback_items[:2]:  # Limit to 2 feedback items per analysis
                self.session.write_feedback(item)
                self.log("generated_feedback", {"type": item.get("type", "")})

        except Exception as e:
            self.log("analysis_error", {"error": str(e)[:100]})

    def _format_brief_summary(self, brief: dict[str, Any]) -> str:
        """Format brief for LLM analysis."""
        lines = []

        for category in ["arguments", "answers"]:
            if category not in brief or not brief[category]:
                continue

            lines.append(f"\n## {category.upper()}")

            for arg_name, arg_data in brief[category].items():
                lines.append(f"\n### {arg_name}")

                for group_key, group_data in arg_data.get("semantic_groups", {}).items():
                    card_count = len(group_data.get("cards", []))
                    lines.append(f"  - {group_key}: {card_count} cards")

                    # Show card tags
                    for card in group_data.get("cards", [])[:2]:
                        lines.append(f"    * {card.get('tag', '')[:50]}")

        return "\n".join(lines) if lines else "(Empty brief)"
