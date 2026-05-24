#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
source .venv/bin/activate 2>/dev/null || true
python -m src.main --no-ui --dry-run "$@"
