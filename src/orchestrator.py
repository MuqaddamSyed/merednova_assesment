"""Core voice pipeline orchestrating audio -> VAD -> STT -> routing -> actions."""

from __future__ import annotations

import logging
import queue
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np

from src.agent.aider_client import AiderClient
from src.audio.capture import AudioCapture
from src.commands.system import ListeningMode, SystemCommandHandler
from src.commands.terminal import TerminalCommandHandler
from src.config import AppConfig
from src.events.types import EventKind, UIEvent
from src.router.classifier import CommandRouter, RoutedCommand
from src.router.intents import Intent
from src.session.context import SessionContext
from src.stt.whisper import WhisperTranscriber
from src.utils.metrics import LatencyMetrics
from src.utils.shutdown import ShutdownCoordinator
from src.utils.tts import Speaker
from src.vad.silero import SileroVAD
from src.wakeword.detector import WakeWordDetector

if TYPE_CHECKING:
    from src.vad.silero import SpeechSegment

logger = logging.getLogger("voice_coder.orchestrator")


class AppMode(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    EXECUTING = "executing"


@dataclass
class OrchestratorState:
    mode: AppMode = AppMode.IDLE
    last_transcript: str = ""
    last_status: str = "Say 'Hey coder' to activate"
    last_summary: str = ""
    agent_busy: bool = False
    speech_active: bool = False
    audio_level: float = 0.0
    command_history: list[str] = field(default_factory=list)


class VoiceOrchestrator:
    """Background pipeline with thread-safe typed UI events."""

    def __init__(
        self,
        config: AppConfig,
        shutdown: ShutdownCoordinator,
        event_queue: queue.Queue[UIEvent] | None = None,
    ) -> None:
        self._config = config
        self._shutdown = shutdown
        self._events = event_queue or queue.Queue()
        self.state = OrchestratorState()
        wake_phrase = config.wakeword.phrases[0] if config.wakeword.phrases else "Hey coder"
        self.state.last_status = f"Say '{wake_phrase}' to activate"
        self.context = SessionContext()

        self._audio = AudioCapture(config.audio, on_chunk=self._on_audio_chunk)
        self._vad = SileroVAD(config.vad, sample_rate=config.audio.sample_rate)
        self._vad.set_callbacks(
            on_speech_start=self._on_speech_start,
            on_speech_end=self._on_speech_end,
        )
        self._stt = WhisperTranscriber(config.stt)
        self._wakeword = WakeWordDetector(config.wakeword, config.audio.sample_rate)
        self._router = CommandRouter(config.router)
        self._terminal = TerminalCommandHandler(config.router.terminal_aliases)
        self._system = SystemCommandHandler(self._audio, shutdown)
        self._speaker = Speaker(config.tts.enabled, config.tts.max_chars)
        self._agent = AiderClient(
            config.agent,
            on_output=self._on_agent_output,
            on_line=lambda line: self._push(UIEvent(EventKind.AGENT, detail=line)),
        )
        self._confirming_command = None
        self._pending_transcript: str | None = None
        self._pending_transcript_time: float = 0.0

        self._chunk_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=200)
        self._worker: threading.Thread | None = None
        self._last_active = time.monotonic()
        self._stt_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt")
        self._stt_future: Future | None = None
        self._metrics = LatencyMetrics()
        self._stopped = False
        self._stop_lock = threading.Lock()

    def _push(self, event: UIEvent) -> None:
        self._events.put(event)

    def _record_history(self, entry: str) -> None:
        self.state.command_history.append(entry)
        if len(self.state.command_history) > 8:
            self.state.command_history = self.state.command_history[-8:]
        self._push(UIEvent(EventKind.HISTORY, message=entry))

    def _push_metrics(self) -> None:
        self._push(UIEvent(EventKind.METRICS, message=self._metrics.summary()))

    def _announce(self, summary: str, speak: bool = True) -> None:
        self.state.last_summary = summary
        self._push(UIEvent.summary(summary))
        if speak:
            self._speaker.speak(summary)

    def _on_audio_chunk(self, chunk: np.ndarray) -> None:
        if self._shutdown.requested:
            return
        level = min(1.0, float(np.abs(chunk).mean() * 12))
        self.state.audio_level = level
        self._push(UIEvent.audio_level(level))
        try:
            self._chunk_queue.put_nowait(chunk)
        except queue.Full:
            pass

    def _on_speech_start(self) -> None:
        self.state.speech_active = True
        self._push(UIEvent.speech_active(True))

    def _on_speech_end(self) -> None:
        self.state.speech_active = False
        self._push(UIEvent.speech_active(False))
        self._push(UIEvent(EventKind.SPEECH_ENDED, message="End detected"))

    def _on_agent_output(self, text: str) -> None:
        self.context.record_aider(text)

    def start(self) -> None:
        self._audio.start()
        self._agent.start()
        self._worker = threading.Thread(target=self._process_loop, daemon=True, name="voice-pipeline")
        self._worker.start()
        self._shutdown.register(self.stop)
        threading.Thread(target=self._preload_whisper, daemon=True, name="whisper-preload").start()
        wake_phrase = self._config.wakeword.phrases[0] if self._config.wakeword.phrases else "Hey coder"
        self._push(UIEvent.status(f"Voice Coder ready. Press L or say '{wake_phrase}'."))
        logger.info("Orchestrator started")

    def _preload_whisper(self) -> None:
        self._push(UIEvent(EventKind.PRELOAD, message="Loading Whisper model..."))
        self._push(UIEvent.spinner(True, "Loading Whisper..."))
        try:
            self._stt.warmup()
            self._push(UIEvent(EventKind.PRELOAD, message="Whisper ready"))
        except Exception as exc:
            self._push(UIEvent(EventKind.ERROR, message=f"Whisper preload failed: {exc}"))
        finally:
            self._push(UIEvent.spinner(False))

    def stop(self) -> None:
        with self._stop_lock:
            if self._stopped:
                return
            self._stopped = True

        try:
            segment = self._vad.flush()
            if segment:
                self._handle_segment(segment)
        except Exception:
            pass
        self._stt_pool.shutdown(wait=False, cancel_futures=True)
        self._audio.stop()
        self._agent.stop()
        logger.info("Orchestrator stopped")

    def _process_loop(self) -> None:
        while not self._shutdown.requested:
            try:
                chunk = self._chunk_queue.get(timeout=0.5)
            except queue.Empty:
                self._check_wake_timeout()
                continue

            if self._wakeword.check_audio(chunk) and self._system.mode == ListeningMode.IDLE:
                self._activate_listening("Wake word detected")
                continue

            segment = self._vad.process_chunk(chunk)
            if segment:
                self._handle_segment_async(segment)

    def _check_wake_timeout(self) -> None:
        if self._system.mode != ListeningMode.ACTIVE:
            return
        elapsed = time.monotonic() - self._last_active
        remaining = int(self._config.system.wake_timeout_sec - elapsed)
        if remaining > 0:
            self._push(UIEvent.countdown(remaining))
        if elapsed > self._config.system.wake_timeout_sec:
            self._system.deactivate()
            self.state.mode = AppMode.IDLE
            self.state.last_status = "Timed out — say wake word again"
            self._push(UIEvent(EventKind.MODE, message="idle", detail="Listening timed out"))

    def _activate_listening(self, reason: str = "Wake word detected") -> None:
        self._system.activate()
        self.state.mode = AppMode.LISTENING
        self.state.last_status = "Listening — speak your command"
        self._last_active = time.monotonic()
        self._push(UIEvent(EventKind.MODE, message="listening", detail=reason))
        self._announce("Listening.", speak=False)

        # If user pressed L and there's a recent transcript that was ignored, dispatch it now
        if self._pending_transcript and (time.monotonic() - self._pending_transcript_time) < 10.0:
            text = self._pending_transcript
            self._pending_transcript = None
            logger.info("Dispatching pending transcript: %s", text[:80])
            self._push(UIEvent(EventKind.TRANSCRIPT, message=text))
            self._dispatch(text)

    def _handle_segment_async(self, segment: "SpeechSegment") -> None:
        self.state.mode = AppMode.PROCESSING
        self._metrics.begin_stt()
        self._push(UIEvent.spinner(True, "Transcribing..."))
        self._push(UIEvent.status("Transcribing..."))
        self._stt_future = self._stt_pool.submit(self._stt.transcribe_segment, segment)
        threading.Thread(
            target=self._await_transcription,
            args=(self._stt_future,),
            daemon=True,
            name="stt-await",
        ).start()

    def _await_transcription(self, future: Future) -> None:
        try:
            result = future.result(timeout=120)
        except Exception as exc:
            logger.exception("STT failed")
            self._push(UIEvent(EventKind.ERROR, message=str(exc)))
            self._push(UIEvent.spinner(False))
            self.state.mode = (
                AppMode.LISTENING if self._system.mode == ListeningMode.ACTIVE else AppMode.IDLE
            )
            return

        self._push(UIEvent.spinner(False))
        self._metrics.end_stt()
        self._push_metrics()
        text = result.text
        if not text:
            self.state.last_status = "Couldn't understand — try again"
            self._push(UIEvent.status(self.state.last_status))
            self.state.mode = (
                AppMode.LISTENING if self._system.mode == ListeningMode.ACTIVE else AppMode.IDLE
            )
            return

        self.state.last_transcript = text
        self.context.last_transcript = text
        self._push(UIEvent(EventKind.TRANSCRIPT, message=text))
        self._last_active = time.monotonic()

        # Check if we are currently in voice confirmation gating mode
        if self._confirming_command is not None:
            cmd = self._confirming_command
            clean_text = text.lower().strip().strip(".,!?")
            if any(w in clean_text for w in ("yes", "yeah", "ok", "sure", "yep", "do it", "confirm")):
                self._confirming_command = None
                self._announce("Confirmed. Executing.")
                self.state.mode = AppMode.LISTENING
                if cmd.intent == Intent.TERMINAL:
                    self._run_terminal(cmd, confirmed=True)
                elif cmd.intent == Intent.NAVIGATION:
                    self._run_navigation(cmd)
                elif cmd.intent == Intent.CODING:
                    self._run_coding(cmd)
            elif any(w in clean_text for w in ("no", "nope", "cancel", "negative", "don't", "abort")):
                self._confirming_command = None
                self._announce("Cancelled. Command aborted.")
                self.state.mode = AppMode.LISTENING
                self._push(UIEvent.status("Cancelled command."))
            else:
                self._announce("Please say yes or no to confirm.", speak=True)
                self._push(UIEvent.status("Confirm: Say yes or no."))
                self.state.mode = AppMode.LISTENING
            return

        if self._system.mode == ListeningMode.IDLE:
            if self._wakeword.check_transcript(text):
                remainder = self._wakeword.strip_wake_phrase(text)
                self._activate_listening("Wake word in speech")
                if remainder:
                    self._dispatch(remainder)
            elif self._should_auto_dispatch_from_idle(text):
                logger.info("Auto-activating from idle for direct coding request: %s", text[:80])
                self._activate_listening("Direct coding request")
                self._dispatch(text)
            else:
                # Store transcript so pressing L can replay it
                self._pending_transcript = text
                self._pending_transcript_time = time.monotonic()
                logger.info("Speech in IDLE mode (no wake word): '%s' — press L or say wake word", text[:80])
                self.state.mode = AppMode.IDLE
                wake_phrase = self._config.wakeword.phrases[0] if self._config.wakeword.phrases else "Hey coder"
                self.state.last_status = f"Say '{wake_phrase}' or press L to activate"
                self._push(UIEvent(EventKind.MODE, message="idle", detail="Wake word not found"))
                self._push(UIEvent.status(self.state.last_status))
            return

        if self._wakeword.check_transcript(text):
            remainder = self._wakeword.strip_wake_phrase(text)
            if not remainder:
                self._push(UIEvent.status("Yes? I'm listening."))
                return
            text = remainder

        self._dispatch(text)

    def _handle_segment(self, segment: "SpeechSegment") -> None:
        self._handle_segment_async(segment)

    def _should_auto_dispatch_from_idle(self, text: str) -> bool:
        routed = self._router.route(text)
        return routed.intent == Intent.CODING and not routed.needs_clarification

    def _dispatch(self, text: str) -> None:
        self._metrics.begin_route()
        routed = self._router.route(text)
        self._metrics.end_route()
        self._push_metrics()

        if routed.needs_clarification:
            self._push(UIEvent(EventKind.CLARIFY, message=routed.clarification_prompt))
            self._announce(routed.clarification_prompt, speak=False)
            self.state.mode = AppMode.LISTENING
            return

        if routed.needs_confirmation:
            self._confirming_command = routed
            self._push(UIEvent(EventKind.CLARIFY, message=routed.confirmation_prompt))
            self._announce(routed.confirmation_prompt, speak=True)
            self.state.mode = AppMode.LISTENING
            return

        conf_pct = int(routed.confidence * 100)
        route_msg = f"{routed.intent.value} → {routed.action} ({conf_pct}%)"
        self._record_history(f"{text[:50]} → {route_msg}")
        self._push(UIEvent(EventKind.ROUTE, message=route_msg, detail=text))

        if routed.intent == Intent.SYSTEM:
            if routed.action == "cancel_agent":
                self._agent.cancel()
                self.state.agent_busy = False
                self._push(UIEvent.spinner(False))
            result = self._system.handle(routed.action)
            summary = result.message
            self._announce(summary)
            self.state.last_status = summary
            self._push(UIEvent.status(summary))
            if result.new_mode == ListeningMode.IDLE:
                self.state.mode = AppMode.IDLE
            elif result.new_mode == ListeningMode.ACTIVE:
                self.state.mode = AppMode.LISTENING
            return

        if routed.intent == Intent.TERMINAL:
            self._run_terminal(routed)
            self.state.mode = AppMode.LISTENING
            self._push(UIEvent(EventKind.MODE, message="listening", detail="Command done"))
            return

        if routed.intent == Intent.NAVIGATION:
            self._run_navigation(routed)
            self.state.mode = AppMode.LISTENING
            self._push(UIEvent(EventKind.MODE, message="listening", detail="Navigation done"))
            return

        if routed.intent == Intent.CODING:
            self._run_coding(routed)
            return

        self._announce("Could not understand command.")
        self.state.mode = AppMode.LISTENING

    def _run_terminal(self, routed: RoutedCommand, confirmed: bool = False) -> None:
        cmd_label = routed.action
        if routed.action == "commit_with_message":
            cmd_label = f"commit: {routed.payload[:40]}"
        elif routed.action == "custom_command":
            cmd_label = f"custom: {routed.payload[:40]}"
        summary = f"Running: {cmd_label}"
        self._announce(summary, speak=False)
        self._push(UIEvent.status(summary))
        self.state.mode = AppMode.EXECUTING
        self._push(UIEvent(EventKind.MODE, message="executing", detail=summary))

        if confirmed or routed.action != "custom_command":
            if routed.action == "custom_command":
                result = self._terminal.execute_confirmed(routed.payload)
            else:
                payload = routed.payload if routed.action == "commit_with_message" else routed.payload
                result = self._terminal.execute(routed.action, payload)
        else:
            result = self._terminal.execute(routed.action, routed.payload)

        output = (result.stdout or "") + (result.stderr or "")
        self.context.record_terminal(routed.action, output, result.success)
        self._push(UIEvent(EventKind.TERMINAL, detail=output[:3000]))
        if result.success:
            done = f"Done — {cmd_label} succeeded"
        else:
            done = f"Done — {cmd_label} failed"
        self._announce(done)

    def _run_navigation(self, routed: RoutedCommand) -> None:
        self.state.mode = AppMode.EXECUTING
        self._push(UIEvent(EventKind.MODE, message="executing", detail=f"Navigating: {routed.action}"))
        if routed.action == "open_file":
            result = self._terminal.open_file_hint(routed.payload)
        else:
            result = self._terminal.search_code(routed.payload)
        self._push(UIEvent(EventKind.TERMINAL, detail=result.stdout))
        self._announce(result.stdout[:120] or "Search complete.")

    def _run_coding(self, routed: RoutedCommand) -> None:
        prompt = self.context.enrich_coding_prompt(routed.payload)
        backend = self._agent.describe_backend()
        summary = f"Routed to Aider: {routed.payload[:80]}"
        self._announce(summary, speak=False)
        self.state.agent_busy = True
        self.state.mode = AppMode.EXECUTING
        self._push(UIEvent(EventKind.MODE, message="executing", detail="Aider working"))
        self._push(UIEvent.spinner(True, "Aider thinking..."))
        self._push(UIEvent.status(f"{backend}..."))
        self._push(UIEvent.summary(f"{summary} [{backend}]"))

        def _work() -> None:
            output, success = self._agent.send_prompt(prompt)
            self.state.agent_busy = False
            self.state.mode = AppMode.LISTENING
            self._push(UIEvent(EventKind.MODE, message="listening", detail="Aider finished"))
            self._push(UIEvent.spinner(False))
            self.context.record_aider(output)
            status = "Aider finished" if success else "Aider error"
            self._push(UIEvent(EventKind.AGENT_DONE, message=status, detail=output[:3000]))
            self._announce(status if success else "Aider error. Check API key.")

        threading.Thread(target=_work, daemon=True, name="aider-worker").start()
