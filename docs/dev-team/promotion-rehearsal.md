# Promotion rehearsal — the composed dev-main system, end to end

- When: 2026-11-17 (plan-4 direction 1). Artifact: `tests/test_promotion_rehearsal.py` (2 tests).
- Why: every wave of this run tested its own slice. Nothing had ever run the composed system — pack install, daily pipeline, day-status, publisher, learn ingest, proposals — as one exercise. A promotion decision made on slice tests alone is a leap; this rehearsal converts the in-repo part of it into a checklist with a green test behind it.

## What was exercised (scratch runtime only, no network, no production path)

1. **Pack install** of a fixture pack into an empty v2 daily config (`install_pack`, liveness off) — the registry gains exactly the pack's source.
2. **Daily pipeline** (`run_pipeline`, text-only, local units file) over that registry — one episode finalized, `day_status` outcome `success`, zero discrepancies.
3. **Day-status CLI** (`focu daily day-status`) — prints the stored record's summary verbatim and the pack source's collected/considered/selected line.
4. **Reader publisher** (`publish.build`) — a registered-item delivery built from the pipeline's selected unit (per the publisher's `content.json` contract: `content_id`, `source_name`, `source_url`) plus a daily-compilation delivery whose article is the pipeline's composed script and whose `covered_content_ids` names the unit. The bundle's compilation resolves its coverage; the covered item keeps its real source name and original URL.
5. **Learn ingest** — a reading-summary export marking the *compilation* Not-for-me fans out (F1) to exactly one `not_useful` event on the covered unit; nothing pools as unattributed.
6. **Proposals** — on one attributed event the engine drafts nothing, states `insufficient attributed signal: 1 events in 30 days`, and its sparsity slot for the source is keyed by the same `source_id` the pack install minted. The preference record's bytes are unchanged by the whole exercise.
7. **Repeatability** — re-running the same day reuses the run and its stored day-status; re-ingesting the same export records zero new events.

## The identity result

The rehearsal's load-bearing finding is that one identity survives the whole chain: pack-install `source_id` == pipeline unit `source_id` == learn sparsity key, and publisher compilation coverage resolves to the pipeline's `content_id`. The two historical leak classes — Q6's registry/reader identity divergence and F1's unattributed briefing marks — do not recur in the composed system.

## What the rehearsal does NOT cover (the remaining promotion checklist)

- **Audio / TTS.** The rehearsal runs text-only. Synthesized-audio finalization, the script-QC → TTS → post-audio audit chain, and the voice rate-limit failure mode are production-path concerns, untested here by design.
- **Live collectors.** Ingest consumed a local units file. Real RSS/adapter collection at human pace against real feeds is the production job's behavior, not rehearsed.
- **The host bridge that writes delivery folders.** In production, delivery folders for the publisher are written by host-side steps outside this repo. The rehearsal constructs them from pipeline outputs strictly per the publisher's documented `content.json` contract; whether the production host writes them in exactly that shape is a promotion-time verification, not something this test can prove.
- **Scheduling and hosting.** Who runs `focu pack refresh-due`, the reader's hosting, and Q11 cold-start implementation remain promotion decisions for the owner, as recorded in BACKLOG (Q2, Q11).

## Verdict

The in-repo composed chain is coherent and safe to promote as far as this exercise reaches: no integration defect was found, no product code changed, and the exercise is now a permanent regression test — a future wave that breaks a seam between subsystems fails this test instead of failing silently at promotion.
