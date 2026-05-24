"""Silero VAD for speech start/end detection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

import numpy as np
import torch

from src.config import VadConfig

logger = logging.getLogger("voice_coder.vad")

# Silero requires exactly 512 samples per inference at 16 kHz
SILERO_WINDOW_SAMPLES = 512


class VadState(Enum):
    IDLE = "idle"
    SPEECH = "speech"


@dataclass
class SpeechSegment:
    """Completed speech segment ready for transcription."""

    audio: np.ndarray
    sample_rate: int


class SileroVAD:
    """Streaming voice activity detector using Silero VAD."""

    def __init__(self, config: VadConfig, sample_rate: int = 16000) -> None:
        if sample_rate != 16000:
            raise ValueError("Silero VAD in this project supports 16 kHz only")
        self._config = config
        self._sample_rate = sample_rate
        self._state = VadState.IDLE
        self._speech_samples: list[np.ndarray] = []
        self._silence_ms = 0
        self._speech_ms = 0
        self._pending = np.array([], dtype=np.float32)

        self._min_speech_samples = int(sample_rate * config.min_speech_ms / 1000)
        self._window_ms = int(SILERO_WINDOW_SAMPLES / sample_rate * 1000)

        self._model, self._utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            onnx=False,
            trust_repo=True,
        )
        self._on_speech_start = None
        self._on_speech_end = None
        logger.info("Silero VAD loaded (window=%d samples)", SILERO_WINDOW_SAMPLES)

    def set_callbacks(
        self,
        on_speech_start=None,
        on_speech_end=None,
    ) -> None:
        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end

    def _probability(self, window: np.ndarray) -> float:
        if len(window) != SILERO_WINDOW_SAMPLES:
            return 0.0
        tensor = torch.from_numpy(window.astype(np.float32))
        with torch.no_grad():
            prob = self._model(tensor, self._sample_rate).item()
        return float(prob)

    def process_chunk(self, chunk: np.ndarray) -> SpeechSegment | None:
        """Process audio; returns a SpeechSegment when the user stops speaking."""
        self._pending = np.concatenate([self._pending, chunk.astype(np.float32)])
        result: SpeechSegment | None = None

        while len(self._pending) >= SILERO_WINDOW_SAMPLES:
            window = self._pending[:SILERO_WINDOW_SAMPLES]
            self._pending = self._pending[SILERO_WINDOW_SAMPLES:]

            segment = self._process_window(window)
            if segment is not None:
                result = segment

        return result

    def _process_window(self, window: np.ndarray) -> SpeechSegment | None:
        prob = self._probability(window)
        is_speech = prob >= self._config.threshold

        if is_speech:
            if self._state == VadState.IDLE:
                self._state = VadState.SPEECH
                self._speech_samples = []
                logger.info("Speech started (prob=%.2f)", prob)
                if self._on_speech_start:
                    self._on_speech_start()
            self._silence_ms = 0
            self._speech_ms += self._window_ms
            self._speech_samples.append(window.copy())
        elif self._state == VadState.SPEECH:
            self._silence_ms += self._window_ms
            self._speech_samples.append(window.copy())
            if self._silence_ms >= self._config.min_silence_ms:
                return self._finalize_segment()
        else:
            self._speech_ms = 0

        return None

    def _finalize_segment(self) -> SpeechSegment | None:
        self._state = VadState.IDLE
        if not self._speech_samples:
            return None

        audio = np.concatenate(self._speech_samples)
        self._speech_samples = []
        self._silence_ms = 0
        self._speech_ms = 0

        duration = len(audio) / self._sample_rate
        if len(audio) < self._min_speech_samples:
            logger.debug("Discarding short segment (%.2fs)", duration)
            return None

        logger.info("Speech ended (%.2fs) — sending to STT", duration)
        if self._on_speech_end:
            self._on_speech_end()
        return SpeechSegment(audio=audio, sample_rate=self._sample_rate)

    def flush(self) -> SpeechSegment | None:
        """Force-finalize any in-progress speech (e.g. on shutdown)."""
        if self._state == VadState.SPEECH and self._speech_samples:
            return self._finalize_segment()
        return None
