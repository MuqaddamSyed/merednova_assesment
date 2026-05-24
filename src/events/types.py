"""Typed UI event bus."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventKind(Enum):
    STATUS = "status"
    MODE = "mode"
    TRANSCRIPT = "transcript"
    AUDIO_LEVEL = "audio_level"
    SPEECH_ACTIVE = "speech_active"
    SPEECH_ENDED = "speech_ended"
    SPINNER = "spinner"
    SUMMARY = "summary"
    ROUTE = "route"
    TERMINAL = "terminal"
    AGENT = "agent"
    AGENT_DONE = "agent_done"
    ERROR = "error"
    ONBOARDING = "onboarding"
    COUNTDOWN = "countdown"
    PRELOAD = "preload"
    METRICS = "metrics"
    HISTORY = "history"
    CLARIFY = "clarify"


@dataclass
class UIEvent:
    kind: EventKind
    message: str = ""
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def status(cls, message: str) -> "UIEvent":
        return cls(EventKind.STATUS, message=message)

    @classmethod
    def summary(cls, message: str) -> "UIEvent":
        return cls(EventKind.SUMMARY, message=message)

    @classmethod
    def spinner(cls, active: bool, label: str = "") -> "UIEvent":
        return cls(EventKind.SPINNER, message=label, data={"active": active})

    @classmethod
    def audio_level(cls, level: float) -> "UIEvent":
        return cls(EventKind.AUDIO_LEVEL, data={"level": level})

    @classmethod
    def speech_active(cls, active: bool) -> "UIEvent":
        return cls(EventKind.SPEECH_ACTIVE, data={"active": active})

    @classmethod
    def countdown(cls, seconds_left: int) -> "UIEvent":
        return cls(EventKind.COUNTDOWN, data={"seconds": seconds_left})
