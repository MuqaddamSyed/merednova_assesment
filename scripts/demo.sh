#!/usr/bin/env bash
# Voice Coder demo script — run from project root
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=============================================="
echo "  Voice Coder — Live Demo"
echo "=============================================="
echo ""
echo "Prerequisites:"
echo "  - Python 3.10+"
echo "  - Microphone access"
echo "  - pip install -r requirements.txt"
echo "  - pip install aider-chat  (for coding agent)"
echo ""
echo "Demo flow (speak each phrase after startup):"
echo "  1. 'Hey coder'"
echo "  2. 'Create a Python REST API'"
echo "  3. 'Run tests'"
echo "  4. 'Explain the failing test'"
echo "  5. 'Fix the bug'"
echo "  6. 'Commit changes'"
echo ""
echo "Keyboard shortcuts in UI:"
echo "  l = force listen mode"
echo "  m = mute microphone"
echo "  q = quit"
echo ""

if [[ ! -d .venv ]]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate
pip install -q -r requirements.txt

export PYTHONPATH="$ROOT"
mkdir -p logs

# Dry-run mode if aider not installed
if ! command -v aider &>/dev/null; then
  echo "Note: 'aider' not found — starting with --dry-run"
  EXTRA=(--dry-run)
else
  EXTRA=()
fi

echo "Starting Voice Coder..."
python -m src.main "${EXTRA[@]}"
