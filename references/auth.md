# Auth-gated sources (x, linkedin)

`x` and `linkedin` types need credentials. v0.1 does not implement
their fetchers — ingest logs a warning and skips them, and the run
continues. This is deliberate: an unreachable source must never fail
the day's episode.

## What's needed to wire them

- **x**: an API bearer token (`THEVIEW_X_BEARER`) or a logged-in
  session. Fetcher to implement in `scripts/ingest.py::fetch_x`:
  user timeline since `since_id`, map to units.
- **linkedin**: a login session cookie (`THEVIEW_LINKEDIN_COOKIE`).
  Fetcher to implement in `scripts/ingest.py::fetch_linkedin`:
  profile recent activity, map to units.

## Rules

- Secrets live in env vars, never in `sources.yaml`, never in git.
- No credentials → skip with a warning, never crash, never retry-loop.
- When a fetcher is implemented, keep the unit schema identical to
  the other types (`references/architecture.md`).
