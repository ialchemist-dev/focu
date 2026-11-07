# PR #25 — Muse E2E Acceptance Results (Information Gate Provider A/B)

Date: 2026-11-07 (America/Denver)
PR: https://github.com/ialchemist-dev/focu/pull/25 — **still Draft, not merged**
Branch: `feat/information-gate-provider-ab`
Head tested: `d5ac0f1c36911e0a142ce053a0faf7ac08bc4a30` (matches the PR head at acceptance start)
Base: `main` @ `df1e0cb744d564c42c40c765392f369edafb36bd` (unchanged)
Runbook: `docs/INFORMATION_GATE_PROVIDER_AB.md`

Isolation: worktree `~/workspace/focu-pr25`, acceptance root
`~/workspace/focu-pr25-acceptance/` (fresh data dirs throughout). The production
checkout `~/workspace/focu`, its data, the 06:14 job, registered sources and
the production Podcast Library were not modified. No code changes were made to
the PR branch by this acceptance (see §9).

## Verdict summary

| Area | Verdict |
|---|---|
| Offline regression tests (full suite) | **PASS** — 138/138 |
| Gate tests specifically | **PASS** — 17/17 |
| Real candidate collection (14 items) | **PASS** (collector limits recorded, §3) |
| Credential check method (no values exposed) | **PASS** |
| `OPENAI_API_KEY` / `TYPESAFE_API_KEY` availability | **BLOCKED** — neither is configured for the host environment (§4) |
| Fail-closed pre-flight (missing keys) | **PASS** (§5) |
| Bad-credential handling + audit (real HTTP) | **PASS** (§5) |
| Live three-provider Shadow A/B (judgments, disagreements, latency, tokens, cost) | **BLOCKED / UNVERIFIED** — no valid credentials (§6) |
| Active mode rank-only, Daily Pipeline integration (stub transport) | **PASS** (§7, transport caveat) |
| Feedback persistence | **PASS** (§8) |
| iPhone | **UNVERIFIED** — this PR ships no iPhone UI (per its own doc) |

## 1. Baselines

- PR #25 open + Draft; head SHA and main SHA verified via the GitHub API
  before any work.
- Production checkout inspected before and preserved exactly (branch
  `feat/v04-unified-content-feed` @ `609bc98`, its staged/untracked files
  untouched).

## 2. Offline regression tests

`python -m unittest discover -s tests -p 'test_*.py'` in the isolated
worktree venv: **138 tests, OK**. The gate file alone:
**17 tests, OK** — documented-shape contract tests for all three providers
(Responses structured output, Decisions predicate answers, Jev `noul`
answers), refusal/malformed rejection, no-key-means-no-network, cache
repeat = zero additional calls, transient errors not cached, shadow
non-invasiveness, active rank-only with revision matching, feedback
append-only, and daily-pipeline shadow/active wiring.

## 3. Candidate collection — 14 real items

Two collection paths were exercised:

1. **Direct CLI collector** (`focu.daily.cli ingest`, no input units):
   OpenAI News RSS succeeded (1,368 items), Felix Rieseberg RSS succeeded
   (15). The M1 collector does not implement the HTML sources (Anthropic
   sections, OpenAI Research/Index, DeepMind, Claude Blog —
   `collector_not_implemented`; in production those are collected by the
   worker flow), X sources report `needs_auth`, YouTube failed in this venv
   (`yt_dlp` not installed there), Ethan Mollick hit a network
   `IncompleteRead`. Full record:
   acceptance `logs/collector-ingest-2026-11-07.json`.
2. **Production-equivalent units**: the archive-scale RSS backlog is not a
   realistic daily candidate set, so the data dir was wiped and re-ingested
   via `--input-units` with the 14 real items the production pipeline itself
   collected on Nov 6–7 (8 + 6, from those days' briefing-units, URLs
   restored from the evidence packs, source names mapped to the registered
   config: 9× OpenAI News, 4× Anthropic Research, 1× 北美王路飞).
   `pending_candidates` returned exactly these 14, bodies 272–1,400 chars.

