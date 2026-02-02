"""AI judge for evaluating debate rounds and providing decisions."""

import json
from pathlib import Path

import anthropic

from debate.models import JudgeDecision, RoundState, Side


def load_prompt_template(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompts_dir = Path(__file__).parent / "prompts"
    template_path = prompts_dir / f"{name}.md"
    return template_path.read_text()


class JudgeAgent:
    """An AI judge that evaluates debate rounds using standard judging criteria.

    Evaluates based on:
    - Argument strength and warranting
    - Evidence quality and application
    - Refutation and clash
    - Impact calculus
    - Strategic choices (collapse, extensions, drops)
    """

    def __init__(self):
        """Initialize the judge agent."""
        self.client = anthropic.Anthropic()

    def judge_round(
        self,
        round_state: RoundState,
        stream: bool = True,
    ) -> JudgeDecision:
        """Judge a completed debate round and provide a decision.

        Args:
            round_state: The completed round with all speeches
            stream: Whether to stream the decision as it's generated

        Returns:
            JudgeDecision with winner, voting issues, RFD, and feedback
        """
        template = load_prompt_template("judge_decision")

        # Format the round for judging
        round_context = self._format_round_for_judging(round_state)

        prompt = template.format(
            resolution=round_state.resolution,
            team_a_side=round_state.team_a_side.value.upper(),
            team_b_side=round_state.team_b_side.value.upper(),
            round_context=round_context,
        )

        if stream:
            response_text = ""
            print("\n" + "=" * 60)
            print("JUDGE'S DECISION")
            print("=" * 60 + "\n")
            with self.client.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}],
            ) as stream_response:
                for text in stream_response.text_stream:
                    print(text, end="", flush=True)
                    response_text += text
            print("\n")
        else:
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = message.content[0].text

        # Parse the decision
        return self._parse_decision(response_text, round_state)

    def _format_round_for_judging(self, round_state: RoundState) -> str:
        """Format the complete round transcript for the judge."""
        lines = []

        # Opening cases
        lines.append("## OPENING CASES\n")

        if round_state.team_a_case:
            lines.append(f"### Team A ({round_state.team_a_side.value.upper()}) Case\n")
            lines.append(round_state.team_a_case.format())
            lines.append("")

        if round_state.team_b_case:
            lines.append(f"### Team B ({round_state.team_b_side.value.upper()}) Case\n")
            lines.append(round_state.team_b_case.format())
            lines.append("")

        # All speeches
        if round_state.speeches:
            lines.append("## SPEECHES\n")
            for i, speech in enumerate(round_state.speeches, 1):
                team = "Team A" if speech.side == round_state.team_a_side else "Team B"
                side = speech.side.value.upper()
                lines.append(f"### Speech {i}: {team} ({side}) - {speech.speech_type.value.title()}\n")
                lines.append(speech.content)
                lines.append("")

        # Crossfires
        if round_state.crossfires:
            lines.append("## CROSSFIRES\n")
            for i, cf in enumerate(round_state.crossfires, 1):
                lines.append(f"### Crossfire {i}: {cf.crossfire_type.title()}\n")
                for j, exchange in enumerate(cf.exchanges, 1):
                    q_team = "Team A" if exchange.questioner_side == round_state.team_a_side else "Team B"
                    a_team = "Team B" if exchange.questioner_side == round_state.team_a_side else "Team A"
                    lines.append(f"**Q{j} ({q_team}):** {exchange.question}")
                    lines.append(f"**A{j} ({a_team}):** {exchange.answer}")
                    lines.append("")

        return "\n".join(lines)

    def _parse_decision(self, response_text: str, round_state: RoundState) -> JudgeDecision:
        """Parse the judge's decision from the response."""
        # Try to extract JSON
        json_str = self._extract_json_from_text(response_text)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse judge decision JSON: {e}") from e

        # Parse winner
        winner_str = data.get("winner", "").lower()
        if "team a" in winner_str or "a" == winner_str:
            winner = round_state.team_a_side
            winning_team = "Team A"
        elif "team b" in winner_str or "b" == winner_str:
            winner = round_state.team_b_side
            winning_team = "Team B"
        else:
            raise ValueError(f"Could not determine winner from: {winner_str}")

        return JudgeDecision(
            winner=winner,
            winning_team=winning_team,
            voting_issues=data.get("voting_issues", []),
            rfd=data.get("rfd", ""),
            feedback=data.get("feedback", []),
        )

    def _extract_json_from_text(self, text: str) -> str:
        """Extract JSON object from text, handling markdown code blocks."""
        import re

        # Try to extract JSON from markdown code block first
        code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if code_block_match:
            potential_json = code_block_match.group(1).strip()
            if potential_json.startswith("{"):
                return potential_json

        # Fall back to finding raw JSON by matching balanced braces
        json_start = text.find("{")
        if json_start == -1:
            raise ValueError("No JSON found in response")

        depth = 0
        in_string = False
        escape_next = False
        json_end = json_start

        for i, char in enumerate(text[json_start:], start=json_start):
            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    json_end = i + 1
                    break

        if depth != 0:
            raise ValueError("Unbalanced JSON braces in response")

        return text[json_start:json_end]
