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

1. **User-authorized inputs only.** Scheduled collection follows registered sources; one-time research follows explicit user ideas or links. No recommendations, trending feeds, or unsolicited subscriptions.
2. **Follow people, not platforms.** Each source is a person, author, or
   editorial voice — not an algorithmic feed.
3. **Daily, unattended.** Ingest runs on a schedule (cron). The agent
   needs no prompting once sources are defined.
4. **Research first.** Articles are durable. Optional generated audio includes its transcript and evidence-linked script; audio is not required for an article.
5. **Content only.** Episodes never explain how they were made, what the
   selection logic is, or the philosophy behind the pipeline.

## Personal secretary briefings — owner-editable voice

The daily report is a **private secretary briefing addressed to one person**,
not a podcast show. All voice, wording, length and prohibited framing rules
live in [references/briefing-style.md](references/briefing-style.md).

**On natural-language style feedback** ("too formal", "shorter", "stop giving
the why-line"), edit **only** that file, append a dated Changelog entry with
the feedback, commit, and have the next *new* episode read it. Do not add
a parallel persona in a provider prompt or Python constant.

- Daily scripts run through `focu.daily.pipeline.compose` and mandatory
  pre-TTS coverage/figure QC.
- Muse/Open Notebook must use `focu podcast generate --briefing-units ...`
  and QC-gated `focu deliver --briefing-units ...` for a secretary briefing.
  Scripts dropping any source item or numeric facts must fail, not publish.
- Read [Muse 06:14 job handoff](docs/MUSE_SECRETARY_BRIEFING_HANDOFF.md).
  The actual VM cron has to be inspected; a GitHub commit is not a deployment.

## Podcast decisions and audience calibration — required

Load [the origin-specific policy and Muse handoff](docs/PODCAST_ORIGIN_AUDIENCE_POLICY.md)
and [the owner-authorized audience profile](references/audience-profile.md)
before writing a Focu article or generating its audio.

When the owner says **"research this"** or shares a URL:
- Capture a one-time intent with focu request. The default podcast_mode is
  none. Do not generate audio without a direct podcast request.
- If the owner requests research *and* a podcast in one sentence, use
  focu request --podcast when capturing it.
- If the owner later says **"make this one a podcast"**, resolve the
  canonical content/intent ID, then call focu request-podcast <intent-id>.
  Never guess the target item when more than one candidate exists.
- After the evidence-backed article exists, use focu podcast-for <intent-id>
  with the established Open Notebook profiles and real delivery folder.
  The command checks every section heading and figure; two QC failures
  stop without attaching audio. Never silently override or reduce the gate.

For a subject outside the owner's expert fields, the same profile requires
additional basic orientation. Use focu audience-prompt --domain <domain>
to obtain the authoritative constraints for a host-agent-written article.
No per-provider copy of this profile and no background inferred skill edits.

Registered-source articles get no individual podcast. Daily compilation
may summarize completed, independently published user-initiated research
alongside registered-source updates, linked with covered_content_ids.
This does NOT authorize a standalone MP3 for the on-demand article:
its own mode remains none until explicitly requested, or single afterward.
The registered-source *collector* must refuse injected user-initiated
records; editorial inclusion happens by linking published content IDs.
Device Read aloud is a separate, low-cost feature and is not a podcast MP3.

A static Muse Artifact only learns about a newly attached MP3 after the
host republishes an immutable snapshot. The existing article and podcast
remain one Content Item with the same Inbox/Archive state.

## Muse on-demand research: spoken idea or URL

When the user tells Muse "research this link", "look into this idea", or
"research this and add it to Focu", treat it as a one-time user-initiated
research request, **not** a registration or subscription.

**Load [Muse on-demand research protocol](docs/MUSE_ON_DEMAND_RESEARCH.md)**
before handling this workflow. On the new feature branch, the agent can:

```bash
.venv/bin/focu request "Evaluate whether this technical claim is credible" --url "https://example.org/post"
.venv/bin/focu requests
```

The command durably captures an intent; it does **not** autonomously launch
research. The host agent must actually execute or schedule research with
supported capabilities, produce a verified Evidence Pack and readable report,
and rebuild the private Muse Artifact to surface the result. The UI Research
tab is a static status snapshot, never live synchronization. Do not claim
background completion without a real running worker.

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

**compose** (`scripts/compose.py`): a single-person secretary script per channel,
reading `references/briefing-style.md` and producing a QC receipt. Output:
`data/episodes/YYYY-MM-DD/<channel>-script.txt`.

**synthesize** (`scripts/synthesize.sh`): text-to-speech via the
configured backend (see `references/tts-backends.md`). Output:
`data/episodes/YYYY-MM-DD/<channel>.mp3`.

## Conventions for agents working here

- Read `references/architecture.md` before changing the pipeline.
- Source schema changes go in `references/source-schema.md` first.
- Secretary briefing voice changes go **only** in `references/briefing-style.md` with a dated feedback changelog; digest/ingest prompts remain in `references/prompts.md`.
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
