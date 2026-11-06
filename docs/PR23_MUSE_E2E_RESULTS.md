# PR #23 — Muse end-to-end acceptance results

Date: 2026-11-05 (America/Denver)
Repository: https://github.com/ialchemist-dev/focu
PR: https://github.com/ialchemist-dev/focu/pull/23 — **kept Draft, not merged** (PR #22 also untouched, still Draft)
Branch: `feat/podcast-origin-audience-policy`

- Verified starting head: `6cd875182d212c93054d8f5dcf50268a21136694` (matches the assignment; main `df1e0cb744d564c42c40c765392f369edafb36bd` unchanged)
- Head after the acceptance fix (see "Bug found and fixed"): `92bef637b84ca0131a44a0423cc7288eef6f28cd`
- Worktree: `~/workspace/focu-pr23` (detached at the PR branch; production checkout `~/workspace/focu` inspected and preserved untouched, including its staged file)
- Isolated acceptance root: `~/workspace/focu-pr23-acceptance/` — fresh test SQLite DB (`focu-test.sqlite3`), deliveries, bundles, fixtures, logs. No production data, production library, registered sources, scheduled jobs, or provider credentials were modified.

Every check below is reported as PASS / FAIL / BLOCKED / UNVERIFIED only. Fixture results are labeled as fixtures and are never conflated with real provider or iPhone results.

## 1. Configuration and provider readiness

- Open Notebook at the existing local install: health endpoint healthy; episode profiles include `solo_expert`; speaker profiles include `solo_expert`; `ready_for_generation: true`. `focu podcast doctor` reports worker_status `not_verified` (a known doctor limitation; the worker demonstrably processed both generation jobs below). No new TTS service, credential, or provider was configured. — **PASS**

## 2. Regression tests

Run before and after the §9 fix, using the CI workflow's own steps (`.github/workflows/tests.yml`).

| Suite | Before fix | After fix |
| --- | --- | --- |
| Python (`tests/`) | 133 passed | **135 passed** (2 new regression tests) |
| HTTP fixtures (`tests/unit/`) | 4 passed | 4 passed |
| Publisher + reader (`experiments/muse-artifact-reader`) | 23 passed | 23 passed |
| Reader inline JS syntax (CI extraction procedure) | OK | OK |
| Reader behavior (Node simulation: article, local read-aloud, persistence, audio end) | passed | passed |

Coverage confirmed in the suite: legacy SQLite schema migration, default podcast mode, explicit opt-in, idempotent podcast request, refusal without opt-in, single-item generation with a fake provider, failed-QC leaving the article without MP3, audience calibration, daily compilation policy, publisher validation, reader audio controls. No test was disabled, skipped, or weakened. — **PASS**

GitHub CI on the originally verified head `6cd8751`: run 42106356342, success. Final CI on the post-fix head `92bef63`: run 42153047819, **success**.

## 3. Audience calibration (§4 of the assignment)

Authoritative profile: `references/audience-profile.md`, version **2026-11-05.1**, SHA-256 `72692d4a0781d25a7833a5f5c1d39f00434002db1f1b216b5242cca254a43ddb`. It contains only owner-stated facts (PhD; software/ML engineer; expert CS/programming/ML; sociology as the novice example; working knowledge default). The committed profile was not modified during testing.

- Test A — `focu audience-prompt --domain machine_learning` → level **expert**. Instructions favor precise mechanisms, original quantitative results, assumptions/evidence quality, limitations, counterarguments, negative controls, independent replication, demonstrated-vs-claimed separation; they discourage basics exposition and chef/sculptor/detective analogies. — **PASS**
- Test B — `focu audience-prompt --domain sociology` → level **novice**. Instructions provide disciplinary context, term definitions, scaffolding, and teaching analogies. — **PASS**
- Same neutral fixture source rendered under both calibrations (host-written sample passages, no paid calls, saved in the acceptance logs): the difference is substantive — the expert rendering leads with the identification problem and treats the effect size as an upper bound; the novice rendering defines the comparison-group method and explains the caveats in plain terms. Domain selection in these tests was **explicit**. — **PASS**

## 4. New on-demand research request (§5)

