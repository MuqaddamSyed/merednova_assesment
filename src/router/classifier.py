"""Lightweight intent classification via regex and keyword routing."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from src.config import RouterConfig
from src.router.intents import Intent

logger = logging.getLogger("voice_coder.router")

_SYSTEM_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"\bstop listening\b", re.I), "stop_listening", 0.98),
    (re.compile(r"\b(mute|silence) (the )?microphone\b", re.I), "mute", 0.95),
    (re.compile(r"\b(resume|unmute) (listening|microphone)?\b", re.I), "resume", 0.95),
    (re.compile(r"\b(cancel|stop|abort)( the)? (agent|aider|task)?\b", re.I), "cancel_agent", 0.92),
    (re.compile(r"\b(exit|quit|shutdown)\b", re.I), "exit", 0.98),
]

_TERMINAL_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"\brun tests?\b", re.I), "run tests", 0.95),
    (re.compile(r"\bstart (the )?server\b", re.I), "start server", 0.93),
    (re.compile(r"\bgit status\b", re.I), "git status", 0.98),
    (re.compile(r"\bcommit(?: changes)? with message (?P<msg>.+)", re.I), "commit_with_message", 0.94),
    (re.compile(r"\bcommit changes?\b", re.I), "commit changes", 0.92),
    (re.compile(r"\b(pytest|run pytest)\b", re.I), "run tests", 0.90),
    (re.compile(r"^\s*(run terminal|run command|run shell|execute|run) (?P<cmd>.+)", re.I), "custom_command", 0.50),
]

_NAV_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"\bopen (file|the file) (?P<path>[\w./-]+)\b", re.I), "open_file", 0.93),
    (re.compile(r"\bsearch for (?P<query>.+)\b", re.I), "search", 0.90),
    (re.compile(r"\bfind (?P<query>.+) (in |code)\b", re.I), "search", 0.88),
]

_CODING_VERBS = re.compile(
    r"\b(create|build|implement|fix|explain|refactor|add|update|write|debug|optimize|"
    r"generate|modify|change|remove|delete|improve|patch|show|give)\b",
    re.I,
)

_CODING_REQUEST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(give|show) me\b.*\b(code|program|script|function|class|example)\b", re.I),
    re.compile(r"\b(simple|example)\b.*\b(code|program|script)\b", re.I),
]


@dataclass
class RoutedCommand:
    intent: Intent
    action: str
    payload: str
    raw_text: str
    confidence: float = 0.0
    needs_clarification: bool = False
    clarification_prompt: str = ""
    needs_confirmation: bool = False
    confirmation_prompt: str = ""


class CommandRouter:
    """Classify transcribed speech into actionable commands."""

    def __init__(self, config: RouterConfig) -> None:
        self._config = config
        self._coding_keywords = set(k.lower() for k in config.coding_keywords)
        self._terminal_aliases = {k.lower(): v for k, v in config.terminal_aliases.items()}
        self._min_confidence = config.min_confidence
        self._clarify = config.clarify_on_low_confidence

    def route(self, text: str) -> RoutedCommand:
        text = text.strip()
        if not text:
            return RoutedCommand(Intent.UNKNOWN, "noop", "", text, 0.0)

        candidates: list[RoutedCommand] = []

        for pattern, action, conf in _SYSTEM_PATTERNS:
            if pattern.search(text):
                candidates.append(RoutedCommand(Intent.SYSTEM, action, text, text, conf))

        for pattern, alias_key, conf in _TERMINAL_PATTERNS:
            match = pattern.search(text)
            if match:
                if alias_key == "commit_with_message":
                    msg = match.group("msg").strip().strip('"').strip("'")
                    candidates.append(
                        RoutedCommand(Intent.TERMINAL, alias_key, msg[:120], text, conf)
                    )
                elif alias_key == "custom_command":
                    cmd = match.group("cmd").strip().strip('"').strip("'")
                    candidates.append(
                        RoutedCommand(Intent.TERMINAL, alias_key, cmd, text, conf)
                    )
                else:
                    cmd = self._terminal_aliases.get(alias_key.lower(), alias_key)
                    candidates.append(
                        RoutedCommand(Intent.TERMINAL, alias_key, cmd, text, conf)
                    )

        for pattern, action, conf in _NAV_PATTERNS:
            match = pattern.search(text)
            if match:
                payload = match.groupdict().get("path") or match.groupdict().get("query", "")
                candidates.append(
                    RoutedCommand(Intent.NAVIGATION, action, payload.strip(), text, conf)
                )

        if _CODING_VERBS.search(text) or self._looks_like_coding(text):
            candidates.append(RoutedCommand(Intent.CODING, "prompt", text, text, 0.85))

        if not candidates:
            result = RoutedCommand(Intent.CODING, "prompt", text, text, 0.60)
        else:
            result = max(candidates, key=lambda c: c.confidence)

        if result.confidence < self._min_confidence and self._config.llm_fallback:
            logger.info("Confidence low (%.0f%%), trying LLM fallback...", result.confidence * 100)
            llm_result = self._llm_route(text)
            if llm_result and llm_result.confidence >= self._min_confidence:
                logger.info("LLM route succeeded: %s", llm_result.intent.value)
                result = llm_result

        # Check if the command requires voice confirmation (e.g. any terminal command not in the static allowlist)
        static_cmds = {"run tests", "run test", "start server", "git status", "commit changes", "commit_with_message"}
        if result.intent == Intent.TERMINAL and result.action not in static_cmds:
            result.needs_confirmation = True
            result.confirmation_prompt = f"Run terminal command '{result.payload}'? (Say Yes or No)"
        elif self._clarify and result.confidence < self._min_confidence:
            alts = self._suggest_alternatives(text)
            if alts:
                result.needs_clarification = True
                result.clarification_prompt = f"Did you mean: {', '.join(alts)}?"

        logger.info(
            "Routed %s: %s (%.0f%%)%s%s",
            result.intent.value,
            result.action,
            result.confidence * 100,
            " [clarify]" if result.needs_clarification else "",
            " [confirm]" if result.needs_confirmation else "",
        )
        return result

    def _llm_route(self, text: str) -> RoutedCommand | None:
        import os
        import urllib.request
        import urllib.error
        import json

        api_key = os.environ.get("OPENAI_API_KEY", "")
        endpoint = "https://api.openai.com/v1/chat/completions"
        model = self._config.llm_model

        if not api_key:
            api_key = os.environ.get("GROQ_API_KEY", "")
            if api_key:
                endpoint = "https://api.groq.com/openai/v1/chat/completions"
                # Use Llama-3 model for Groq completions
                model = "llama-3.3-70b-versatile"

        if not api_key:
            return None

        # Build prompt for intent classification
        system_prompt = (
            "You are the intent router for a voice-controlled coding assistant.\n"
            "Classify the spoken query into one of these intents:\n"
            "1. SYSTEM: System commands. Supported actions: 'stop_listening' (pause), "
            "'mute' (mute mic), 'resume' (unmute mic), 'cancel_agent' (stop aider), 'exit' (quit app).\n"
            "2. TERMINAL: Terminal commands. Supported actions: 'run tests' (pytest), "
            "'start server' (run flask), 'git status', 'commit changes', 'commit_with_message' (if they specify a message).\n"
            "3. NAVIGATION: Search or files. Supported actions: 'open_file' (payload: path), 'search' (payload: query).\n"
            "4. CODING: Coding prompt sent to AI coding agent. Action: 'prompt'. Payload: the coding instruction.\n\n"
            "Reply strictly with a JSON object containing:\n"
            "{\n"
            '  "intent": "SYSTEM" | "TERMINAL" | "NAVIGATION" | "CODING",\n'
            '  "action": "...",\n'
            '  "payload": "...",\n'
            '  "confidence": 0.0 to 1.0\n'
            "}"
        )

        user_content = f"User said: '{text}'"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0
        }

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                resp = json.loads(res.read().decode("utf-8"))
                choice = resp["choices"][0]["message"]["content"]
                data = json.loads(choice)
                
                # Convert string intent to Enum
                from src.router.intents import Intent
                intent_map = {
                    "SYSTEM": Intent.SYSTEM,
                    "TERMINAL": Intent.TERMINAL,
                    "NAVIGATION": Intent.NAVIGATION,
                    "CODING": Intent.CODING
                }
                intent_val = intent_map.get(data.get("intent", "").upper(), Intent.CODING)
                action = data.get("action", "prompt")
                payload_val = data.get("payload", text)
                confidence = float(data.get("confidence", 0.8))
                
                # Check for commit_with_message action
                if intent_val == Intent.TERMINAL and action == "commit_with_message" and not payload_val:
                     payload_val = "Voice Coder commit"

                return RoutedCommand(
                    intent=intent_val,
                    action=action,
                    payload=payload_val,
                    raw_text=text,
                    confidence=confidence
                )
        except Exception as exc:
            logger.debug("LLM fallback classification failed: %s", exc)
            return None

    def _suggest_alternatives(self, text: str) -> list[str]:
        lower = text.lower()
        alts: list[str] = []
        if any(w in lower for w in ("test", "pytest", "run")):
            alts.append("run tests")
        if "commit" in lower:
            alts.append("commit changes")
        if "status" in lower or "git" in lower:
            alts.append("git status")
        if "server" in lower or "start" in lower:
            alts.append("start server")
        return alts[:3]

    def _looks_like_coding(self, text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in self._coding_keywords) or any(
            pattern.search(text) for pattern in _CODING_REQUEST_PATTERNS
        )
