# Focu v0.4 — Muse Acceptance Report

Validation of the first Unified Content Feed implementation (Podcast + Article
sharing one `content_id` and one consumption state) on Muse Artifacts.

## 1. Branch and commit tested

- Branch: `feat/v04-unified-content-feed`
- Commit: `609bc98154f8713a7295cbd4298b357e997877ae`
- PR: #18 (left as Draft; nothing merged to main)
- Test Artifact: `focu-v04-test` (separate private entry; the validated
  production `focu-podcast-library` was not modified — its files predate this
  session and were not rebuilt).

## 2. Unit tests

Command:

```
cd experiments/muse-artifact-reader
python3 -m unittest -v test_publish.py
```

Result: **5 ran, 5 passed, 0 failed** — `test_build_and_checksum`,
`test_dates_and_chronological_limit`, `test_muse_loader_fallback_structure`,
`test_reject_empty_and_unsafe_output`,
`test_unified_item_with_article_and_editorial_metadata`.

## 3. Bundles

Fixture deliveries: `~/workspace/focu-v04-test-deliveries/` (copies of real
production deliveries; production data untouched, no MP3 regenerated or
re-encoded). One fixture item (`frontier-20261103`) carries an acceptance-only
`article.html` derived verbatim from its own `research.md` plus a
`content.json` with a content-specific English title and summary.

- Version A: `~/workspace/focu-artifact-builds/v04-test-a` — 4 items
  (`frontier-20261103`, `frontier-20261102`, `frontier-20261031`,
  `felix-hunger-20261028`).
- Version B: `~/workspace/focu-artifact-builds/v04-test-b` — same 4 items plus
  `frontier-20261029`; consumed item's `content_id` unchanged; no duplicate
  content IDs.

Manifest checks (both bundles): every item has a stable `content_id` equal to
its delivery folder name; `items` and legacy `episodes` arrays are identical;
the manifest embedded in `index.html` is byte-equivalent (after JSON parse) to
the staged `assets/episodes.json`; dates are valid ISO dates, ordered newest
first; title/summary from `content.json` populate only the fixture item, all
other items fall back to their `research.md` heading.

## 4. SHA-256 verification

**Pass.** Every entry in each bundle's `build-report.json` matches the bundled
file on disk, and every bundled MP3 is byte-identical (SHA-256) to both the
fixture copy and the original production delivery file in
`~/workspace/focu/data/deliveries/`.

## 5. Article/Podcast shared-state results (audit-browser probe, Version A)

Driven live against the published test Artifact:

- Open Inbox — all 4 unconsumed items appear. **Pass**
- Mark article done ("Done reading" on `frontier-20261103`) — the *entire*
  item left the Inbox; Podcast and Article were not tracked separately.
  **Pass**
- Open Archive — the completed item appears, and its archived card still
  exposes both the audio player and the "Read article" link. **Pass**
- Mark unread — the item returned to the Inbox (count back to 4). **Pass**
- Audio playback and seeking — the native player renders with controls on
  every card, but the audit probe cannot operate native audio controls or
  observe playback position, and the `ended` → consumed transition could not
  be driven end-to-end. **Unverified** in this environment (manual iPhone
  steps below).
- Invalid/missing audio — the reader attaches an `error` listener that
  appends a visible "Audio unavailable" message per card (code-verified,
  matching the v3 production behaviour); not triggered live here.
  **Unverified**

## 6. Refresh and reopen persistence

- Refresh / full page reload inside one browser session: after reload the
  Inbox still showed 3 items and the consumed item remained in Archive —
  localStorage state (`focu:content-consumption:v1`) survived. **Pass**
  (browser-session scope only.)
- Reopen after closing the Artifact, and iPhone force-quit survival:
  **Unverified** — requires the physical device (steps below).

## 7. Update-in-place persistence — the critical gate

The same `focu-v04-test` entry was rebuilt in place with the Version B bundle
(same slug, no second entry created): the update itself works, the new item
`frontier-20261029` appears as unread, ordering stays newest-first, and no
duplicate content IDs appear.

However, the Muse audit harness launches a **fresh browser profile for each
audit session**, so the Version B session started with empty localStorage and
showed all 5 items in the Inbox. That is a property of the test harness, not
evidence about the iPhone WebView: it neither proves nor disproves that
consumption state survives an in-place update on device.

**Status: Unverified — pending physical iPhone verification.** This is the
critical gate for v0.4 and it is *not* passed yet.

Manual verification steps (Version B is the currently published build):

1. Open `focu-v04-test` in the Muse iPhone app; confirm 5 items in Inbox.
2. On "Provable Inference, Pando, and LifeVal — Frontier Briefing, November 3,
   2026" (`frontier-20261103`), tap **Done reading**. Confirm it leaves the
   Inbox and appears under **Archive**.
3. Force-quit the Muse app, relaunch, reopen the Artifact: confirm the item
   is still absent from Inbox and present in Archive.
4. Ask for a Version C rebuild of the same entry (metadata-only change),
   reopen, and confirm the item is *still* consumed and any new item arrives
   unread. Only then can this gate be marked Pass.

## 8. Controlled force-quit results

Not performed — no physical iPhone access from the build environment.
**Unverified** (see steps above).

## 9. Observations / evidence

- Audit screenshots (mobile + desktop) for both builds are under
  `~/workspace/ts-spaces/focu-v04-test/audits/` (build A:
  `2026-11-03T19-23-01Z`, build B: `2026-11-03T19-24-19Z`); both audits report
  no console errors, no broken assets, no horizontal overflow.
- Inbox counts observed live: A = "4 in inbox" → after Done reading "3 in
  inbox" → Archive shows the item → after Mark unread "4 in inbox" → after
  reload still "3 in inbox" with the item consumed again → B (fresh profile)
  "5 in inbox".

## 10. Failures, limitations, recommendations

- No functional failures observed in the reader or publisher.
- Limitation: consumption state lives only in WebView `localStorage` under
  one key; nothing in this environment can confirm its lifecycle across
  Artifact rebuilds on iOS. Recommendation: complete the manual gate in §7
  before relying on v0.4 consumption state; do not build a server/sync
  workaround without further approval.
- Limitation: only the fixture item has an article; article packaging for
  real deliveries remains a production-pipeline gap, intentionally not
  implemented here.
- Covers: no delivery contains a cover image, so all cards use the
  placeholder tile (same "No data" status as v3).
