"""Round controller for managing debate flow and speech order."""

from typing import Optional

from debate.debate_agent import DebateAgent
from debate.evidence_storage import load_debate_file
from debate.evidence_validator import validate_speech_evidence
from debate.judge_agent import JudgeAgent
from debate.models import (
    Case,
    Crossfire,
    CrossfireExchange,
    DebateFile,
    JudgeDecision,
    RoundState,
    Side,
    Speech,
    SpeechType,
)


# PF Speech Order (from CLAUDE.md)
SPEECH_ORDER = [
    # (team, speaker_number, speech_type, time_seconds)
    ("A", 1, SpeechType.CONSTRUCTIVE, 240),  # 4 min
    ("B", 1, SpeechType.CONSTRUCTIVE, 240),  # 4 min
    # Crossfire 1
    ("A", 2, SpeechType.REBUTTAL, 240),  # 4 min
    ("B", 2, SpeechType.REBUTTAL, 240),  # 4 min
    # Crossfire 2
    ("A", 1, SpeechType.SUMMARY, 180),  # 3 min
    ("B", 1, SpeechType.SUMMARY, 180),  # 3 min
    # Crossfire 3 (Grand)
    ("A", 2, SpeechType.FINAL_FOCUS, 120),  # 2 min
    ("B", 2, SpeechType.FINAL_FOCUS, 120),  # 2 min
]


