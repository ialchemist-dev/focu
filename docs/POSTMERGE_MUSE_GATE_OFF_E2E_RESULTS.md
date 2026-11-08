# Post-Merge Gate-OFF E2E Acceptance — Muse Results

Run: 2026-11-07 (America/Denver), side chat "播客生成", at the repo owner's
assignment (`docs/MUSE_GATE_OFF_POSTMERGE_ACCEPTANCE.md`).

**Tested commit:** `00e936897aa69a76301adfae4b43446f3d87bba9` (`origin/main`;
PRs #22 `96000723a553`, #23 `133d8801f5a8`, #24 `4ae7ad90ea85`,
#25 `dfd51df57be7`, #26 `00e936897aa6` all confirmed merged).

**Isolation:** worktree `~/workspace/focu-gate-off-e2e` (detached at the target
commit, fresh venv); acceptance root `~/workspace/focu-gate-off-e2e-acceptance/`
(daily-data / research / deliveries / bundles / logs / wiki-sandbox). The
production checkout, production databases, the 06:14 scheduled job, Open
Notebook credentials and the production Podcast Library were never modified
(verified before and after; see §10).

**Gate discipline:** every run used `--gate-mode off --gate-provider off`.
`OPENAI_API_KEY` and `TYPESAFE_API_KEY` were absent from the environment
(verified `PRESENT=0` for both), were never requested, extracted or configured,
and no shadow/active/compare arm ran. The daily result carries `gate: null`
and no `gate/` ledger exists anywhere in the acceptance data.

## Verdict summary

| Area | Verdict |
| --- | --- |
| Regression suites | PASS (167 + 4 + 25 + JS behavior + syntax) |
| Daily pipeline, Gate OFF (text path) | PASS |
| On-demand research (podcast_mode=none) | PASS (research completeness self-marked partial — see §5) |
| Consolidated briefing + publisher checks | PASS (1 positive, 6 rejection cases) |
| Audio — reader/fixture mechanics | PASS (headless); device playback UNVERIFIED |
| Audio — Open Notebook script generation | FAIL (script); QC gate PASS (blocked); new audio BLOCKED |
| Transcript extractor vs current provider shape | FAIL (new defect instance; gate still fails closed) |
| LLM Wiki integration | PASS as sandbox proposal; automated bridge NOT IMPLEMENTED |
| Test Artifact publication | PASS (byte-for-byte); iPhone checks UNVERIFIED |
| Automated on-demand → daily orchestration | NOT IMPLEMENTED (manual host composition only) |

## 1–2. Baselines and regression suites

- `origin/main` == target commit. Production checkout recorded and preserved:
  branch `feat/v04-unified-content-feed` @ `609bc98`, staged uncommitted
  `experiments/muse-artifact-reader/V04_ACCEPTANCE_REPORT.md`, untracked
  `scripts/build_compilation.py` and `systemd/focu-reader.service`.
- The 06:14 job (`focu-daily-research-podcast`) was inspected read-only and
  left unchanged. Note for the owner: it still targets the production
  checkout, so production daily runs still use the pre-merge path. Switching
  production to `main` was out of scope and was not done.
- Tests, all in the fresh worktree venv, all green:
  - focu main suite: **167 tests OK**
  - `tests/unit`: **4 tests OK**
  - reader Python tests: **25 tests OK**
  - `node experiments/muse-artifact-reader/test_reader_behavior.js`: exit 0
    ("article, local read-aloud, persistence and audio end passed")
  - Inline-JS syntax check (the CI workflow's method): OK
  - CLI smokes (`focu --help`, `focu-gate --help`,
    `python -m focu.daily.cli --help`, init + capture): OK

## 3. Daily run (Gate OFF)

Command shape: `focu daily run --config <acceptance sources.yaml>
--data-dir <acceptance daily-data> --date 2026-11-09 --text-only
--input-units <14 genuine items> --json --gate-mode off --gate-provider off`.
The 14 input items are the genuine Nov 6–7 contents captured for the PR #25
acceptance, replayed through the pipeline's own `--input-units` path. This is
authentic content, honestly labeled: it does **not** prove the live HTML/X
collectors work; only the store → rank → compose → QC → finalize path is
exercised.

- Result: `status: completed`, `gate: null`, 14 inserted, episode
  `ep_8f0e0d16e0b5455f94dd88b44938a8cc` finalized as `text_only`.
- Script composer: `secretary_briefing_v1` (the deterministic pipeline
  composer — **not** Open Notebook). Script SHA-256
  `9bc677ad59e3ab68f15e386134d7befe0775093858d654e5590f568cfca5bc41`.
- **Briefing QC: passed = true** — 9 covered sections, and no section lists
  missing figures.
- **Audience diagnostics:** profile version `2026-11-05.1`; profile SHA-256
  `72692d4a0781d25a7833a5f5c1d39f00434002db1f1b216b5242cca254a43ddb`
  (byte-identical to `references/audience-profile.md`); briefing style
  SHA-256 `f33654b3874bbf9497bc10529435800237ee029b5a3d11634562c7d1891c16a1`
  (matches `references/briefing-style.md`); `blocking = false`.
- Selected 9, in order (identical to the PR #25 gate-off baseline order —
  existing priority/age rules, no Decision-Gate influence; `gate_priority`
  is `"normal"` on all 9 units): Den of Thieves 04; Project EVE; The
  components of agent memory; How scientists use Claude; Teaching AI to build
  scientific models; GPT-6 Cyber; Australian universities; wet-lab science;
  responsible AI infrastructure.
- Not selected (Cult.fit, Merge, Franklin Templeton, Flipsnack, Hacktron)
  remain traceable in the store as pending candidates; coverage rows = 9;
  nothing was deleted.
- Re-running the same date returns `status: reused` (no duplicate episode).

## 4. On-demand research

Request (no podcast flag): "Investigate this research, its evidence,
limitations, and independent reactions" on METR, Kwa et al., "Measuring AI
Ability to Complete Long Tasks" (arXiv:2503.14499).

- Intent `int_71bc70a187d84a44c8a5e24b21980215`: `origin = user_initiated`,
  `podcast_mode = none`, `podcast_requested_at = null`,
  `automatic_research_started = false` at capture, and the podcast fields
  were unchanged at completion. No subscription was created — the research
  database has no subscriptions table at all, and the acceptance
  `sources.yaml` is byte-identical to its pre-run copy.
- Evidence pack `ev_metr_time_horizon_20261107`: 20 findings, 7 sources;
  every evidence quote was programmatically asserted as a verbatim substring
  of its source's extracted text before ingest.
- Canonical content ID: `int_71bc70a187d84a44c8a5e24b21980215` (the intent ID,
  per protocol). Delivery contains `article.md`, `research.md`,
  `content.json` (origin `user_initiated`, `podcast_mode: "none"`),
  `provenance.json`. Zero MP3 files exist anywhere in the deliveries tree;
  no podcast command was invoked.
- Article: **"METR's Doubling Held for Twenty Months. The Ruler Is Now the
  Problem."** — with an explicit Research Delta and a Connections section
  (Anthropic agent memory; OpenAI wet-lab bench; the owner's measurement
  interest), interpretive links labeled as such.
- Research Delta (verified against primary texts): the paper's construction
  (170 tasks; >800 baselines, 2,529 hours; only 286 of 558 HCAST/RE-Bench
  attempts succeeded, so task times are success-conditioned); 50% horizon
  doubling 207 days, 80% horizon 204 days at 4–6× shorter; an internal
  inconsistency (SWE-bench Verified implies ~70-day doubling for 2024 models
  vs 143 days from the main suites); TH1.1 (2026-01-29) rebuilt the suite
  170 → 228 tasks and re-estimated GPT-5 from 138 to 214 minutes, with
  doubling 196.5 days all-period and 130.8 [107, 161] since 2023; METR flags
  measurements above 16h unreliable; GPT-5.6 Sol's horizon is 11.3h / 71h /
  >270h purely by cheating-scoring convention; Toby Ord's half-life
  formalization (arXiv:2505.05115) and the Weibull refit (shape k ≈ 0.6,
  Ord's public withdrawal 2026-02-04) correct the tail extrapolations.
- **Absence, stated plainly:** no independent replication of the full
  horizon fit on independently collected tasks/baselines exists; external
  work is refits of METR's public data. The investigation marks its own
  completeness `partial` for this reason. Nothing was invented to fill it.

## 5. Consolidated briefing and publisher checks

A consolidated daily briefing was composed by the host agent (manual
composition — see "NOT IMPLEMENTED" below): one `article.md` covering the 9
registered items plus the METR findings, with relationships stated and
`covered_content_ids` pointing at the 10 original canonical IDs
(9 × `cnt_…` + the research intent ID). The research article remains
`podcast_mode = none`; being summarized in the briefing grants no audio
permission.

Publisher (`experiments/muse-artifact-reader/publish.py`, audio audit ON):

- **Positive build PASS:** 11 items (1 compilation + 1 research + 9
  registered), 0 with audio, 0 warnings; every referenced ID resolves;
  every covered item is individually readable; the article-only compilation
  was accepted with **no MP3 required**; all bundle SHA-256 values verified
  against the built files.
- **Rejections (all fail with the designed error):** duplicate canonical
  content ID; compilation referencing a missing content ID; stray MP3 on a
  `podcast_mode = none` item (verified twice — the integrity audit rejects
  garbage bytes, and with a valid MP3 the policy error
  `podcast_mode=none item has a stray MP3` fires); a `user_initiated` item
  claiming `daily_compilation` ("User research must not enter daily
  compilation" — this is also the concrete surface for "registered-source
  ingestion cannot pretend to be / absorb a user request": the daily
  `--input-units` schema has no origin field to spoof, and the publisher
  rejects the spoofed combination); corrupt audio attached to the
  compilation (build fails, and the source `article.md` is byte-identical
  afterwards — malformed audio fails closed and never deletes articles);
  two compilations for the same day.
- **NOT IMPLEMENTED:** automated daily orchestration that includes
  on-demand items. The code path exercised here is manual host composition
  plus the publisher's linkage checks; no scheduler/runbook step performs
  it automatically.

## 6. Audio

- Fixture mechanics: a synthetic 3.000 s tone MP3 (SHA-256
  `b38b901c4f1fa84cb92abb782e9cc05ab6bdf2fcc9cda17d443f45fe6fb402b4`)
  decodes cleanly with exact duration; the reader behavior suite covers
  play / pause / seek / completion headlessly (passed). Actual playback on
  the owner's iPhone is **UNVERIFIED** (see §8 checklist).
- **One bounded Open Notebook generation** (its own existing credential;
  no focu API keys involved; isolated `--db`): job
  `command:hooywopqyxq48e1v7ukq`, episode `episode:i2kf5ksvkqm225c92gr3`,
  name "Personal update — November 9, 2026", 9 briefing units, style
  version 2026-11-05.1 recorded by the generator.
  - The script: 18 segments, 4,566 characters, a single invented speaker
    ("Professor Sarah Kim"), a show-style opening ("Welcome to our
    discussion today on a fascinating aspect of modern research…"), and
    thematic restructuring. The repository's own gate
    (`focu.briefing.validate_script`, the exact function `deliver` uses)
    run over the real words returns **passed = false** with
    `missing_headline_or_wrong_order` for all 9 items (0/9 literal
    headlines).
  - **New defect instance:** the shipped extractor
    (`focu.podcast_delivery.transcript_script`) returns an empty string
    for this provider response shape —
    `{"transcript": [{"dialogue": …, "speaker": …}, …]}` (nested
    `transcript` key; `dialogue`-keyed segments). This is the same defect
    class the PR #23 acceptance fixed, recurring with a new payload
    variant. The gate still fails closed (an empty transcript cannot
    pass), so the failure is safe, but QC would audit nothing if a future
    shape ever let an empty extraction pass silently. Provider payload
    shapes need regression fixtures taken from real responses.
  - Recorded per the runbook format: **Script generation FAIL /
    QC gate PASS (delivery blocked) / Daily text article PASS /
    New Podcast audio BLOCKED.** No regeneration was attempted; no MP3
    was downloaded into any delivery or bundle.
- A 30–40 minute high-fidelity briefing remains a product target. It is
  **not implemented** by any evidence in this run.

## 7. LLM Wiki integration (sandbox only)

The canonical wiki was not written. A fresh copy (42 files) was made into
the acceptance `wiki-sandbox/`, `SCHEMA.md` followed, and a proposal
prepared (full memo: acceptance root `WIKI_INTEGRATION.md`):

- `raw/2026-11-07_metr-time-horizon-research.md` added unmodified; no
  pre-existing raw file was touched.
- New pages: `wiki/metr-time-horizon-source.md` (source) and
  `wiki/agent-time-horizon.md` (concept); cross-reference notes appended
  to `knowledge-base-evolution-evaluation` (instrument validity) and
  `project-mirror-experiment` (extrapolation inputs); `index.md` and
  `log.md` updated (log entry labeled SANDBOX PROPOSAL); `overview.md`
  intentionally unchanged at proposal stage.
- Contradictions preserved, not smoothed: exponential vs Weibull tail
  behavior; "the doubling held" vs "frontier point estimates are not
  robust" (both from METR's own publications). Facts name their sources;
  the "instrument is the weak point" judgment is labeled interpretation.
- **Automated wiki bridge: NOT IMPLEMENTED.** Manual host-agent
  orchestration is the only path. Pushing this proposal to the canonical
  wiki is a separate owner decision, not part of this acceptance.

## 8. Test Artifact

- Entry: **Focu V04 Test** (private; unchanged name/slug). The production
  **Focu Podcast Library was not modified.**
- The staged bundle (§5) was deployed byte-for-byte and verified against
  the deployed entry: recursive diff identical; SHA-256 of `index.html`
  (`7beaa808…`), `assets/episodes.json` (`7b71140c…`) and
  `build-report.json` (`e8521c37…`) match the staging bundle; all 22
  checksums in the build report verify; live item count = 11, episodes
  with audio = 0, `assets/audio/` empty.
- Deployed reader checks (from the bundle + headless behavior suite): one
  item per canonical ID; the compilation shows its article and each
  covered item carries the "In the daily briefing" link logic; the
  research item has no Listen button (no audio exists to attach);
  device "Read aloud" remains a separate reader feature, distinct from a
  generated Podcast; the read-state store (`focu:content-consumption:v1`),
  manual Archive controls (Inbox cards and article reader) and Restore
  handlers are present in the deployed page; automatic read completion is
  covered by the headless behavior suite.
- **iPhone status: UNVERIFIED.** Nothing in this section claims a device
  PASS. Checklist for the owner (Focu V04 Test entry, ~2 minutes):
  1. The entry shows 11 items with "Daily Briefing — November 9, 2026" on
     top.
  2. Open the briefing; open one covered article from it via its
     "In the daily briefing" link and return.
  3. Open the METR article: it is readable and has **no** Listen button.
  4. Archive the METR article from its Inbox card; confirm it moves;
     open it and Restore from the article reader.
  5. (Optional) Use the reader's own Read aloud on any article — this is
     the device feature, not a generated podcast.

## 9. Safety checks

- Malformed/unauthorized audio fails closed without deleting articles
  (§5 corrupt-audio and stray-MP3 cases; source files byte-identical
  after failure).
- Unavailable providers are reported, not substituted: with both Decision
  providers absent by design, the daily text path completed and recorded
  `gate: null`; the one audio generation used only Open Notebook's own
  pre-existing credential, and its failure was reported as BLOCKED rather
  than replaced by another provider.
- No production subscription, delivery, database or library was created,
  changed or deleted by this run.

## 10. Production preservation (verified after the run)

- Production checkout: same branch, same HEAD (`609bc98`), the staged
  acceptance report and both untracked files exactly as recorded at
  baseline.
- Production `data/focu.sqlite3`: mtime still the morning production run
  (2026-11-07 06:25); every focu command in this acceptance used an
  isolated `--db` / `--data-dir`.
- 06:14 job definition unchanged; Podcast Library artifact unchanged;
  Open Notebook used only through its normal API for the single bounded
  generation (its data files and credentials were never read or modified
  directly).

## Open items for the owner (not decided by this acceptance)

1. Script-first audio (D1) and voice (D2) decisions remain open; the
   provider's scriptwriting still fails the fidelity gate on merged main,
   and the transcript extractor needs a regression fixture for the
   current provider payload shape (§6).
2. Whether to switch the production checkout and the 06:14 job to merged
   `main` (resolving the staged `V04_ACCEPTANCE_REPORT.md`) — production
   still runs the pre-merge path.
3. The iPhone checklist in §8.
4. Whether the sandbox wiki proposal (§7) should be pushed to the
   canonical wiki as a separate step.
