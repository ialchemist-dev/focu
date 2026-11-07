# Focu Information Gate — provider A/B v0.1

Status: Draft / isolated Muse acceptance only. Defaults to OFF. No production deployment.

## What this change actually implements

The registered-source daily pipeline can now evaluate eligible content with four provider modes:

| Provider | API | Interpretation |
|---|---|---|
| off | None, legacy deterministic source-priority/age logic | zero new model calls |
| openai-llm | OpenAI Responses + Structured Outputs | baseline rubric ratings |
| openai-decisions | OpenAI Decisions API gpt-6-luna | native predicate probabilities |
| jev | TypeSafe Jev jev-latest | native noul probabilities |

The same four questions are used for all model arms: new evidence, explicit goal relevance, contradiction of prior evidence, and benefit of independent verification.

The gate has three modes:
- **off**: preserve existing behavior;
- **shadow**: call providers and store comparisons, without changing the reader, research queue or selection;
- **active**: rank-only adjustment of still-pending items before selection. No automatic suppression, no silent deleting of content, and no automatic research spending. An error leaves legacy ranking in effect.

Provider results, input SHA, model names, token counts, latencies and failures are retained in an independent SQLite ledger at DATA_DIR/gate/ledger.sqlite3. Explicit human corrections are append-only. Only the chosen primary arm influences ranking; comparison arms never change selection.

**Limits:** This is RFC 4 phase one, not the whole vNext product. User-initiated research is not yet compiled into the daily briefing; the LLM Wiki is currently consulted via compact overview/index snippets, not full claim-level graph retrieval; the research_candidate signal does not automatically commission a research agent. The existing PR #22/#23 features still require integration. No current iPhone UI toggle is implemented—choose provider on the CLI or ask the host Muse agent to run it.

## Isolated installation / safety

Test in a clean worktree with a fresh data dir and copied test source config, NOT production:
~~~bash
python -m pip install -e .
python -m unittest discover -s tests -p 'test_*.py' -v
~~~

Provide OPENAI_API_KEY and/or TYPESAFE_API_KEY in the host's secure environment. Do not store API keys in GitHub, YAML, source config or archived test artifacts.

**Privacy:** Source titles/bodies and, when configured, Wiki and principal-goals excerpts go to the selected external API providers. The ledger records SHA hashes and normalized judgments, not full prompts or credentials. You must approve external transmission of sensitive Wiki details before real calls.

## Choose the provider each day

Existing daily entrypoint is run through Python (not an assumed focu-daily console command).

**OFF — current system unchanged:**
~~~bash
python -m focu.daily.cli run \
  --config /test/sources.yaml --data-dir /test/data --date 2026-11-09 \
  --text-only --json
~~~

**SHADOW — compare three provider arms on exactly the same inputs:**
~~~bash
python -m focu.daily.cli run \
  --config /test/sources.yaml --data-dir /test/data --date 2026-11-09 \
  --text-only --json --gate-mode shadow \
  --gate-provider openai-llm \
  --gate-compare openai-decisions,jev \
  --gate-wiki /test/llm-wiki --gate-goals-file /test/current-goals.md \
  --gate-limit 20
~~~

**ACTIVE — use Decisions for rank ordering, keep other arms for comparisons:**
~~~bash
python -m focu.daily.cli run \
  --config /test/sources.yaml --data-dir /test/data --date 2026-11-10 \
  --text-only --json --gate-mode active \
  --gate-provider openai-decisions --gate-compare jev,openai-llm \
  --gate-limit 20
~~~

If you switch between off and active after a day's selection is already frozen, the original selection remains unchanged. Use a new isolated day/run for a different actual selection; use standalone preview for same-input experiments.

**Standalone evaluation, separate from daily publishing:**
~~~bash
python -m focu.daily.cli ingest --config /test/sources.yaml \
  --data-dir /test/data --date 2026-11-11 --json

focu-gate evaluate --data-dir /test/data --date 2026-11-11 \
  --mode shadow --provider jev --compare openai-decisions,openai-llm \
  --wiki-dir /test/llm-wiki --goals-file /test/current-goals.md --limit 20

focu-gate report --data-dir /test/data --date 2026-11-11
~~~

**Explicit feedback, no auto-changing profile:**
~~~bash
focu-gate feedback --data-dir /test/data --date 2026-11-11 \
  --content-id content-id-from-report --verdict missed \
  --note "This result should have been in the briefing"
~~~

Valid verdicts: useful, not_useful, missed, incorrect, too_basic, other.

The max item limit bounds candidate count, not API tokens. Three arms × 20 candidates may make up to 60 paid calls. Cached answers avoid repeat charges on unchanged content/context/provider/policy, unless an explicit refresh is requested. Use small limits for first tests.

## Failure and evidence policy

- Invalid model answers/refusals/HTTP errors are saved as failures; they are never converted into low-value judgments.
- An active model cannot delete, expire, or mark a candidate as covered; it can only change its position among otherwise eligible items.
- A result only applies to the exact item revision used to generate it.
- The original source and the person's explicit goals are not overwritten.
- A model output is not a truth verification, calibrated probability, or proof of value; no opaque model decides final permission to spend or publish.
- For now, the gate leaves the existing daily composition unchanged. The future 30–40 minute unified scripted Briefing needs separate work.

## Real Muse acceptance to do

1. Execute offline tests.
2. Ingest 10–20 actual sources into a fresh isolated test database.
3. After owner-controlled key setup, verify live OpenAI Responses, OpenAI Decisions and Jev requests with actual API responses, cost and timing.
4. Inspect comparison records and disagreement cases; ask the owner to annotate some valuable, unhelpful, and missed information.
5. Run a new-date active rank-only test. Compare against off using frozen equivalent input; confirm selection differs only in ranking and that no item vanishes.
6. Simulate bad credentials, rate limiting and malformed provider results; confirm safe fallback and audit.
7. Report PASS / FAIL / BLOCKED / UNVERIFIED separately for mocked tests, real calls, selected items, briefing and iPhone. Do NOT claim external-provider PASS based on mocked shapes.

This is a paired model comparison, not a randomized causal A/B test. Calibrated thresholds, suppression and automated deep-research triggers need separately approved benchmarks.

Sources:
- https://developers.openai.com/api/docs/guides/decisions
- https://developers.openai.com/api/docs/guides/structured-outputs
- https://api.typesafe.ai/redoc
