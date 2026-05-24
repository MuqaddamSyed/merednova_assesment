"""Regression tests for STT module."""

from src.stt.whisper import WhisperTranscriber
from src.config import SttConfig


def test_transcribe_segment_method_exists() -> None:
    t = WhisperTranscriber(SttConfig())
    assert callable(getattr(t, "transcribe_segment", None))
    assert callable(getattr(t, "warmup", None))


def test_cloud_provider_api_key(monkeypatch) -> None:
    cfg = SttConfig(provider="openai")
    t = WhisperTranscriber(cfg)
    
    # Check that it reads OpenAI API Key from environment
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-123")
    assert t._get_api_key() == "test-key-123"
    assert t._get_endpoint() == "https://api.openai.com/v1/audio/transcriptions"
    
    # Check Groq provider key and endpoint
    cfg_groq = SttConfig(provider="groq")
    t_groq = WhisperTranscriber(cfg_groq)
    monkeypatch.setenv("GROQ_API_KEY", "groq-key-abc")
    assert t_groq._get_api_key() == "groq-key-abc"
    assert t_groq._get_endpoint() == "https://api.groq.com/openai/v1/audio/transcriptions"
