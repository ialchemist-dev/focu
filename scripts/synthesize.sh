#!/usr/bin/env bash
# Compatible stage entry point; state and safe argv substitution live in Python.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"
PYTHON="${FOCU_PYTHON:-${THEFEW_PYTHON:-$REPO/.venv/bin/python}}"
[[ -x "$PYTHON" ]] || PYTHON=python3
exec "$PYTHON" -m focu.daily.cli synthesize \
  --config "$REPO/sources.yaml" --data-dir "$REPO/data" "$@"
