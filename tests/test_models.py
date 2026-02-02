"""Tests for debate models."""

import pytest

from debate.models import (
    Card,
    Case,
    Contention,
    Side,
    Speech,
    SpeechType,
)


class TestSide:
    def test_opposite_pro(self):
        assert Side.PRO.opposite == Side.CON

    def test_opposite_con(self):
        assert Side.CON.opposite == Side.PRO


class TestCard:
    def test_format(self):
        card = Card(
            tag="Economic impact",
            cite="Smith, 2024",
            text="GDP growth decreased by 4.2%",
        )
        assert card.format() == "[Smith, 2024] GDP growth decreased by 4.2%"


class TestContention:
    def test_creation(self):
        contention = Contention(
            title="Contention 1: Economic Impact",
            content="This is a test argument with evidence. " * 10,
        )
        assert contention.title == "Contention 1: Economic Impact"
        assert len(contention.content) > 0


class TestCase:
    def test_creation(self):
        contentions = [
            Contention(
                title="Contention 1: Test",
                content="Test content " * 20,
            ),
            Contention(
                title="Contention 2: Test",
                content="More test content " * 20,
            ),
        ]
        case = Case(
            resolution="Resolved: Test resolution",
            side=Side.PRO,
            contentions=contentions,
        )
        assert case.resolution == "Resolved: Test resolution"
        assert case.side == Side.PRO
        assert len(case.contentions) == 2

    def test_format_pro(self):
        contentions = [
            Contention(title="Contention 1: Test", content="Test content"),
            Contention(title="Contention 2: Test", content="More content"),
        ]
        case = Case(
            resolution="Resolved: Test",
            side=Side.PRO,
            contentions=contentions,
        )
        formatted = case.format()
        assert "AFFIRMATIVE CASE" in formatted
        assert "Contention 1: Test" in formatted

    def test_format_con(self):
        contentions = [
            Contention(title="Contention 1: Test", content="Test content"),
            Contention(title="Contention 2: Test", content="More content"),
        ]
        case = Case(
            resolution="Resolved: Test",
            side=Side.CON,
            contentions=contentions,
        )
        formatted = case.format()
        assert "NEGATIVE CASE" in formatted

    def test_min_contentions_validation(self):
        """Case must have at least 2 contentions."""
        with pytest.raises(ValueError):
            Case(
                resolution="Test",
                side=Side.PRO,
                contentions=[
                    Contention(title="Only one", content="Content"),
                ],
            )

    def test_max_contentions_validation(self):
        """Case can have at most 3 contentions."""
        with pytest.raises(ValueError):
            Case(
                resolution="Test",
                side=Side.PRO,
                contentions=[
                    Contention(title=f"Contention {i}", content="Content")
                    for i in range(4)
                ],
            )


class TestSpeech:
    def test_creation(self):
        speech = Speech(
            speech_type=SpeechType.CONSTRUCTIVE,
            side=Side.PRO,
            speaker_number=1,
            content="My constructive speech content.",
            time_limit_seconds=240,
        )
        assert speech.speech_type == SpeechType.CONSTRUCTIVE
        assert speech.side == Side.PRO
        assert speech.speaker_number == 1

    def test_speaker_number_validation(self):
        """Speaker number must be 1 or 2."""
        with pytest.raises(ValueError):
            Speech(
                speech_type=SpeechType.CONSTRUCTIVE,
                side=Side.PRO,
                speaker_number=3,
                content="Content",
                time_limit_seconds=240,
            )
