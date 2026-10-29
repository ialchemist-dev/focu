# Source schema (`sources.yaml`)

```yaml
version: 1

channels:
  - id: research            # episode id; one MP3 per channel per day
    name: "Research Digest"
    language: zh            # episode language
    voice: default          # TTS voice key (see references/tts-backends.md)
    max_minutes: 12         # target episode length; compose aims here

  - id: personal
    name: "Personal Briefing"
    language: zh
    voice: default
    max_minutes: 6

sources:
  - name: "3Blue1Brown"
    type: youtube           # rss | youtube | blog | x | linkedin
    channel: research       # which episode this source feeds
    handle: "3blue1brown"   # type-specific locator (see below)
    notes: "Grant Sanderson's math channel"

  - name: "Ethan Mollick"
    type: rss
    channel: research
    feed_url: "https://www.oneusefulthing.org/feed"
```

## Per-type locators

- `rss`: `feed_url` (required).
- `youtube`: `handle` or `channel_id` (explicit channel ID). Optional `playlist_id`
  to scope to one playlist.
- `blog`: `site_url` (required); `feed_url` (optional — used first when
  present, else requires host HTML collection; the bundled daily adapter reports unsupported).
- `x`: `username` (required). Requires credentials — see
  `references/auth.md`.
- `linkedin`: `profile_url` or `company_page` (required). Requires a
  login session — see `references/auth.md`.

Legacy `type: anthropic` with `section: news | research | engineering` is accepted by the daily config loader as the corresponding official blog URL. This registration does not implement an HTML collector.

## Common fields

- `name` (required): human label, shown in the episode ("Elon Musk
  posted…").
- `channel` (required): must match a channel id.
- `notes` (optional): curator's note, e.g. "only posts about agents".
- `enabled: false` (optional): keep the source defined but skip it.
- `max_items_per_day` (optional, default 5): cap per source so one loud
  source can't eat the episode.

## Rules

- A source belongs to exactly one channel.
- Unknown `type` → ingest errors loudly at startup (fail fast on config
  bugs, degrade gracefully on network/auth failures).
- `sources.yaml` is personal — never commit it. Share `examples/`
  instead.
