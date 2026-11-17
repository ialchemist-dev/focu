# Focu 24h Run — PM Self-Iteration Sweep #3

- When: 2026-11-17 ~05:24 America/Denver. Run hard stop: 2026-11-18 01:45 (~20h20m remain).
- Scope of this sweep: the whole dev-main branch as it now stands — all four PM plans shipped (plan-1 PRD backlog + hunt questions, plan-2 sweep fixes F1–F5, plan-3 waves 25–30, plan-4 directions 1–3) — re-checked against the code in `~/workspace/focu-dev-checkout`. Full suite re-run firsthand during this sweep: **615 tests, OK**.
- Method: as sweep #2 — every claim cites a file and line or a command run during the sweep. Verified non-problems are recorded as closed, not omitted. This sweep edited no product code and pushed nothing.

---

## 1. The twelve hunt questions — final accounting

Eleven of twelve are closed. The three that remain open are open **by owner decision**, and this sweep verified each for hidden buildable residue:

**Q1 — Reader attention-tax walk. CLOSED.** Re-walked wave-21 (morning ritual 1 tap / 0 scrolls); findings N1–N3 shipped wave-22; the two bounded residuals (F8 button-swap, Archive done-vs-dismissed) closed wave-27; the bullet-digest glance hole closed wave-28. No open residual.

**Q2 — Pack staleness / re-verification. TOOLING CLOSED; CADENCE OWNER-GATED — verified nothing buildable hides inside.** Tooling: refresh-check (wave-14), refresh-due + affiliation surfaces (wave-29), and the due constants themselves validated against recorded rot history (plan-4 direction 2, wave-31 — no constant moved). What remains is exactly one decision: *who runs `focu pack refresh-due`, how often, starting when* — a production-scheduling assignment that only exists once promotion creates a production schedule to attach it to. The one code-shaped candidate (surfacing refresh-due inside day-status) would be an inert display without that schedule, and bolting a consumer onto an unowned cadence repeats the run's own lesson in reverse. Nothing to build.

**Q3 — Affiliation rot. OPEN BY DESIGN — reaffirmed for the third time, nothing buildable.** Automation rejected on evidence in sweep #2 and plan-3: a leaver's feed stays live, no fetcher meets the affiliation evidence bar. The visibility half shipped wave-29 (affiliation-as-of on every `focu pack show` source line; affiliation-staleness section in refresh-check, report-only). The residual is the human/agent refresh act itself, prompted by those surfaces at whatever cadence Q2's decision sets. Nothing to build.

**Q4 — Cadence vs. value. CLOSED** @ 4522e84b (warnings in previews and `pack show`; dominance/high-volume named, nothing auto-capped).

**Q5 — Empty-briefing failure surface. CLOSED.** Day-status record assembled per run (wave-23), owner-visible CLI (wave-26), and — since the live rehearsal's D2 — a failed run still gets its record with the failing stage named (wave-33; `focu/daily/pipeline.py:711` `_record_run_failure`, verified in tree this sweep).

**Q6 — Dedupe pressure. CLOSED.** Preview cross-locator warning @ b3c5a87f; one identity space across reader/registry/packs, re-verified composed in the promotion rehearsal (pack source_id == pipeline unit source_id == sparsity key).

**Q7 — Feedback sparsity floors. CLOSED** @ 4f101e4a. Floors validated by harness, zero values changed; sparsity block + stop rule shipped. The pruning pause class was validated by the same harness.

**Q8 — Learning vs. reporter-only boundary. CLOSED.** Boundary in code (demote-only inference, [0.5, 1.5] clamp at one consumption point, caps only lower, fail-closed record, frozen factors + `learn explain`); the F5 residuals (renewals, pause reviews, explicit 90-day step rule) closed @ 4cfc4742 + a7add740.

**Q9 — Import trust. CLOSED, and hardened past the original finding.** Fetch guard @ 0e06ef48; wave-33's D1 refinement verified in tree (`focu/packs.py:524` `_address_class`: 198.18.0.0/15 resolver answers proceed as *indeterminate*, literal private targets and private redirect hops still refused). `MAX_SOURCES_PER_PACK = 50` bound in place.

