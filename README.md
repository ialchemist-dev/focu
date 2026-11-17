# Focu

Current integrated version: **0.4.0**. Research/evidence handoff, podcast delivery, finite mobile reader, versioned source packs, explicit feedback, collector PoCs, auditable snapshots, and the recoverable daily pipeline are available on `main`. Recurring research orchestration and authenticated mobile hosting remain host integration work.

**Agent-native Attention Infrastructure** — focus on what matters, stay quiet about the rest.

Focu is evolving from the original feed-to-podcast prototype into an intent-led, evidence-backed information workflow. The current v0.2 code implements research-intent capture, evidence persistence and agent handoff; recurring Watches, change detection and silence-by-default delivery are **planned, not yet implemented**.

## Design philosophy — Attention Sovereignty

Focu is built on the owner's essay [Attention Sovereignty](https://aipraxislab.com/front/attention-sovereignty.html): attention sovereignty is meaningful control over **what is allowed to claim my attention, and how much attention a task is allowed to require from me**.

- **De-recommendation.** Not no recommendation — recommendation subordinated to human intent. Platforms may rank; the user's own agent is the final filter, applying priorities the user defined. Focu has no engagement-ranked feed: sources are chosen by the user, items are compressed (most deserve half a second, a few ten seconds, one earns a full read), and the agent reduces the cost of *the user deciding* what matters — it does not decide for them.
- **De-interface.** Interfaces are valuable as display surfaces (understanding at a glance) and costly as control surfaces (operating the system). Focu removes mechanical operation and keeps human judgment in the loop: *Look. Understand. Judge. Leave.*
- **The metric is attention returned.** Not time-in-app or engagement: how much information the user did not need to process, and how many interfaces they did not need to operate.

## Development — the `dev-main` branch and the multi-agent team

Day-to-day development integrates on **`dev-main`**, not `main`. `main` stays the stable, production-running line; work lands on `dev-main` first.

Since 2026-11-17, development is run by a multi-agent team whose SOP follows **MetaGPT** (the most-starred open-source multi-agent framework): a project-manager agent owns the backlog and acceptance criteria, an infra designer owns platform and tooling choices, backend and UI developers implement, and an integrator runs the tests, lands commits on `dev-main`, and keeps this README truthful about the philosophy, the architecture, and what is actually implemented. Current team focus: the reader UI (simplicity and delight), the source-pack marketplace (the **Source Library** — curated, one-step-importable packs of people and publications, e.g. Anthropic and OpenAI people with personal blogs, Silicon Valley startups, geothermal), broader own-feed platform adapters in the pattern of the existing LinkedIn reader, and the feedback loop that lets Focu learn its user over time. Reader improvements land on `dev-main` first — already in: one-tap play from the feed, a cost chip on every item (audio length or reading time, visible before the user commits attention), and resume-where-you-left-off for both audio and articles. The player bar stays out of the way (recovery appears only after a real stall, with plain-language status and -15s/+30s skips), content refreshes itself when the app returns to the foreground, articles open with title and Listen before the cover, and un-compiled source cards collapse into a single row in the Daily Briefing tab. Each card also carries a glance layer — a short gist extracted verbatim from the item's own text, never generated — so most items can be judged in half a second, exactly as the compression ladder intends. The first platform adapter prototype (YouTube, `focu/adapters/`) generalizes the LinkedIn own-feed pattern into repo code: channel RSS plus the production transcript ladder, one digest unit per channel-day with per-day identity, hard caps, transcripts withheld when missing, and no credentials inside Focu. A second prototype (Instagram own-feed) reuses an owner-created Instaloader session file — the adapter never accepts credentials and never logs in, and any platform checkpoint stops the day with nothing emitted. A third (RedNote) consumes only an export file produced by owner-run tooling outside Focu — the repo ships no platform code for it at all, which keeps the collector's non-commercial license outside Focu's boundary. The learning loop's Phase 1 is in (`focu learn show / proposals / accept / dismiss`): proposals computed from the feedback ledger, each carrying its evidence, applied only on the owner's accept into a provenance-checked preference record (`references/learned-preferences.md`) — selection code deliberately untouched until a later phase.

