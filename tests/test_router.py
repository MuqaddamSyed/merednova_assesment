"""Tests for command routing."""

import pytest

from src.config import RouterConfig
from src.router.classifier import CommandRouter
from src.router.intents import Intent


@pytest.fixture
def router() -> CommandRouter:
    config = RouterConfig(
        coding_keywords=["authentication", "flask"],
        terminal_aliases={
            "run tests": "pytest -q",
            "commit changes": 'git add -A && git commit -m "test"',
        },
    )
    return CommandRouter(config)


def test_system_stop_listening(router: CommandRouter) -> None:
    r = router.route("stop listening")
    assert r.intent == Intent.SYSTEM
    assert r.action == "stop_listening"


def test_terminal_run_tests(router: CommandRouter) -> None:
    r = router.route("run tests")
    assert r.intent == Intent.TERMINAL
    assert "pytest" in r.payload


def test_coding_create_api(router: CommandRouter) -> None:
    r = router.route("Create a Flask API with JWT authentication")
    assert r.intent == Intent.CODING
    assert "Flask" in r.payload


def test_coding_explain_error(router: CommandRouter) -> None:
    r = router.route("explain the error")
    assert r.intent == Intent.CODING


def test_coding_give_me_program(router: CommandRouter) -> None:
    r = router.route("Give me a simple Fibonacci program in Python")
    assert r.intent == Intent.CODING
    assert r.confidence >= 0.85


def test_navigation_open_file(router: CommandRouter) -> None:
    r = router.route("open file app.py")
    assert r.intent == Intent.NAVIGATION
    assert r.payload == "app.py"


def test_commit_with_message(router: CommandRouter) -> None:
    r = router.route("commit with message add JWT auth")
    assert r.intent == Intent.TERMINAL
    assert r.action == "commit_with_message"
    assert "JWT" in r.payload


def test_cancel_agent(router: CommandRouter) -> None:
    r = router.route("cancel agent")
    assert r.intent == Intent.SYSTEM
    assert r.action == "cancel_agent"


def test_commit_changes(router: CommandRouter) -> None:
    r = router.route("commit changes")
    assert r.intent == Intent.TERMINAL
    assert r.confidence > 0.5


def test_custom_command(router: CommandRouter) -> None:
    r = router.route("run git log -n 5")
    assert r.intent == Intent.TERMINAL
    assert r.action == "custom_command"
    assert r.payload == "git log -n 5"
    assert r.needs_confirmation is True


def test_llm_route_env_resolution(monkeypatch, router: CommandRouter) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    
    import urllib.request
    from unittest.mock import MagicMock
    from src.router.intents import Intent
    
    mock_urlopen = MagicMock()
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"choices": [{"message": {"content": "{\\"intent\\": \\"CODING\\", \\"action\\": \\"prompt\\", \\"payload\\": \\"some task\\", \\"confidence\\": 0.95}"}}]}'
    mock_urlopen.return_value.__enter__.return_value = mock_response
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    
    r = router._llm_route("make a flask app")
    
    assert r is not None
    assert r.intent == Intent.CODING
