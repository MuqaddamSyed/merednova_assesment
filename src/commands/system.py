"""System-level voice commands (mute, exit, listening mode)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.audio.capture import AudioCapture
    from src.utils.shutdown import ShutdownCoordinator

logger = logging.getLogger("voice_coder.commands.system")


class ListeningMode(Enum):
    IDLE = "idle"  # waiting for wake word
    ACTIVE = "active"  # accepting commands
    MUTED = "muted"


@dataclass
class SystemResult:
    handled: bool
    message: str
    new_mode: ListeningMode | None = None
    should_exit: bool = False


class SystemCommandHandler:
    """Handle system intents and manage listening state."""

    def __init__(
        self,
        audio: "AudioCapture",
        shutdown: "ShutdownCoordinator",
    ) -> None:
        self._audio = audio
        self._shutdown = shutdown
        self.mode = ListeningMode.IDLE

    def handle(self, action: str) -> SystemResult:
        if action == "stop_listening":
            self.mode = ListeningMode.IDLE
            return SystemResult(True, "Stopped listening. Say wake word to continue.", ListeningMode.IDLE)

        if action == "mute":
            self._audio.mute()
            self.mode = ListeningMode.MUTED
            return SystemResult(True, "Microphone muted.", ListeningMode.MUTED)

        if action == "resume":
            self._audio.unmute()
            self.mode = ListeningMode.ACTIVE
            return SystemResult(True, "Listening resumed.", ListeningMode.ACTIVE)

        if action == "cancel_agent":
            return SystemResult(True, "Agent task cancelled.", ListeningMode.ACTIVE)

        if action == "exit":
            self._shutdown.request_shutdown()
            return SystemResult(True, "Shutting down...", should_exit=True)

        return SystemResult(False, f"Unknown system action: {action}")

    def activate(self) -> None:
        self.mode = ListeningMode.ACTIVE
        logger.info("Listening mode ACTIVE")

    def deactivate(self) -> None:
        self.mode = ListeningMode.IDLE
        logger.info("Listening mode IDLE")
