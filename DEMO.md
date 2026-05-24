# Voice Coder — Live Demo Script

Use this script for interviews, recordings, or rehearsal. Expected UI states are listed so you know when to proceed.

## Prerequisites (5 min before demo)

```bash
cd merednova_assesment
source .venv/bin/activate
cp .env.example .env   # if not done
# Set OPENAI_API_KEY in .env
export $(grep -v '^#' .env | xargs)
make check             # mic + deps OK
```

Ensure **System Settings → Privacy → Microphone** allows Terminal/Cursor.

---

## Launch

```bash
make run
# or: make dry-run   (voice only, no Aider/API)
```

**Expected startup UI:**
- Onboarding panel: green checks for Mic, Whisper, Aider+API key
- Summary: `Ready.` then `Loading Whisper model...` then `Whisper ready`
- Status: `Press L to listen, or say 'Hey coder'`

---

## Demo flow (speak clearly, pause ~0.5s at end of each phrase)

### Step 1 — Activate listening

| You say / do | Expected UI |
|--------------|-------------|
| Press **`L`** | Mode: `listening` · Summary: `Listening.` |
| or say **"Hey coder"** | Same + transcript shows wake phrase |

> Tip: `L` is most reliable in noisy rooms.

---

### Step 2 — Coding prompt

| You say | Expected UI |
|---------|-------------|
| **"Create a Python REST API with JWT authentication"** | Mic bar moves · green **● Listening…** pulse · `End detected — transcribing…` · Spinner: `Transcribing…` · Route: `coding → prompt (85%)` · Summary: `Routed to Aider: Create a Python REST API` · Spinner: `Aider thinking…` · Agent log streams output |

**If Aider auth fails:** Summary shows API key hint — verify `OPENAI_API_KEY` in `.env`.

---

### Step 3 — Run tests

| You say | Expected UI |
|---------|-------------|
| **"Run tests"** | Summary: `Running: run tests` · Terminal log shows pytest output · Summary: `Done — run tests succeeded` or `failed` |

---

### Step 4 — Explain failure (smart context)

| You say | Expected UI |
|---------|-------------|
| **"Explain the failing test"** | Summary: `Routed to Aider: Explain the failing test` · Aider prompt includes last pytest output in a code block |

This step demonstrates **context memory** — not a bare prompt.

---

### Step 5 — Fix the bug

| You say | Expected UI |
|---------|-------------|
| **"Fix the bug"** or **"Fix the failing test"** | Aider receives test output context · Agent log shows edits |

---

### Step 6 — Commit

| You say | Expected UI |
|---------|-------------|
| **"Commit with message add JWT authentication"** | Summary: `Running: commit: add JWT authentication` · git output in log |

---

### Optional — Cancel / system commands

| You say | Expected UI |
|---------|-------------|
| **"Cancel agent"** | Summary: `Agent task cancelled.` |
| **"Stop listening"** | Mode: `idle` |
| **"Mute microphone"** | Mic stops responding |
| Press **`Q`** | Clean exit |

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `L` | Start listening |
| `M` | Mute / unmute mic |
| `Q` | Quit |

---

## Troubleshooting during demo

| Problem | Fix |
|---------|-----|
| No mic bar movement | Check mic permission · press `M` to unmute |
| No transcription | Speak louder · pause at end · press `L` first |
| OpenRouter browser opens | Set `OPENAI_API_KEY` · restart app |
| Slow first command | Whisper preloads at startup — wait for `Whisper ready` |
| Low confidence route | Speak full phrase: "run tests" not just "tests" |

---

## 60-second elevator pitch (while demo runs)

> "Voice Coder is a hands-free terminal interface for AI coding agents. It captures speech locally with Silero VAD and faster-whisper — no cloud STT costs — routes commands safely through an allowlisted router, and sends coding prompts to Aider. The UI shows live mic feedback, latency metrics, and context-aware debugging — when I say 'explain the failing test', it automatically attaches the last pytest output."

---

## Recording checklist

- [ ] Terminal font size readable (16pt+)
- [ ] Close unrelated tabs/notifications
- [ ] Run `make check` first
- [ ] Wait for `Whisper ready` before speaking
- [ ] Keep phrases short with a clear pause at the end
