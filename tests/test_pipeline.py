"""Pipeline integration tests (router + context, no mic)."""

import struct
import wave
from pathlib import Path

import pytest

from src.config import RouterConfig
from src.router.classifier import CommandRouter
from src.router.intents import Intent
from src.session.context import SessionContext

FIXTURES = Path(__file__).parent / "fixtures"


def _write_wav(path: Path, samples: list[float], sample_rate: int = 16000) -> None:
    """Write mono 16-bit PCM WAV for fixture generation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


@pytest.fixture(scope="module", autouse=True)
def wav_fixtures() -> None:
    """Generate minimal WAV fixtures once per test session."""
    silent = [0.0] * 16000
    tone = [0.3 * (i % 50) / 50 for i in range(8000)]
    _write_wav(FIXTURES / "silent_1s.wav", silent)
    _write_wav(FIXTURES / "tone_0.5s.wav", tone)


def test_wav_fixtures_exist() -> None:
    assert (FIXTURES / "silent_1s.wav").exists()
    assert (FIXTURES / "tone_0.5s.wav").exists()


def test_demo_script_routing_chain() -> None:
    """Simulate the recommended demo voice commands through router + context."""
    router = CommandRouter(
        RouterConfig(
            coding_keywords=["authentication", "rest", "api"],
            terminal_aliases={"run tests": "pytest -q"},
            min_confidence=0.70,
        )
    )
    ctx = SessionContext()

    steps = [
        ("create a python rest api with jwt authentication", Intent.CODING),
        ("run tests", Intent.TERMINAL),
        ("explain the failing test", Intent.CODING),
        ("fix the bug", Intent.CODING),
        ("commit with message add jwt authentication", Intent.TERMINAL),
    ]

    for phrase, expected in steps:
        r = router.route(phrase)
        assert r.intent == expected, phrase

    ctx.record_terminal("run tests", "FAILED tests/test_auth.py - AssertionError", False)
    enriched = ctx.enrich_coding_prompt("explain the failing test")
    assert "AssertionError" in enriched


def test_low_confidence_clarification() -> None:
    router = CommandRouter(
        RouterConfig(
            min_confidence=0.90,
            clarify_on_low_confidence=True,
            terminal_aliases={"run tests": "pytest -q"},
        )
    )
    r = router.route("maybe run something")
    assert r.confidence < 0.90
    assert r.needs_clarification or r.intent == Intent.CODING


def test_direct_program_request_routes_to_coding() -> None:
    router = CommandRouter(RouterConfig(min_confidence=0.70))
    r = router.route("Give me a simple Fibonacci program in Python")
    assert r.intent == Intent.CODING
