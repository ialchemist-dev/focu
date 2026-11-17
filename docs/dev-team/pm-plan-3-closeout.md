# PM Plan #3 — Close-Out Verdict (wave 30, 2026-11-17)

Plan-3 (waves 25–30) is complete as a plan: every wave shipped or is accounted for below. This doc records what the plan got right, what it got wrong, the final backlog↔STATE↔remote reconciliation, and the three directions worth handing to a plan-4 if the owner extends the run.

## 1. Scoreboard

| Wave | Item | Result |
|---|---|---|
| 25 | Q7 sparsity + stop rule + floor validation | Shipped @ `4f101e4a`. **No floor value changed** — the harness (noise / completions-only / concentrated-signal / stop-rule / exact-accounting fixtures) passed against the floors as designed. Suite 548 OK. |
| 26 | `focu daily day-status` CLI | Shipped @ `2dc57a3d`. Stored record printed as-is; `--json` byte-identical; missing record = one explicit line, exit 0. Suite 558 OK. |
| 27 | Reader honesty residuals (F8, Archive label, Archive quieting) | Shipped @ `496f13bb`. "Try device read-aloud" grep = 0; Archive cards label Finished / Not for me; export payload byte-identical (wave-5/6 tests unmodified). |
| 28 | Bullet-digest gist/summary fallback | Shipped @ `19cdd5c8`. Shape-gated (≥3 bullet blocks), first bullet only, URLs stripped; prose output byte-identical. |
| 29 | Pack freshness ownership (refresh-due, affiliation-as-of, totals pin) | **Implemented and tested in the dev checkout** (suite 574 OK per STATE 04:52; live shelf check 0 packs due) — but see §3: the push was not visible on the remote at final verification. |
| 30 | Q11 design + close-out hygiene | This wave: `team/q11-cold-start-design.md`, this verdict, BACKLOG.md reconciled (§3). |
| (interleaved) | Pruning `source_pause` proposals | Shipped by a loop chunk @ `a7d5c0ae` concurrently with the plan's writing; the sequencing conflict was resolved by wave 25's harness validating the class after the fact (STATE 04:36). Backlog line now closed with the resolution recorded. |

## 2. Premises: what held, what did not

**Held**

1. **"The floors are probably fine; the defect is that silence is illegible."** Wave 25 changed zero floor values. What was missing was accounting (sparsity block) and a named stop rule — exactly the plan's diagnosis. The trust boundary was legibility, not calibration.
2. **"Shipped-but-invisible work is the cheapest attention available."** True twice over: the day-status record existed for a full wave with zero consumers (wave 26 was pure surface, no construction changes), and the Q1 re-walk behind the plan found the morning ritual already at 1 tap / 0 scrolls — the remaining cost was honesty defects (N1–N3, F8), not missing features.
3. **Sequencing: attribution (F1) before floor validation (Q7).** Correct and load-bearing. The wave-25 harness fixtures are shaped like the post-F1 world (per-unit observations, compilation fan-out); run before F1, the same harness would have validated floors against signal that could never arrive.
4. **Cut-from-the-bottom sizing.** Not needed — all six waves landed inside the run with hours to spare — but the ordering meant the two trust-critical waves (25, 26) were never at risk.

**Did not hold**

1. **"Gate new proposal classes on floor validation."** The plan's strongest sequencing claim was procedurally violated within minutes of being written: the loop chunk shipped the pruning pause class (`a7d5c0ae`) from a backlog read taken before plan-3 existed. It turned out substantively fine — the pause class carries its *own* stricter floors (≥20 delivered / ≥10 distinct days / zero completions / zero useful) over a different evidence type (delivery accounting, not feedback marks), and wave 25's harness validated it after the fact. The premise as stated was too broad: the gate is real for classes that *reuse* the statistics floors, and unnecessary for classes with independent evidence and independent floors. A plan-4 should state gates per evidence type, not per subsystem.
2. **"One wave, one agent, disjoint files" as the concurrency model.** Twice this run (F5, pruning) a live wave and a loop chunk implemented overlapping work concurrently in the shared checkout. Both reconciliations were clean and both produced at least one genuinely additive delta — but the CLAIMED-marker convention that now governs this was a mid-run patch (STATE 04:09), not a plan premise. The plan assumed a coordination discipline the run had to invent.
3. **The plan treated wave 29's constants as settled policy.** `REFRESH_DUE_PACK_DAYS = 14` / `REFRESH_DUE_SOURCE_DAYS = 30` / `AFFILIATION_STALE_DAYS = 90` are judgment-set and unvalidated — precisely the condition wave 25 was created to fix for the learn floors. The plan noticed this class of risk in one subsystem and reproduced it in another. (The recorded `STALE_DAYS = 180` non-change, by contrast, was a deliberate, evidence-cited decision and stands.)

## 3. Reconciliation result (BACKLOG ↔ STATE ↔ remote dev-main)

Verified 2026-11-17 ~04:55 against the GitHub API (repo id 1262367522, branch dev-main) and the dev checkout. BACKLOG.md has been corrected in this wave; the discrepancies found were:

