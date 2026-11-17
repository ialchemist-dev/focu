# Focu 24h Run — PM Plan #3 (ranked waves 25–30)

- When: 2026-11-17 ~04:30 America/Denver (wave 24). Run hard stop: 2026-11-18 01:45 (~21h remain).
- State at planning: PM sweep #2's wave order is fully shipped on dev-main — F1–F5, Q1 re-walk, N1–N3, Q5 day-status assembly — full suite **532 tests OK**. This plan ranks what remains: the still-open hunt questions (Q3, Q7, Q10, Q11), the two Q1 re-walk residuals (F8 button-swap, Archive done-vs-dismissed), and three gaps the shipped work itself exposed.
- Method note: every acceptance criterion below names a file, symbol, string, or test an implementer can check without asking the PM anything. Where a question's honest answer is "do not build," this plan says so and records the non-change as the deliverable.

## Verdicts on the candidate list (before ranking)

- **Q10 — CLOSED, not a wave.** The one-full-read budget was answered by F4 (wave 18, 0e06ef48): publish emits `original_url`, the article view carries one quiet Original link. The BACKLOG line was simply never updated; this plan's backlog pass closes it.
- **Q3 — automation REJECTED (again, on evidence).** Sweep #2's reasoning stands: refresh-check probes feeds, and a leaver's feed stays live, so no fetcher can meet the affiliation evidence bar. The buildable half is *visibility* — making "affiliation as of" a date the owner sees, and making staleness of that date a reported signal that prompts the human/agent refresh act. That half is Wave 29.
- **Q11 — design only, last.** Sweep #2 and the PRD agree: cold start matters at promotion-to-main time, not before. It gets a PM document (Wave 30), not code.
- **Q12 residual — excluded.** Chat-delivered MP3s writing nothing back to the reader store is a production delivery habit; off-limits this run, already recorded for the promotion decision.
- **Adapters' owner-side collection — excluded as a wave.** The RedNote/Facebook exporters live outside Focu *by license and by design* (MediaCrawler's non-commercial license must not be vendored; Instagram's session file is created by owner tooling). F2 made the three types registrable; whether any owner-side collection ever runs against real accounts is an owner decision after the run. An in-repo "preflight checker" for export files would validate a shape no real exporter has produced yet — speculative surface, not attention returned. Not ranked.

---

## Wave 25 — NEXT — (BE) Q7: sparsity accounting, an explicit stop rule, and floor validation

**Why first.** Every other open item is an improvement; this one is a trust boundary. The learning engine's floors (`focu/learn.py:94–101`: `WINDOW_DAYS = 30`, `MIN_DELIVERED = 10`, `MIN_NEGATIVE_EVENTS = 3`, `MIN_NEGATIVE_RATE = 0.2`, `MIN_USEFUL_EVENTS = 3`) were set by design judgment and have never been validated against any data, shaped real or otherwise. F1 (8fa8412a) removed the blocker: briefing marks now attribute. From promotion onward, real exports will flow into these floors. If the floors fire on noise, the owner learns to ignore proposals — and the entire P2 objective ("visibly learns its user — with permission") dies of proposal fatigue, the failure mode learning-design §6 was written against. If they never fire, Phase 3 is inert and nobody can tell. Either failure is currently *invisible*: when the engine proposes nothing, the output does not distinguish "healthy silence" from "no signal arrived." Attention returned: protects every future proposal's credibility — the scarcest resource in the learning loop — at a cost of zero owner attention (the surface speaks only when proposals are already being reviewed).

**Exact scope** — `focu/learn.py` + CLI print path + new tests. No floor value changes unless the validation harness first produces a named failing fixture (see criterion 5).

