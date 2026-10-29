# Focu

**Agent-native Attention Infrastructure** — focus on what matters, stay quiet about the rest.

Focu is evolving from the original feed-to-podcast prototype into an intent-led, evidence-backed information workflow. The current v0.2 code implements research-intent capture, evidence persistence and agent handoff; recurring Watches, change detection and silence-by-default delivery are **planned, not yet implemented**.

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

Run `python -m focu.cli reader serve` to read explicitly published research batches, save/complete items, and inspect/subscribe to versioned source groups. See [Reader App](docs/READER_APP.md), [product design](docs/READER_MARKETPLACE_PLAN.md), and [Anthropic source validation](docs/ANTHROPIC_SOURCE_DISCOVERY.md). Local-only server; authenticated HTTPS hosting and iOS installation acceptance remain outstanding.
