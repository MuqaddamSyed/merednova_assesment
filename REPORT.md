# Voice Coder — Engineering Report

## Executive summary

Voice Coder is a locally runnable, hands-free terminal interface that connects microphone input to the **Aider** coding agent. The design prioritizes **low recurring cost**, **predictable latency**, and **demo reliability** over maximal accuracy. The pipeline is modular: capture → VAD → STT → wake word gating → intent routing → execution → terminal UI.

---

## Why Aider?

**Aider** was chosen as the coding agent because it is purpose-built for terminal pair-programming:

1. **Native CLI workflow** — fits subprocess/PTY integration without a custom IDE plugin.
2. **Repository-aware edits** — understands project files and applies patches directly.
3. **Open source & local-friendly** — no mandatory cloud UI; LLM calls are configurable via env vars.
4. **Mature messaging API** — supports `--message` one-shot and interactive `>` prompts.

Alternatives considered:

| Agent | Pros | Cons |
|-------|------|------|
| **Aider** | Terminal-native, edit-focused | Requires LLM API key |
| Claude Code / Cursor CLI | Polished | Less scriptable for PTY injection in a student project |
| Raw `openai` API | Full control | Must rebuild file editing, context, and git flow |

For a voice layer, the agent should accept **plain-text prompts** and return **streamable terminal output** — Aider satisfies both.

---

## Why faster-whisper?

**faster-whisper** implements OpenAI Whisper with CTranslate2, yielding **2–4× faster** inference than the original PyTorch Whisper on CPU, with lower memory via `int8` quantization.

| Criterion | faster-whisper (local) | Cloud STT (e.g. Google, Deepgram) |
|-----------|------------------------|-----------------------------------|
| Cost per hour | Fixed (electricity) | Per-minute billing |
| Privacy | Audio stays on device | Audio leaves machine |
| Latency | ~0.5–2s for short utterances on CPU | Network RTT + queue |
| Offline | Yes (after model download) | No |
| Accuracy | Good with `base`/`small` | Often slightly better |

**Tradeoff chosen:** `base` model with `int8` on CPU — acceptable WER for command-style speech, fast enough for conversational demos. For noisier environments, `small` or GPU `float16` is a one-line config change.

**Streaming note:** True streaming STT would reduce perceived latency but adds complexity (partial hypotheses, endpointing conflicts with VAD). This project uses **segment-based** transcription after Silero detects utterance end — simpler and avoids transcribing silence.

---

## Latency vs accuracy

| Stage | Typical latency | Accuracy impact |
|-------|-----------------|-----------------|
| Audio chunk (30 ms) | negligible | — |
| Silero VAD | ~1–5 ms/chunk | Threshold trades false starts vs missed speech |
| Whisper `base` | 0.5–2 s / utterance | Dominant bottleneck |
| Routing (regex) | &lt;1 ms | High precision for known commands |
| Aider LLM | 5–60+ s | Dominated by model, not voice stack |

**Optimizations applied:**

- VAD gates STT — no Whisper call during silence.
- `beam_size=1` for greedy decoding speed.
- Wake word on transcript avoids continuous STT in idle mode.

**If latency is critical:** `tiny` model, GPU, or shorter `min_silence_ms` (risks cutting off trailing words).

---

## Hybrid STT Architecture (Local & Cloud)

We have upgraded the transcription pipeline to support a hybrid STT approach:

1. **Cloud STT Integration (OpenAI & Groq)**: Provides near-zero startup time, robust noise reduction, and extremely fast (<200ms) transcription.
2. **Local STT Fallback**: A local `faster-whisper` model (`base` / `int8` on CPU) remains ready to take over automatically if network latency spikes, API limits are reached, or internet connectivity is lost.
3. **Zero-overhead implementation**: The API calls are made directly through Python's standard `urllib.request` using an in-memory WAV buffer, avoiding heavy external library wrappers.

---

## Wake word design

Two complementary mechanisms:

1. **Transcript phrase matching (primary)** — after STT, check for "hey coder", "assistant", etc. Simple, no extra model, works well when the user speaks clearly.
2. **openWakeWord (optional)** — lightweight ONNX models on raw audio for pre-STT activation; configured but not required for MVP.

