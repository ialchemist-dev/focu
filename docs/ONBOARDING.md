# Onboarding a new user

The Few is meant to be handed to another person (or their agent) as a
link. They should be able to go from "I got this repo" to "my daily
podcast is scheduled" in one sitting, without reading the whole repo.
This doc is the script for that — an agent with this repo open can run
it as-is.

## The default questions

Ask these, in order. Every answer maps directly to `sources.yaml` or
a channel setting. Defaults are marked; if the user says "just use the
defaults", apply all of them.

1. **Who do you want to follow?** Name 3–10 people whose work you
   actually want to keep up with — researchers, writers, builders,
   YouTubers. (Follow people, not platforms: each source is a person
   or an editorial voice, never an algorithmic feed.)
2. **Any official blogs or labs?** e.g. OpenAI blog, Anthropic news,
   Google DeepMind blog. These are the only institutions allowed —
   no news aggregators, no trending pages.
3. **How many episodes per day?** Default: one research digest.
   Optional: a second, shorter personal briefing channel.
4. **How long per episode?** Defaults: research 12 min, personal 6 min.
5. **What language?** Default: English.
6. **What should the host be called?** Default: 小北 (Xiaobei).
   (Voice mapping lives in `references/tts-backends.md`.)

Then: write `sources.yaml` from the answers (schema in
`references/source-schema.md`), choose timezone and audio/text_only explicitly, configure TTS if audio,
run `few run --dry-run --json`, then run once to verify an artifact and schedule it (see `references/scheduling.md`).

## Recommended starter packs

If the user has no strong opinions yet, offer one of these. Each is a
complete `sources:` block they can paste into `sources.yaml`.

> **Groups** are the laziest way to start: a group is a named bundle of
> sources kept in `examples/groups/<name>.yaml`. The user picks a group,
> the agent copies its `sources:` block into their `sources.yaml`, and
> they're done. Current groups:
>
> - `ai-frontier` — official news from the frontier labs (OpenAI News, with Anthropic News defined but disabled until M2). The default recommendation.
>
> New groups are welcome as pull requests: one file per group, same
> shape as `examples/groups/ai-frontier.yaml`.

**AI labs tracker** — what the frontier labs officially publish:

```yaml
sources:
  - name: "OpenAI News"
    type: rss
    channel: research
    feed_url: "https://openai.com/news/rss.xml"
  - name: "Anthropic News"
    type: blog
    enabled: false  # HTML collector not implemented in M1
    channel: research
    site_url: "https://www.anthropic.com/news"
  - name: "Google DeepMind"
    type: blog
    enabled: false  # HTML collector not implemented in M1
    channel: research
    site_url: "https://deepmind.google/discover/blog/"
```

**Learning & thinking** — explainers and essays, low volume:

```yaml
sources:
  - name: "3Blue1Brown"
    type: youtube
    enabled: false  # experimental; install the optional youtube extra first
    channel: research
    handle: "3blue1brown"
  - name: "Ethan Mollick"
    type: rss
    channel: research
    feed_url: "https://www.oneusefulthing.org/feed"
```

**One person, deeply** — e.g. following a single builder:

```yaml
sources:
  - name: "Elon Musk"
    type: x
    enabled: false  # collector not implemented in M1
    channel: research
    username: "elonmusk"
    # needs X API access or a session; skipped gracefully without it
```

## Notes for the onboarding agent

- Keep the source list short at first (3–7 sources). A loud source
  can be capped with `max_items_per_day`.
- Keep X/LinkedIn and HTML-only sources disabled: their collectors are not
  implemented in M1. Credentials alone do not make them supported.
- Never add a source the user didn't name or approve. The contract
  (SKILL.md) forbids the pipeline from pulling anything outside
  `sources.yaml` — the onboarding must not either.

## M1 completion check

Default examples enable RSS only. Do not report audio setup complete without
a validated MP3 and finalized manifest. Text_only must be explicitly chosen.
M1 does not summarize/translate or run prompts; body-rich short RSS items produce
a deterministic skeleton. Read README for v0.1 migration before touching data.
