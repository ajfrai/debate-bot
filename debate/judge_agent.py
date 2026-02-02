"""AI judge for evaluating debate rounds and providing decisions."""

from pathlib import Path

import anthropic

from debate.models import JudgeDecision, RoundState


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

        # Parse the decision from formatted text
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
        """Parse the judge's decision from formatted text."""
        import re

        # Extract winner
        decision_match = re.search(r"\*\*DECISION:\s*(Team [AB])\*\*", response_text, re.IGNORECASE)
        if not decision_match:
            raise ValueError("Could not find DECISION marker in response")

        winner_str = decision_match.group(1)
        if "Team A" in winner_str:
            winner = round_state.team_a_side
            winning_team = "Team A"
        elif "Team B" in winner_str:
            winner = round_state.team_b_side
            winning_team = "Team B"
        else:
            raise ValueError(f"Could not determine winner from: {winner_str}")

        # Extract voting issues (numbered list after VOTING ISSUES:)
        voting_issues = []
        voting_section = re.search(
            r"\*\*VOTING ISSUES:\*\*\s*(.*?)\s*\*\*REASON FOR DECISION:\*\*", response_text, re.DOTALL | re.IGNORECASE
        )
        if voting_section:
            issues_text = voting_section.group(1)
            # Extract numbered items
            issue_matches = re.findall(r"^\d+\.\s*(.+?)(?=^\d+\.|$)", issues_text, re.MULTILINE | re.DOTALL)
            voting_issues = [issue.strip() for issue in issue_matches]

        # Extract RFD
        rfd = ""
        rfd_match = re.search(
            r"\*\*REASON FOR DECISION:\*\*\s*(.*?)\s*\*\*FEEDBACK FOR TEAM", response_text, re.DOTALL | re.IGNORECASE
        )
        if rfd_match:
            rfd = rfd_match.group(1).strip()

        # Extract feedback
        feedback = []
        feedback_a = re.search(
            r"\*\*FEEDBACK FOR TEAM A:\*\*\s*(.*?)(?=\*\*FEEDBACK FOR TEAM B:|\Z)",
            response_text,
            re.DOTALL | re.IGNORECASE,
        )
        if feedback_a:
            feedback.append(f"Team A: {feedback_a.group(1).strip()}")

        feedback_b = re.search(r"\*\*FEEDBACK FOR TEAM B:\*\*\s*(.*?)(?=\Z)", response_text, re.DOTALL | re.IGNORECASE)
        if feedback_b:
            feedback.append(f"Team B: {feedback_b.group(1).strip()}")

        return JudgeDecision(
            winner=winner,
            winning_team=winning_team,
            voting_issues=voting_issues if voting_issues else ["(No voting issues extracted)"],
            rfd=rfd if rfd else "(No RFD extracted)",
            feedback=feedback if feedback else ["(No feedback extracted)"],
        )
