# PR #22 — Muse end-to-end acceptance results (2026-11-05)

Executed on the Muse VM against PR #22. Labels use only
PASS / FAIL / BLOCKED / UNVERIFIED; PASS is claimed only for directly
observed behavior.

## Baseline and checkout state

- GitHub verified before work: main `df1e0cb744d564c42c40c765392f369edafb36bd`;
  PR #18, #20, #21 merged; PR #22 Draft, base main, head
  `32d3578f23e4da11b81cba9c12c2118a1e31d13f`, mergeable clean. PASS
- Long-lived checkout `~/workspace/focu` BEFORE: branch
  `feat/v04-unified-content-feed` @ `609bc98`, with a staged uncommitted
  addition (`experiments/muse-artifact-reader/V04_ACCEPTANCE_REPORT.md`)
  and two untracked files (`scripts/build_compilation.py`,
  `systemd/focu-reader.service`).
- Because uncommitted changes were present, the checkout was NOT switched
  (per instruction §2: preserve, use a separate worktree). AFTER: unchanged.
  Switching the production checkout to main remains BLOCKED on the owner
  deciding what to do with that staged file.
- Acceptance ran in isolated worktree `~/workspace/focu-pr22` @ `32d3578`
  (detached from `origin/feat/manual-archive-secretary-briefing`), fresh
  venv, fresh test database. No production data, schedule, source list, or
  Library entry was modified except the cron instruction update in §3,
  which the task explicitly directed.

## Test suites (local rerun in the pr22 worktree)

- Focu Python tests (`tests/`): 135 ran — PASS
- HTTP fixture tests (`tests/unit`): 4 — PASS
- Muse publisher tests: 20 — PASS
- Inline reader JavaScript (`node --check`, workflow extraction): PASS
- Reader behavior simulation: PASS, including the new cases — manual
  Archive from Inbox card (`via: 'manual'`), manual Archive from article
  reader (reader closes), Restore from Archive card and from archived
  reader, persistence across simulated reload, no resurrection on rerender,
  and the pre-existing automatic article/audio/read-aloud completion paths.

Consistent with the cited CI run (41988089303). The historical failure at
`2ed61fbe` was not re-investigated, per instruction.

## The actual 06:14 job and the briefing integration

- The real production job is the Muse scheduled agent task
  `focu-daily-research-podcast` (daily 06:14 America/Denver), a host-agent
  workflow that runs the focu CLI from `~/workspace/focu` and invokes Open
  Notebook through `focu podcast generate`. It is NOT `scripts/run-daily.sh`
  and NOT `focu.daily.cli`. Inspected in full before editing. PASS