1. **Sparsity report.** `generate_proposals` computes, for the current window, a `sparsity` block: per source — delivered count, attributed feedback events by kind (negative / useful / completion), and distance-to-floor for each gate (e.g. `delivered: 12/10 ✓`, `negative: 2/3`); plus window totals (total attributed events, `unattributed_feedback` count as already tracked). The block is additive in the proposals result and printed by `focu learn proposals` beneath any proposals (and when there are none).
2. **Stop rule.** A named constant in the constants block beside `MIN_DELIVERED` (implementer's name, e.g. `MIN_ATTRIBUTED_EVENTS`) gates *statistics* proposals: when total attributed feedback events in the window fall below it, the engine emits zero `source_weight` proposals and the result carries an explicit reason string of the form `insufficient attributed signal: N events in 30 days`. Review proposals (`renewal`, `pause_review` — record-driven, not statistics-driven) are **not** gated by the stop rule.
3. **Validation harness** — `tests/test_learn_sparsity.py`, fixtures shaped like the post-F1 world (marks arrive as per-unit observations, including fan-out from one compilation mark):
   - (a) *Completions-only history at scale* (≥5 sources, ≥10 delivered each, zero negative/useful marks) → zero proposals; sparsity block shows the gates unmet.
   - (b) *Uniform noise*: fixed-seed pseudo-random marks spread thinly and evenly across ≥5 sources over 30 days at a low rate → no demotion and no promotion proposal fires (floors hold against noise).
   - (c) *Concentrated real-shaped signal*: one source, 12 delivered, 4 `not_useful` observations (≥3 events, ≥20%) → the demotion proposal **does** fire (floors are not so high they never fire).
   - (d) *Stop rule*: a window whose total attributed events fall below the constant, including one source that would individually pass its floors on a technicality the totals contradict — assert zero statistics proposals and the reason string present verbatim in the result.
   - (e) Sparsity numbers in (a) match the fixture's counts exactly (no off-by-one in the accounting itself).

**Acceptance (line-checkable):**
1. `grep -n "MIN_ATTRIBUTED_EVENTS\|insufficient attributed signal" focu/learn.py` (constant name may differ; the reason-string prefix `insufficient attributed signal` may not) returns the constant in the constants block and the string in the engine.
2. `tests/test_learn_sparsity.py` exists and passes with fixtures (a)–(e) as separate test methods.
3. `focu learn proposals` output on an empty-history scratch store prints the sparsity block and the insufficient-signal reason, and zero proposals — no traceback, no bare empty list.
4. Renewal and pause_review proposals still generate under the stop rule (a test with a past-`review_after` entry and an empty feedback window asserts the review proposal exists).
5. No floor constant's value differs from learn.py:94–101 at plan time, **or** the diff names the harness fixture that failed without the change, quoted in the wave's STATE.md line.
6. Full suite green at ≥532 + new tests.

---

## Wave 26 — (BE) Q5's missing half: an owner-visible day-status surface

**Why second.** Wave 23 built the honest record — `assemble_day_status` (focu/daily/pipeline.py:191), persisted as a `day_status` stage row and returned in the run result (pipeline.py:700–757) — and then stopped one step short: a grep for `day_status` across `focu/` outside pipeline.py returns **nothing**. No CLI prints it, nothing renders it. Q5's acceptance was "one place the owner actually sees"; today the record is visible only to someone reading the run-result dict. A thin day still arrives unexplained unless the owner's agent happens to surface the dict. Attention returned: converts shipped-but-invisible work into the Q5 payoff — on a thin or failed day, one factual sentence ("1 collector failed (LinkedIn); Paused by you on …: X; nothing new from Y") instead of a silent gap or a debugging session. Est. several minutes on every abnormal day, and abnormal days are exactly when attention is scarcest.

**Exact scope** — a read-only CLI surface over the existing record. No changes to `assemble_day_status`, the record's shape, or the reader (the reader's status-line discipline — status speaks only when it *is* the content — is a separate, later decision once this text has proven itself in the job report).

1. New subcommand `focu daily day-status [--date YYYY-MM-DD] [--json]`: resolves the run for the date (default: the latest run in the store), reads its `day_status` stage report via the same `_stage_report` path pipeline.py:700 uses, and prints: the outcome class, the record's own `summary` string verbatim, one line per source (name; collected/considered/selected counts; each withholding or failure named as the record names it), and the audio roll-up line.
2. `--json` prints the stored record byte-for-byte (no re-assembly, no re-computation — the surface reads, it does not reinterpret).
3. Missing record (no run for the date, or a pre-wave-23 run with no `day_status` row): print exactly one line — `No day-status record for <date>.` plus the reason (no run / predates day-status assembly) — and exit 0. Never fabricate counts.