**Q10 — The one-full-read budget. CLOSED** @ 0e06ef48 (additive `original_url`; one quiet Original link in the article view; cards untouched).

**Q11 — Cold start. DESIGN + IMPLEMENTATION SHIPPED; production wiring is the promotion decision.** Design wave-30 (`team/q11-cold-start-design.md`); implementation wave-34 — verified in tree this sweep: `focu/daily/cli.py` `_installed_pack_lines` implements design §7.3 exactly (first briefing only, sourced from the install manifest, `--json` never carries it), and `tests/test_cold_start.py` asserts the §7 strings including the verbatim `insufficient attributed signal: 0 events in 30 days`, the installed-pack line's presence on day 1 and absence on day 2. One wording defect in the design itself is Finding S3-F5 below.

**Q12 — Podcast vs. reader consumption-state divergence. ANSWERED within the reader; residual OWNER-GATED — verified nothing buildable hides inside.** One store, `via` preserved through export + ingest. The residual (an MP3 played from a chat attachment writes nothing back to the reader's store) is a production delivery habit: no dev-main code can observe a chat playback, so there is nothing to build — the promotion decision either changes the delivery habit or accepts the divergence knowingly.

**Also accounted for, from plans 2–4 (not hunt questions):** sweep-2 findings F1–F5 all closed (attribution fan-out, adapter registration, fetch guard, Original door, anti-spiral machinery). Plan-3 waves 25–30 all closed. Plan-4 direction 1 closed twice over — fixture rehearsal (`tests/test_promotion_rehearsal.py`) and live rehearsal (`docs/dev-team/promotion-rehearsal-live.md`), the latter producing defects D1/D2 and frictions F1/F3, all fixed wave-33 and verified in tree this sweep; F2 (serializer byte-precision) accepted as documented behavior; **F4 (parser divergence) was never closed — it is Finding S3-F1 below.** Plan-4 direction 2 closed (constants validated, none moved). Plan-4 direction 3 closed (Q11 above). One designed-but-ungenerated class remains by the backlog's own note: `source_cap` proposals (schema-supported since Phase 1; "needs its own evidence design") — a future-wave item, not a defect.

---

## 2. Seams checked and found clean (no action)

- **Wave-33 fixes are in the code, not just in STATE.** `_address_class` with the indeterminate disposition (`focu/packs.py:485–550`); one shared version-token notion in `VERSION_REF` consumed by both figure extractor and checker (`focu/briefing.py:65–76` — the comment states the K3.1/GPT-5.2 rule explicitly); failed-run day-status (`focu/daily/pipeline.py:711`); the `registry_rewrite` disclosure present in *both* the install plan (`focu/packs.py:890`) and the update plan (`focu/packs.py:1843` — the wave-34 carried item landed).
- **Adapter registration.** `KNOWN_TYPES` (`focu/daily/config.py:10–11`) includes `instagram`, `rednote`, `facebook` alongside the original five — sweep-2's F2 fix is in the tree.
- **The live rehearsal's checklist is executable as written.** Its item 5 prescribes `focu daily run --dry-run` against a copy of the production config; the flag exists (`focu/daily/cli.py:37`, handled at `:103`). Its item 7 prescribes `focu pack list`; the command exists (`focu/packs.py:2481`) — though see the README nit in §4.
- **Design-doc status headers (close-out §3 follow-ups) are in place.** `docs/dev-team/backend-design.md` and `docs/dev-team/learning-design.md` both carry the superseded/status headers the close-out proposed verbatim. (That this hygiene was applied to those two docs and not to the run's newer point-in-time docs is Finding S3-F3.)
- **Cold-start never-fake prohibitions hold in the shipped code.** The wave-34 surface writes nothing: `_installed_pack_lines` reads the manifest and the runs table only; the preference record's only-writer invariant is untouched; no floor constant moved (the learn.py constants block is as wave-25 left it).

---

## 3. New findings, ranked by attention returned

### S3-F1 — Pack liveness and daily collection judge feeds by different parsers *and* different size caps; the divergence is real, and the right closure is a recorded divergence, not a shared parser (live-rehearsal F4, never closed)

The chain, verified in code this sweep:

- Pack liveness and refresh-check parse with `focu/source_collection.py:15` `parse_feed` — strict `xml.etree.ElementTree.fromstring`; malformed XML raises. Call sites: `focu/packs.py:718` (liveness) and `focu/packs.py:1476` (refresh probe).
- Daily collection parses with `feedparser` (`focu/daily/collectors.py:44–45`) — a lenient, error-recovering parser (with its own strictness quirk: `bozo` ⇒ hard `parse_error` at `:46`).
- The fetch caps also differ: the pack path's bounded fetch stops at 2 MB; the daily collector reads up to 8 MB (`focu/daily/collectors.py`, `payload = response.read(8 * 1024 * 1024 + 1)`).

Measured consequences, all already in the run's own records: Felix Rieseberg's feed (one unclosed CDATA) is **malformed/dead to liveness, healthy to collection** (15 items fetched in the live rehearsal). Joe Carlsmith's feed (~2.87 MB) and PostHog's (~3.29 MB) are **oversized to liveness, collectable by the daily pipeline**. So a curator reading refresh-check output can be told a source is rotten while the pipeline would have read it fine — and the reverse trust error is also possible in principle (a feed feedparser recovers that the strict parser accepts is not the issue; the issue is the verdict's wording claims more than the probe knows).

**Judgment: do NOT unify the parsers.** The asymmetry is defensible where it sits: the pack path processes *third-party* data at install/refresh time, where a strict, bounded, stdlib parser is the right trust posture (the same reasoning as F3's fetch guard); the daily collector reads sources the owner already chose, where recovery is worth more than strictness. What is *not* defensible is that the verdict doesn't say which judge produced it. The closure is a recorded divergence:

Acceptance (line-checkable): (1) liveness and refresh-check results for the `malformed` and `oversized` classes carry the producing discipline in the result (e.g. a `probe: "strict-xml/2mb"` field or equivalent wording) and a standing note that the daily collector's lenient parser and 8 MB read may still read such a feed — the verdict is "the probe cannot consume this", never "this feed is dead"; (2) refresh-check groups malformed/oversized verdicts separately from hard rot (404, unreachable) in its summary, so a curator's refresh decision isn't taxed by re-checking probe-limited sources as if they were gone; (3) tests pin both: a malformed fixture feed yields the qualified verdict, and a >2 MB well-formed fixture yields the qualified oversized verdict; (4) suite green. *Severity in attention terms: medium.* Every pack refresh from now on risks one wrong curator decision per probe-limited source — small per event, but it taxes exactly the judgment the Source Library exists to price honestly, and it compounds with each new pack.

### S3-F2 — Two pack consumers read one directory under different contracts; the legacy reader store's contract is held by writer discipline, not by any test

`focu/reader.py:208–214` (`ReaderStore.packs()`) raw-loads every `focu/source_packs/*.json` with no validation, and `ReaderStore.sources()` (reader.py, ~line 233) indexes `source['site_url']` unconditionally. But schema v1's canonical field is `homepage`; `site_url` is a *legacy alias* (schemas/source-pack.schema.json, description at line 219), kept in shipped packs only because v1 writers emit both. Verified this sweep: all four shipped packs carry `site_url` on every source (11/11, 12/12, 6/6, 18/18) — so the seam is latent, not live. It opens the moment a pack is written canonically (homepage only), which the schema explicitly blesses: `focu pack install` accepts it, and `focu reader serve` then KeyErrors. Symmetrically, one malformed JSON file in the directory makes `ReaderStore.packs()` raise outright, while `focu pack catalog` degrades the same file to an error entry. No test loads a shipped pack through ReaderStore (grep of tests/: `ReaderStore` is exercised only against fixtures).

Acceptance: (1) a pinning test round-trips every shipped pack through `ReaderStore` — `packs()` loads, `subscribe` at the pinned version, `sources()` returns every source; (2) `sources()` falls back to `homepage` when `site_url` is absent (one-line, matching the alias rule packs.py already implements); (3) suite green. *Severity: low now, promotion-shaped.* Zero cost while all packs are first-party and dual-emitted; the cost lands exactly when third-party packs arrive — the same moment Q9/F3 hardened the install path for. Cheap to close while it's still free.

### S3-F3 — Point-in-time docs go stale silently: the rehearsal docs already misdescribe the branch they rehearsed

The run learned this lesson once (sweep #2 flagged aging design docs; wave-30/close-out applied status headers — verified present in §2) and then produced two new unheadered point-in-time docs. `docs/dev-team/promotion-rehearsal-live.md`'s promotion checklist still labels item 1 (D1) and item 2 (D2) as *"still-unverified — owner decision"* and item 11 states Q11 "remains a design with acceptance criteria, to be implemented as the first promotion-gated feature." All three were overtaken within hours: D1 and D2 were decided *by fixing them* (wave-33), and Q11 was implemented (wave-34). The fixture rehearsal doc (`docs/dev-team/promotion-rehearsal.md`) likewise never mentions the live rehearsal or its defects. A promotion reader following the checklist as written would re-litigate two settled decisions and conclude a shipped feature doesn't exist — the checklist is the one document in the repo whose entire purpose is to be read at promotion time.

Acceptance (docs only): (1) both rehearsal docs gain a status header in the established form, the live one mapping checklist items 1, 2, and 11 to their wave-33/34 resolutions (with the still-open items — 3's comment-porting act, 4's merge-and-suite run, 5's production-config dry-run, 8's device listen-through, 9's cadence assignment — explicitly left standing); (2) README's pack-command enumeration gains `list` (it currently lists `catalog / show / validate / preview / install / update / refresh-check / uninstall / restore` — `focu/packs.py:2481` — and the rehearsal checklist itself tells the promoter to verify with `focu pack list`); (3) README's dev-section "Current team focus" paragraph is refreshed to include day-status, the rehearsals, and cold start, or is reworded to stop enumerating focus. *Severity: medium at promotion, zero before it.* This is the cheapest finding on the board and the one most precisely aimed at the next reader's attention.

### S3-F4 — Run bookkeeping drift, third occurrence: STATE and BACKLOG lag the branch again

Same failure class sweep #2 corrected and close-out §3 reconciled, recurring within hours of the last reconciliation:

- STATE.md's final log line still reads "CLAIMED (live wave-34)" — wave-34 has landed (615 tests; suite re-run green in this sweep).
- BACKLOG.md's plan-4 direction-3 line is still `[ ]`, and its Q11 seed line still says "implementation is deferred to promotion, per the design" — both stale against wave-34.
- BACKLOG.md's Q2 seed line still calls the refresh-due constants "themselves judgment-set and unvalidated — plan-4 candidate", although plan-4 direction 2 validated them and the direction-2 line *in the same file* is checked `[x]`.
- STATE.md line 8 still names the marketplace working name "**Focu Exchange**", against STATE.md line 16's own correction to Source Library (owner has still not ruled; the file should not contradict itself about what the working name is).

*Severity: low per line, structural in pattern.* Three occurrences in one run say the cause is not carelessness: reconciliation only happens when a PM sweep does it, because no wave's definition-of-done includes the state files it invalidates. Closure is procedural, and it is plan-5's last wave below: a final reconciliation pass as a *scheduled* wave before the hard stop, with the four lines above flipped as its first actions.

### S3-F5 — Q11 design §7.5 asserts a byte-exactness the system deliberately does not provide

Design criterion 5 (`team/q11-cold-start-design.md` §7) requires the implementation wave to assert that uninstalling the starter pack "returns `sources.yaml` to its pre-install bytes (the existing uninstall semantics, asserted on the cold-start path specifically)." The live rehearsal's F2 proved the existing semantics are byte-exact **only serializer-to-serializer**: a hand-written registry round-trips to identical *content* in normalized formatting, not identical bytes — and wave-33 shipped the `registry_rewrite` disclosure precisely because that normalization is real (comments and hand formatting are not preserved). Wave-34's walkthrough passes §7.5 because its starter registry is written canonically; production's registry is hand-maintained and comment-rich (rehearsal F1), so a promoter verifying cold start against §7.5 as written would chase a phantom failure on a working system. The design and the shipped disclosure currently contradict each other.

Acceptance (docs only): amend §7.5 to read content-exact always, byte-exact when the starting file was canonical — one sentence, folded into S3-F3's doc wave. *Severity: low*, but it is a trap planted in the acceptance criteria of the first promotion-gated feature, which is the worst place for one.

### Also recorded (not findings)

- **Anthropic pack basis prose (sweep #2's nit) is still uncorrected in v1.1.0** and has aged further: the `attention_estimate.basis` still counts Olah twice in one sentence ("Two enabled sources (Olah, Askell) are dormant… and two more (Olah again, Carlsmith) have feeds focu cannot currently consume"), and the second clause now understates Olah — his own readiness note records the feed as HTTP 404 (dead), not merely unconsumable. Fix at the next pack refresh (a curator act), not a wave; recorded here so the refresh sees it.
- **Dormant-source silence is honest but undifferentiated.** The live rehearsal's run 2 withheld 255 items as `expired`; pack sources whose newest posts predate retention contribute zero selected items indefinitely, and day-status reports that faithfully per source. A dormant-but-healthy people blog and a quietly broken one look alike in the daily surface for weeks — but both correctly demand no attention today, and refresh-check/refresh-due own the distinction at the pack layer. Recorded as a considered non-problem, not a gap.

---

## 4. Plan-5 — ranked waves for the remaining hours

Sized honestly: ~20 hours remain, and what is left is small. Four waves close everything buildable; the rest of the run's time belongs to the loop's continued operation, not to inventing scope.

1. **Wave 35 (BE, small) — S3-F1: record the parser/cap divergence in liveness and refresh-check verdicts.** Qualified verdicts for malformed/oversized, probe discipline named in the result, refresh summary separating probe-limited from hard rot, pinning tests. *Buildable now.*
2. **Wave 36 (BE, small) — S3-F2: pin the ReaderStore pack contract.** Shipped-pack round-trip test through `ReaderStore` + `homepage` fallback in `sources()`. *Buildable now.*
3. **Wave 37 (docs only) — S3-F3 + S3-F5: promotion-facing doc reconciliation.** Status headers + checklist addendum on both rehearsal docs; Q11 §7.5 amendment; README command list and team-focus refresh. *Buildable now.*
4. **Wave 38 (integrator, final, scheduled as the run's last wave before the 01:45 stop) — S3-F4: final STATE ↔ BACKLOG ↔ remote reconciliation**, flipping the four stale lines named there as its first actions, and leaving the run's books in a state where the final summary can be generated from them without a fourth reconciliation. *Buildable now — but only worth doing once, at the end.*

**Owner-gated (not waves; for the promotion decision):** Q2's refresh-due schedule assignment; Q3's refresh act at that cadence; Q12's production delivery habit; the Anthropic pack prose fix (next curator refresh); `source_cap` proposal evidence design (future wave, per the backlog's own note); adapter production wiring against real accounts; and promotion itself, whose checklist now stands at: rehearsal items 3 (port production registry comments before first install), 4 (land dev-main in the production checkout, full suite), 5 (`--dry-run` the production config — flag verified present), 8 (iPhone listen-through — the one check no rehearsal can do), and 9 (the Q2 cadence assignment).

---

## 5. STATE.md log line draft (for the integrator to append)

`- 2026-11-17 05:24 PM sweep #3 delivered (team/pm-sweep-3.md): 11 of 12 hunt questions closed; Q2/Q3/Q12 residuals verified owner-gated with no buildable residue. New findings S3-F1 (parser/cap divergence — recorded-divergence closure, not a shared parser), S3-F2 (ReaderStore pack contract unpinned), S3-F3 (rehearsal docs stale re waves 33/34), S3-F4 (STATE/BACKLOG drift, third occurrence), S3-F5 (Q11 §7.5 byte-exactness overpromise). Plan-5 = waves 35–38, wave 38 = final reconciliation as the run's last wave. Suite re-run firsthand in the sweep: 615 tests OK.`
