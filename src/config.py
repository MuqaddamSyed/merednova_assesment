"""Configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    chunk_duration_ms: int = 30
    device: int | str | None = None


@dataclass
class VadConfig:
    threshold: float = 0.5
    min_speech_ms: int = 250
    min_silence_ms: int = 500
    speech_pad_ms: int = 100


@dataclass
class SttConfig:
    model_size: str = "base"
    device: str = "auto"
    compute_type: str = "int8"
    language: str = "en"
    provider: str = "local"  # local or openai


@dataclass
class WakewordConfig:
    phrases: list[str] = field(default_factory=lambda: ["hey coder", "assistant"])
    transcript_fallback: bool = True
    openwakeword_models: list[str] = field(default_factory=list)


@dataclass
class RouterConfig:
    coding_keywords: list[str] = field(default_factory=list)
    terminal_aliases: dict[str, str] = field(default_factory=dict)
    min_confidence: float = 0.70
    clarify_on_low_confidence: bool = True
    llm_fallback: bool = True
    llm_model: str = "gpt-4o-mini"


@dataclass
class AgentConfig:
    command: str = "aider"
    args: list[str] = field(default_factory=lambda: ["--yes", "--no-auto-commits"])
    startup_timeout_sec: int = 30
    response_timeout_sec: int = 300
    dry_run: bool = False
    lazy_spawn: bool = True


@dataclass
class TtsConfig:
    enabled: bool = True
    max_chars: int = 200


@dataclass
class UiConfig:
    refresh_hz: int = 10
    show_onboarding: bool = True


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/voice_coder.log"


@dataclass
class SystemConfig:
    wake_timeout_sec: int = 30


@dataclass
class AppConfig:
    profile: str = "default"
    audio: AudioConfig = field(default_factory=AudioConfig)
    vad: VadConfig = field(default_factory=VadConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    wakeword: WakewordConfig = field(default_factory=WakewordConfig)
    router: RouterConfig = field(default_factory=RouterConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    tts: TtsConfig = field(default_factory=TtsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    system: SystemConfig = field(default_factory=SystemConfig)


def _merge_dataclass(cls: type, data: dict[str, Any] | None) -> Any:
    if not data:
        return cls()
    fields = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    filtered = {k: v for k, v in data.items() if k in fields}
    return cls(**filtered)


def _apply_profile(raw: dict[str, Any], config: AppConfig) -> AppConfig:
    """Apply named config profiles (demo, quality)."""
    profile = raw.get("profile") or config.profile
    profiles = raw.get("profiles") or {}
    if profile in profiles:
        overrides = profiles[profile]
        if "stt" in overrides:
            for k, v in overrides["stt"].items():
                if hasattr(config.stt, k):
                    setattr(config.stt, k, v)
        if "system" in overrides:
            for k, v in overrides["system"].items():
                if hasattr(config.system, k):
                    setattr(config.system, k, v)
        if "tts" in overrides:
            for k, v in overrides["tts"].items():
                if hasattr(config.tts, k):
                    setattr(config.tts, k, v)
    config.profile = profile
    return config


def load_config(path: str | Path | None = None, profile: str | None = None) -> AppConfig:
    """Load YAML config from disk or return defaults."""
    if path is None:
        path = Path(__file__).resolve().parent.parent / "config.yaml"
    path = Path(path)
    if not path.exists():
        cfg = AppConfig()
        if profile:
            cfg.profile = profile
        return cfg

    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if profile:
        raw = dict(raw)
        raw["profile"] = profile

    return _apply_profile(
        raw,
        AppConfig(
            profile=raw.get("profile", "default"),
            audio=_merge_dataclass(AudioConfig, raw.get("audio")),
            vad=_merge_dataclass(VadConfig, raw.get("vad")),
            stt=_merge_dataclass(SttConfig, raw.get("stt")),
            wakeword=_merge_dataclass(WakewordConfig, raw.get("wakeword")),
            router=_merge_dataclass(RouterConfig, raw.get("router")),
            agent=_merge_dataclass(AgentConfig, raw.get("agent")),
            ui=_merge_dataclass(UiConfig, raw.get("ui")),
            tts=_merge_dataclass(TtsConfig, raw.get("tts")),
            logging=_merge_dataclass(LoggingConfig, raw.get("logging")),
            system=_merge_dataclass(SystemConfig, raw.get("system")),
        ),
    )


def save_config(config: AppConfig, path: str | Path | None = None) -> None:
    """Save AppConfig back to YAML on disk."""
    import dataclasses
    if path is None:
        path = Path(__file__).resolve().parent.parent / "config.yaml"
    path = Path(path)
    
    data = {
        "profile": config.profile,
        "audio": dataclasses.asdict(config.audio),
        "vad": dataclasses.asdict(config.vad),
        "stt": dataclasses.asdict(config.stt),
        "wakeword": dataclasses.asdict(config.wakeword),
        "router": dataclasses.asdict(config.router),
        "agent": dataclasses.asdict(config.agent),
        "ui": dataclasses.asdict(config.ui),
        "tts": dataclasses.asdict(config.tts),
        "logging": dataclasses.asdict(config.logging),
        "system": dataclasses.asdict(config.system),
    }
    
    # Filter out empty openwakeword models or list types to keep it clean
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
