"""Conversation and execution context across commands."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionContext:
    """Remembers recent outputs for smarter follow-up commands."""

    last_terminal_output: str = ""
    last_terminal_command: str = ""
    last_terminal_success: bool = True
    last_aider_output: str = ""
    last_transcript: str = ""
    last_route_summary: str = ""

    def record_terminal(self, command: str, output: str, success: bool) -> None:
        self.last_terminal_command = command
        self.last_terminal_output = output[-8000:]
        self.last_terminal_success = success

    def record_aider(self, output: str) -> None:
        self.last_aider_output = output[-8000:]

    def enrich_coding_prompt(self, prompt: str) -> str:
        lower = prompt.lower()
        if any(k in lower for k in ("explain", "why", "what went wrong")) and any(
            k in lower for k in ("error", "fail", "test", "bug")
        ):
            if self.last_terminal_output.strip():
                snippet = self.last_terminal_output.strip()[-3000:]
                return (
                    f"{prompt.strip()}\n\n"
                    f"Here is the latest terminal output:\n\n```\n{snippet}\n```"
                )
        if "fix" in lower and self.last_terminal_output.strip() and "test" in lower:
            snippet = self.last_terminal_output.strip()[-3000:]
            return (
                f"{prompt.strip()}\n\n"
                f"Failing test output:\n\n```\n{snippet}\n```"
            )
        return prompt