Context fixtures (privacy decision): the gate prompt sends source excerpts
plus goals/wiki context to external providers. The runbook's own privacy
note requires owner approval before transmitting sensitive Wiki details, and
no such approval was in scope for this acceptance. The shadow/active runs
therefore used **host-authored fixtures** (`current-goals.md`,
`wiki-fixture/` — generic statements of the owner's standing interests), NOT
the real llm-wiki. The real-wiki transmission decision remains the owner's.

## 4. Credential check

Checked by presence only (boolean/length probes; values never printed,
logged, or committed): shell environment, shell profiles, systemd user
environment, Open Notebook's env files, focu data dir.

- `OPENAI_API_KEY`: **not configured** in any checked location. (An OpenAI
  key exists sealed inside Open Notebook's encrypted credential store for
  that application only; it is not an environment credential and was not
  extracted.)
- `TYPESAFE_API_KEY`: **not configured** anywhere found.

Consequence per the task's own condition ("when authorization and
credentials are in place"): the live-call portion (§6) is BLOCKED, and
everything credential-independent was completed instead.

## 5. Fail-closed and failure modes (real behavior, real HTTP)

- **No-key shadow evaluate** (`focu-gate evaluate`, all three arms):
  exit 1 with `OPENAI_API_KEY required for OpenAI`, before any network call;
  no ledger or snapshot was created. **PASS.**
- **No-key daily `run` with gate opted in**: the whole run aborts with a
  structured `gate_error` (`retryable: false`). This is fail-fast on an
  explicit opt-in misconfiguration; it is NOT the silent legacy fallback.
  The per-arm fallback (§below) is what the doc's "an error leaves legacy
  ranking in effect" describes. Flagged as an owner judgment call in §9 —
  behavior is safe and loud either way; no patch made.
- **Bad-credential probes** (scratch store, deliberately bogus key values,
  limit 3 items × 3 arms, real HTTPS through the host egress proxy):
  - OpenAI Responses: `provider HTTP 401` on all 3 items — endpoint
    reachable, auth rejected.
  - OpenAI Decisions (`/v1/decisions`): `provider HTTP 401` on all 3 items
    — the documented path is live (a wrong path would 404).
  - TypeSafe Jev (`/v1/systemone`): `provider HTTP 401` on 2 items; the
    first call returned `provider request failed (TimeoutError)` — the
    gate's 25 s transport timeout fired before auth completed. Recorded as
    an observation (§9), not a defect verdict: a single cold call through
    the proxy is not evidence about Jev's real latency.
  - All 9 arm results were saved as failures; **zero judgments were
    fabricated**; the run completed (`evaluated 3, errors 9`);
    `focu-gate report` on the scratch snapshot shows (0 ok, 3 errors) per
    provider. Errors are not cached (unit-tested), so a later valid run
    retries them. **PASS.**
  - Disclosure: the probe requests carried the standard gate payload
    (public registered-source excerpts + the authored fixtures of §3) to
    the two providers' endpoints, where they were rejected at auth.

## 6. Live three-provider Shadow A/B — BLOCKED

Not run: no valid `OPENAI_API_KEY` or `TYPESAFE_API_KEY` is available to
the host. Therefore this acceptance makes **no claim** about:

- whether the three providers' real response shapes match the parsers on
  authenticated success paths (only the 401 error path was exercised live);
- per-model judgments or disagreements on the 14 real candidates;
- latency, token usage, or cost of any arm;
- whether `gpt-6-luna` (Decisions) or `jev-latest` respond as documented
  for this account.

Unblocking requires the owner to provision both keys into the host
environment through a secure channel (e.g. a 600-permission env file the
run command sources, as the Open Notebook stack does). Once provisioned,
the exact shadow command from the runbook runs unchanged against the
preserved acceptance data dir (14 candidates, fixtures, ledger).

## 7. Active mode — rank-only integration (stub transport)

Method: full daily `run --text-only` executed in-process on three identical
store copies (off / shadow / active), new isolated run date **2026-11-08**,
with ONLY the provider transport seam replaced by a deterministic stub —
the same seam the repo's own pipeline integration tests use. The stub
promoted two items (Anthropic agent-memory; GPT-6 Cyber), deferred one
(Flipsnack), and rated the rest normal. This verifies pipeline mechanics,
**not** provider judgment quality.

Results:

- All three runs completed. Episode selection: **9 units** in every mode;
  **episode content sets identical** across off/shadow/active; **pending
  sets identical**; 14 contents in every store; coverage rows identical
  (9, created by selection itself — the gate created none).
- **Shadow order == off order, exactly** (non-invasive). **PASS.**
- **Active order**: the two promoted items moved to positions 1–2 (from
  3rd and 6th in the off order); all other items kept their relative legacy
  order; `gate_priority` is recorded on every selected unit (promote /
  normal / defer). The deferred item (Flipsnack) was outside the capped
  episode in BOTH modes and remains pending — deferred ≠ hidden or
  deleted. **PASS: rank-only, no suppression, no vanishing.**

## 8. Feedback persistence

Two `focu-gate feedback` entries were written via separate CLI processes
against the active store (agent-memory → `useful`; Flipsnack →
`not_useful`; both notes labeled as acceptance fixtures) and read back in a
fresh process from `gate/ledger.sqlite3`: both rows intact, append-only.
The same ledger holds the 42 evaluation rows (14 items × 3 arms) from the
active run, and `focu-gate report` renders the snapshot correctly
(mode active, primary jev, 14 ok / 0 errors per arm under the stub).
**PASS.**

## 9. Defects and fixes

**No code was changed.** No defect was evidenced: the only live-path
failures trace to absent credentials, which is an environment state, not a
PR defect. Two observations for the owner, neither patched on speculation:

1. **Jev timeout observation**: one bogus-key Jev call exceeded the
   transport's 25 s timeout before returning 401. If Jev's real
   time-to-first-response under load approaches that bound, live runs
   could record spurious timeouts. Verify during the first credentialed
   run; consider a provider-specific timeout only on that evidence.
2. **Missing-key semantics**: opting the gate in without keys aborts the
   daily run (fail-fast, §5) rather than degrading to legacy ranking.
   Defensible for an explicit opt-in, but it is a product decision: in
   production, an expired/revoked key would stop the briefing instead of
   merely disabling the gate.

## 10. What remains before this Gate can run in the daily Briefing

1. **Provision credentials** (owner action, §6) and run the credentialed
   shadow A/B on these same 14 candidates; inspect the disagreement cases
   and per-arm latency/token/cost records in the ledger.
2. **Owner annotation round**: the runbook asks the owner to mark valuable,
   unhelpful, and missed items (feedback CLI is verified ready, §8) so the
   rubric and the `recommend()` thresholds can be judged against his taste.
3. **Probability discipline**: Decisions/Jev outputs are model-reported
   probabilities, the LLM arm's are rubric ratings; neither is calibrated.
   No threshold (promote/defer cutoffs, `research_candidate`) has been
   validated against outcomes yet.
4. **Wiki/goals transmission approval**: real llm-wiki excerpts and a real
   goals file go to OpenAI/TypeSafe on every uncached evaluation. The
   owner must explicitly approve that data flow (this acceptance used
   authored fixtures instead).
5. **Integration debt (pre-existing, per the PR's own limits)**: PR #22/#23
   (briefing flow, by-origin podcast policy) are still unmerged Drafts;
   the gate currently ranks the legacy daily selection, not the unified
   briefing. The 06:14 production job does not pass gate flags, and the
   production checkout does not carry this code.
6. **Cost shape**: three arms × N candidates are separate paid calls
   (cache prevents repeats on unchanged context). A daily budget/limit
   policy is an owner decision before active mode is enabled anywhere
   near production.
