#!/usr/bin/env python3
"""Quick environment check for Voice Coder."""

from __future__ import annotations

import shutil
import sys


def main() -> int:
    print("Voice Coder setup check\n")
    ok = True

    for mod in ("numpy", "sounddevice", "torch", "faster_whisper", "textual", "yaml"):
        try:
            __import__(mod if mod != "yaml" else "yaml")
            print(f"  OK  {mod}")
        except ImportError:
            print(f"  FAIL {mod} — pip install -r requirements.txt")
            ok = False

    if shutil.which("aider"):
        print("  OK  aider (on PATH)")
    else:
        print("  WARN aider not found — pip install aider-chat (or use --dry-run)")

    try:
        import sounddevice as sd

        print("\nAudio devices:")
        print(sd.query_devices())
        print("\nDefault input:", sd.query_devices(kind="input"))
    except Exception as exc:
        print(f"  FAIL audio: {exc}")
        ok = False

    try:
        from src.config import load_config
        from src.vad.silero import SILERO_WINDOW_SAMPLES

        cfg = load_config()
        chunk = int(cfg.audio.sample_rate * cfg.audio.chunk_duration_ms / 1000)
        print(f"\n  VAD window: {SILERO_WINDOW_SAMPLES} samples")
        print(f"  Audio chunk: {chunk} samples")
        if chunk != SILERO_WINDOW_SAMPLES:
            print("  WARN chunk size != VAD window (buffering handles this)")
    except Exception as exc:
        print(f"  FAIL config/vad: {exc}")
        ok = False

    print("\nRun: export PYTHONPATH=. && python -m src.main")
    print("Tip: press L to start listening, then speak your command.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
