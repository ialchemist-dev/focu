# Finite reader and source marketplace

Implementation: Python/SQLite core, same-origin JSON API, mobile web UI, PWA app shell, pinned pack subscriptions, explicit RSS/Atom collection and finite publication. No dependency on unmerged PRs or paid generation services.

## Run

```bash
python -m focu.cli --db data/focu.sqlite3 reader serve --media-root data --port 8765
```

Open http://127.0.0.1:8765 on the machine running Focu. The initial inbox is empty: no sample content, auto-subscription or synthetic research is inserted. Discover shows packaged source groups. Select a group to inspect its authors, identity links and transport readiness, then subscribe explicitly.

The development server is intentionally loopback-only and rejects foreign Host/Origin headers. For use from an iPhone, deploy the same-origin API and frontend behind authenticated HTTPS with a production server adapter; do not expose this local HTTP server. The manifest/service worker are implemented, but remote hosting, authentication and real iOS Add to Home Screen acceptance are not complete. Service worker caches only the shell; research/API/media responses remain private and uncached. Safari installation uses Share -> Add to Home Screen once HTTPS hosting exists.

## Muse handoff: subscribe, collect, research, publish

Use Discover to subscribe, or explicitly run:

```bash
python -m focu.cli --db data/focu.sqlite3 reader subscribe anthropic-personal-blogs --version 0.1.0
python -m focu.cli --db data/focu.sqlite3 reader sources > /tmp/focu-subscribed-sources.json
python -m focu.cli --db data/focu.sqlite3 reader collect --output data/reader-collection.json
```

`collect` requests only enabled subscribed RSS/Atom sources, at most 2 MB per feed with a 15-second request timeout. Failed/disabled sources remain explicit. Repeated identical source URL/title/text snapshots deduplicate into a durable raw queue. The pending queue is exported on retries until explicitly acknowledged. Feed excerpts are raw material, not verified research or necessarily full articles. Collection does not call an LLM, generate audio, publish cards or register additional sources.

Muse reads the pending queue, chooses a bounded set fitting the user's intent/language/length budget, retrieves original pages as needed, creates an Evidence Pack using the existing provenance contract, and runs the existing research/report/podcast workflow. After research is completed and its canonical report is archived:

```bash
python -m focu.cli --db data/focu.sqlite3 report ev_REAL_ID --output data/reports/research.md
python -m focu.cli --db data/focu.sqlite3 reader publish \
  --batch-id frontier-unique-batch --title '本次 AI 阅读' \
  --evidence-id ev_REAL_ID --limit 10
```

Repeat `--evidence-id` to publish several distinct reports atomically. Publication requires completed research correctly linked to its evidence pack and an archived `research:ID` report. Retrying unchanged publication succeeds; changing a published batch or item fails. New formats should be prepared before publishing an immutable item; later format revisions need a future explicit versioning design.

Optional `--media-json data/reader-media.json` maps evidence IDs to local files relative to `--media-root`:

```json
{"ev_REAL_ID":{"audio":"deliveries/frontier/podcast.mp3","video":"deliveries/frontier/video.mp4"}}
```

Only available media should be registered. Media URLs contain item IDs, never local filesystem paths. Root containment, symlinks and file suffix are checked on reads. Audio/video byte ranges support seeking. There is no video generator in this implementation.

After successful publication, acknowledge the *specific* raw queue entries covered by the report:

```bash
python -m focu.cli --db data/focu.sqlite3 reader acknowledge --record-id REAL_RAW_RECORD_ID
```

Acknowledgement is a separate explicit ingestion operation, not user reading completion. Do not mark unseen raw records covered, infer preferences from scrolling, or start recurring collection without an explicitly configured host workflow. Opening or refreshing the reader never starts collection or generation.

## Interfaces

- GET `/api/batches`, `/api/batch?id=...`, `/api/library`, `/api/packs`, `/api/sources`
- POST `/api/state`: `{ "id": "ev_ID", "changes": { "completed": true } }` (or saved boolean)
- POST `/api/subscribe`: `{ "id": "anthropic-personal-blogs", "enabled": true, "version": "0.1.0" }`
- GET `/media?id=ev_ID&kind=audio` (or video)

Mutations require JSON and the same-origin `X-Focu-Reader: 1` header; API GETs never mutate subscriptions, publish or generate. This is a single-owner local app; multi-user isolation is a production-hosting requirement.

## Verification and remaining work

Offline tests cover batch atomicity/idempotence, persisted state, shared consumption identity across formats/batches, pinned membership/source dedup, media byte ranges and path escapes, and foreign-origin/Host rejection. RSS source checks are recorded in ANTHROPIC_SOURCE_DISCOVERY.md. Source discovery is an initial verified six-author pack with four enabled feeds, not all Anthropic employees. HTML blog adaptation, hosted HTTPS/authentication, live Muse publication from the user's own DB and physical iOS installation remain separate acceptance items.
