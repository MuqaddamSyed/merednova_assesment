"""Textual terminal UI for Voice Coder."""

from __future__ import annotations

import queue
import os
from collections import deque
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Footer,
    Header,
    Label,
    LoadingIndicator,
    Log,
    Static,
    TabbedContent,
    TabPane,
    Input,
    Checkbox,
    Select,
    Button,
)

from src.events.types import EventKind, UIEvent

if TYPE_CHECKING:
    from src.orchestrator import VoiceOrchestrator
    from src.utils.preflight import PreflightCheck


class StatusBar(Static):
    def update_status(self, mode: str, status: str, countdown: int | None = None) -> None:
        cd = f"  |  [dim]Listening {countdown}s[/]" if countdown is not None else ""
        self.update(
            f"[bold cyan]Mode:[/] {mode.upper()}{cd}  |  [bold green]Status:[/] {status}"
        )
        
        # Color codes:
        # - Confirming / Gating: Amber Orange
        # - Listening: Emerald Green
        # - Processing: Dodger Blue
        # - Executing: Royal Purple
        # - Default: Slate / Surface Charcoal
        status_lower = status.lower()
        mode_lower = mode.lower()
        if "confirm" in status_lower or "confirm" in mode_lower or "say yes or no" in status_lower:
            self.styles.background = "#e67e22"
        elif mode_lower == "listening":
            self.styles.background = "#2ecc71"
        elif mode_lower == "processing":
            self.styles.background = "#3498db"
        elif mode_lower == "executing":
            self.styles.background = "#9b59b6"
        else:
            self.styles.background = "#2c3e50"


class TranscriptPanel(Static):
    def set_transcript(self, text: str) -> None:
        self.update(f"[bold yellow]You said:[/]\n{text}")


class SummaryPanel(Static):
    def set_summary(self, text: str) -> None:
        self.update(f"[bold magenta]▶[/] {text}")


class MetricsPanel(Static):
    def set_metrics(self, text: str) -> None:
        self.update(f"[dim]Latency:[/] {text}")


class HistoryPanel(Static):
    def set_history(self, lines: list[str]) -> None:
        body = "\n".join(f"  [dim]•[/] {line}" for line in lines[-5:]) or "  [dim]No commands yet[/]"
        self.update(f"[bold]Recent[/]\n{body}")


class SpeechIndicator(Static):
    """Pulses when VAD detects speech."""

    DEFAULT = "[dim]Mic idle[/]"
    ACTIVE = "[bold green]● Listening…[/]"

    def set_active(self, active: bool) -> None:
        self.update(self.ACTIVE if active else self.DEFAULT)


class OnboardingPanel(Static):
    def set_checks(self, checks: list["PreflightCheck"]) -> None:
        lines = ["[bold]System checks[/]"]
        for c in checks:
            icon = "[green]✓[/]" if c.ok else "[red]✗[/]"
            lines.append(f"  {icon} {c.name}: {c.detail}")
        lines.append("")
        lines.append("[dim]Shortcuts: L listen · M mute · Q quit[/]")
        self.update("\n".join(lines))


