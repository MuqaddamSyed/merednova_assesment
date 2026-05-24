"""Safe allowlisted terminal command execution."""

from __future__ import annotations

import logging
import shlex
import subprocess
from dataclasses import dataclass

logger = logging.getLogger("voice_coder.commands.terminal")

# Explicit allowlist: spoken alias -> shell command parts
ALLOWLIST: dict[str, list[str]] = {
    "run tests": ["pytest", "-q"],
    "start server": ["python", "-m", "flask", "run"],
    "git status": ["git", "status"],
}

# Compound commands allowed as single strings (parsed carefully)
ALLOWLIST_SHELL: dict[str, str] = {
    "commit changes": 'git add -A && git commit -m "Voice coder: automated commit"',
}


@dataclass
class CommandResult:
    success: bool
    stdout: str
    stderr: str
    returncode: int


class TerminalCommandHandler:
    """Execute only pre-approved terminal commands."""

    def __init__(self, extra_aliases: dict[str, str] | None = None) -> None:
        self._aliases = dict(ALLOWLIST_SHELL)
        if extra_aliases:
            self._aliases.update(extra_aliases)
        self._argv_aliases = dict(ALLOWLIST)

    def execute_confirmed(self, cmd: str) -> CommandResult:
        logger.info("Executing confirmed shell command: %s", cmd)
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return CommandResult(
                success=proc.returncode == 0,
                stdout=proc.stdout,
                stderr=proc.stderr,
                returncode=proc.returncode,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(False, "", "Command timed out", -1)

    def execute(self, alias_key: str, shell_command: str | None = None) -> CommandResult:
        key = alias_key.lower().strip()

        if key == "commit_with_message":
            msg = (shell_command or "").replace('"', "'").strip()[:120]
            if not msg:
                return CommandResult(False, "", "No commit message provided", 1)
            cmd = f'git add -A && git commit -m "{msg}"'
            return self._run_shell_safe(cmd)

        if key in self._argv_aliases:
            return self._run_argv(self._argv_aliases[key])

        cmd = shell_command or self._aliases.get(key)
        if cmd and key in self._aliases:
            return self._run_shell(cmd)

        if shell_command and self._is_allowed_shell(shell_command):
            return self._run_shell(shell_command)

        logger.warning("Blocked non-allowlisted command: %s", alias_key)
        return CommandResult(
            success=False,
            stdout="",
            stderr=f"Command not in allowlist: {alias_key}",
            returncode=1,
        )

    def _is_allowed_shell(self, cmd: str) -> bool:
        return cmd.strip() in self._aliases.values()

    def _run_argv(self, argv: list[str]) -> CommandResult:
        logger.info("Executing: %s", " ".join(argv))
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return CommandResult(
                success=proc.returncode == 0,
                stdout=proc.stdout,
                stderr=proc.stderr,
                returncode=proc.returncode,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(False, "", "Command timed out", -1)
        except FileNotFoundError as exc:
            return CommandResult(False, "", str(exc), -1)

    def _run_shell(self, cmd: str) -> CommandResult:
        return self._run_shell_safe(cmd)

    def _run_shell_safe(self, cmd: str) -> CommandResult:
        allowed = set(self._aliases.values())
        if cmd not in allowed and not cmd.startswith('git add -A && git commit -m "'):
            logger.warning("Shell command blocked: %s", cmd)
            return CommandResult(False, "", "Shell command not allowlisted", 1)
        logger.info("Executing shell: %s", cmd)
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return CommandResult(
                success=proc.returncode == 0,
                stdout=proc.stdout,
                stderr=proc.stderr,
                returncode=proc.returncode,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(False, "", "Command timed out", -1)

    def search_code(self, query: str, cwd: str = ".") -> CommandResult:
        """Safe ripgrep-based code search."""
        safe_query = query.replace('"', "").replace(";", "")[:200]
        argv = ["rg", "-n", "--max-count", "20", safe_query, cwd]
        return self._run_argv(argv)

    def open_file_hint(self, path: str) -> CommandResult:
        safe = path.replace("..", "").strip()
        return CommandResult(
            success=True,
            stdout=f"Open file in editor: {safe}",
            stderr="",
            returncode=0,
        )
