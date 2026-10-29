# Source collector PoC: Muse acceptance

Goal: validate two popular upstream projects without coupling the Focu evidence model to their internals.

- YouTube: [jdepoix/youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api), primary transcript adapter. The dependency is optional (`pip install youtube-transcript-api`). No yt-dlp fallback is implemented yet; log explicit failures instead of pretending fallback succeeded.
- LinkedIn: [stickerdaniel/linkedin-mcp-server](https://github.com/stickerdaniel/linkedin-mcp-server). **Focu does not automate LinkedIn login or scrape its Feed.** An operator may export posts from a permitted, authorized MCP session to JSON and import them. Check LinkedIn policies and account risks before using the upstream tool.

## Commands

```bash
focu --db data/focu.sqlite3 collect youtube 'https://www.youtube.com/watch?v=VIDEO_ID' --scope frontier-youtube --output data/collectors/youtube.json
focu --db data/focu.sqlite3 collect linkedin-export --input data/collectors/linkedin-feed.json --scope frontier-linkedin --output data/collectors/linkedin.json
```

LinkedIn input: `{"posts":[{"post_url":"https://www.linkedin.com/feed/update/urn:li:activity:.../","text":"...","author":"...","published_at":"..."}]}`. It also accepts a top-level list, `items`, and `url`/`content` aliases. Upstream output may differ; explicitly map upstream data to this contract, do not assume compatibility.

## Acceptance matrix

YouTube: test 10–20 publicly accessible videos across channels and transcript languages. Record transcript success, failure type, segments and timestamps, wall-clock latency, network/proxy settings, and rate-limit incidents. Never download audio or generate ASR without an explicit decision.

LinkedIn: with an authorized account and isolated browser profile, validate a small manual MCP feed export; check real post permalinks, text fidelity, repeated-run deduplication, login/session longevity and behavior after VM replacement. Do not store cookies, tokens or session profiles in Focu's SQLite or output JSON.

Both: verify repeat observations are unchanged and changed content is recorded; verify source URL, author when known, collection method and collection time. SourceRecords are **unverified collected material**, not Evidence Packs; research verification and provenance validation remain separate.

Stop criteria: authentication challenges, rate limiting, account warnings or unexpected platform behavior. No automated scheduled LinkedIn collection in this PoC.