1. **Plan-3 wave lines 25–28 were still unchecked** although STATE records them integrated and the remote confirms commits `4f101e4a`, `2dc57a3d`, `496f13bb`, `19cdd5c8`. → Fixed: all four marked shipped with SHAs.
2. **Wave 29 is claimed integrated in STATE (04:52, 574 tests OK) but is NOT on the remote.** Remote dev-main HEAD at verification = `19cdd5c8` (wave 28). The wave-29 code and tests exist in the dev checkout (`focu/packs.py` refresh-due, `tests/test_pack_freshness.py`). → Backlog marks wave 29 `[~]` with the discrepancy named; **owner: integrator — confirm or land the push, then flip the line to [x] with its SHA.** (This doc does not push.)
3. **The pruning line's conflict flag was stale.** STATE 04:36 records the resolution (harness-validated, `a7d5c0ae` accepted as-is). → Backlog line closed with the resolution text.
4. **Seed lines Q5 and Q7 still showed open residuals** that waves 26 and 25 respectively closed. → Both marked closed with commits. Q2 and Q3 lines updated: their buildable halves shipped in wave 29; what remains is named with its owner (promotion decision for the refresh-due schedule; the human/agent refresh act for affiliation). Q11's line now points at the delivered design, owner = promotion decision.
5. **Q1's two bounded residuals** (F8, Archive distinction) were closed by wave 27 but still described as open in two backlog places. → Both updated; Q1 has no open residual after wave 28.

**Named follow-ups from plan-3's wave-30 scope that this docs wave did not perform** (they are repo edits for the integrator's next push; exact texts proposed so the check stays line-level):

- README.md cold-read pointer — insert as the second line of README.md, after the version line:
  `> Development note: active development happens on the dev-main branch — see "Development — the dev-main branch and the multi-agent team" below; main carries the last integrated release.`
- `docs/dev-team/backend-design.md` — first line after the title:
  `> Superseded in part: the pack CLI sketched here shipped as the focu pack surface (validate/preview/install/uninstall/restore/list/catalog/show/update/refresh-check/refresh-due); treat command sketches below as design history.`
- `docs/dev-team/learning-design.md` — first line after the title:
  `> Status: Phases 1–3 shipped on dev-main during the 2026-11-17 run, plus renewal/pause-review proposals, the anti-spiral step rule, and sparsity accounting; "(next run)" labels below are history.`

Everything else in BACKLOG.md was verified line-by-line against STATE's integration log and the remote commit list: pack lines (09c67c0b, d6b3d0be, e7324580, 79550ec8, 8eaaffa0), adapter lines (85425098, 7b3ba2e7, 1a863a3c, a69eb825, e98b023f), learning lines (c7bbfaa2, 8f0194a6, 043518a6, 4cfc4742 + a7add740), sweep lines (8fa8412a, 0e06ef48, c6fa01d1), Q4/Q6/Q9 pins (4522e84b, b3c5a87f, 5186ca91) — all present on the remote with matching subjects. **Result: reconciled, with the single named exception of wave 29's unlanded push (item 2).**

## 4. Three directions for a plan-4

1. **A promotion rehearsal, end to end, on a scratch runtime.** Every wave this run tested its own slice; nothing has ever run the composed dev-main system — publisher from dev-main against real delivery folders, the day-status record inside a real job-shaped run, a real reading-summary export through `focu learn ingest` into proposals — as one exercise. Evidence: ~35 commits sit between dev-main and production, and every remaining open item (Q11 implementation, Q2's schedule, Q12's production residual, adapter wiring) is gated on the same promotion decision. A rehearsal converts that decision from a leap into a checklist, and it is the only way to find integration defects while they are still free.
2. **Validate the pack-freshness constants the way wave 25 validated the learn floors.** `REFRESH_DUE_PACK_DAYS = 14`, `REFRESH_DUE_SOURCE_DAYS = 30`, `AFFILIATION_STALE_DAYS = 90` are unvalidated judgment calls, and the observed rot rate argues the question is real: within ~3 weeks of the Anthropic pack's v1.0.0 verification, a refresh found three distinct rot modes (a malformed feed, a 404, a feed grown past the 2 MB fetch cap). Build the harness from recorded rot histories: packs/fixtures with known rot should trip `refresh-due`; freshly verified packs should not; then keep or move the constants on fixture evidence, under the same rule as the learn floors.
3. **Implement the Q11 cold start as the first promotion-gated feature.** It is the only hunt question that ends this run with a design and no code, and it is precisely the surface a second user — or this owner on a fresh registry — meets first. The evidence for its shape is now quantitative: the floors' math (a people-pack user's first statistics proposal is months away by `MIN_DELIVERED` alone) means an undesigned cold start reads as a broken product, while the designed one (one stated pack, priced at preview; sparsity as an instrument readout; first-proposal bounds stated in advance) costs one wave against the acceptance criteria in `team/q11-cold-start-design.md` §7.
