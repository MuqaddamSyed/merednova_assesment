"""Tests for wake word detection."""

from src.config import WakewordConfig
from src.wakeword.detector import WakeWordDetector


def test_wake_phrase_detected() -> None:
    det = WakeWordDetector(WakewordConfig(phrases=["hey coder", "assistant"]))
    assert det.check_transcript("Hey coder")
    assert det.check_transcript("okay assistant please help")


def test_wake_strip() -> None:
    det = WakeWordDetector(WakewordConfig(phrases=["hey coder"]))
    assert det.strip_wake_phrase("Hey coder create a REST API") == "create a REST API"


def test_no_false_positive() -> None:
    det = WakeWordDetector(WakewordConfig(phrases=["hey coder"]))
    assert not det.check_transcript("run tests")
