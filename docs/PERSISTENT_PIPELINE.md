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

Daily audio mode needs `ffmpeg`/`ffprobe`. A run that is not `--text-only`
finalizes each compilation episode through script fidelity QC (already
enforced at compose and re-verified at finalize), synthesis, and the
decoded-audio audit. Which synthesis backend runs depends on configuration,
in this order:

1. **Explicit argv template** (`tts_argv` in sources.yaml, or `FOCU_TTS_CMD`;
   older `THEFEW_TTS_CMD`/`THEVIEW_TTS_CMD` remain accepted). The template is
   a command contract — input script file in, output MP3 out, optional
   `{voice}` — and is never shell-eval'd. This is also how a host connector
   helper is plugged in on hosts where the speech credential is not directly
   reachable by the pipeline: the helper exposes the same contract and calls
   the provider itself. This route keeps its original fail-hard contract:
   a missing or failed backend retains the script and selection, registers
   no coverage, and the run reports the failure so it can resume.
   Example using Focu's configured TTS (long-form entry point, so daily
   scripts over the provider's 4,000-character limit are chunked):

   ```yaml
   tts_argv:
     - /absolute/focu/.venv/bin/python
     - -m
     - focu.tts
     - synthesize-long
     - --input
     - '{input}'
     - --output
     - '{output}'
   ```

2. **Built-in `focu tts` adapter** (no argv template configured). Synthesis
   runs when `focu tts status` reports a configured credential — a locally
   configured `focu tts` credential (environment or the private config file
   from `focu tts setup`); the pipeline never assumes where the key lives
   beyond that status check. This route is fail-soft (owner decision
   2026-11-08): an unconfigured backend is a recorded skip, and a synthesis
   or audit failure is recorded with its stage name (`script_qc`,
   `tts_config`, `tts_synthesis`, `audio_audit`) in the episode manifest's
   `audio_attempt`; the episode still finalizes as `text_only` and the run
   succeeds. Failed or absent audio never blocks the text pipeline and
   never ships.

The host workflow for the default route is: finish the briefing, author or
generate the spoken script (a host-authored script placed at
`episodes/<date>/<channel>-script.txt` before compose is adopted and held to
the same coverage QC as the deterministic script), then run the daily
pipeline in audio mode; the manifest records the script QC verdict
(`script_qc`: coverage, issues, style version/SHA, script SHA), the audience
calibration applied (`audience_qc`: domain, level, profile version/SHA), and
the `audio_attempt` outcome. Audio decoding checks do not prove narration
completeness; script-text QC is the fidelity gate.

Feedback remains explicit via `python -m focu.feedback`; consuming/scrolling in the reader does not change preferences. Scheduled collection is owned by the host; reinstall does not create or resume scheduled jobs automatically.

Re-delivery preserves already archived research reports when the renderer changes (for example, audit-quote formatting). Historical report bytes are not silently replaced. New reports use the current renderer.