**Rationale:** Pure audio wake word models add dependency weight and false positives in noisy environments. Phrase matching post-STT is **good enough for a coding assistant** where the user intentionally addresses the system. openWakeWord is included as an upgrade path for true hands-free idle listening.

**Limitations:**

- Saying the wake phrase in a coding prompt could theoretically trigger activation — mitigated by requiring idle state.
- Homophones ("hay coder") may be missed — configurable phrase list helps.

---

## Command routing decisions

Routing uses **regex + keyword rules** first (no LLM cost, deterministic, testable):

| Intent | Signals |
|--------|---------|
| SYSTEM | "stop listening", "mute", "exit" |
| TERMINAL | "run tests", "commit changes", allowlisted aliases |
| NAVIGATION | "open file X", "search for Y" |
| CODING | Verbs: create, fix, explain, …; default fallback |

**LLM Intent Router Fallback**: If the regex classifier confidence is below `min_confidence` (e.g., 0.70), the system makes a fast JSON schema request to `gpt-4o-mini` to classify the intent (SYSTEM, TERMINAL, NAVIGATION, CODING) and extract key parameters dynamically.

**Voice Gating & Yes/No Confirmation**: Any terminal command that is not in the static allowlist (e.g. custom commands matched via `"run <command>"`) is flagged for confirmation. The orchestrator enters a confirmation state and asks the user: *"Run terminal command '...'? Say Yes or No"*. The user confirms verbally, enabling safe hands-free execution of custom commands without compromising default safety boundaries.

---

## Aider integration approach

1. **Preferred:** `pexpect` PTY session — persistent context, natural multi-turn coding.
2. **Fallback:** `aider --message "..." --yes` subprocess — works when PTY fails or for one-shot prompts.

`--dry-run` mode logs prompts without calling Aider — useful for CI and UI development without API keys.

---

## Terminal UI (Rich / Textual)

**Textual** provides:

- Live-updating panes without fighting `curses` boilerplate.
- **Tabbed Layout**: A tabbed structure separating the main execution **Dashboard** from the **Configuration** panel.
- **Form Controls**: Interactive select inputs, text fields, checkboxes, and buttons to adjust settings (STT provider, model size, API keys, wake phrases) and persist them directly to `config.yaml` and `.env`.
- **Scrolling Waveform Visualizer**: A custom real-time visualizer that charts microphone amplitude levels using unicode block characters: ` ▂▃▅▇█▆▃  `.
- The orchestrator pushes events through a `queue.Queue` to keep **audio processing off the UI thread** — critical for glitch-free capture.

---

## Limitations

1. **English-first** — Whisper language fixed to `en` in config.
2. **Single speaker** — no diarization; background voices may trigger VAD.
3. **Aider requires API keys** — voice layer does not solve LLM authentication.
4. **Wake word accuracy** — transcript-based detection needs a full utterance before activation unless openWakeWord is tuned.
5. **Platform support** — tested for macOS/Linux; Windows audio stack not validated.
6. **No true streaming STT** — user waits until end of sentence for transcription.

---

## Future improvements

| Area | Enhancement |
|------|-------------|
| STT | Partial streaming hypotheses in UI |
| Wake word | Custom trained openWakeWord model ("hey coder") |
| Agent | Support Claude Code CLI, multi-agent switching |
| Context | Inject last test output automatically before "explain error" |
| Metrics | Latency histograms (VAD → STT → Aider) |
| CI | Recorded WAV integration tests |

---

## Conclusion

Voice Coder demonstrates **systems integration**: real-time audio, ML inference, safe command execution, and agent automation in one cohesive terminal experience. Technology choices favor **local, testable, cost-bounded** components while leaving clear upgrade paths for production hardening.

---

## Use of AI Tools Disclosure

In accordance with the selection criteria guidelines, the following discloses the use of AI tools in this project:
- **AI Tool Used**: Antigravity (a pair-programming AI agent designed by the Google DeepMind team).
- **Scope of Use**: The AI assistant was actively used to design the architecture, refactor the hybrid STT client, construct the confirmation gating mechanisms, implement the tabbed configuration UI, build the scrolling visualizer, write unit tests, and compile the final engineering documentation.
