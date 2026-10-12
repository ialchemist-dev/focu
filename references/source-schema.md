# Source/config schema

```yaml
version: 2
timezone: America/Denver
output_mode: audio  # audio | text_only
channels:
  - id: research
    name: Research Digest
    language: en
    voice: default
    max_minutes: 12
    words_per_minute: 150
sources:
  - name: Ethan Mollick
    type: rss
    channel: research
    feed_url: https://www.oneusefulthing.org/feed
    max_items_per_day: 5
    retention_days: 7
    priority: 1
```

Versions 1/2 are accepted. UTC and audio are defaults; text-only completion must
be explicit in config or CLI. Channel IDs are unique safe filename components.
Configured source names must be unique/non-empty and channels must exist.
Disabled sources may be incomplete placeholders. Unknown enabled types fail
validation before fetch. Renaming a source keeps its URL identity unchanged.

Locators:

- rss: feed_url required; optional canonical_url to preserve identity.
- blog: site_url or feed_url; only blog-with-feed can fetch in M1.
- youtube: channel_id (preferred stable ID) or handle; optional dependencies;
  experimental latest-ten window, no full backfill or yt-dlp subtitle fallback.
- x: username; collector not implemented.
- linkedin: profile_url or company_page URL; collector not implemented.

Common settings: enabled (boolean), notes (private curator text),
max_items_per_day (positive selection quota, not a fetch cap), retention_days
(positive expiry window), priority (positive source weight). No feedback-driven
updates are implemented yet. Every source belongs to one channel. Same canonical
URL twice is a config error: merge subscriptions rather than assigning new IDs.

`source_id` and `content_id` are core-generated, versioned full SHA-256 IDs. Manual
units from an agent must identify an enabled source by its configured name or
source_id. Output channel is always derived from config, never trusted from units.
Secrets belong in the environment, not in YAML. Personal config/data stays out
of git; `examples/sources.yaml` is deliberately tracked.
