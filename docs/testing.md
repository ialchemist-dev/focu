# Testing The Few v0.2

## Offline tests (default CI)

Run from repository root:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m unittest discover -s tests/unit -p 'test_*.py' -v
```

The default tests use temporary SQLite databases and a loopback HTTP server. They verify persistence, evidence referential integrity, state transitions, local HTTP extraction and failure handling, and the evidence-to-Markdown handoff. **They do not establish factual correctness.**

## Live internet smoke tests (opt-in)

```bash
THE_FEW_LIVE_TESTS=1 python -m unittest discover -s tests/integration -p 'test_*.py' -v
```

These access real external websites, can fail due to networking, rate limits or website changes, and must not be treated as deterministic unit tests. In GitHub Actions use **Run workflow** for the manually triggered live-web job. No API keys are needed for the public-page smoke test.

## Agent-assisted acceptance test (manual, real research)

1. Capture: `python -m the_few.intents capture 'What is advertising?'` and record the ID.
2. Move that intent to `researching` using `IntentStore.transition(id, 'queued', 'researching')`.
3. Ask your research agent to retrieve **real** primary sources and write an Evidence Pack JSON matching `schemas/evidence-pack.schema.json`. Each finding must cite an existing source ID; check original pages and record uncertainty. Do not substitute invented references.
4. Ingest and render: `python -m the_few.research --evidence /path/to/evidence.json --output data/research/advertising.md`.
5. Review the saved Markdown, original URLs, and factual alignment. Record any dead links, incorrect attributions, unsupported claims, and omissions.

The handoff is functional, but the research agent is **not automatically orchestrated** by this repo yet. Web retrieval currently handles public HTML/plain-text pages only, not PDF or JavaScript-rendered pages. Live fetching of untrusted URLs must run with network egress controls before deployment in an agent/server environment (SSRF protection is not yet implemented).

## Quality gates before production

- Unit tests and loopback HTTP tests pass.
- Live smoke test succeeds on at least one real public source.
- Real research produces a reviewable Evidence Pack and cited Markdown.
- A human checks that claims are actually supported by cited pages.
- Long-form audio delivery is a later milestone; do not label this slice podcast-ready.
