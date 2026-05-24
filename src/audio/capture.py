"""Microphone capture via sounddevice."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from src.audio.buffer import RingBuffer
from src.config import AudioConfig

logger = logging.getLogger("voice_coder.audio")


class AudioCapture:
    """Continuous microphone capture into a ring buffer with chunk callbacks."""

    def __init__(
        self,
        config: AudioConfig,
        on_chunk: Callable[[np.ndarray], None] | None = None,
    ) -> None:
        self._config = config
        self._on_chunk = on_chunk
        self._chunk_samples = int(
            config.sample_rate * config.chunk_duration_ms / 1000
        )
        max_samples = config.sample_rate * 30  # 30 seconds history
        self.buffer = RingBuffer(max_samples)
        self._stream: sd.InputStream | None = None
        self._running = threading.Event()
        self._muted = threading.Event()
        self._stopped = False
        self._lock = threading.Lock()

    @property
    def sample_rate(self) -> int:
        return self._config.sample_rate

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._stream is not None and not self._stopped

    @property
    def is_muted(self) -> bool:
        return self._muted.is_set()

    def mute(self) -> None:
        self._muted.set()
        logger.info("Microphone muted")

    def unmute(self) -> None:
        self._muted.clear()
        logger.info("Microphone unmuted")

    def _callback(self, indata: np.ndarray, _frames: int, _time, status) -> None:
        if self._stopped or not self._running.is_set():
            raise sd.CallbackAbort
        if status:
            logger.warning("Audio status: %s", status)
        if self._muted.is_set():
            return
        chunk = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
        self.buffer.write(chunk)
        if self._on_chunk:
            self._on_chunk(chunk)

    def start(self) -> None:
        with self._lock:
            if self._stream is not None:
                return
            self._stopped = False
            self._running.set()
            self._stream = sd.InputStream(
                samplerate=self._config.sample_rate,
                channels=self._config.channels,
                dtype="float32",
                blocksize=self._chunk_samples,
                device=self._config.device,
                callback=self._callback,
            )
            self._stream.start()
        logger.info(
            "Audio capture started (%d Hz, chunk=%d samples)",
            self._config.sample_rate,
            self._chunk_samples,
        )

    def stop(self) -> None:
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            self._running.clear()
            stream = self._stream
            self._stream = None

        if stream is not None:
            for method_name in ("stop", "close"):
                try:
                    getattr(stream, method_name)()
                except Exception as exc:
                    logger.debug("Stream %s: %s", method_name, exc)

        # Release PortAudio device so macOS clears the mic indicator.
        try:
            sd.stop()
        except Exception as exc:
            logger.debug("sd.stop(): %s", exc)

        logger.info("Audio capture stopped")
