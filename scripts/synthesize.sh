#!/bin/bash
# synthesize.sh — text-to-speech for one channel's script.
# Usage: synthesize.sh --date YYYY-MM-DD --channel <id>
# Reads data/episodes/<date>/<channel>-script.txt, writes <channel>.mp3.
#
# v0.1: BYO TTS backend. Set FOCU_TTS_CMD to a command that reads a
# text file ($IN) and writes an MP3 ($OUT), e.g.:
#   export FOCU_TTS_CMD="tts --text $IN --out $OUT"
# Backend notes: references/tts-backends.md
set -euo pipefail

DATE=""; CHANNEL=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --date) DATE="$2"; shift 2;;
    --channel) CHANNEL="$2"; shift 2;;
    *) echo "unknown arg: $1"; exit 1;;
  esac
done
[[ -n "$DATE" && -n "$CHANNEL" ]] || { echo "usage: synthesize.sh --date YYYY-MM-DD --channel <id>"; exit 1; }

REPO="$(cd "$(dirname "$0")/.." && pwd)"
IN="$REPO/data/episodes/$DATE/$CHANNEL-script.txt"
OUT="$REPO/data/episodes/$DATE/$CHANNEL.mp3"
[[ -f "$IN" ]] || { echo "missing script: $IN"; exit 1; }

if [[ -z "${FOCU_TTS_CMD:-}" ]]; then
  echo "FOCU_TTS_CMD not set — skipping synthesis (script kept at $IN)"
  echo "see references/tts-backends.md to wire a backend"
  exit 0
fi

# shellcheck disable=SC2086
eval "${FOCU_TTS_CMD//\$IN/$IN}"
# normalize: ensure MP3 container
if [[ -f "$OUT" ]]; then
  echo "episode → $OUT"
else
  echo "backend did not produce $OUT"
  exit 1
fi
