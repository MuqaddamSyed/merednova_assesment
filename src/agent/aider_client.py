"""Aider coding agent integration via PTY/subprocess."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
from collections.abc import Callable

from src.config import AgentConfig

logger = logging.getLogger("voice_coder.agent")

_AUTH_ERROR_PATTERNS = [
    re.compile(r"openrouter", re.I),
    re.compile(r"api key", re.I),
    re.compile(r"authentication", re.I),
    re.compile(r"unauthorized", re.I),
    re.compile(r"401", re.I),
]


class AiderClient:
    """
    Lazy-spawned Aider session with streaming output and auth error detection.
    """

    def __init__(
        self,
        config: AgentConfig,
        on_output: Callable[[str], None] | None = None,
        on_line: Callable[[str], None] | None = None,
        cwd: str | None = None,
    ) -> None:
        self._config = config
        self._on_output = on_output
        self._on_line = on_line
        self._cwd = cwd
        self._child = None
        self._lock = threading.Lock()
        self._started = False
        self._dry_run = config.dry_run
        self._cancelled = threading.Event()
        self._env = self._build_env()

    @property
    def is_running(self) -> bool:
        return self._child is not None and self._child.isalive()

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        for key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"):
            if os.environ.get(key):
                env[key] = os.environ[key]
        return env

    def start(self) -> bool:
        """Eager start (optional). Lazy mode skips until first prompt."""
        if self._dry_run:
            logger.info("Aider dry-run mode enabled")
            self._started = True
            return True
        if self._config.lazy_spawn:
            logger.info("Aider lazy spawn enabled — starts on first coding command")
            return True
        return self._ensure_session()

    def _ensure_session(self) -> bool:
        if self._started and (self._dry_run or self.is_running or self._child is None):
            if self._dry_run:
                return True
        if not shutil.which(self._config.command):
            logger.error("Aider not found on PATH. Install: pip install aider-chat")
            return False
        if self.is_running:
            return True
        try:
            import pexpect

            args = [self._config.command, *self._config.args]
            self._child = pexpect.spawn(
                args[0],
                args=args[1:],
                encoding="utf-8",
                cwd=self._cwd,
                timeout=self._config.startup_timeout_sec,
                env=self._env,
            )
            self._child.expect([pexpect.TIMEOUT, pexpect.EOF, "> ", r"\?"], timeout=15)
            initial = self._child.before or ""
            if initial:
                self._emit(initial)
                if self._detect_auth_error(initial):
                    return False
            self._started = True
            logger.info("Aider session started")
            return True
        except Exception as exc:
            logger.warning("PTY spawn failed (%s), using subprocess fallback", exc)
            self._child = None
            self._started = True
            return True

    def cancel(self) -> None:
        self._cancelled.set()
        if self._child:
            try:
                self._child.close(force=True)
            except Exception:
                pass
            self._child = None

    def send_prompt(self, prompt: str) -> tuple[str, bool]:
        if self._cancelled.is_set():
            self._cancelled.clear()

        if self._dry_run:
            msg = f"[DRY RUN] Would send to Aider: {prompt}"
            self._emit(msg)
            return msg, True

        if not self._ensure_session():
            msg = "Aider unavailable. Set OPENAI_API_KEY in .env and restart."
            self._emit(msg)
            return msg, False

        with self._lock:
            if self._child and self._child.isalive():
                return self._send_pty(prompt)
            return self._send_oneshot(prompt)

    def _send_pty(self, prompt: str) -> tuple[str, bool]:
        import pexpect

        assert self._child is not None
        try:
            self._child.sendline(prompt)
            idx = self._child.expect(
                [pexpect.TIMEOUT, pexpect.EOF, "> "],
                timeout=self._config.response_timeout_sec,
            )
            chunk = (self._child.before or "") + (self._child.after or "")
            self._emit(chunk)
            if self._detect_auth_error(chunk):
                return chunk, False
            return chunk, idx != 1
        except Exception as exc:
            logger.exception("PTY prompt failed")
            return str(exc), False

    def _send_oneshot(self, prompt: str) -> tuple[str, bool]:
        cmd = [self._config.command, *self._config.args, "--message", prompt]
        logger.info("Aider one-shot: %s", prompt[:80])
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self._cwd,
                env=self._env,
            )
            lines: list[str] = []
            assert proc.stdout is not None
            for line in proc.stdout:
                if self._cancelled.is_set():
                    proc.kill()
                    return "Cancelled.", False
                lines.append(line)
                self._emit_line(line.rstrip())
            proc.wait(timeout=self._config.response_timeout_sec)
            output = "".join(lines)
            if self._detect_auth_error(output):
                return self._auth_help_message(), False
            return output, proc.returncode == 0
        except subprocess.TimeoutExpired:
            return "Aider timed out", False
        except FileNotFoundError:
            return "Aider not installed. Run: pip install aider-chat", False

    def _detect_auth_error(self, text: str) -> bool:
        if any(p.search(text) for p in _AUTH_ERROR_PATTERNS):
            if "localhost:8484" in text or "sign-up" in text.lower():
                return True
            if not any(os.environ.get(k) for k in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY")):
                return True
        return False

    def _auth_help_message(self) -> str:
        return (
            "Aider needs an API key. Set OPENAI_API_KEY in .env to avoid OpenRouter browser redirect."
        )

    def _emit(self, text: str) -> None:
        if self._on_output:
            self._on_output(text)
        for line in text.splitlines():
            self._emit_line(line)

    def _emit_line(self, line: str) -> None:
        if self._on_line and line.strip():
            self._on_line(line)

    def stop(self) -> None:
        if self._child:
            try:
                self._child.close(force=True)
            except Exception:
                pass
            self._child = None
        logger.info("Aider session stopped")