class WaveformVisualizer(Static):
    """Visualizes live microphone amplitude levels as a scrolling, colored waveform."""

    def on_mount(self) -> None:
        self.levels = deque([0.0] * 40, maxlen=40)
        self.render_waveform()

    def add_level(self, level: float) -> None:
        self.levels.append(level)
        self.render_waveform()

    def render_waveform(self) -> None:
        blocks = [" ", " ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
        parts = []
        for val in self.levels:
            idx = int(val * (len(blocks) - 1))
            idx = max(0, min(len(blocks) - 1, idx))
            char = blocks[idx]
            
            if val > 0.4:
                parts.append(f"[bold green]{char}[/]")
            elif val > 0.15:
                parts.append(f"[bold cyan]{char}[/]")
            else:
                parts.append(f"[dim]{char}[/]")
                
        waveform_str = "".join(parts)
        self.update(f"[bold]Level:[/] {waveform_str}")


class VoiceCoderApp(App):
    CSS = """
    Screen { layout: vertical; }
    #main { height: 1fr; }
    #left { width: 42%; border: solid $accent; padding: 0 1; }
    #right { width: 58%; border: solid $accent; }
    StatusBar { height: 3; padding: 1; background: $surface; }
    SummaryPanel { height: 3; padding: 0 1; background: $panel; }
    MetricsPanel { height: 1; padding: 0 1; }
    HistoryPanel { height: 7; padding: 1; border: solid $accent-darken-2; }
    #meter-row { height: 3; padding: 0 1; }
    SpeechIndicator { width: 18; }
    #waveform { width: 1fr; }
    TranscriptPanel { height: 5; padding: 1; }
    OnboardingPanel { height: auto; max-height: 12; padding: 1; }
    #spinner-row { height: 1; padding: 0 1; }
    #agent-log { height: 1fr; }
    LoadingIndicator { height: 1; }

    /* Config Panel Styling */
    #config-form { padding: 1 2; }
    .section-header { margin-top: 1; margin-bottom: 1; }
    .config-row { height: 3; align: left middle; margin-bottom: 1; }
    .config-row-checkbox { height: 2; align: left middle; margin-bottom: 1; }
    .form-label { width: 30; text-style: bold; }
    #cfg-stt-provider, #cfg-stt-model, #cfg-wake-phrases, #cfg-api-key { width: 1fr; }
    .config-actions { margin-top: 2; align: right middle; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("m", "toggle_mute", "Mute"),
        ("l", "activate", "Listen"),
    ]

    TITLE = "Voice Coder"
    SUB_TITLE = "Hands-free Aider interface"

    def __init__(
        self,
        orchestrator: "VoiceOrchestrator",
        event_queue: queue.Queue,
        preflight: list["PreflightCheck"] | None = None,
    ) -> None:
        super().__init__()
        self._orchestrator = orchestrator
        self._events = event_queue
        self._preflight = preflight or []
        self._countdown: int | None = None
        self._spinner_label = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusBar(id="status")
        yield SummaryPanel(id="summary")
        yield MetricsPanel(id="metrics")

        with TabbedContent():
            with TabPane("Dashboard", id="tab-dashboard"):
                with Horizontal(id="meter-row"):
                    yield SpeechIndicator(id="speech")
                    yield WaveformVisualizer(id="waveform")
                yield TranscriptPanel(id="transcript")
                with Horizontal(id="main"):
                    with Vertical(id="left"):
                        yield OnboardingPanel(id="onboarding")
                        yield HistoryPanel(id="history")
                        wake_phrase = self._orchestrator._config.wakeword.phrases[0] if self._orchestrator._config.wakeword.phrases else "Hey coder"
                        yield Static(
                            "[bold]Voice commands[/]\n"
                            f"• {wake_phrase.title()}\n"
                            "• Run tests / Commit changes\n"
                            "• Run terminal: 'run git log -n 5'\n"
                            "• Explain the failing test\n"
                            "• Cancel agent / Stop listening",
                            id="help",
                        )
                    with Vertical(id="right"):
                        with Horizontal(id="spinner-row"):
                            yield LoadingIndicator(id="spinner")
                            yield Label("", id="spinner-label")
                        yield Log(id="agent-log", highlight=True)

            with TabPane("Configuration", id="tab-config"):
                with Vertical(id="config-form"):
                    yield Label("[bold cyan]Speech-to-Text Configuration[/]", classes="section-header")
                    yield Horizontal(
                        Label("STT Provider:", classes="form-label"),
                        Select(
                            [
                                ("Local Model (faster-whisper)", "local"),
                                ("OpenAI Cloud Whisper API", "openai"),
                                ("Groq Cloud Whisper API", "groq"),
                            ],
                            value=self._orchestrator._config.stt.provider,
                            id="cfg-stt-provider",
                            allow_blank=False,
                        ),
                        classes="config-row",
                    )
                    yield Horizontal(
                        Label("Local Model Size:", classes="form-label"),
                        Select(
                            [
                                ("tiny", "tiny"),
                                ("base", "base"),
                                ("small", "small"),
                                ("medium", "medium"),
                            ],
                            value=self._orchestrator._config.stt.model_size,
                            id="cfg-stt-model",
                            allow_blank=False,
                        ),
                        classes="config-row",
                    )
                    yield Horizontal(
                        Label("Wake Word Phrases:", classes="form-label"),
                        Input(
                            value=", ".join(self._orchestrator._config.wakeword.phrases),
                            placeholder="hey coder, assistant",
                            id="cfg-wake-phrases",
                        ),
                        classes="config-row",
                    )
                    yield Horizontal(
                        Label("OpenAI / Groq API Key:", classes="form-label"),
                        Input(
                            value=self._get_api_key_masked(),
                            password=True,
                            placeholder="sk-...",
                            id="cfg-api-key",
                        ),
                        classes="config-row",
                    )

                    yield Label("[bold cyan]Routing & Output Behavior[/]", classes="section-header")
                    yield Horizontal(
                        Label("LLM Intent Router Fallback:", classes="form-label"),
                        Checkbox(
                            value=self._orchestrator._config.router.llm_fallback,
                            id="cfg-llm-fallback",
                        ),
                        classes="config-row-checkbox",
                    )
                    yield Horizontal(
                        Label("Enable TTS Voice Feedback:", classes="form-label"),
                        Checkbox(
                            value=self._orchestrator._config.tts.enabled,
                            id="cfg-tts-enabled",
                        ),
                        classes="config-row-checkbox",
                    )

                    yield Horizontal(
                        Button("Save & Apply Config", variant="primary", id="btn-save-config"),
                        classes="config-actions",
                    )
        yield Footer()

    def _get_api_key_masked(self) -> str:
        key = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("GROQ_API_KEY", "")
        return "********" if key else ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save-config":
            self._save_settings()

    def _save_settings(self) -> None:
        from src.config import save_config

        provider = self.query_one("#cfg-stt-provider", Select).value
        model_size = self.query_one("#cfg-stt-model", Select).value
        wake_str = self.query_one("#cfg-wake-phrases", Input).value
        api_key = self.query_one("#cfg-api-key", Input).value
        llm_fallback = self.query_one("#cfg-llm-fallback", Checkbox).value
        tts_enabled = self.query_one("#cfg-tts-enabled", Checkbox).value

        cfg = self._orchestrator._config
        cfg.stt.provider = str(provider)
        cfg.stt.model_size = str(model_size)
        cfg.wakeword.phrases = [p.strip() for p in wake_str.split(",") if p.strip()]
        cfg.router.llm_fallback = llm_fallback
        cfg.tts.enabled = tts_enabled
        self._orchestrator._speaker._enabled = tts_enabled

        if api_key and api_key != "********":
            os.environ["OPENAI_API_KEY"] = api_key
            self._update_env_file(api_key)

        try:
            save_config(cfg)
            self._orchestrator._wakeword.update_phrases(cfg.wakeword.phrases)
            self._orchestrator._router._config = cfg.router
            self._orchestrator._router._min_confidence = cfg.router.min_confidence
            self._orchestrator._router._coding_keywords = set(k.lower() for k in cfg.router.coding_keywords)
            self._orchestrator._stt._config = cfg.stt

            self.query_one("#summary", SummaryPanel).set_summary("Settings successfully saved and loaded!")
            self.notify("Settings saved successfully!")
        except Exception as e:
            self.query_one("#summary", SummaryPanel).set_summary(f"Failed to save settings: {e}")
            self.notify(f"Error: {e}", severity="error")

    def _update_env_file(self, api_key: str) -> None:
        from pathlib import Path
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        lines = []
        key_found = False
        if env_path.exists():
            with env_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("OPENAI_API_KEY="):
                        lines.append(f"OPENAI_API_KEY={api_key}\n")
                        key_found = True
                    else:
                        lines.append(line)
        if not key_found:
            lines.append(f"OPENAI_API_KEY={api_key}\n")
        with env_path.open("w", encoding="utf-8") as f:
            f.writelines(lines)

    def on_mount(self) -> None:
        wake_phrase = self._orchestrator._config.wakeword.phrases[0] if self._orchestrator._config.wakeword.phrases else "Hey coder"
        self.query_one("#status", StatusBar).update_status(
            "idle", f"Press [bold]L[/] to listen, or say '{wake_phrase}'"
        )
        self.query_one("#transcript", TranscriptPanel).set_transcript("(waiting for speech)")
        self.query_one("#summary", SummaryPanel).set_summary("Ready.")
        self.query_one("#metrics", MetricsPanel).set_metrics("—")
        self.query_one("#history", HistoryPanel).set_history([])
        self.query_one("#onboarding", OnboardingPanel).set_checks(self._preflight)
        self.query_one("#spinner", LoadingIndicator).display = False
        self._orchestrator.start()
        self.set_interval(0.08, self._drain_events)

    def _drain_events(self) -> None:
        status = self.query_one("#status", StatusBar)
        transcript = self.query_one("#transcript", TranscriptPanel)
        summary = self.query_one("#summary", SummaryPanel)
        metrics = self.query_one("#metrics", MetricsPanel)
        history = self.query_one("#history", HistoryPanel)
        log = self.query_one("#agent-log", Log)
        speech = self.query_one("#speech", SpeechIndicator)
        waveform = self.query_one("#waveform", WaveformVisualizer)
        spinner = self.query_one("#spinner", LoadingIndicator)
        spinner_label = self.query_one("#spinner-label", Label)
        orch = self._orchestrator.state

        while True:
            try:
                event: UIEvent = self._events.get_nowait()
            except queue.Empty:
                break

            kind = event.kind

            if kind == EventKind.TRANSCRIPT:
                transcript.set_transcript(event.message)
            elif kind == EventKind.MODE:
                status.update_status(event.message, event.detail or orch.last_status, self._countdown)
            elif kind == EventKind.STATUS:
                status.update_status(orch.mode.value, event.message, self._countdown)
            elif kind == EventKind.SUMMARY:
                summary.set_summary(event.message)
            elif kind == EventKind.METRICS:
                metrics.set_metrics(event.message)
            elif kind == EventKind.HISTORY:
                history.set_history(list(orch.command_history))
            elif kind == EventKind.CLARIFY:
                summary.set_summary(event.message)
                log.write_line(f"[clarify] {event.message}")
            elif kind == EventKind.AUDIO_LEVEL:
                level = event.data.get("level", 0.0)
                waveform.add_level(level)
            elif kind == EventKind.SPEECH_ACTIVE:
                speech.set_active(bool(event.data.get("active")))
            elif kind == EventKind.SPEECH_ENDED:
                summary.set_summary("End detected — transcribing…")
            elif kind == EventKind.SPINNER:
                active = bool(event.data.get("active"))
                spinner.display = active
                if active:
                    spinner_label.update(event.message or "Working…")
                else:
                    spinner_label.update("")
            elif kind == EventKind.COUNTDOWN:
                self._countdown = int(event.data.get("seconds", 0))
                if orch.mode.value == "listening":
                    status.update_status("listening", orch.last_status, self._countdown)
            elif kind in (EventKind.TERMINAL, EventKind.AGENT, EventKind.AGENT_DONE):
                prefix = "Agent" if "agent" in kind.value else "Terminal"
                log.write_line(f"--- {prefix} ---")
                for line in (event.detail or event.message).splitlines()[:60]:
                    if line.strip():
                        log.write_line(line)
            elif kind == EventKind.ROUTE:
                log.write_line(f"[route] {event.message}")
            elif kind == EventKind.ERROR:
                log.write_line(f"[error] {event.message}")
                summary.set_summary(f"Error: {event.message[:80]}")
            elif kind == EventKind.PRELOAD:
                summary.set_summary(event.message)

    async def action_quit(self) -> None:
        self._orchestrator._shutdown.request_shutdown()
        self.exit()

    def action_toggle_mute(self) -> None:
        if self._orchestrator._audio.is_muted:
            self._orchestrator._audio.unmute()
            self.query_one("#summary", SummaryPanel).set_summary("Microphone unmuted.")
        else:
            self._orchestrator._audio.mute()
            self.query_one("#summary", SummaryPanel).set_summary("Microphone muted.")

    def action_activate(self) -> None:
        self._orchestrator._activate_listening("Manual listen (L key)")

    def on_unmount(self) -> None:
        self._orchestrator._shutdown.request_shutdown()
