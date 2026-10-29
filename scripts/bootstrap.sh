#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
.venv/bin/focu doctor
.venv/bin/focu init
echo "Focu installed. Run: .venv/bin/focu --help"
echo "Optional podcast speech: .venv/bin/focu tts status; .venv/bin/focu tts setup (requires user consent and an interactive terminal)"