Source Library status: the pack format is implemented (`schemas/source-pack.schema.json`, `focu/packs.py`) with `focu pack validate / preview / install / uninstall / restore`. Installs are preview-first (adds, duplicates, unverified candidates with reasons, and the total attention cost), deduplicated against the existing registry, and reversible. Verified packs so far: **Anthropic people** (`focu/source_packs/anthropic-personal-blogs.json`, 10 sources, ≈5.5 posts/month in total) and **OpenAI people** (`focu/source_packs/openai-personal-blogs.json`, 6 sources, ≈0.9 posts/month — OpenAI staff keep far fewer personal blogs; affiliation re-verified per person, with leavers and no-blog cases recorded in the pack's unverified list), and the **geothermal industry** pack (`focu/source_packs/geothermal-industry.json`, 12 sources, ≈92 posts/month — dominated by the ThinkGeoEnergy wire and bounded by a per-day cap; outlets without a working feed are listed disabled or unverified with dated reasons). A fourth pack, **Silicon Valley startups** (`focu/source_packs/silicon-valley-startups.json`, 18 sources, ≈127 posts/month — two bursty wires capped at 2/day), applies the same bar to company engineering blogs: independent, Bay Area, and writing engineers actually read.

## Agent-native installation (v0.2 preview)

The v0.2 agent-installable workflow is available on `main`. Requires Python 3.10+ and Git.

```bash
git clone https://github.com/ialchemist-dev/focu.git focu
cd focu
bash scripts/bootstrap.sh
.venv/bin/focu capture "Why do tools constrain us?"
.venv/bin/focu list --status queued
```

See [Agent Installation](docs/AGENT_INSTALL.md) for Muse/OpenClaw usage, limitations and an end-to-end evidence handoff. Focu does not yet autonomously run a research agent or produce v0.2 audio.

**Research reports (manual workflow):** [docs/research-reports/](docs/research-reports/README.md) covers the flow from purpose to an English mission, then a frozen report with sources and claims, then a self-contained responsive HTML page with QA. It includes templates, a buildless HTML kit, a stdlib citation/structure checker and a [copy-paste Muse instruction](docs/research-reports/muse-instruction.zh.md). It does not change the scheduled Daily pipeline.

---

## Legacy v0.1 feed-to-podcast pipeline

Your sources. Your podcast. Every day.

Focu is a personal feed-to-podcast pipeline with one rule: **you define
the sources, nothing else gets in.** A background agent checks your sources
once a day, pulls their latest updates, and turns them into a podcast
episode — with the full script kept alongside the audio.

No recommendations. No trending tabs. No algorithmic feed. Just the people
and publications you chose, read to you.

## New here? Start in one sitting

Hand this repo to your agent (or a friend's) and answer six questions:
who to follow, any official blogs, how many episodes, how long, what
language, what the host is called. The full script is in
[`docs/ONBOARDING.md`](docs/ONBOARDING.md) — it includes recommended
starter packs (AI labs tracker, learning & thinking) you can paste
straight into `sources.yaml`.

## How it works

```
You define sources (sources.yaml)
        ↓  daily, automatic
Agent ingests each source's latest updates
        ↓
Updates → digest → single-host script → MP3 episode
        ↓
data/episodes/2026-09-28/research.mp3 (+ research-script.txt)
```

## Install

Prerequisites: Python 3.10+, `ffmpeg`, a TTS backend (see
`references/tts-backends.md`).

```bash
git clone <this-repo> focu
cd focu
pip install -r requirements.txt
cp examples/sources.yaml sources.yaml   # then edit: your sources
./scripts/run-daily.sh                  # run once now
```

Schedule it daily (cron example — 7:14 AM):

```cron
14 7 * * * /path/to/focu/scripts/run-daily.sh >> /path/to/focu/data/cron.log 2>&1
```

## Defining sources

`sources.yaml` is the whole product. Example:

```yaml
sources:
  - name: "3Blue1Brown"
    type: youtube
    channel: research
    handle: "3blue1brown"

  - name: "Ethan Mollick"
    type: rss
    channel: research
    feed_url: "https://www.oneusefulthing.org/feed"
```

Full schema: `references/source-schema.md`. Source types: `rss`,
`youtube`, `blog`, `x`, `linkedin`.

## For agents

This repo is a skill: `SKILL.md` is the agent-readable entry point.
Agents (Muse, or any agent that reads skills) can install, configure,
run, and extend the pipeline from these docs alone.

## Status

v0.1 — framework. Pipeline skeleton, source schema, script conventions,
and prompt templates are in place. Prompt quality for natural-sounding
episodes is the next iteration (see `references/prompts.md`).

## License

MIT — see [LICENSE](LICENSE).

## Finite mobile reader and source marketplace

Run `python -m focu.cli reader serve` to read explicitly published research batches, save/complete items, and inspect/subscribe to versioned source groups. See [Reader App](docs/READER_APP.md), [product design](docs/READER_MARKETPLACE_PLAN.md), and [Anthropic source validation](docs/ANTHROPIC_SOURCE_DISCOVERY.md). Local-only server; authenticated HTTPS hosting and iOS installation acceptance remain outstanding. Reader subscriptions and the daily pipeline's `sources.yaml` registry dedupe sources by one shared canonical URL identity (`focu.daily.identity.canonical_url`): tracking parameters are stripped and platform URL forms are normalized, while trailing slashes, path case, and unknown query parameters stay significant — a source is the same source in both registries, and never silently merged in one but not the other.

## Recoverable daily pipeline

`focu daily ...` exposes the persistent backlog and safe resume functionality without replacing the research CLI. See [Persistent Pipeline](docs/PERSISTENT_PIPELINE.md). For an existing installation, follow [Muse Reinstall](docs/MUSE_REINSTALL.md) to preserve databases, sources and credentials.

## Durable files and cross-device state

`focu sync` replicates registered artifacts to private Google Drive and metadata/state checkpoints to a separate private GitHub repository. `focu host` checks deployment prerequisites and generates service units for an exact private HTTPS origin. See [Data Flow](docs/DATA_FLOW.md) and the [Muse deployment-only handoff](docs/MUSE_DATA_SYNC_DEPLOY.md). These adapters are implemented; account authorization and target-host/iPhone verification still happen at deployment.
