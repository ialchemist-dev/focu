# Focu clean-slate end-to-end acceptance — 2026-11-04

Executed in the Muse environment against PR #21. Result labels use only
PASS / FAIL / UNVERIFIED / BLOCKED, and PASS is claimed only for directly
observed behavior.

## Baseline

- Branch: `fix/media-completion-reader-stability`
- Code under test: `ff7b62bbd908700fb9e4065e2f3e63338e085570`
- Publisher fix committed during this run (see "Bug found and fixed"):
  `42725c2cd55b3c139e242e2db55464060c244c66` (fix) and
  `00e9c45a6f12e895b5298fd2aa382f502c1a7d3d` (regression test)
- Run identifier: cleanslate-20261104-a
- Test environment: fresh worktree, fresh SQLite database, fresh delivery
  and staging directories. Registered sources file unchanged
  (md5 `96406fe3ea40fffcc46dce56c861ee72` before and after).
- PR #21 remains Draft. It was not merged.

## Cleanup

Inventory was recorded before deletion. Deleted (test workspaces only):
3 generated delivery directories, 11 publisher staging delivery copies,
1 stale research-request snapshot, and 10 obsolete publisher bundles
(80+ generated MP3s and associated articles/covers across them).

Deliberately preserved: all SQLite databases and historical intent records;
all Evidence Packs and raw research (original provenance); registered source
definitions; production deliveries and production media (they feed the live
production library and the daily compilation, and are outside the test's
contamination surface because the test used a fresh worktree, database, and
directories); credentials, configuration, git history, source code.

Post-cleanup verification that no stale generated article or MP3 remained in
the test workspace: PASS

## Code verification (pre-fix baseline)

- Focu Python tests (`tests/`): 121 tests — PASS
- HTTP fixture tests (`tests/unit`): 4 tests — PASS
- Muse publisher tests: 18 tests — PASS (19 after the fix below)
- Inline reader JavaScript syntax (`node --check`): PASS
- Reader behavior simulation (`test_reader_behavior.js`: article
  completion, local read-aloud, persistence, audio end): PASS

## Registered sources used (Path A)

- OpenAI (RSS + full articles, primary): five items published 2026-11-04
  were collected fresh — Pierre acquisition, Daybreak Red in AWS GovCloud,
  autonomous vulnerability pipeline research, Images 2.6, DevRev story.
- Anthropic (newsroom, primary): accessible; no announcement newer than
  previously covered items. PASS (checked, no new content)
- Google DeepMind (blog listing): accessible; no dated new item could be
  identified from the fetched listing. PASS (checked)
- Felix Rieseberg RSS: FAIL (unreachable in this run — TLS handshake
  timeout via urllib, empty response via focu fetch; actual failure
  reported, no substitute content inserted)
- Ethan Mollick RSS: FAIL (same failure mode)
- X and YouTube sources were not re-harvested in this run.

## User-initiated requests tested (Path B)

- B1 (URL-driven): a KDnuggets technical article assessing Claude Opus 5.5,
  captured as a durable one-time intent, researched against independent
  coverage, delivered as a claim-check article. Status transitions
  queued → researching → completed observed.
- B2 (idea-driven, no URL): "How do production AI systems decide to abstain
  from answering when evidence is insufficient?" Researched from two arXiv
  papers and one production system's documentation. Transitions observed.
- Two registered-source captures (evening briefing; vulnerability-pipeline
  deep dive) followed the same lifecycle.
- Neither B request became a registered source; the sources file hash is
  unchanged. PASS

## Fresh research and articles

Four Evidence Packs were built with verbatim-quote provenance and ingested
(35 findings total). Four new Content Items, all dated 2026-11-04:

| Content ID | Origin | Formats | Title |
| --- | --- | --- | --- |
| cleanslate-20261104-openai | registered sources | article + podcast | OpenAI's November 4: A Code-Review Acquisition, a GovCloud Cyber Launch, and 948 Patched Linux Vulnerabilities |
| cleanslate-20261104-linux-vuln | registered sources | article + podcast | 948 Linux Vulnerabilities, Patched by Agents — and the 20 Exploits That Took the Wrong Path |
| int_c2cfee2623d8f75d0d148dbf1300b8cc | user-initiated (B1) | article only | Checking the Opus 5.5 Rundown: What Holds Up, and What Is Vendor-Reported |
| int_c22de06da3b550f2d92faf6f57a5cc7f | user-initiated (B2) | article only | Knowing When Not to Answer: Three Layers of Abstention |

## Fresh podcasts and audio integrity

