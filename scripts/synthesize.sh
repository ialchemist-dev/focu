#!/usr/bin/env bash
# Generate an MP3 for a channel with the opt-in Focu TTS backend.
set -euo pipefail
DATE=""; CHANNEL=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --date) DATE="$2"; shift 2;;
    --channel) CHANNEL="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 1;;
  esac
done
[[ -n "$DATE" && -n "$CHANNEL" ]] || { echo "usage: synthesize.sh --date YYYY-MM-DD --channel <id>" >&2; exit 1; }
REPO="$(cd "$(dirname "$0")/.." && pwd)"
IN="$REPO/data/episodes/$DATE/$CHANNEL-script.txt"
OUT="$REPO/data/episodes/$DATE/$CHANNEL.mp3"
[[ -f "$IN" ]] || { echo "missing script: $IN" >&2; exit 1; }
cd "$REPO"
PYTHON="$REPO/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python3
if [[ -z "${OPENAI_API_KEY:-}" && ! -f "$REPO/data/tts-config.json" ]]; then
  echo "TTS not configured. Run .venv/bin/focu tts setup (script retained)." >&2
  exit 1
fi
"$PYTHON" -m focu.tts synthesize --input "$IN" --output "$OUT"
