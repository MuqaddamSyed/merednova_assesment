# Voice Coder

**Hands-free voice interface for terminal-based AI coding agents (Aider).**

Speak coding prompts, run tests, and control your dev workflow without touching the keyboard. Built for live demos and internship-quality engineering.

## Architecture

```
┌─────────────┐    ┌──────────┐    ┌─────────────┐    ┌──────────────┐
│ Microphone  │───▶│ Silero   │───▶│ faster-     │───▶│ Command      │
│ (sounddevice)│   │ VAD      │    │ whisper STT │    │ Router       │
└─────────────┘    └──────────┘    └─────────────┘    └──────┬───────┘
       │                │                  │                    │
       │                │                  │         ┌────────┼────────┐
       │                │                  │         ▼        ▼        ▼
       │                │                  │    ┌────────┐ ┌────┐ ┌────────┐
       │                │                  │    │ Aider  │ │Term│ │ System │
       │                │                  │    │ (PTY)  │ │cmd │ │ cmds   │
       └────────────────┴──────────────────┴────┴────────┴ └────┴ └────────┘
                                        │
                                        ▼
                              ┌──────────────────┐
                              │ Textual Terminal │
                              │ UI (Rich)        │
                              └──────────────────┘
```

### Event flow

1. **Idle** — microphone streams audio; VAD watches for speech.
2. **Wake** — user says _"Hey agent"_ → transcript or openWakeWord triggers **ACTIVE** mode.
3. **Capture** — VAD detects speech start/end; only completed utterances are transcribed (saves CPU).
4. **Route** — regex/keyword classifier picks: coding prompt, terminal command, navigation, or system.
5. **Execute** — Aider PTY receives prompts; allowlisted shell commands run safely.
6. **Display** — Textual UI shows transcript, mode, agent output, and status.

## Project structure

```
merednova_assesment/
├── config.yaml
├── requirements.txt
├── pyproject.toml
├── README.md
├── REPORT.md
├── src/
│   ├── main.py              # Entry point
│   ├── config.py            # YAML configuration
│   ├── orchestrator.py      # Pipeline coordinator
│   ├── audio/               # Microphone capture
│   ├── vad/                 # Silero VAD
│   ├── stt/                 # faster-whisper
│   ├── wakeword/            # Wake phrase detection
│   ├── router/              # Intent classification
│   ├── agent/               # Aider PTY client
│   ├── commands/            # Terminal & system handlers
│   ├── ui/                  # Textual app
│   └── utils/               # Logging, shutdown
├── tests/
└── scripts/
    ├── demo.sh
    └── run_headless.sh
```

## Requirements

- **Python 3.10+**
- **macOS or Linux** (Windows untested)
- Microphone
- Optional: NVIDIA GPU for faster Whisper inference

## Setup

```bash
cd merednova_assesment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install aider-chat   # coding agent CLI
```

### Aider API keys (fixes OpenRouter browser redirect)

