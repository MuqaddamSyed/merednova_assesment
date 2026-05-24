"""Optional text-to-speech for hands-free confirmations."""

from __future__ import annotations

import logging
import platform
import subprocess
import threading

logger = logging.getLogger("voice_coder.tts")


class Speaker:
    """Non-blocking TTS using macOS `say` or espeak on Linux."""

    def __init__(self, enabled: bool = True, max_chars: int = 200) -> None:
        self._enabled = enabled
        self._max_chars = max_chars
        self._lock = threading.Lock()

    def speak(self, text: str) -> None:
        if not self._enabled or not text.strip():
            return
        snippet = text.strip()[: self._max_chars]
        threading.Thread(target=self._speak_sync, args=(snippet,), daemon=True).start()

    def _speak_sync(self, text: str) -> None:
        try:
            system = platform.system()
            if system == "Darwin":
                subprocess.run(["say", text], check=False, timeout=30)
            elif system == "Linux" and shutil_which("espeak"):
                subprocess.run(["espeak", text], check=False, timeout=30)
        except Exception as exc:
            logger.debug("TTS failed: %s", exc)


def shutil_which(cmd: str) -> bool:
    import shutil

    return shutil.which(cmd) is not None
