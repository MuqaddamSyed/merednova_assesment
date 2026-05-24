"""Tests for latency metrics."""

from src.utils.metrics import LatencyMetrics


def test_stt_timing() -> None:
    m = LatencyMetrics()
    m.begin_stt()
    ms = m.end_stt()
    assert ms >= 0
    assert "STT" in m.summary()


def test_route_timing() -> None:
    m = LatencyMetrics()
    m.begin_route()
    ms = m.end_route()
    assert ms >= 0
    assert "route" in m.summary()
