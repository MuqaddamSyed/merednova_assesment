"""Tests for session context enrichment."""

from src.session.context import SessionContext


def test_explain_error_attaches_terminal_output() -> None:
    ctx = SessionContext()
    ctx.record_terminal("run tests", "FAILED test_auth.py::test_login", success=False)
    prompt = ctx.enrich_coding_prompt("explain the failing test")
    assert "FAILED test_auth" in prompt
    assert "```" in prompt


def test_fix_with_test_output() -> None:
    ctx = SessionContext()
    ctx.record_terminal("run tests", "AssertionError: 401 != 200", success=False)
    prompt = ctx.enrich_coding_prompt("fix the failing test")
    assert "AssertionError" in prompt
