"""Startup health checks surfaced in onboarding UI."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

from src.config import AppConfig


@dataclass
class PreflightCheck:
    name: str
    ok: bool
    detail: str


def run_preflight(config: AppConfig) -> list[PreflightCheck]:
    checks: list[PreflightCheck] = []

    # Microphone
    try:
        import sounddevice as sd

        device = sd.query_devices(kind="input")
        if isinstance(device, dict):
            device_name = str(device.get("name", "unknown"))
        else:
            device_name = str(device)
        checks.append(
            PreflightCheck(
                "Microphone",
                True,
                f"Default input: {device_name}",
            )
        )
    except Exception as exc:
        checks.append(PreflightCheck("Microphone", False, str(exc)))

    # Whisper (model loads on first use; verify import)
    try:
        from faster_whisper import WhisperModel  # noqa: F401

        checks.append(
            PreflightCheck(
                "Whisper STT",
                True,
                f"Model '{config.stt.model_size}' (loads on first speech)",
            )
        )
    except Exception as exc:
        checks.append(PreflightCheck("Whisper STT", False, str(exc)))

    # Aider + API key
    import sys
    venv_bin = os.path.dirname(sys.executable)
    search_path = venv_bin + os.pathsep + os.environ.get("PATH", "")
    if config.agent.dry_run:
        checks.append(PreflightCheck("Aider", True, "Dry-run mode (no API key needed)"))
    elif not shutil.which(config.agent.command, path=search_path):
        checks.append(
            PreflightCheck(
                "Aider",
                False,
                "Not installed — pip install aider-chat",
            )
        )
    else:
        has_key = any(
            os.environ.get(k)
            for k in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY")
        )
        if has_key:
            model = next(
                (config.agent.args[i + 1] for i, a in enumerate(config.agent.args) if a == "--model"),
                "default",
            )
            checks.append(PreflightCheck("Aider + API key", True, f"Model: {model}"))
        else:
            checks.append(
                PreflightCheck(
                    "Aider + API key",
                    False,
                    "Set OPENAI_API_KEY in .env (avoids OpenRouter browser redirect)",
                )
            )

    checks.append(
        PreflightCheck(
            "Ready",
            True,
            f"Press L to listen, or say '{config.wakeword.phrases[0] if config.wakeword.phrases else 'Hey coder'}'",
        )
    )
    return checks