class RoundController:
    """Controls the flow of a complete debate round.

    Manages:
    - Speech order and timing
    - User input for their speeches
    - AI opponent speech generation
    - Crossfire exchanges
    - Judge decision at the end
    """

    def __init__(
        self,
        resolution: str,
        user_side: Side,
        user_case: Optional[Case] = None,
        ai_case: Optional[Case] = None,
    ):
        """Initialize a debate round.

        Args:
            resolution: The debate resolution
            user_side: Which side the user is debating (PRO or CON)
            user_case: Optional pre-generated case for the user
            ai_case: Optional pre-generated case for the AI
        """
        self.resolution = resolution
        self.user_side = user_side
        self.ai_side = user_side.opposite

        # Team A is always the user, Team B is always the AI
        self.round_state = RoundState(
            resolution=resolution,
            team_a_side=user_side,
            team_b_side=self.ai_side,
            team_a_case=user_case,
            team_b_case=ai_case,
        )

        # Initialize agents
        self.ai_agent = DebateAgent(side=self.ai_side, resolution=resolution)
        self.judge = JudgeAgent()

        # Load debate file if available
        self.debate_file = self._load_debate_file()

    def _load_debate_file(self) -> Optional[DebateFile]:
        """Try to load debate file for this resolution."""
        try:
            return load_debate_file(self.resolution)
        except Exception:
            return None

    def run_round(self) -> JudgeDecision:
        """Run a complete debate round and return the judge's decision.

        Returns:
            The judge's decision with winner and feedback
        """
        print("\n" + "=" * 60)
        print(f"DEBATE ROUND: {self.resolution}")
        print("=" * 60)
        print(f"You (Team A): {self.user_side.value.upper()}")
        print(f"AI (Team B): {self.ai_side.value.upper()}")
        print("=" * 60 + "\n")

        # Generate AI's case if not provided (user will deliver theirs as a speech)
        if not self.round_state.team_b_case:
            print("\nGenerating AI opponent's case...\n")
            self.round_state.team_b_case = self._generate_case(self.ai_side)

        # Run through speech order
        speech_index = 0
        for i, (team, speaker_num, speech_type, time_seconds) in enumerate(SPEECH_ORDER):
            # Check for crossfire before certain speeches
            if i == 2:  # After constructives
                self._run_crossfire("first", 180)
            elif i == 4:  # After rebuttals
                self._run_crossfire("second", 180)
            elif i == 6:  # After summaries
                self._run_crossfire("grand", 180)

            # Deliver speech
            if team == "A":  # User's turn
                self._user_speech(speech_type, speaker_num, time_seconds)
            else:  # AI's turn
                self._ai_speech(speech_type, speaker_num, time_seconds)

            speech_index += 1

        # Judge the round
        print("\n\nThe round is complete. The judge is now deliberating...\n")
        decision = self.judge.judge_round(self.round_state, stream=True)

        return decision

    def _generate_case(self, side: Side) -> Case:
        """Generate a case for the specified side."""
        if side == self.user_side:
            # For user, just use case generator directly
            from debate.case_generator import generate_case
            return generate_case(
                resolution=self.resolution,
                side=side,
                evidence_buckets=None,  # User can research evidence separately
                stream=True,
            )
        else:
            # For AI, use the debate agent
            return self.ai_agent.generate_case(
                debate_file=self.debate_file,
                stream=True,
            )

    def _user_speech(self, speech_type: SpeechType, speaker_num: int, time_seconds: int):
        """Prompt user to enter their speech."""
        print("\n" + "=" * 60)
        print(f"YOUR TURN: {speech_type.value.title()} ({time_seconds // 60} minutes)")
        print("=" * 60)
        print("Enter your speech below. When done, press Enter on an empty line.")
        print("(Press Ctrl+D or Ctrl+Z to finish)\n")

        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass

        content = "\n".join(lines)

        # Validate evidence citations in user's speech
        if self.debate_file:
            validation_result = validate_speech_evidence(
                speech_text=content,
                side=self.user_side.value.upper(),
                debate_file=self.debate_file
            )

            # Display validation results if there are errors or warnings
            if validation_result.errors or validation_result.warnings:
                print("\n" + "-" * 60)
                print("Evidence Validation Results:")
                print("-" * 60)

                for error in validation_result.errors:
                    print(f"ERROR: {error}")

                for warning in validation_result.warnings:
                    print(f"WARNING: {warning}")

                print("-" * 60)

                # If there are errors, warn the user
                if validation_result.errors:
                    print("\n⚠️  Your speech contains citations not backed by evidence files.")
                    print("This violates evidence requirements.")
                    response = input("\nContinue anyway? (y/n): ")
                    if response.lower() != 'y':
                        print("Speech cancelled. Please revise and try again.\n")
                        return self._user_speech(speech_type, speaker_num, time_seconds)

        speech = Speech(
            speech_type=speech_type,
            side=self.user_side,
            speaker_number=speaker_num,
            content=content,
            time_limit_seconds=time_seconds,
        )

        self.round_state.speeches.append(speech)
        print("\nSpeech recorded.\n")

    def _ai_speech(self, speech_type: SpeechType, speaker_num: int, time_seconds: int):
        """Generate AI opponent's speech."""
        print("\n" + "=" * 60)
        print(f"AI OPPONENT: {speech_type.value.title()} ({time_seconds // 60} minutes)")
        print("=" * 60 + "\n")

        # Determine the goal based on speech type
        goal = self._get_speech_goal(speech_type)

        # Generate the speech
        content = self.ai_agent.generate_speech(
            goal=goal,
            round_state=self.round_state,
            time_limit_seconds=time_seconds,
            debate_file=self.debate_file,
            stream=True,
        )

        # Validate evidence citations in the speech
        if self.debate_file:
            validation_result = validate_speech_evidence(
                speech_text=content,
                side=self.ai_side.value.upper(),
                debate_file=self.debate_file
            )

            # Display validation results if there are errors or warnings
            if validation_result.errors or validation_result.warnings:
                print("\n" + "-" * 60)
                print("Evidence Validation Results:")
                print("-" * 60)

                for error in validation_result.errors:
                    print(f"ERROR: {error}")

                for warning in validation_result.warnings:
                    print(f"WARNING: {warning}")

                print("-" * 60)

                # If there are errors, the speech cites unbacked evidence
                if validation_result.errors:
                    print("\n⚠️  The AI speech contains citations not backed by evidence files.")
                    print("This violates evidence requirements.\n")

        speech = Speech(
            speech_type=speech_type,
            side=self.ai_side,
            speaker_number=speaker_num,
            content=content,
            time_limit_seconds=time_seconds,
        )

        self.round_state.speeches.append(speech)
        print()

    def _get_speech_goal(self, speech_type: SpeechType) -> str:
        """Get the goal description for a speech type."""
        goals = {
            SpeechType.CONSTRUCTIVE: "Constructive: Present your opening case with 2-3 contentions. Establish your framework and key arguments.",
            SpeechType.REBUTTAL: "Rebuttal: Attack opponent's contentions with direct refutation. Defend your own case against their attacks. Focus on clash.",
            SpeechType.SUMMARY: "Summary: Extend your strongest 1-2 contentions from constructive. Rebuild these arguments after opponent's rebuttal. Respond to their rebuttal attacks. Begin impact comparison.",
            SpeechType.FINAL_FOCUS: "Final Focus: Crystallize the 1-2 key voting issues. Explain why you win these issues and why they outweigh everything else. Comparative weighing is crucial.",
        }
        return goals.get(speech_type, "Deliver a speech")

    def _run_crossfire(self, cf_type: str, time_seconds: int):
        """Run a crossfire exchange."""
        print("\n" + "=" * 60)
        print(f"CROSSFIRE: {cf_type.title()} ({time_seconds // 60} minutes)")
        print("=" * 60)
        print("Answer opponent questions and ask your own strategic questions.\n")

        crossfire = Crossfire(
            crossfire_type=cf_type,
            time_limit_seconds=time_seconds,
        )

        # Run 3-5 exchanges
        num_exchanges = 4
        for i in range(num_exchanges):
            # Alternate who asks first (user starts on odd exchanges)
            if i % 2 == 0:
                # User asks, AI answers
                print(f"\n--- Exchange {i + 1} ---")
                question = input("Your question to AI: ")
                print("\nAI's answer:")
                answer = self.ai_agent.answer_crossfire_question(
                    question=question,
                    round_state=self.round_state,
                    stream=True,
                )
                print()

                crossfire.exchanges.append(
                    CrossfireExchange(
                        questioner_side=self.user_side,
                        question=question,
                        answer=answer,
                    )
                )
            else:
                # AI asks, user answers
                print(f"\n--- Exchange {i + 1} ---")
                print("AI's question:")
                question = self.ai_agent.ask_crossfire_question(
                    round_state=self.round_state,
                    stream=True,
                )
                print()
                answer = input("Your answer: ")

                crossfire.exchanges.append(
                    CrossfireExchange(
                        questioner_side=self.ai_side,
                        question=question,
                        answer=answer,
                    )
                )

        self.round_state.crossfires.append(crossfire)
        print("\nCrossfire complete.\n")
