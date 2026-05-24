"""Latency and pipeline performance metrics."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class LatencyMetrics:
    """Tracks stage latencies for demo and debugging."""

    stt_ms: float | None = None
    route_ms: float | None = None
    last_total_ms: float | None = None
    _stt_start: float | None = field(default=None, repr=False)
    _route_start: float | None = field(default=None, repr=False)

    def begin_stt(self) -> None:
        self._stt_start = time.monotonic()

    def end_stt(self) -> float:
        if self._stt_start is None:
            return 0.0
        self.stt_ms = (time.monotonic() - self._stt_start) * 1000
        self._stt_start = None
        return self.stt_ms

    def begin_route(self) -> None:
        self._route_start = time.monotonic()

    def end_route(self) -> float:
        if self._route_start is None:
            return 0.0
        self.route_ms = (time.monotonic() - self._route_start) * 1000
        self._route_start = None
        return self.route_ms

    def summary(self) -> str:
        parts: list[str] = []
        if self.stt_ms is not None:
            parts.append(f"STT {self.stt_ms:.0f}ms")
        if self.route_ms is not None:
            parts.append(f"route {self.route_ms:.0f}ms")
        return " · ".join(parts) if parts else "—"