When Voice Coder starts Aider without an API key, Aider opens **[OpenRouter sign-up](https://openrouter.ai/sign-up)** in your browser (`localhost:8484` OAuth). That is **Aider asking for an LLM**, not Voice Coder itself.

**Pick one approach:**

**Option A — OpenAI (simplest)**

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-...
export $(grep -v '^#' .env | xargs)   # or: source .env if you add export lines
```

`config.yaml` already uses `--model gpt-4o`. Restart Voice Coder.

**Option B — OpenRouter API key (no browser OAuth)**

1. Create an account at [OpenRouter](https://openrouter.ai/)
2. Create an API key at [openrouter.ai/keys](https://openrouter.ai/keys) (not the OAuth redirect)
3. Set in `.env`:

```bash
export OPENROUTER_API_KEY=sk-or-v1-your-key
```

4. Update `config.yaml` agent args:

```yaml
args:
  [
    "--yes",
    "--no-auto-commits",
    "--model",
    "openrouter/anthropic/claude-3.5-sonnet",
  ]
```

**Option C — Test voice only (no LLM)**

```bash
python -m src.main --dry-run
```

### First run (downloads models)

- **Silero VAD** — downloaded via `torch.hub` on first start (~2 MB)
- **faster-whisper** — downloads `base` model on first transcription (~150 MB)
- **openWakeWord** (optional) — if configured in `config.yaml`

## Usage

```bash
make setup
make check
make run          # full UI
make dry-run      # voice only, no Aider
make test-fast    # unit tests
```

See **[DEMO.md](DEMO.md)** for the full live demo script with expected UI states.

```bash
export PYTHONPATH=.
python -m src.main
```

### Config profiles

```bash
python -m src.main --profile demo     # tiny Whisper, longer timeout — best for live demos
python -m src.main --profile quality  # small Whisper — better accuracy
```

### Options

| Flag                    | Description                     |
| ----------------------- | ------------------------------- |
| `--dry-run`             | Simulate Aider without spawning |
| `--no-ui`               | Headless mode (logging only)    |
| `--whisper-model small` | Override STT model              |
| `--profile demo`        | Fast STT profile for live demos |

### Demo script

```bash
chmod +x scripts/demo.sh
./scripts/demo.sh
```

### Suggested demo script

1. **"Hey coder"** — activates listening
2. **"Create a Python REST API"** — sent to Aider
3. **"Run tests"** — executes `pytest -q`
4. **"Explain the failing test"** — coding prompt to Aider
5. **"Fix the bug"** — coding prompt to Aider
6. **"Commit changes"** — allowlisted git commit

### Voice commands

| Category       | Examples                                                  |
| -------------- | --------------------------------------------------------- |
| **Wake**       | "Hey coder", "Assistant"                                  |
| **Coding**     | "Create a React login page", "Fix the authentication bug" |
| **Terminal**   | "Run tests", "Git status", "Commit changes"               |
| **Navigation** | "Open file app.py", "Search for authentication code"      |
| **System**     | "Stop listening", "Mute microphone", "Exit"               |

### Keyboard shortcuts (fallback)

| Key | Action            |
| --- | ----------------- |
| `l` | Force listen mode |
| `m` | Mute microphone   |
| `q` | Quit              |

### Demo UI features

- **Live mic level bar** — shows audio input amplitude
- **Speech pulse** — green indicator while you're speaking
- **Spinners** — during Whisper transcription and Aider execution
- **Summary line** — spoken + written confirmation after each command
- **Onboarding panel** — mic, Whisper, Aider/API key checks at startup
- **Listen countdown** — seconds remaining before idle timeout
- **Smart context** — "explain the failing test" auto-attaches last terminal output
- **TTS** — macOS `say` reads short status messages (disable in `config.yaml`)

Voice commands added: **"cancel agent"**, **"commit with message …"**

## Configuration

Edit `config.yaml` to tune:

- Audio sample rate and device index
- VAD sensitivity (`threshold`, `min_silence_ms`)
- Whisper model size (`tiny` / `base` / `small`)
- Wake phrases and terminal command aliases
- Aider CLI args and timeouts

## Testing

```bash
export PYTHONPATH=.
pytest tests/ -v
```

### Testing strategy

| Layer     | Approach                                      |
| --------- | --------------------------------------------- |
| Router    | Unit tests with fixed phrases                 |
| Wake word | Transcript matching tests                     |
| Terminal  | Allowlist enforcement tests                   |
| STT/VAD   | Manual / integration with sample WAV (future) |
| Aider     | `--dry-run` mode for CI                       |
| UI        | Textual pilot tests (future)                  |

## Troubleshooting

| Issue                         | Fix                                                                |
| ----------------------------- | ------------------------------------------------------------------ |
| No microphone                 | Check `sounddevice` default device; set `audio.device` in config   |
| Slow transcription            | Use `--whisper-model tiny` or enable CUDA                          |
| Aider not found               | `pip install aider-chat` and ensure API keys in env                |
| OpenRouter sign-up page opens | Set `OPENAI_API_KEY` or `OPENROUTER_API_KEY` in `.env` (see above) |
| Torch hub errors              | Ensure network on first run for Silero VAD download                |

## License

MIT

# merednova_assesment
