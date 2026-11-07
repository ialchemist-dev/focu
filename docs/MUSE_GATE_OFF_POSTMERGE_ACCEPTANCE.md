# Muse integrated acceptance — Decision APIs OFF

Date: 2026-11-07
Target: merged main after PRs #22, #23, #24, #25.
Status: executable TEST instruction, not permission to change production.

## Mission
Run one full, isolated test of the **integrated** Focu pipeline and deliver a readable article + consolidated source-backed briefing with Decision API **OFF**. Do not require or recover `OPENAI_API_KEY` or `TYPESAFE_API_KEY`. Existing Open Notebook encrypted credentials remain private to Open Notebook; do not extract them or enable any new paid provider.

## 1. Isolation and checkout

Inspect `~/workspace/focu` first. Earlier Muse runs found staged/untracked work in that old checkout. Do not stash, reset, clean, move, discard, switch, or overwrite any of it. Do not alter the daily 06:14 Denver host task, source registrations, data, credentials or the production Focu Podcast Library.

Use a NEW isolated worktree and data root:

~~~bash
cd ~/workspace/focu
git fetch origin
git worktree add --detach ~/workspace/focu-gate-off-e2e origin/main
cd ~/workspace/focu-gate-off-e2e
git rev-parse HEAD
~~~

If this worktree exists, inspect it before reusing. Set up an isolated virtual environment and `~/workspace/focu-gate-off-e2e-acceptance/` containing all test data. Verify GitHub reports PR #22–#25 merged; report any missing PR as BLOCKED before asserting the test is integrated.

## 2. OFF means NO decision-model calls

For every real daily command set:
`--gate-mode off --gate-provider off`

Do NOT pass `--gate-compare`, call `jev` or `openai-decisions`, use `shadow` or `active`, or send personal Wiki/goals excerpts to external decision providers. Check presence only of any keys; their absence is expected and must NOT block OFF-mode delivery. Record zero Gate network requests and zero provider-funded judgments. Gate OFF preserves the legacy source ranking.

## 3. All regression tests

Run from new worktree with a fresh venv:
~~~bash
python -m pip install -e .
python -m unittest discover -s tests -p 'test_*.py' -v
python -m unittest discover -s tests/unit -p 'test_*.py' -v
(cd experiments/muse-artifact-reader && python -m unittest discover -p 'test_*.py' -v)
node experiments/muse-artifact-reader/test_reader_behavior.js
~~~

Also run inline JS syntax extraction/check exactly as .github/workflows/tests.yml. Run `focu --help`, `focu-gate --help`, `python -m focu.daily.cli --help`. Record exact test counts/failures, specifically merged secretary QC + audience QC + origin mode + gate OFF integration.

## 4. Real registered-source daily path

Use a fresh data dir and a disposable source config with registered IDs. Replay the actual 14 source items preserved in the isolated PR #25 acceptance directory; preserve original titles, URLs and content bodies. An `--input-units` replay is a real-input fixture, not evidence that every live collector works. Optionally test public RSS fetch with separate data directory; HTML and X may need host collectors.

Use a new date and choose explicit `--text-only`, so the absence of configured audio does not block a valid article/briefing test:

~~~bash
python -m focu.daily.cli run --config "$TEST_SOURCES" \
  --data-dir "$TEST_DAILY_DATA" --date "$TEST_DATE" \
  --text-only --input-units "$TEST_UNITS_JSON" --json \
  --gate-mode off --gate-provider off
~~~

Verify source ingestion and dedup, source `podcast_mode=daily_compilation`, actual selected IDs, deterministic source ranking, complete source/headline/number briefing QC, audience-profile diagnostic and exact hashes. No Decision API calls. Validate text output, backlog and truthful errors.

## 5. One new on-demand research case

Create a NEW isolated research request through `focu --db "$TEST_DB" request` without `--podcast`. Choose a real public primary technical paper/post, not the previous Weight-Space or Sleeper Agents test. Host agent performs genuine evidence-backed investigation, cites original results, checks real external assessment where available, and writes a standalone article with explicit Research Delta, mechanisms, figures and limitations. Do not invent independent replication if none exists.

Delivery has `origin=user_initiated`, `podcast_mode=none`, canonical content_id, article.md, research.md, content.json. Verify no standalone MP3/Listen by default. **No automatic new standalone podcast generation is authorized by this test.**

## 6. Unified briefing policy and knowledge

Build a **single private test daily compilation** that summarizes both registered-source article(s) and the finished on-demand article, and references original content IDs through `covered_content_ids`. The on-demand article's mode stays `none` and gets no MP3. Registered source collector must still reject injected on-demand records; editorial linkage is a separate operation. Test valid coverage and negative cases: missing IDs, duplicate compilation, item with `none` plus stray MP3.

Read canonical llm-wiki SCHEMA.md and use it to propose factual links and conflicts in a SANDBOX COPY only. Do not mutate canonical Wiki. Distinguish a manual host-agent Wiki update demonstration from an actually implemented automated Wiki bridge. If auto-bridge is absent, report NOT IMPLEMENTED.

If the scheduler cannot yet automatically mix on-demand findings into daily editorial content, prove the publisher supports the format and report automated orchestration as NOT IMPLEMENTED / BLOCKED, not PASS.

## 7. Reader and test Artifact

Build an immutable private bundle with existing publish.py; follow actual CLI help. Update only a disposable private Artifact such as Focu V04 Test, never the production Podcast Library. Validate exactly one content item per ID, source links, "In the daily briefing" linkage, article-only Listen behavior (Listen only for an actual MP3), separate device Read aloud, manual Archive/Restore from card and reader, and existing auto-completion mechanics. Use only an existing QC-verified MP3 fixture for playback/seeking/ending; never attach rejected Open Notebook generations.

Provide the precise Library entry name and owner iPhone acceptance steps. Do not mark an on-device test PASS before owner confirmation.

## 8. Failure and safety checks

Prove OFF mode succeeds without API keys or external decision calls. Malformed/unauthorized audio must fail closed, not delete articles. Corrupt audio must be rejected. An unavailable provider must be reported, not substituted. Test input to registered source cannot pretend to be a user request. Confirm production checkout, data, schedule, source list, provider credentials and production Artifact remained untouched.

## 9. Acceptance report

Save `docs/POSTMERGE_MUSE_GATE_OFF_E2E_RESULTS.md` on a NEW Draft documentation PR (not main; no auto-merge) with exact main SHA, local worktree, suite counts, source IDs, delivery paths, QC receipts, test Artifact hash, source/active-research policy, Wiki status, and phone status.

Report PASS, FAIL, BLOCKED, UNVERIFIED, NOT IMPLEMENTED individually. Preserve distinctions between:
- Real input and synthetic fixtures.
- Mocked provider mechanics and genuine external calls.
- Verified article/briefing script and a compliant generated MP3.
- Manual Wiki integration and actual automated Wiki bridge.

The current high-fidelity 30–40-minute audio target, autonomous budget research and full knowledge gate are planned capabilities, not demonstrated by merged code. Never claim they are working without evidence. Do not change production or request new Decision keys to complete this OFF test.
