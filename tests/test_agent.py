"""Tests for Aider startup argument resolution."""

from unittest.mock import Mock

from src.agent.aider_client import AiderClient
from src.config import AgentConfig


def test_effective_args_force_no_browser(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client = AiderClient(AgentConfig(args=["--yes", "--model", "gpt-4o"]))

    args = client._effective_args()

    assert args is not None
    assert "--no-browser" in args
    assert args[args.index("--model") + 1] == "gpt-4o"


def test_effective_args_translate_openai_model_for_openrouter(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    client = AiderClient(AgentConfig(args=["--yes", "--model", "gpt-4o"]))

    args = client._effective_args()

    assert args is not None
    assert args[args.index("--model") + 1] == "openrouter/openai/gpt-4o"


def test_effective_args_fail_when_openai_model_has_no_compatible_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = AiderClient(AgentConfig(args=["--yes", "--model", "gpt-4o"]))

    args = client._effective_args()

    assert args is None
    assert "API key" in client._last_start_error


def test_describe_backend_uses_translated_openrouter_model(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    client = AiderClient(AgentConfig(args=["--yes", "--model", "gpt-4o"]))

    description = client.describe_backend()

    assert description == "Aider via OpenRouter (openrouter/openai/gpt-4o)"


def test_send_prompt_uses_oneshot_when_lazy_spawn_enabled(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client = AiderClient(AgentConfig(args=["--yes", "--model", "gpt-4o"], lazy_spawn=True))
    mock_send_oneshot = Mock(return_value=("ok", True))
    client._send_oneshot = mock_send_oneshot  # type: ignore[method-assign]

    result = client.send_prompt("write fibonacci code")

    assert result == ("ok", True)
    mock_send_oneshot.assert_called_once_with("write fibonacci code")
