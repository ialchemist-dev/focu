#!/bin/bash
# run-daily.sh — the whole pipeline for one date.
# Usage: run-daily.sh [--date YYYY-MM-DD]   (default: today, UTC)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"

DATE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --date) DATE="$2"; shift 2;;
    *) echo "unknown arg: $1"; exit 1;;
  esac
done
DATE="${DATE:-$(date -u +%F)}"

echo "=== focu daily run: $DATE ==="
python3 "$REPO/scripts/ingest.py" --date "$DATE"
python3 "$REPO/scripts/digest.py" --date "$DATE"
python3 "$REPO/scripts/compose.py" --date "$DATE"

# one MP3 per channel that has a script
for script in "$REPO/data/episodes/$DATE/"*-script.txt; do
  [[ -f "$script" ]] || continue
  channel="$(basename "$script" -script.txt)"
  "$REPO/scripts/synthesize.sh" --date "$DATE" --channel "$channel" || echo "synthesize failed for $channel (script kept)"
done

echo "=== done: $REPO/data/episodes/$DATE/ ==="
ls "$REPO/data/episodes/$DATE/"