- Subject (new; not the Weight-Space item): "Sleeper Agents: Training Deceptive LLMs that Persist Through Safety Training", Hubinger et al., arXiv:2401.05566 — https://arxiv.org/abs/2401.05566 (full text: https://arxiv.org/html/2401.05566v3).
- Created with the isolated DB: `focu --db "$TEST_DB" request "Investigate the technical mechanism, evidence and limitations of this paper" --url https://arxiv.org/abs/2401.05566`
- Intent ID: **`int_bc060962cacc80117f32b356ad8bd039`**
- Initial state verified in SQLite and via `focu show`: origin `user_initiated`, `podcast_mode: none`, `podcast_requested_at: null`, `automatic_research_started: false`, status queued, durable in SQLite. No background worker or audio was started by capture. The intent is a one-time research request; `examples/sources.yaml` was not touched. — **PASS**

## 5. Research and article (§6)

Host-executed, evidence-backed research (no automatic investigation was claimed):

- Sources: the paper's full arXiv HTML text (213,614 chars extracted), the arXiv abstract page, and an independent explainer (Superalignment Research) for cross-checking figure values. Anthropic's own research page returned HTTP 404 via the fetcher — recorded as a limitation, not papered over.
- Evidence Pack `ev_pr23_sleeper_agents_20261105`: 17 findings, 3 sources, schema 0.2 with verbatim `evidence_quote`s; completeness **partial** (figure-level values beyond prose-reported rates not digitized from plots; persistence rates are the authors' measurements — no independent replication of the training pipeline exists in the consulted literature). Ingested against the test DB; intent completed and linked.
- Article: **"Sleeper Agents: Backdoors That Survive Safety Training"** (~2,000 words, 8 sections: setup/mechanisms, RL persistence, SFT persistence, adversarial-training backfire, scale and CoT effects, causal-CoT evidence, what the paper does not show, implications). Written at expert calibration for `machine_learning`: mechanisms and hard numbers preserved (55%/15% RL rates; distilled-CoT deltas 15→9 and 56→55 under PPO, 15/56→16/57 under SFT; 25,000 red-team prompts, 2,000–12,000 successful; true-trigger defection 99–100% after adversarial training; 810M–175B scale scan), limitations and the authors' own scope caveats stated, no elementary analogies.
- Delivery `idea-bc060962cacc80117f32b356ad8bd039-20251105/` in the isolated deliveries dir: `article.md`, `research.md`, `content.json` with content_id = the intent ID, origin `user_initiated`, `podcast_mode: none`, the article title, publication date 2026-11-05, `audience_domain: machine_learning`, and provenance (evidence pack ID, profile version + SHA). No audio was generated at this stage. — **PASS**

## 6. Version A — article only (§7)

- `publish.py --deliveries "$TEST_DELIVERIES" --output bundles/version-a --limit 15` → 1 item: content_id unchanged, origin `user_initiated`, `podcast_mode: none`, formats = article only, **zero MP3 files in the bundle**, no warnings. No generated-podcast Listen control exists for this item (device Read aloud is a separate reader feature, not a podcast). — **PASS**
- Negative policy test (isolated fixture, removed afterward): a dummy MP3 placed beside the same item with `podcast_mode: none` → publisher rejected the build: "podcast_mode=none item has a stray MP3". — **PASS**

## 7. Explicit podcast authorization (§8)

- `focu --db "$TEST_DB" request-podcast int_bc060962cacc80117f32b356ad8bd039 --deliveries "$TEST_DELIVERIES"` → `podcast_mode: single`, `podcast_requested_at: 2026-11-06T02:47:18.314803+00:00`, delivery found. SQLite and the delivery's `content.json` agree.
- Idempotency: the command was run a second time; the timestamp is byte-identical, no duplicate intent or content item was created. No hand-editing of SQLite. — **PASS**

## 8. Podcast generation and mandatory QC (§9–§10) — FAIL (provider), gate behaved correctly

Generation used the finished `article.md` via `focu podcast-for <intent> --deliveries ... --domain machine_learning`, episode/speaker profile `solo_expert`/`solo_expert`. Two provider jobs (the initial attempt and the implementation's single retry — the full extent of the authorization; no further generation was run):

- Attempt 1: episode `episode:zlhyh7mykpmiybxh0coc` (completed on the provider, audio produced there)
- Attempt 2: episode `episode:2j57aisrex686z2uoq8t` (completed on the provider, audio produced there)

### Bug found and fixed (§16)

The two attempts initially "failed QC" for the wrong reason. Root cause, reproduced against a real completed episode: `focu/single_podcast.py::_transcript_text` did not understand Open Notebook's actual transcript payload shape — `{"transcript": [{"speaker": ..., "dialogue": ...}]}`. It accepted only string-valued `text`/`transcript`/`script` keys and the test fixture's `{"segments": [{"text": ...}]}` shape, so for every real episode it silently returned an **empty string**, and fidelity QC audited nothing (0 chars). The PR's unit tests could not catch this because the fake provider returns the fixture shape. Consequences had it shipped: `podcast-for` could never succeed against the real provider, and every QC record (section coverage, figure checks, audience report) would have been computed on empty text.

Fix, committed to this branch (head `92bef63`): `_transcript_text` now recurses into list-valued keys and accepts `dialogue` segments, with a docstring recording the real shape; two regression tests were added (`test_transcript_text_accepts_real_open_notebook_shape`, `test_single_item_success_with_real_provider_transcript_shape` — the latter runs the full generate→QC→attach flow against the real payload shape). Full suite re-run: 135/4/23 + JS + behavior, all green; remote files verified byte-identical to the tested worktree; GitHub CI success (run 42153047819). No QC threshold was weakened. — **PASS (fix)**

### True QC verdicts (fixed extractor, real transcripts, host-read in full)

Both transcripts were then re-audited with the fixed extractor and read end-to-end by the host. No new audio was generated for this recheck. The delivery's `podcast-qc.json` preserves the original attempts and adds a transparent `recheck` record.

- Attempt 1 (1,002 words): **FAIL** — covered sections **0/8**. No article heading appears as a literal standalone heading; the episode restructures the article into flowing prose with a show-style opening ("Hello, and welcome to this in-depth analysis…"). Figure review: §1 figures present (2023, 2024); §2: 55 and 15 present, 9 and 56 missing; §3: 56 and 15 stated, the actual post-SFT values 16 and 57 missing; §4: 25,000 present, 5,000 / 10 / 2,000 / 12,000 / 50 / 99 / 100 missing; §5: 810 million and 175 billion present; §§6–8 blended into closing prose, the causal steering result is not stated. Substantively it is a competent general overview that keeps some numbers, but it is not the article, and it is pitched below the article's level.
- Attempt 2 (938 words): **FAIL** — covered sections **0/8**, and weaker: structure reordered with the scale section covered twice; §1 missing 2023; §2 missing 15, 9, 56; §3: 56 and 57 present, 15 and 16 missing; §4: **no figures at all** (all eight missing); §5 figures present. Contains a decorative "secret key / door" analogy and a show-style opening.
- Audience mismatch report (non-blocking, as designed): domain `machine_learning`, level `expert`, profile version 2026-11-05.1, SHA `72692d4a…`. Patterns checked: chef_analogy, sculptor_analogy, detective_analogy, basics_exposition. Matches found: **none** in either transcript; `requires_review: false`. Recorded limitation: the detector's pattern list is narrow — attempt 2's "secret key" analogy is a genuine audience mismatch substantively but is outside the pattern list, so the report alone would not have caught it. Per the assignment, this was measured and reported, not silently turned into a blocking gate; and per the same rule, neither episode is called a success on the strength of the empty mismatch report.

Failure behavior followed exactly: failures recorded in `podcast-qc.json`; only the one existing retry was used; the article is intact and remains article-only; **no MP3 was attached**; no QC threshold was weakened. — **FAIL (provider fidelity), PASS (fail-closed gate behavior)**

## 9. Audio integrity (§11)

Not applicable to the delivery: because QC failed, no MP3 was downloaded or attached, and §11's acceptance measurements (duration, decode, checksum) have nothing valid to measure. The two provider-side episodes exist on Open Notebook with audio URLs, but attaching either would violate the QC gate. — **BLOCKED by the §8 QC outcome**

## 10. Version B and manifest comparison (§12)

- Second immutable bundle built from the same isolated deliveries (`bundles/version-b`); Version A was not rebuilt in place.
- Comparison: same single content_id in both; no duplicates; no unrelated item gained audio; article payload byte-identical. The **only** differences: Version B records `podcast_mode: single` and `podcast_requested_at: 2026-11-06T02:47:18.314803+00:00`. Audio format is absent in both — in Version A because there was no authorization, in Version B because authorization existed but QC blocked the audio. This is precisely the policy distinction the PR introduces: authorization is necessary, QC is decisive.
- Published to the private test Artifact **"Focu V04 Test"** (`focu-v04-test`) only, replacing its previous snapshot in the same entry. The production **Focu Podcast Library was not touched**. — **PASS for the publish mechanics; the "article plus podcast" expectation is FAIL by consequence of §8 (article-only content, single mode recorded)**

## 11. Daily compilation policy fixtures (§13)

Synthetic fixtures in the isolated environment only (never published to any Artifact; the scheduled daily job was not run or reconfigured):

1. Three registered-source articles separately readable — PASS
2. Each uses `podcast_mode: daily_compilation` — PASS
3. None has an individual MP3 — PASS
4. Compilation's `covered_content_ids` = exactly the three article IDs, compilation carries the audio format — PASS
5. Reader shows a minimal "In the \<date\> briefing" link on covered items (rendered dynamically from `covered_content_ids`) — PASS
6. The link opens the compiled item — PASS
7. A user-initiated item in coverage → build rejected ("Daily compilation cannot include on-demand research") — PASS
8. A missing referenced article → build error ("Daily compilation references missing content") — PASS
9. A second compilation for the same date → rejected ("Multiple daily compilations for 2026-11-05") — PASS

## 12. Reader behavior (§14)

- The Node reader-behavior simulation passes against this branch (article rendering, local Read aloud as a separate action, consumption persistence, audio end behavior). Manifest-level checks on Version B: the Inbox contains exactly one item for the research (no duplicate); the article is readable; the item shows **no** MP3 Listen button, which is correct for a QC-blocked item; Read aloud remains a separate device action. PR #22's manual Archive/Restore buttons are not part of this branch and were not validated or claimed. Cross-rebuild localStorage persistence is outside this acceptance. — **PASS (as scoped)**

## 13. iPhone acceptance (§15)

**Owner-confirmed 2026-11-05 (evening, America/Denver).** The owner checked the private Artifact "Focu V04 Test" on his iPhone and confirmed the article state: the Sleeper Agents article is present exactly once, readable, with no duplicate, and shows no Listen button — the correct presentation of a QC-blocked item. Those device checks **PASS**. Checklist items 4–9 (Listen button, playback, seeking, ending, correspondence) remain **BLOCKED**: because the podcast failed QC there is deliberately no audio attached, and a passing audio checklist requires a future provider episode that satisfies the fidelity contract; none was produced within the authorized attempts.

## 14. Remaining limitations

- The provider (Open Notebook `solo_expert`) does not follow the literal-section contract: on this article it restructured thematically on both attempts (0/8 literal headings), dropped most section figures, and used show-style openings — the same failure class recorded in PR #22's acceptance for the daily briefing. PR #23's policy, authorization, and QC machinery all behaved correctly; the blocker is provider script fidelity, not policy code.
- The transcript-extraction defect fixed here (§8) means any `podcast-for` result produced before commit `92bef63` was audited against an empty transcript; results on or after that head are audited against real text (covered by the new regression tests).
- The audience mismatch detector is report-only and pattern-based; its list does not cover all decorative analogies (see §8).
- The research evidence is partial by design (see §5): exact persistence rates are the paper's own measurements; no independent replication of the training pipeline was found.
- iPhone verification of the article state is owner-confirmed (see §13); the audio checklist remains blocked by the QC outcome.

## 15. Final state

- PR #23: Draft, head `92bef637b84ca0131a44a0423cc7288eef6f28cd`, CI success. Not merged.
- PR #22: untouched, still Draft. Production checkout, production data, registered sources, the 06:14 job, and the production Podcast Library: untouched.
- Paid generation used: exactly the two episodes the assignment authorized (initial attempt + one retry), both on the isolated test item. No other generation was performed; the post-fix re-audit reused the existing episodes' transcripts.
