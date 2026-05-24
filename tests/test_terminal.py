"""Tests for allowlisted terminal commands."""

from src.commands.terminal import TerminalCommandHandler


def test_blocks_unknown_command() -> None:
    handler = TerminalCommandHandler()
    result = handler.execute("rm -rf /")
    assert not result.success
    assert "allowlist" in result.stderr.lower()


def test_git_status_allowed() -> None:
    handler = TerminalCommandHandler()
    result = handler.execute("git status")
    # May fail if not in git repo, but should not be blocked
    assert "allowlist" not in result.stderr.lower() or result.returncode != 1