**Acceptance (line-checkable):**
1. `focu daily day-status --help` (or the CLI's arg-error path) shows the subcommand wired; the command is dispatched from the same CLI module as the other `focu daily` subcommands.
2. Tests build three fixture days through the existing pipeline test helpers — clean success, thin (nothing selected), partial_failure (one failing source) — and assert the printed output contains the stored record's `summary` string **verbatim** and, for the failure day, the failing source's name.
3. A `--json` test asserts the output parses to a dict equal to the stored stage report.
4. The missing-record test asserts the single explicit line and exit 0.
5. `git diff` for the wave touches no line of `assemble_day_status` or of the record's construction; README's daily-pipeline section gains one line naming the command (integrator, same push, per point 9).

---

## Wave 27 — (UI) Reader honesty residuals: F8 fallback parity + Archive state label

**Why third.** Both residuals are places where the reader makes the owner model the system instead of just using it — the exact tax the philosophy forbids — and both are small, bounded, and fully evidenced by the Q1 re-walk (§2, §4). Together they are one reader wave; separately neither justifies a wave slot.

**Exact scope** — `experiments/muse-artifact-reader/index.html` + behavior tests only. No store-shape change; the export payload must remain byte-identical for the same store.

1. **F8 — the reader's audio-failure path joins the card path.** Today the card path falls back automatically (`playItem()` → `readAloud()` on failure) while the reader swaps two buttons (`#listen` / `#readaloud` visibility logic, index.html:639–642) and, on audio error, instructs the owner: index.html:885–886 sets `#readaloud` visible and writes *"Cached audio could not load. Try device read-aloud instead."* Change: on cached-audio failure for an item with article blocks, the reader starts device read-aloud automatically (the same fallback the card path performs), and the state line states the fact without an instruction (form: *"Playing with device voice — the recorded audio could not load."*). The owner is never asked to choose an engine.
2. **Archive cards say which kind of done they are.** `render()`'s archive branch (index.html:503) lists `isDone || isNotForMe` with no card-level distinction, though the predicates are already evaluated per card. Change: `appendCard` in Archive view renders a one-word state label — `Finished` when `isDone(id)`, `Not for me` when `isNotForMe(id)` — in the card's existing meta line. No new control, no store change; Restore behavior untouched (it already reverses both identically).
3. **Archive's visual weight matches its neighbours (audit §2.3's unimplemented line).** The re-walk's recount found Archive kept its bordered `.card-action` weight while Not-for-me and Useful went borderless (`.quiet-action`). Change: the card-level Archive action uses the same quiet styling as its two neighbours. CSS/markup diff limited to that class application.

**Acceptance (line-checkable):**
1. `grep -c "Try device read-aloud" experiments/muse-artifact-reader/index.html` returns 0.
2. Behavior test: opening an item whose `audio_url` is set and whose id is the failed-audio id engages the read-aloud path with **no second tap** and shows exactly one primary listen control; pre-existing behavior tests are modified only where they pinned the two-button swap, and each such modification is named in the wave report.
3. Behavior test: an Archive card for a done item renders `Finished`; for a not-for-me item renders `Not for me`; neither label appears in Briefing or Research views.
4. The wave-5/6 export tests pass **unmodified** (payload byte-identical guard).
5. JS behavior suite green; publish tests green; full suite green at ≥ current count.

---

## Wave 28 — (BE/publisher) The glance layer's last hole: bullet-shaped digests get no gist and no summary

**Why fourth.** Wave 22 (N1) fixed the compilation gist, but the re-walk's pipeline measurement (§3) left a second, quieter hole: gist coverage was 59/61, and the two misses — both **LinkedIn Feed digests** — miss *completely*: `make_gist` (editorial.py:119) finds no synopsis, claim, or lead paragraph in a bullet-list body, returns `""`, and the same shape leaves `summary` empty too, so those cards render **title + price and no text at all**. The LinkedIn digest is not an edge case; it is a standing production source whose items recur in the bundle (as covered items, in Archive, and uncovered whenever the selector skips a day). A card with no text forces a full open or a blind skip — the two outcomes the gist layer exists to prevent. Attention returned: the 0.5s rung restored for the one source shape that currently has no rung at all, every day that shape appears.

**Exact scope** — `experiments/muse-artifact-reader/editorial.py` (+ publish.py only if the summary derivation lives there) + publish tests. Extraction stays **extractive-only** — every character from the item's own text, per the gist layer's founding rule.

