# Persistent daily pipeline (integrated PR #1)

The M1 backlog/recovery implementation is now `focu.daily`, exposed as `focu daily ...`. It coexists with the research/evidence/reader interface instead of replacing `focu.cli` or the newer YouTube/LinkedIn collector PoC.

Implemented: transactional ingestion and native cursors, canonical URL identities, persistent backlog, source selection quotas, frozen run configuration and episode selection, safe TTS argv execution, MP3 validation, audio receipts for crash recovery, kernel writer locks, explicit legacy import, status/state export. Existing M1 tests are retained under `tests/test_pipeline.py`.

## Commands

```bash
.venv/bin/focu daily run --config sources.yaml --data-dir data/persistent --text-only --dry-run --json
.venv/bin/focu daily run --config sources.yaml --data-dir data/persistent --text-only --json
.venv/bin/focu daily status --data-dir data/persistent --json
.venv/bin/focu daily export-state --data-dir data/persistent --json
```

Older `type: anthropic` section registrations normalize in memory to their official blog URLs without rewriting user configuration. HTML-only blogs remain host-collected/unsupported by the RSS adapter; no successful scraping is claimed.

Other stages: `ingest`, `digest`, `compose`, `synthesize`; `--date YYYY-MM-DD` identifies a frozen run. An existing date must resume using the same configuration and output mode. A failed earlier episode reserves its input; resume the original date rather than silently selecting the same material elsewhere. Source quota limits selection, not ingestion.

`python -m focu.daily.cli ...` is also supported. The existing `scripts/ingest.py`, `digest.py`, `compose.py`, `run-daily.sh`, `synthesize.sh` now delegate to this persistent core. Shell wrappers prefer the checkout's `.venv/bin/python`; override with `FOCU_PYTHON` if necessary (`THEFEW_PYTHON` retained as compatibility fallback).

The daily store remains `<data-dir>/few.sqlite3` for existing M1 database compatibility. It is a separate schema from the research/evidence/reader database selected by the top-level `--db`. Do not combine or rename the two files. Prefer `data/persistent` for a new daily store. A v0.1 directory containing old state/episodes is rejected for automatic initialization.

## Existing v0.1 data

Stop the old writer before an explicitly chosen migration. Back up files and use a separate, non-nested destination:

```bash
.venv/bin/focu daily import-legacy --config sources.yaml \
  --from-dir /absolute/old-data --data-dir /absolute/new-persistent-data --json
```

Import does not assume old output was delivered/listened to. `--register-coverage` is an explicit attestation, not a routine reinstall flag. Never run it implicitly.

## TTS and composition

The daily composer is a deterministic skeleton; it is not the evidence-based Muse research/podcast workflow. For editorial-quality research/podcasts, keep using `ingest-evidence`, `report`, `podcast`, `deliver` and `reader publish` as described in READER_APP.md.

Daily audio mode needs `ffmpeg`/`ffprobe` and an explicit argv template in sources.yaml. Example using Focu's configured TTS:

```yaml
tts_argv:
  - /absolute/focu/.venv/bin/python
  - -m
  - focu.tts
  - synthesize
  - --input
  - '{input}'
  - --output
  - '{output}'
```

`FOCU_TTS_CMD` is parsed into an argument list as a compatibility alternative; older `THEFEW_TTS_CMD`/`THEVIEW_TTS_CMD` remain accepted. No shell eval. Missing/failed TTS retains script and selection and does not register coverage. The simple TTS adapter's input limit still applies. Audio decoding checks do not prove narration completeness.

Feedback remains explicit via `python -m focu.feedback`; consuming/scrolling in the reader does not change preferences. Scheduled collection is owned by the host; reinstall does not create or resume scheduled jobs automatically.

Re-delivery preserves already archived research reports when the renderer changes (for example, audit-quote formatting). Historical report bytes are not silently replaced. New reports use the current renderer.
