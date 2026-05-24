"""Tests for audio capture cleanup."""

from unittest.mock import MagicMock, patch

from src.audio.capture import AudioCapture
from src.config import AudioConfig


def test_stop_is_idempotent() -> None:
    cap = AudioCapture(AudioConfig())
    cap._stream = MagicMock()
    cap._stopped = False

    with patch("src.audio.capture.sd.stop") as mock_sd_stop:
        cap.stop()
        cap.stop()

    assert cap._stream is None
    mock_sd_stop.assert_called_once()


def test_stop_calls_sd_stop() -> None:
    cap = AudioCapture(AudioConfig())
    stream = MagicMock()
    cap._stream = stream

    with patch("src.audio.capture.sd.stop") as mock_sd_stop:
        cap.stop()

    stream.stop.assert_called_once()
    stream.close.assert_called_once()
    mock_sd_stop.assert_called_once()