Both MP3s were generated fresh through the existing Open Notebook backend
(solo_expert profile) and audited with `focu.media_integrity`. The publisher
was run with its default strict audio audit; `--skip-audio-audit` was not
used.

| Item | Metadata duration | Decoded duration | Size | SHA-256 |
| --- | --- | --- | --- | --- |
| cleanslate-20261104-openai | 386.808s | 386.808s | 6,190,124 B | 308c9522d9e6b479d9dc3f34fba954b25b1b7e203e2cac72d5a792e253c589ae |
| cleanslate-20261104-linux-vuln | 374.352s | 374.352s | 5,990,828 B | 80371feeaaf1891c9cfd2795355a986fda6d4ccc17f266f5afbbf3bad3c4463b |

- Metadata vs decoded duration agreement: PASS (exact, both files)
- Full ffmpeg decode without errors: PASS
- No silences longer than 2s: PASS
- Delivered report byte-identical to canonical report (md5): PASS
- Bundled MP3 hashes match source delivery files and build report: PASS
- Transcript endings are complete closing segments (no mid-sentence
  truncation): PASS
- Transcript content coverage, briefing episode: FAIL — the spoken script
  covers 3 of the 5 report items (Pierre, Daybreak Red, Images 2.6); the
  vulnerability-pipeline and DevRev items are absent, and analogies not in
  the report were added. This is a script-generation fidelity gap, recorded
  here rather than repaired by regeneration, which is not guaranteed to
  improve coverage.
- Transcript content coverage, deep-dive episode: PASS with note — the core
  narrative (pipeline, Scout/Analyst split, wrong-0-day failure, independent
  check) is covered; the hard figures (948; $1.2M; 5,034) were paraphrased
  away.
- Podcast QC remains automated checks only; there was no human listening.

## Publication

- Method: immutable publisher bundle (strict audio audit on) → in-place
  update of the same private test Artifact entry, **Focu V04 Test**.
  The production library entry was not touched.
- Bundle verification: 4 unique Content IDs; all items newly generated;
  article-only and audio-capable items both present; embedded manifest
  identical to assets/episodes.json; decoded durations present in
  build-report.json; no historical items; no credentials or database files
  in the bundle. PASS
- Live-entry verification after update: exactly the 4 new items present;
  all 10 asset hashes match the build report; all previous items' assets
  removed. PASS
- Research section in the snapshot reflects the real request state (both
  on-demand requests completed and published; pending list empty). PASS

## Bug found and fixed

**Publisher ignored `content.json` `published_at`.** The publisher derived
an item's date only from a trailing `YYYYMMDD` in the delivery folder name,
so a delivery folder whose name does not end with the date shipped with
`published_at: null` even when its content.json declared one — mis-dating
and mis-sorting the item. Reproduced with two clean-slate deliveries.

Fix (minimal, on this branch): an explicit, valid ISO `published_at` in
content.json now takes precedence; the folder-name date remains the
fallback. Regression test `test_content_json_published_at_is_honored`
covers both the no-suffix and the disagreeing-suffix cases. Publisher suite
after fix: 19 tests PASS. Reader behavior simulation and the full Focu
suite were re-run green after the fix. The published bundle was rebuilt
with the repaired publisher.

## Reader and device acceptance (awaiting the user)

The following are UNVERIFIED until performed on the user's iPhone against
the published Focu V04 Test entry; nothing here is inferred from source
inspection:

- Inbox rendering, covers, spacing on device: UNVERIFIED
- Real MP3 playback to natural ending (premature-ending check), observed
  duration, pause/resume, seeking: UNVERIFIED
- Article-only Read aloud on device (availability of speech synthesis in
  the Muse iOS WebView, pause/resume, completion auto-archive, no paid
  TTS call): UNVERIFIED
- Reading completion rules on device (fast scroll does not archive;
  genuine reading does): UNVERIFIED
- Podcast completion auto-archive on device: UNVERIFIED
- Restore from Archive: UNVERIFIED
- Archive initially free of the new items: UNVERIFIED
- Update-in-place persistence, Version B (after the user confirms one
  consumed item from Version A): BLOCKED on the user's Version A
  confirmation
- Force-quit / relaunch persistence: UNVERIFIED

## Remaining limitations

- Device behavior of the Muse iOS WebView (localStorage survival across
  in-place rebuilds and force-quit) remains the open acceptance gate, as
  documented in docs/MEDIA_RELIABILITY_FIX_2026_11.md.
- TTS script generation compresses source reports lossily (see the
  coverage findings above); the canonical article/report remains the
  complete record.
- Two registered RSS sources were unreachable from this environment during
  the run; their failure is reported, not substituted.
