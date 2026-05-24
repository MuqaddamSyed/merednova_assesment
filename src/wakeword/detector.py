"""Wake word detection via transcript matching and optional openWakeWord."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

import numpy as np

from src.config import WakewordConfig

logger = logging.getLogger("voice_coder.wakeword")


class WakeWordDetector:
    """
    Dual-mode wake word detector:
    1. Transcript phrase matching (primary, low latency after STT)
    2. openWakeWord on raw audio (optional, for pre-STT activation)
    """

    def __init__(self, config: WakewordConfig, sample_rate: int = 16000) -> None:
        self._config = config
        self._sample_rate = sample_rate
        self._phrases = [p.lower().strip() for p in config.phrases]
        self._patterns = [
            re.compile(r"\b" + re.escape(p) + r"\b", re.IGNORECASE) for p in self._phrases
        ]
        self._oww_model = None
        if config.openwakeword_models:
            self._init_openwakeword()
        else:
            logger.info("Using transcript-based wake word detection")

    def _init_openwakeword(self) -> None:
        try:
            from openwakeword.model import Model

            self._oww_model = Model(
                wakeword_models=self._config.openwakeword_models,
                inference_framework="onnx",
            )
            logger.info("openWakeWord models loaded: %s", self._config.openwakeword_models)
        except Exception as exc:
            logger.warning("openWakeWord unavailable: %s", exc)
            self._oww_model = None

    def check_transcript(self, text: str) -> bool:
        """Return True if transcript contains a wake phrase."""
        if not text:
            return False
        normalized = text.lower().strip()
        for phrase, pattern in zip(self._phrases, self._patterns):
            if phrase in normalized or pattern.search(text):
                logger.info("Wake word detected in transcript: '%s'", phrase)
                return True
        return False

    def strip_wake_phrase(self, text: str) -> str:
        """Remove wake phrase from transcript, returning remainder as command."""
        result = text
        for phrase in self._phrases:
            result = re.sub(re.escape(phrase), "", result, flags=re.IGNORECASE)
        return result.strip(" ,.!")

    def check_audio(self, audio: np.ndarray) -> bool:
        """Check raw audio chunk with openWakeWord (if enabled)."""
        if self._oww_model is None or len(audio) < self._sample_rate // 2:
            return False
        try:
            # openWakeWord expects 16-bit PCM at 16kHz
            pcm = (audio * 32767).astype(np.int16)
            self._oww_model.predict(pcm)
            for name, scores in self._oww_model.prediction_buffer.items():
                if scores and scores[-1] > 0.5:
                    logger.info("openWakeWord detected: %s", name)
                    return True
        except Exception as exc:
            logger.debug("openWakeWord predict error: %s", exc)
        return False

    def on_wake(self, callback: Callable[[], None]) -> None:
        self._wake_callback = callback
