---
name: focu
description: Agent-native information digestion. Capture spontaneous research questions, follow user-curated entities and sources, preserve evidence, and deliver attention-aware digests. The existing daily feed-to-podcast pipeline remains available. Use for research-intent capture, source management, digest planning, and podcast workflows.
---

# Focu

Focu is evolving into an agent-native information digestion system: user-defined sources, recurring routines, and one-time research intents feed evidence-backed, attention-aware digests. The existing v0.1 feed-to-podcast pipeline remains supported. Recurring Watches, change detection, and silence-by-default delivery are planned rather than implemented:


```
sources.yaml → ingest → digest → compose → synthesize → episode.mp3 + script.txt
```

## The contract

1. **User-defined sources only.** The pipeline never pulls from anything
   outside `sources.yaml`. No recommendations, no trending, no filler.
2. **Follow people, not platforms.** Each source is a person, author, or
   editorial voice — not an algorithmic feed.
3. **Daily, unattended.** Ingest runs on a schedule (cron). The agent
   needs no prompting once sources are defined.
4. **Podcast + script.** Every episode ships as audio *and* its full
   script. The script is the durable artifact; audio is the interface.
5. **Content only.** Episodes never explain how they were made, what the
   selection logic is, or the philosophy behind the pipeline.

## Quick start

1. Copy `examples/sources.yaml` to `sources.yaml` and list your sources.
   See `references/source-schema.md` for the full schema.
2. Run the daily pipeline:
   ```
   ./scripts/run-daily.sh --date 2026-09-28
   ```
   This ingests, digests, composes, and synthesizes one episode per
   channel. Outputs land in `data/episodes/YYYY-MM-DD/`.
3. Schedule it: add a cron entry calling `run-daily.sh` (see
   `references/scheduling.md`).

## Layout

- `SKILL.md` — this file; the agent-readable entry point.
- `sources.yaml` — (you create) the user's defined sources.
- `references/` — durable docs: architecture, source schema, script
  conventions, prompt templates, scheduling, TTS backend notes.
- `scripts/` — the pipeline: `ingest.py`, `digest.py`, `compose.py`,
  `synthesize.sh`, `run-daily.sh`.
- `examples/` — example `sources.yaml` and example episode output.
- `data/` — runtime outputs (units, scripts, episodes). Git-ignored.

## Pipeline stages

**ingest** (`scripts/ingest.py`): for each source in `sources.yaml`,
fetch new items since the last run (tracked in `data/state.json`).
Source types: `rss`, `youtube`, `blog`, `x`, `linkedin`. Types that need
credentials or login (`x`, `linkedin`) degrade gracefully — they log a
warning and skip, never fail the run. Output: `data/units/YYYY-MM-DD.json`.

**digest** (`scripts/digest.py`): dedupe by URL/id, drop empties, rank by
recency, group by channel. Output: `data/digested/YYYY-MM-DD.json`.

**compose** (`scripts/compose.py`): one single-host script per channel,
using the prompt template in `references/prompts.md`. Script conventions
in `references/script-conventions.md`. Output:
`data/episodes/YYYY-MM-DD/<channel>-script.txt`.

**synthesize** (`scripts/synthesize.sh`): text-to-speech via the
configured backend (see `references/tts-backends.md`). Output:
`data/episodes/YYYY-MM-DD/<channel>.mp3`.

## Conventions for agents working here

- Read `references/architecture.md` before changing the pipeline.
- Source schema changes go in `references/source-schema.md` first.
- Prompt improvements go in `references/prompts.md` — the pipeline
  reads prompts from there, not from code.
- Never commit `data/` or `sources.yaml` (personal). Commit
  `examples/` instead.
- Keep every stage independently runnable and its output inspectable.
  An agent should be able to re-run `compose` without re-running
  `ingest`.

## v0.2 incremental workflow (experimental)

Read `docs/architecture-v0.2.md` and the versioned schemas before implementing new flows. The installable v0.2 slice supports intent capture, Evidence Pack persistence, public HTML fetching, and agent-authored evidence-to-Markdown delivery. Automatic research orchestration, session planning, and new audio providers are not implemented.

Capture a question without changing permanent subscriptions:

```bash
.venv/bin/focu capture "Why do tools sometimes constrain their users?"
.venv/bin/focu list --status queued
```

The installed `.venv/bin/focu` CLI is the recommended agent interface; `python -m focu.intents` remains available for compatibility. The default SQLite DB lives under ignored `data/`. Do not store API keys, private questions, or generated research in Git. The v0.1 `scripts/run-daily.sh` is unchanged. Never imply an intent has been researched or delivered merely because it has been captured.

## Muse / agent installation (v0.2)

From a terminal with Python 3.10+ and Git:

```bash
git clone https://github.com/ialchemist-dev/the-few.git focu
cd focu
bash scripts/bootstrap.sh
.venv/bin/focu --help
```

Read `docs/AGENT_INSTALL.md` for the complete agent protocol and acceptance test. Agents must not claim autonomous research exists yet.

## Optional TTS credential onboarding (host-agent instructions)

After bootstrap, run `.venv/bin/focu tts status`. If speech is not configured, **ask the user** whether they want to enable OpenAI speech synthesis. Do not assume consent, request the secret in chat, or claim to open a native popup. If the user agrees, direct them to run `.venv/bin/focu tts setup` in a private interactive terminal, or use the host's secure secret-input facility to set `OPENAI_API_KEY`. See `docs/TTS_ONBOARDING.md`. Never send a key to a model prompt or store it in Git.

## Open Notebook podcast backend (Muse testable)

**Preferred podcast backend is Open Notebook, not the standalone Focu TTS adapter.** Read `docs/OPEN_NOTEBOOK_MUSE_TEST.md` before generating audio. After bootstrap, run `.venv/bin/focu podcast doctor` and show the user missing prerequisites. Open Notebook must run separately with API + worker and configured LLM/TTS models. Use the exact Episode Profile and Speaker Profile names returned by doctor. Ask before sending evidence content to a remote service. Generate from approved evidence, poll the returned job ID, list episodes, then download the MP3. Never claim a submitted job is a finished episode. Preserve the evidence separately and verify generated claims. No automatic deployment, scheduling, or feed publishing is implied.

## Canonical report and alternate delivery formats

Research is the primary durable asset; podcast is only one interface. See `docs/MULTIFORMAT_DELIVERY.md`. After an Evidence Pack is ingested, run `focu report EVIDENCE_ID --output data/reports/report.md` to preserve a detailed Markdown report with original source links. For an audio derivative, use the Open Notebook workflow, then `focu sync-podcast --evidence-id EVIDENCE_ID --episode-id EPISODE_ID` after completion to archive its actual transcript, outline, and metadata in Focu SQLite. Run `focu artifacts EVIDENCE_ID` to discover available formats and `focu artifact ARTIFACT_ID --output PATH` to export. The spoken transcript is not the canonical report. Preserve all source claims and uncertainty in the report, and flag unsupported generated podcast statements. Don't claim transcript archival happens automatically yet.

## Unified delivery

After an approved Open Notebook episode completes, follow `docs/MUSE_DELIVERY.md` and run `focu deliver --evidence-id ID --episode-id ID --output-dir PATH`. Return reading and listening paths. Do not confuse transcript with canonical research. If only a job ID is known, `--job-id` can resolve it only when the completed job result explicitly includes the episode ID.

## Source collectors PoC

See `docs/COLLECTOR_POC.md` before running YouTube or importing an authorized LinkedIn MCP feed export. Do not equate collected text with verified Evidence Pack findings.
