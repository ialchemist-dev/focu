#!/usr/bin/env bash
# Compatible stage entry point; state and safe argv substitution live in Python.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"
exec "${THEFEW_PYTHON:-python3}" -m the_few.cli run \
  --config "$REPO/sources.yaml" --data-dir "$REPO/data" "$@"
