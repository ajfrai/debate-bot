"""CutterAgent: Marks and cuts relevant text from staged search results."""

import os
import re
from typing import Any

import anthropic

from debate.config import Config
from debate.prep.base_agent import BaseAgent
from debate.prep.session import PrepSession


class CutterAgent(BaseAgent):
    """Cuts evidence cards from fetched article text.

    Responsibilities:
    - Read search results from SearchAgent
    - Identify relevant passages in article text
    - Cut cards using start/end phrase extraction (token efficient)
    - Stage cut cards for OrganizerAgent

    Token efficiency:
    - Sees full article text (input cheap)
    - Outputs ONLY cut specifications (~50 tokens per card)
    - Text extraction is programmatic
    """

    def __init__(self, session: PrepSession) -> None:
        super().__init__(session, poll_interval=2.0)
        self._client: anthropic.Anthropic | None = None

    @property
    def name(self) -> str:
        return "cutter"

    def _get_client(self) -> anthropic.Anthropic:
        """Get or create Anthropic client."""
        if self._client is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not set")
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    async def check_for_work(self) -> list[Any]:
        """Check for pending search results."""
        return self.session.get_pending_results()

    async def process_item(self, result: dict[str, Any]) -> None:
        """Process a search result: cut cards from fetched articles."""
        result_id = result["id"]
        result_path = str(self.session.staging_dir / "search" / "results" / f"result_{result_id}.json")
        self.session.mark_processed("cutter", result_path)

        self.log("processing_result", {"result_id": result_id})

        # Get sources with content
        sources_with_content = [
            s for s in result.get("sources", []) if s.get("fetch_status") == "success" and s.get("full_text")
        ]

        if not sources_with_content:
            self.log("no_content", {"result_id": result_id})
            return

        # Generate cut specifications
        cuts = await self._generate_cuts(result, sources_with_content)

        if not cuts:
            self.log("no_cuts", {"result_id": result_id})
            return

        # Extract text and create cards
        for cut in cuts:
            card = self._extract_card(cut, sources_with_content, result)
            if card:
                self.session.write_card(card)
                self.state.items_created += 1
                self.log("cut_card", {"tag": card.get("tag", "")[:40]})

    async def _generate_cuts(self, result: dict[str, Any], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Generate cut specifications using LLM."""
        config = Config()
        model = config.get_agent_model("prep_cutter")

        # Format sources for prompt
        sources_text = ""
        for i, source in enumerate(sources):
            title = source.get("title", "Untitled")
            url = source.get("url", "")
            text = source.get("full_text", "")[:8000]  # Limit text length
            sources_text += f"\n\n=== SOURCE {i + 1}: {title} ===\nURL: {url}\n\n{text}"

        prompt = f"""You are cutting evidence cards for debate.

ARGUMENT TO SUPPORT: {result.get("argument", "")}
SEARCH INTENT: {result.get("search_intent", "")}
EVIDENCE TYPE: {result.get("evidence_type", "support")}

SOURCES:{sources_text}

Your task: Identify 1-3 quotable passages that support the argument.

For EACH card, output a JSON object with:
- source_index: Which source (1 or 2)
- start_phrase: First 5-8 words of the quote (exact match)
- end_phrase: Last 5-8 words of the quote (exact match)
- tag: What this evidence proves (5-12 words)
- author: Author name or organization
- year: Publication year (or "2024" if unclear)
- semantic_hint: Category for organizing similar cards

CRITICAL: Output ONLY the cut specifications. DO NOT copy the quote text.

Output as JSON array:
[
  {{
    "source_index": 1,
    "start_phrase": "According to the 2024 study",
    "end_phrase": "significant economic impact",
    "tag": "TikTok ban costs US economy $4 billion",
    "author": "Smith",
    "year": "2024",
    "semantic_hint": "economic costs"
  }}
]

Only output the JSON array, nothing else."""

        try:
            response = self._get_client().messages.create(
                model=model,
                max_tokens=512,  # Minimal output
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

            return json.loads(response_text)

        except Exception as e:
            self.log("cuts_error", {"error": str(e)[:100]})
            return []

    def _extract_card(
        self, cut: dict[str, Any], sources: list[dict[str, Any]], result: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Extract card text using cut specification."""
        source_index = cut.get("source_index", 1) - 1
        if source_index < 0 or source_index >= len(sources):
            return None

        source = sources[source_index]
        full_text = source.get("full_text", "")

        start_phrase = cut.get("start_phrase", "")
        end_phrase = cut.get("end_phrase", "")

        if not start_phrase or not end_phrase:
            return None

        # Find start position (case-insensitive, fuzzy)
        start_idx = self._fuzzy_find(full_text, start_phrase)
        if start_idx == -1:
            return None

        # Find end position after start
        end_idx = self._fuzzy_find(full_text[start_idx:], end_phrase)
        if end_idx == -1:
            return None

        end_idx = start_idx + end_idx + len(end_phrase)

        # Extract text
        extracted_text = full_text[start_idx:end_idx].strip()

        if len(extracted_text) < 50:  # Too short
            return None

        if len(extracted_text) > 2000:  # Too long, truncate
            extracted_text = extracted_text[:2000] + "..."

        return {
            "result_id": result.get("id", ""),
            "task_id": result.get("task_id", ""),
            "tag": cut.get("tag", ""),
            "author": cut.get("author", "Unknown"),
            "credentials": "",  # Will be filled by organizer if needed
            "year": cut.get("year", "2024"),
            "source_name": source.get("title", ""),
            "url": source.get("url", ""),
            "text": extracted_text,
            "semantic_hint": cut.get("semantic_hint", ""),
            "argument": result.get("argument", ""),
            "evidence_type": result.get("evidence_type", "support"),
        }

    def _fuzzy_find(self, text: str, phrase: str) -> int:
        """Find phrase in text with fuzzy matching."""
        # Normalize both
        text_lower = text.lower()
        phrase_lower = phrase.lower().strip()

        # Try exact match first
        idx = text_lower.find(phrase_lower)
        if idx != -1:
            return idx

        # Try with whitespace normalization
        text_normalized = re.sub(r"\s+", " ", text_lower)
        phrase_normalized = re.sub(r"\s+", " ", phrase_lower)

        idx = text_normalized.find(phrase_normalized)
        if idx != -1:
            # Map back to original position (approximate)
            return idx

        # Try matching just key words (fallback)
        words = phrase_lower.split()
        if len(words) >= 3:
            # Match first 3 consecutive words
            pattern = r"\b" + r"\s+".join(re.escape(w) for w in words[:3])
            match = re.search(pattern, text_lower)
            if match:
                return match.start()

        return -1
