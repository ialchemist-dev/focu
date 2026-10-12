# Architecture: v0.2 M1

## Runtime and boundaries

`the_few` owns configuration, identities, collectors, persistence and episode
state. CLI and `scripts/` wrappers invoke it; wrappers do not implement a second
pipeline. One local data directory is one user/profile. Multi-user/server
operation is out of scope.

```
validated sources -> collect -> transactional content store -> backlog selection
                  -> frozen episode inputs -> script -> validated MP3 -> coverage
```

SQLite (`data/few.sqlite3`, schema 1, migrations packaged with the code) is the
source of truth. JSON/text/audio remain inspectable exports. This intentionally
replaces v0.1's overwrite-style JSON state so content, cursors and coverage can
be committed atomically. `few export-state --json` exports all tables, including
private source settings; it is a local diagnostic, not a shareable list.

Modules: `config.py`, `identity.py`, `collectors.py`, `store.py`, `pipeline.py`,
`cli.py`, `legacy.py`. Every writing CLI command holds a kernel `flock` on the
data directory (Linux/macOS). SQLite foreign keys, WAL and FULL synchronous
writes protect state. A crashed process releases the OS lock automatically.

## Identity

Source ID: SHA-256 of `src:v1:` + canonical source URL. Content ID: SHA-256 of
`cnt:v1:` + canonical item URL. Labels, channels and transport types do not
participate. Override `canonical_url` to retain a source identity when changing
transport; automatic URL-move aliases and canonicalizer upgrades are future work.
Use a stable YouTube `channel_id` where available; handle changes otherwise
require an explicit identity-preserving canonical_url.

Canonicalization lowercases hosts, removes fragments and known tracking params
(`utm_*`, fbclid, gclid, dclid, msclkid, mc_cid, mc_eid). It preserves unknown
query parameters, path case and arbitrary trailing slashes/www names. YouTube
watch/short-link/shorts/embed/live URLs normalize to a watch URL with its significant
`v` parameter. Twitter URLs normalize to x.com. Different videos remain different.
Unknown URLs receive conservative identities, rather than guessed equivalences.

No URL: source ID + native item ID is a fallback. No stable item key:
provisional identity; title alone never causes permanent merging, and provisional
items are not selected. Same URL with richer text produces revisions; selection
prefers the longest available body. M1 deliberately does not infer meaningful
updates or republish previously covered URLs. Semantic event dedup is deferred.

## Storage and eligibility

`sources/subscriptions` separate identity from channel/quotas. `contents`,
`content_revisions`, `observations` preserve transport provenance and text.
`fetch_state/fetch_attempts` preserve native cursors and outcomes.
`candidates` holds pending/expired/dismissed state. `runs/stage_runs`,
`episodes/episode_items`, `coverage` represent the generation lifecycle.
Feedback and list-install tables will be added by later migrations when used.

Each fetch batch and its safe cursor commit together. Failed/partial/windowed
fetches do not advance the cursor. RSS always scans its available window, so
reordering and repeated items are harmless upserts. Cursor is a native hint,
not proof that older feed items were obtained. No selection quota is applied
to persisted collection. Conditional requests, bounded retries, RSS archives,
HTML parsing and pagination completeness are M2 work.

Candidates require a non-empty body, a non-provisional identity, an enabled
subscription and no existing coverage/reservation. Missing-body discoveries wait
for later enrichment. Date parsing uses UTC ISO timestamps; missing/unzoned dates
fall back to fetched_at. Default retention is 7 days from publication or first
fetch, adjustable per source. Expiration retains content identity; no semantic
importance estimator or evergreen classification is present yet. Source priority
and age determine deterministic ranking. Source count and approximate speaking
word budgets limit selection, rather than truncating or discarding collected
content. Oversized items remain pending until summarized in M3 or expired.

Global per-user coverage prevents repeated content across dates/channels. One
source has one channel in M1. Items reserved by a failed earlier episode are not
silently duplicated in a later date: resume that original date. `few status`
shows unfinished episodes. Reservations do not mean covered/delivered/played.

## Frozen episode lifecycle

A daily run freezes content configuration and output mode. After selection it
freezes unit/revision JSON. Script retries restore stored text; they do not ingest
again. Repairing `tts_argv` or its environment command is allowed without changing
frozen content. Other config changes require a new date.

Draft -> script_ready -> finalized. Audio mode finalizes only after a non-empty,
decodable MP3 passes ffprobe/ffmpeg checks. Text_only must be explicitly selected.
Missing TTS and failures are visible; no coverage is written on failure. There
is no delivery/player API or receipt for actual listening in M1.

Audio writes to a temp file and is atomically renamed. A receipt ties audio
hash to script hash/episode ID so a crash after publishing audio can resume
without repeating TTS. An artifact manifest is written before coverage commits.
Finalization and coverage commit in one transaction. Finalized episodes are
never rewritten; future revision/supersession needs a separate feature.
Container validation does not prove speech completeness or human listening;
speech-to-script quality validation is future work.

Exports: `units/<date>.json` is the current content inventory at collection time,
not today's delivery ledger; `digested/<date>.json` is the frozen selection;
`episodes/<date>/<channel>-{script.txt,units.json,manifest.json}` plus MP3.
The deterministic composer preserves full selected text and ASCII Host labels;
it does not use prompts.md, translate, summarize long items, or learn feedback.

## Legacy import

`few import-legacy` requires a separate non-nested destination. It validates
snapshots while the old scheduler is stopped. It matches
snapshot source names against enabled config, backs up state/units/digested/
episodes, imports content additively, and never applies old watermarks. Missing
snapshots cannot be reconstructed from state.json. No automatic historic coverage
is inferred. `--register-coverage` is an explicit operator attestation, requiring
non-empty scripts (and MP3 files in audio mode); it does not validate past speech
or infer delivery/listening. Legacy runs do not occupy new daily date slots.
Unknown sources require their original names/locators to be supplied in config.
Original files remain intact; safe repeated import dedupes content/coverage.

See [../docs/V0.2-PLAN.md](../docs/V0.2-PLAN.md) for later milestones.
