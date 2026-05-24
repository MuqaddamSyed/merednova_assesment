"""Thread-safe ring buffer for audio samples."""

from __future__ import annotations

import threading
from collections import deque

import numpy as np


class RingBuffer:
    """Fixed-capacity FIFO buffer for float32 mono audio."""

    def __init__(self, max_samples: int) -> None:
        self._max = max_samples
        self._data: deque[np.ndarray] = deque()
        self._size = 0
        self._lock = threading.Lock()

    def write(self, chunk: np.ndarray) -> None:
        flat = np.asarray(chunk, dtype=np.float32).flatten()
        with self._lock:
            self._data.append(flat)
            self._size += len(flat)
            while self._size > self._max and self._data:
                removed = self._data.popleft()
                self._size -= len(removed)

    def read_all(self) -> np.ndarray:
        with self._lock:
            if not self._data:
                return np.array([], dtype=np.float32)
            merged = np.concatenate(list(self._data))
            self._data.clear()
            self._size = 0
            return merged

    def snapshot(self) -> np.ndarray:
        with self._lock:
            if not self._data:
                return np.array([], dtype=np.float32)
            return np.concatenate(list(self._data))

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._size = 0
