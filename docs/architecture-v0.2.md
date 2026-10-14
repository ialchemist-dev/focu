# The Few v0.2 — Architecture (incremental proposal)

**Mission:** Agent-native information digestion: user-curated entities and sources, recurring routines, captured research intents, traceable evidence, and user-controlled delivery. Protect attention; never optimize for engagement.

## Data flow

Subscriptions + Routines + One-time Intents → Research/Ingestion → Evidence Packs → Digest Sessions → Renditions (reading/audio first).

### Contracts

- `schemas/intent.schema.json`: user-authored question and lifecycle. One-off research must **not** silently become a permanent subscription.
- `schemas/evidence-pack.schema.json`: research summary, findings, and cited source records. Each finding references one or more IDs in `sources`; the research agent must preserve disagreements and uncertainty.
- `schemas/digest-session.schema.json`: planned attention budget, ordered evidence references, and output renditions. An empty session is valid; do not manufacture filler.

These schemas are versioned at `0.2` and are contracts, not a claim that research, planning, or rendering are implemented. The first PR implements only intent capture/persistence and contract files.

## Persistence and lifecycle

`the_few.intents.IntentStore` stores intents in a local SQLite DB (default `data/the-few.sqlite3`, git-ignored). Capture uses a generated stable `int_<uuid4hex>` identifier; a caller may supply an existing ID to make retries idempotent. Lifecycle: `queued → researching → completed`, or `researching → failed → queued`. Completion requires an evidence pack reference; the current module does **not** verify that the referenced pack exists. Transitions use compare-and-swap updates to prevent stale workers overwriting another worker's state.

Example:

```bash
python -m the_few.intents capture 'What is the economics of advertising?'
python -m the_few.intents list --status queued
python -m unittest discover -s tests -v
```

## Compatibility and next increments

The existing v0.1 `scripts/run-daily.sh` pipeline remains unchanged. Next: persist and validate evidence packs with source-ID referential integrity, implement agent research handoff, compose a Markdown rendition, add user-configured neural TTS with BYOK and audio QA, and only then merge with scheduled routines and backlog.

## Non-goals for this slice

Marketplace, semantic claim ledger, knowledge graph, video, and automatic subscription expansion.
