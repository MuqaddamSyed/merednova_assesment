"""Tests for config profiles."""

from src.config import load_config


def test_demo_profile_uses_tiny_model() -> None:
    cfg = load_config(profile="demo")
    assert cfg.stt.model_size == "tiny"
    assert cfg.profile == "demo"


def test_quality_profile_uses_small_model() -> None:
    cfg = load_config(profile="quality")
    assert cfg.stt.model_size == "small"
