# Focu v0.4 — Article-First Muse Acceptance Report

**Date:** 2026-11-03 (America/Denver)
**Branch / commit tested:** `feat/v04-unified-content-feed` @ `c07936c0a5c6ffe2685f18034e07dbb11623ec03` (PR #18, Draft — not merged)
**Artifact:** `focu-v04-test` (private Muse web artifact), updated in place. The production `focu-podcast-library` was not modified.
**Bundle:** `~/workspace/focu-artifact-builds/v04-article-first-a` (publish.py, offline defaults only — no `--fetch-source-covers`, no `--generate-editorial`, no `--generate-ai-covers`; none of the paid/network options were authorized or used)
**Status labels:** Pass = directly verified · Fail = directly observed failure · No data = required source material unavailable · Unverified = not tested or insufficient evidence.

---

## 1. Unit tests and CI

- Local: `python3 -m unittest discover -p 'test_*.py' -v` in `experiments/muse-artifact-reader` → **13 tests, all pass**.
- JavaScript syntax: the template's inline script extracted and checked with `node --check` → **OK**.
- GitHub Actions at head `c07936c0a`: latest runs **success**. An earlier run at `609ae8a40` failed and was superseded by the `c07936c` fix (summary punctuation). CI green is not treated as device validation.

## 2. Content items used (8, all real production deliveries)

| published_at | content_id | formats |
|---|---|---|
| 2026-11-03 | frontier-20261103 | article + audio |
| 2026-11-02 | frontier-20261102 | article + audio |
| 2026-10-31 | frontier-20261031 | article + audio |
| 2026-10-30 | frontier-20261030 | article + audio |
| 2026-10-29 | frontier-20261029 | article + audio |
| 2026-10-28 | frontier-20261028 | article + audio |
| 2026-10-28 | felix-hunger-20261028 | article + audio |
| 2026-10-27 | frontier-20261027 | article + audio |

Article-only and audio-only items are supported by the publisher and covered by unit tests (`test_…article-only/audio-only…`); no such items exist in this delivery set, so that path is **Pass at unit level, No data at bundle level**.

## 3. Integrity verification — Pass

- All 8 bundled MP3s are **SHA-256 identical** to the original files in `~/workspace/focu/data/deliveries/<content_id>/podcast.mp3` and to `build-report.json` (8/8, three-way).
- The manifest embedded in `index.html` is equivalent to `assets/episodes.json`; content_ids are unique; `published_at` values are valid ISO dates in newest-first order.
- Every audio, article, and cover path in the manifest resolves inside the staged bundle and inside the published Artifact.
- The canonical `items` list carries all 8 items; the legacy `episodes` array remains present for audio-based consumers.
- No MP3 was regenerated or re-encoded at any point.

## 4. Cover inventory

| origin | count |
|---|---|
| Original (local file in delivery) | 0 — **No data**: no production delivery contains an original image |
| Source image fetched from metadata | 0 — not enabled (requires explicit authorization) |
| AI-generated | 0 — not enabled (requires provider access + cost authorization) |
| Offline typographic SVG (cover_art) | 8 |

No headphone placeholder tiles are used. Offline SVGs are deterministic, content-specific artwork; they are not described anywhere as AI images.

## 5. Titles and summaries — Pass with a recorded publisher gap

The raw publisher output derives headlines from the first substantive finding, which produces truncated sentence fragments (e.g. "A user querying a model today cannot check that the responses came from the…"), and one question-form headline (the Felix item, whose report is a Q&A). The deployed Artifact therefore carries a **build-time editorial patch**: concise, grounded titles and summaries (e.g. "Provable Inference, Pando, and LifeVal — Frontier Briefing, November 3, 2026"), applied identically to the `items` and legacy `episodes` arrays, with covers regenerated from those titles via the repo's own `cover_art.typographic_svg`. This patch is **not** publisher output and is recorded here so it is not mistaken for one. **Recommendation:** the publisher should emit concise titles itself (or consume curated `content.json` metadata) so the editorial patch becomes unnecessary.

## 6. Article rendering — Pass (audit level), device visual check pending

- Articles are generated deterministically from each delivery's `research.md`, preserving findings, uncertainty notes, and source links; no raw JSON or Evidence Pack structure is shown.
- In the published Artifact, tapping a card opens an in-page reader (title, date/source, summary, full article) — no separate browser window. Article HTML is fetched client-side and sanitized before rendering (scripts/styles/iframes/forms and event handlers stripped).
- The earlier v0.4 report's fixture article (hand-built `article.html`) is superseded: all 8 items now carry publisher-generated articles.

## 7. Automatic completion — implementation Pass; device observation Unverified

Triggers verified in the published build's source, matching `V04_IMPLEMENTATION.md`:

- **Article:** archive only when the reader reaches the article end, reaches ≥70% of the available scroll depth, and accumulates length-scaled active dwell (8s / 18s / 30s). Merely opening the article, or fast-scrolling straight to the bottom, does not satisfy the conditions.
- **Audio:** archive only at the native `ended` event with ≥80% union of actually-played intervals (accumulated from non-seeking playback). Seeking directly to the end does not archive. Pausing does not archive.
- There are no Mark done / Done reading controls. Completion of either format archives the whole Content Item under its single content_id.

Native audio controls cannot be driven by the build harness, and scroll/dwell behaviour in the iOS WebView has not been observed yet: **device observation is Unverified** and is exactly what Phase A (below) tests.

## 8. Archive and Restore — Pass (build level)

Archive retains each consumed item with both article and audio accessible; Restore returns the item to the Inbox without duplication (state is a map keyed by content_id under `focu:content-consumption:v1`; restoring deletes the entry). Exercised by probe on the previous v0.4 build and source-verified in this build; device confirmation folds into Phase A.

## 9. Publishing incident (Muse-side, not a branch defect) — recorded

The first in-place edit of `focu-v04-test` deployed a hybrid: the new article-first UI over the previous experiment's 5-item manifest (only 1 item with an article, 0 covers, and completion thresholds that did not match `V04_IMPLEMENTATION.md`). The staged bundle from §5 of the task was not used. This was corrected by a second in-place edit that installed the staged bundle (`v04-article-first-a`) itself; the published build's thresholds now match the implementation document. The pre-correction state was backed up by the builder before replacement. Lesson recorded for future Muse-side publishes: verify item count, article coverage, and cover inventory of the *published* artifact against the staged bundle, not just the page UI.

## 10. Cross-update persistence (release-blocking) — Unverified

Consumption state lives in `localStorage` under `focu:content-consumption:v1`. Whether the Muse iOS WebView preserves that storage across an in-place Artifact update cannot be observed from the build environment (the audit harness uses a fresh browser profile per session).

- **Phase A (ready, awaiting the user):** open `Focu V04 Test` on iPhone, read or listen through one identifiable item until it auto-archives, confirm it is absent from Inbox and present in Archive, and record its content_id. No rebuild will be made before the user confirms.
- **Phase B (not started):** after confirmation, stage a new bundle preserving the consumed item's content_id (adding one new real item if available), update the same entry in place, and re-check on device, followed by a controlled force-quit and reopen.

## 11. Reopen and force-quit resilience — Unverified

Ordinary reopen, navigation away/back, and controlled force-quit of the Muse iPhone app have not been performed. They are scheduled after Phase B per the test protocol, and are not upgraded to Pass on the basis of the previous UI's results.

## 12. Failures, limitations, recommendations

- **Fail (publishing step, corrected):** the first edit's hybrid deployment in §9.
- **Publisher gap:** finding-derived headlines are truncated sentences; one is question-form. Emit concise titles in the publisher (see §5).
- **No data:** original covers (none exist in deliveries); article-only/audio-only items at bundle level (none in this set).
- **Unverified:** all on-device behaviour — iOS rendering of SVG covers and relative asset paths (the failure class that broke the v2 library), reading-completion timing, audio play/pause/seek and play-through archiving, cross-update persistence, force-quit survival.
- **Not enabled:** LLM editorial generation and AI covers (opt-in, billable; require the user's key and explicit cost authorization). URL/citation validation in that path checks URL presence in the source report, which is not factual verification.
- **Recommendation:** keep PR #18 Draft until the Phase A/B device protocol passes; if localStorage does not survive the in-place update, record the failure precisely and do not introduce a server/database/sync workaround without the user's approval.