- The job's instructions were updated in place (same job, same schedule,
  same sources, compilation and library steps untouched):
  - new step 6b: build `briefing-units.json` from the canonical report
    (every item, literal headline, figures preserved, origin kinds);
  - step 7: generate with `--briefing-units` (episode name
    "Personal update — <date>", solo_expert/solo_expert), recording
    `briefing_style_version` / `briefing_style_sha256`;
  - step 8: deliver with `--briefing-units` (QC-gated); on QC failure,
    regenerate once, retry once, then deliver the report alone — the gate
    must not be bypassed;
  - step 9 and the delivery message now include the `briefing-qc.json`
    result and the style version/SHA;
  - explicit fallback: if the deployed checkout lacks `--briefing-units`
    (PR #22 not yet deployed), use the legacy `--content-file` path for
    that run and flag it prominently in the delivery.
  Read back and verified after update; next run Fri 2026-11-06 06:14 MST.
- Whether production generation reads the style file: the code path is
  verified (`focu/open_notebook.py` builds the provider prompt from
  `focu.briefing.read_style`, i.e. `references/briefing-style.md`, and the
  generation result records style version + SHA + item count). Live
  production use is BLOCKED until PR #22 is merged and the production
  checkout carries the code; until then the fallback flag applies.

## Style editability demonstration (§8)

- Deterministic render of `examples/secretary-briefing-demo-units.json`
  equals `examples/secretary-briefing-demo-script.txt` exactly; QC issues
  none. PASS
- Disposable copy of the style file with only the opening changed
  ("Here's what came in." → "A brief update for you.") plus a dated
  changelog entry: rendered script changes exactly that line; the provider
  prompt for the real 8-item input changes only in the opening line and the
  changelog entry; style SHA changes
  (`f33654b3874bbf94…` → `07c854d64fa97f71…`); coverage QC still passes;
  no Python code modified. The disposable copy was discarded; the owner's
  actual style file was not changed. PASS
- Style used for generation: version `2026-11-05.1`,
  SHA-256 `f33654b3874bbf9497bc10529435800237ee029b5a3d11634562c7d1891c16a1`.

## Real secretary briefing run (§9)

Input (all genuine, source-backed):

- Intent captured in the pr22 test DB:
  `int_666fbac93eef4a90ad6f21ef675db050`.
- Merged Evidence Pack `ev_secretary_briefing_20261105` (55 findings,
  11 sources, completeness partial): the 2026-11-05 registered-source
  report pack (40 findings) plus the two completed 2026-11-04 on-demand
  packs (Opus 5.5 claim-check, 8 findings; abstention mechanisms,
  7 findings). Quotes and source texts carried over verbatim; ingested
  successfully.
- Briefing units: 8 items — 6 registered-source (OpenAI, Nov 5:
  responsible AI infrastructure; Pierre acquisition; Daybreak Red in AWS
  GovCloud; Linux vulnerability pipeline; Images 2.6; DevRev) and
  2 requested-research (`int_c2cfee…` via KDnuggets; `int_c22de0…` via
  arXiv). No interest-follow-up item was fabricated.
- Deterministic composer render of the units passes QC; estimated
  8.44 minutes at 145 wpm — above the 5–8 minute daily target. Flagged,
  per instruction: coverage was prioritized and no item was dropped.

Generation (Open Notebook, episode-profile solo_expert, speaker-profile
solo_expert, single speaker):

- Attempt 1: job `command:5iocodt7jvq2adz5nk9b`, episode
  `episode:fptqiz7zsccrbihd7fr6`, provider status completed.
- Attempt 2 (regeneration): job `command:1rvmxd74zwfylz9mqjg7`, episode
  `episode:7n3hksm1yuwndwzfqycu`, provider status completed.
- Both transcripts restructured the input into thematic segments (the
  provider outline merged items, e.g. Pierre + Images 2.6 in one segment)
  and used show-style framing (attempt 1 opens: "Today, we'll be exploring
  OpenAI's exciting initiatives…"). Spot check: attempt 1 did preserve
  some figures ($4.8 million; 14,000; $6 million) inside its narrative.
- QC-gated delivery REJECTED both attempts with the same result:
  8 of 8 items `missing_headline_or_wrong_order`. No audio was delivered.
  - Transcript coverage QC for Open Notebook generation: FAIL
  - QC gate behavior (fail-closed, nothing delivered, no bypass): PASS
- Root cause: Open Notebook's podcast scriptwriter re-outlines source
  material thematically and does not reproduce the literal per-item
  headlines/structure the prompt contract requires, on either attempt.
  This is a provider behavior, not a defect in the PR #22 code; no repo
  code change was made and QC was not weakened.
- No alternative exact-script synthesis is configured in this environment
  (the `focu.daily` pipeline's audio mode requires an operator-configured
  `tts_argv`; none is set), and per instruction no new paid service or
  credential was enabled. A compliant briefing MP3 is therefore BLOCKED
  until either the provider honors literal structure or the owner approves
  wiring the deterministic composer script to a verbatim TTS path.
- Briefing MP3 metadata/decoded durations, SHA-256, ending check: not
  applicable — no deliverable MP3 exists (BLOCKED, above). The two
  provider-side episodes remain undelivered in Open Notebook.

## Private Artifact test (§10)

- Bundle `pr22-acceptance-20261105-b` built with the PR #22 publisher
  (strict audio audit on): 5 items, unique content IDs, embedded manifest
  identical to staged manifest, MP3 hashes match build report, both MP3s
  media-verified (386.808s and 374.352s, metadata == decoded).
- `Focu V04 Test` was rebuilt in place from that bundle (builder verified:
  12 asset hashes match; template contains the manual Archive/Restore
  controls and the `focu:content-consumption:v1` key). Contents: the
  secretary briefing as a full article (Nov 5, article-only — its audio is
  the blocked item above), the two on-demand research articles, and the
  two Nov 4 article+podcast items. Production `focu-podcast-library` was
  not touched. PASS (publication); device behavior UNVERIFIED (below).

## Manual Archive / Restore (§5)

- Code and simulated behavior: PASS (see test suites).
- iPhone checks awaiting the owner (UNVERIFIED): open **Focu V04 Test**;
  (1) tap Archive on any Inbox card — it should move to Archive instantly;
  (2) Restore it from Archive; (3) open the secretary briefing article and
  Archive it from the article toolbar — the reader should close and the
  item should be in Archive; (4) confirm a podcast item still plays.

## Bugs found and fixes

- No PR #22 code defects were found during acceptance; no code was changed
  on the branch (this document is the only addition).
- Provider contract failure (Open Notebook scriptwriter vs literal
  headline/structure): recorded above as FAIL/BLOCKED, not patched over.
- Operational blocker: production checkout switch to main is prevented by
  the staged uncommitted file described in the baseline section.

## Remaining limitations

- The 06:14 production job will run the legacy fallback (flagged) until
  PR #22 is merged AND the production checkout is on code that includes it.
- Cross-rebuild localStorage persistence on iOS remains partially verified
  and was out of scope for this task, per instruction.
- Article read-aloud voice quality (owner previously rejected the system
  voice) is unchanged and out of scope.
- PR #22 remains Draft: a substantive acceptance failure (provider
  generation QC) is unresolved.