1. When synopsis → claim → lead all yield nothing **and** the body is bullet-shaped (≥3 lines beginning `- ` or `• ` — the production LinkedIn digest unit's shape), the gist falls back to the first bullet's cleaned text, passed through the same sentence-boundary / `shorten()` rules and the same ≤ `GIST_LIMIT` budget as `make_gist`'s existing paths.
2. The item's `summary` gains the same fallback, so a digest-shaped item is never published with both fields empty. (If summary already derives from the gist path, criterion is the observable output, not a second code path.)
3. The existing contract is preserved: a gist that would merely repeat the item's title is still omitted, and non-bullet items' published output is byte-identical to today.

**Acceptance (line-checkable):**
1. A publish fixture shaped like the production LinkedIn digest unit (title + bullet-list body, no synopsis/claim/lead) yields an item with non-empty `gist` **and** non-empty `summary`; a test asserts both are substrings of the fixture body and `len(gist) <= GIST_LIMIT`.
2. All pre-existing editorial/publish tests pass **unmodified** (byte-identical output for every non-bullet shape, including the wave-22 agenda-gist fixtures).
3. A bullet-shaped fixture whose first bullet equals the title still publishes with no `gist` key (omission contract intact).
4. Publish + behavior suites green; full suite green.

---

## Wave 29 — (BE) Pack freshness gets an owner: refresh-due, affiliation-as-of, and the totals pin

**Why fifth.** Q2's tooling shipped (refresh-check, wave 14) but sweep #2 named the residual precisely: *no role or schedule owns running it*, and its age signal (`STALE_DAYS = 180`, packs.py:58) is decorative next to observed hours-scale feed breakage (three rot cases found within hours of the Anthropic v1.0.0 verification). Q3's buildable half is the same shape: affiliation staleness is currently invisible. This wave gives freshness an owner *inside the repo's own vocabulary*: a due-report any agent or cron can run at promotion time, and affiliation dates surfaced where pack decisions are already made (`focu pack show`). It deliberately does **not** schedule anything against production and does **not** automate affiliation checking. Attention returned: prevents the silent-thinning failure (a pack rotting until the briefing quietly loses sources) — the costliest pack failure mode because it is invisible precisely when it happens.

**Exact scope** — `focu/packs.py` + CLI + tests. All additions report-only: no pack file, registry, or record is written by any of it.

1. **`focu pack refresh-due [--json]`**: for each bundled pack, computes days since the pack's `verified_at` and lists packs due under named policy constants in packs.py (defaults: pack due when `verified_at` is >14 days old, or when any member source's own `verified_at` is >30 days old — constants named, e.g. `REFRESH_DUE_PACK_DAYS` / `REFRESH_DUE_SOURCE_DAYS`, values as stated). Output per due pack: name, age in days, the reason (which constant tripped, naming the stalest source where applicable). Not-due packs are counted, not listed.
2. **Affiliation staleness in refresh-check**: the existing report gains a per-pack `affiliation` section listing sources whose affiliation evidence was last verified >90 days ago (per-source `verified_at`, falling back to the pack's), each line carrying the date and the standing instruction in words: a human/agent re-check act, **not** automated. No new network calls of any kind.
3. **Affiliation-as-of in `focu pack show`**: each source line gains its affiliation-as-of date — the source's own `verified_at` when present, else the pack's, labelled `(pack-level)` when inherited — so the date is visible at the exact surface where install/update decisions happen.
4. **Attention-totals pin** (sweep #2 §2's one soft spot): the update plan's accumulator (packs.py ~1468) was never cross-checked against install plan (~713) and catalog/show (`_attention_total`, packs.py:934). Add one test: the same pack state yields the **same** enabled-source attention total from all three paths; if a formatter's scope legitimately differs, the test pins the difference and the formatter gains a scope label instead.

**Explicit non-change (recorded, not an oversight):** `STALE_DAYS` stays 180. The sweep's evidence is that feed-*health* signals carry the real weight and the due-report above is the cadence mechanism; lowering the age threshold would add warning noise to every validate/show run without detecting anything the health probes don't.

**Acceptance (line-checkable):**
1. `focu pack refresh-due` on the four shipped packs (all verified 2026-11-17) prints zero due packs and the not-due count; a fixture pack with `verified_at` 20 days old is listed with its age and the tripped constant's name.
2. A refresh-check test on a fixture whose source `verified_at` is 100 days old asserts the source appears in the `affiliation` section with its date; a second assertion counts fetch calls and proves the section added **zero** network calls versus the same fixture without the section.
3. `focu pack show anthropic-personal-blogs` output contains an affiliation-as-of date on every source line (test asserts the line shape for ≥1 source with its own date and ≥1 inheriting the pack's, if such a source exists in the shipped pack; otherwise the fixture pack covers both cases).
4. The three-accumulator pinning test exists and passes.
5. Report-only proof: the existing refresh tests' byte-identity assertions (no writes) pass unmodified; full suite green.

---

## Wave 30 — (PM) Q11 cold-start design + run close-out hygiene

**Why last, and why it still earns a slot.** Q11 is the only hunt question with no artifact at all, and the run should not end with it unexamined — but its own evidence (PRD §4 Q11; sweep #2) says it matters at promotion time. A PM document now costs one wave and makes the promotion decision concrete instead of reopening the question later. The same wave absorbs sweep #2's recorded doc-hygiene items, which are cheap now and confusing later.

**Exact scope** — documents only (`team/`, `docs/dev-team/` headers, one README line). No product code, no pack data edits.

1. **`team/pm-q11-cold-start.md`** designs the smallest first run the Source Library now makes possible (browse → preview → install → first briefing) and answers the PRD's question in so many words: a starter pack serves the **user's** objective when the user asked their agent to choose — de-recommendation subordinates recommendation to human intent, and an explicit "set me up" *is* intent. The design's hard edges: exactly **one** starter pack, chosen from the user's stated interest (never a bundle of packs); preview before install, same as any pack; removable in one action; installing it enables nothing else (the PRD's no-subscription-by-implication rule); no default is ever silent — the first briefing states which pack is installed and how to remove it. Implementation is explicitly deferred to promotion; the doc states what an implementer would build and how it would be acceptance-tested then.
2. **README cold-read line**: one line at the top of README.md pointing cold readers to the run/dev-main section, so the pre-run framing ("Current integrated version: 0.4.0 … available on `main`") is no longer the first claim a stranger meets. One line; no restructuring.
3. **Design-doc superseded headers**: `docs/dev-team/backend-design.md` gains a one-line header noting its CLI sketch is superseded by the shipped `focu pack` surface; `docs/dev-team/learning-design.md` gains a one-line header noting Phase 3 shipped this run (its "(next run)" labels at lines 179/203 are history). Headers only; bodies untouched — they are point-in-time designs and should read as history, not be rewritten into it.
4. **Backlog↔STATE reconciliation**: a final pass asserting every STATE.md integration line has a matching BACKLOG checkbox state and vice versa (sweep #2 recorded this drift once already; the run ends reconciled or the discrepancies are listed in STATE.md by name).

**Recorded, deliberately not fixed here:** the Anthropic v1.1.0 pack's `attention_estimate` basis counts Olah twice in one sentence (sweep #2, pack prose nit). It is pack *data*; correcting it belongs to the next pack refresh act (Wave 29's due-report is what will prompt that act), not to a docs wave.

**Acceptance (line-checkable):**
1. `team/pm-q11-cold-start.md` exists and contains an explicit answer to "whose objective does a default serve" plus the five hard edges above, each as a checkable statement.
2. README.md's first screen contains the pointer line; `git diff` on README for the wave is that line only.
3. Both design docs carry the superseded header as their first line after the title; bodies byte-identical below it.
4. The reconciliation result is written into STATE.md: either "reconciled" or the named discrepancies.

---

## Order and sizing

| Wave | Item | Role | Why this slot |
|---|---|---|---|
| **25 — NEXT** | Q7 sparsity + stop rule + floor validation | BE | Trust boundary for every future proposal; fully unblocked by F1; zero owner attention |
| 26 | Day-status owner surface (CLI) | BE | Makes wave-23's shipped record visible; Q5's actual acceptance |
| 27 | F8 fallback parity + Archive label + Archive quieting | UI | Daily-surface honesty; one file, three evidenced residuals |
| 28 | Bullet-digest gist/summary fallback | BE | The glance layer's last textless shape; a standing production source |
| 29 | Refresh-due + affiliation visibility + totals pin | BE | Gives pack freshness an owner; Q2/Q3's buildable halves |
| 30 | Q11 design + close-out hygiene | PM | Promotion-time question answered on paper; run ends reconciled |

Waves 25–29 are each sized to the run's established one-wave-one-agent pattern with tests included; none touches production, `main`, or any owner account. If hours run short, cut from the bottom (30, then 29) — 25 and 26 are the two whose absence leaves shipped systems either untrusted or unseen.
