# Focu Learning Loop — Design (Project Manager, wave 6)

> Status: Phases 1–3 shipped on dev-main during the 2026-11-17 run, plus renewal/pause-review proposals, the anti-spiral step rule, and sparsity accounting; "(next run)" labels below are history.

- Scope: the owner's point 8 — "Focu must get smarter; the more the user uses it, the more it understands the user" — under the PRD's hard constraint: **no silent learning** (PRD §1, objective 5). This doc designs P2-1, P2-2, and P2-3 as one system.
- Governing document: `attention-sovereignty.md`. The agent applies priorities the user defined; it reduces the cost of *the user deciding*, it does not decide for them. Where this doc and the article disagree, the article wins.
- Grounding: reader code and pipeline code as of dev-main, 2026-11-17. Tool numbers measured live via the GitHub API on 2026-11-17.

---

## 0. The core decision

Learning in Focu is a **proposal pipeline over an append-only evidence ledger**, not a model that updates itself. The system computes statistics from the user's own acts, drafts a small number of fully-evidenced proposals, and applies **nothing** until the owner accepts; the only thing that may ever influence selection is a versioned, human-readable preference record the owner owns (`references/learned-preferences.md`), written exclusively by owner acts (stated directly, or accepted from a proposal). Everything else in this document is machinery to keep that sentence true.

Two precedents already in the codebase define the shape:

- `focu/feedback.py` is an explicit feedback ledger whose own docstring reads *"learning signals without autonomous policy changes."* It exists, is tested, and is wired to nothing. This design is mostly the wiring it was built for.
- `references/audience-profile.md` is a versioned, human-readable profile whose loader (`focu/audience.py`) *rejects* any domain whose provenance is not `owner-stated`, and whose header states: *"Never silently infer expertise from reading behavior."* The preference record copies this pattern exactly, including the fail-closed loader.

---

## 1. Signal inventory

### 1.1 What exists today (verified in code, not assumed)

**Reader consumption store** — `localStorage` key `focu:content-consumption:v1` in `experiments/muse-artifact-reader/index.html`. One entry per `content_id`:

| Field | Written by | Meaning |
|---|---|---|
| `status: "consumed"`, `via: "audio"` | player `ended` handler, when listened coverage ≥ 80% of duration | The user actually listened to (most of) the item |
| `status: "consumed"`, `via: "article"` | `readingTick()`: bottom of article seen **and** dwell ≥ a length-scaled minimum (7s / 13s / 20s) | The user read to the end |
| `status: "consumed"`, `via: "device_voice"` | device narration runs to completion | The user listened via read-aloud |
| `status: "consumed"`, `via: "manual"` | Archive button (`manualArchive` → `markDone(id,'manual')`) | **Ambiguous** — see §1.3 |
| `updated_at` | every `markDone` | When the act happened |
| `audio_pos` (seconds) | playback save points (wave-2 resume) | Partial listen position on an *unconsumed* item |
| `article_pos` (px) | scroll save points (wave-2 resume) | Partial read position on an *unconsumed* item |
| *(entry deleted)* | Restore (`markUnread`) | The user reversed a completion |

**Pipeline records** (SQLite, `focu/daily/store.py`): every selection is frozen per episode (`episode_items` carries the unit snapshot incl. `score` and `gate_priority`); the `coverage` table records what has ever been used; candidates that were scored but not selected are reconstructible. The pipeline knows exactly what it *offered*, per source, per day.

**Feedback ledger** (`focu/feedback.py`, SQLite `feedback_events`): kinds `useful / not_useful / incorrect / too_long / missed_important / other`, targets `episode / evidence_pack / observation / research_intent`, free-text note ≤ 4000 chars, idempotent by event id. Recordable today via `python -m focu.feedback record` — i.e. by the agent on the owner's word in chat. **The reader has no like/dislike/save UI at all** (verified: no such controls exist in `index.html`); the only in-reader acts are consume, archive, restore.

### 1.2 Signals the system may legitimately use

Each is an *act* by the user, or a fact about what the system itself did. Nothing passive, nothing inferred about the person.

1. **Completions, by via.** `audio` / `article` / `device_voice` completions are genuine consumption. Aggregated per source over ≥ 30 days, they are the denominator-and-numerator of a completion rate. A completion is evidence the item was worth its cost *that day* — nothing more (see §1.3).
2. **Explicit feedback events.** The strongest signal class, because the user said it on purpose. `not_useful`, `too_long`, `incorrect` against an episode or observation are direct evidence about its source/topic; `useful` is the only signal that may ever support a *promotion* proposal (§3.3, rule 2).
3. **Owner statements in chat.** "Stop bringing me X", "I always read Y" — recorded as `owner-stated` preference entries directly (no proposal round-trip; the statement *is* the decision). This is first-class, not a fallback: the owner works through his agent, and a loop that only counts reader taps would be blind to his primary channel (PRD §4 Q7).
4. **Restore acts.** Reversing a completion says the item still matters or the archive was accidental. A source whose items get restored is mis-served by demotion proposals; restores suppress negative proposals for that source in the window.
5. **Started-but-abandoned, in aggregate only.** An unconsumed item with `audio_pos` / `article_pos` > 0 was begun and left. One instance means nothing (interruptions exist); a per-source pattern over ≥ 10 items is weak negative evidence, usable only as corroboration alongside (1), never alone.
6. **Selection history (system-side).** What was offered per source per day, at what score, under what cap. This is the denominator that makes completion rates honest, and it detects a different problem class: a source that is *registered but never selected* (score starvation, budget crowding) — a proposal to fix the registry, not a judgment of the user's taste.

### 1.3 What the system must never infer

Hard list. A design or implementation that needs one of these is rejected at review.

- **Preference from scroll depth or dwell time.** The product contract (PRD P2-1) is explicit: scroll and dwell are *not* feedback. The reader uses dwell internally, on-device, only to decide that a read *completed*; the raw values never leave the device and never become evidence. `article_pos` may be used only as the binary "started" fact in §1.2(5), never as a depth percentage.
- **Endorsement from completion.** Finishing an item ≠ agreeing with it, liking it, or wanting more like it. Completion supports demote-side statistics (absence of completion) and nothing on the promote side.
- **Rejection from a manual archive.** In the current reader, Archive *is* the completion button (`via: "manual"` conflates "done", "read it elsewhere", "not now", and "not for me"). Until Phase 2 adds a distinct negative act, `manual` events are excluded from both positive and negative evidence. Treating them as rejections would train the system on UI ambiguity.
- **Anything from absence at small n.** A source with 3 unconsumed items has not been rejected; it has been sampled 3 times. §5 sets minimum-evidence floors; below them the engine's correct output is *no proposal*, and an empty report is a success state, not a gap.
- **Expertise, knowledge, or identity attributes from behavior.** Forbidden by the audience profile's own change discipline. What the user *knows* is owner-stated only, forever; the learning loop concerns what the system should *fetch and rank*, never who the user is.
- **Topic interest from a single item.** One completion of one long article is an event, not a taste. Topic-level proposals require the same evidence floors as source-level ones, aggregated across sources.
- **Anything about anyone else.** Signals describe one owner's acts on his own registry. No cross-user anything exists or may be designed in.

### 1.4 The transport gap (named, not waved at)

The consumption store lives in the reader's browser storage on the owner's phone; the pipeline runs on the VM. **Today there is no path between them** — the pipeline cannot see a single completion. Any design that quietly assumes this away is fiction. This design's answer:

- Phase 1 needs no transport: it runs on the feedback ledger and pipeline-side selection history, both already on the VM, plus owner statements the agent records.
- Phase 2 builds the transport as an **explicit, user-initiated export**: a reader action ("Share reading summary") that emits exactly the consumption store's contents as JSON for the owner to hand to his agent, which ingests it (`focu learn ingest`, idempotent by content_id + updated_at). The user sees precisely what leaves the device, because he carries it. That is a sovereignty property, not a workaround: no background sync of behavior data, ever. (The existing Drive data-sync machinery could automate this later; automating it is an owner decision, not a default.)

---

## 2. Proposal UX

### 2.1 Where proposals live

- **In chat, delivered by the agent** — a short "Focu learning" block appended to an existing delivery the owner already reads (or standalone when he asks), generated by `focu learn proposals`. Chat is where the owner already accepts/rejects/edits everything else in this system; proposals go where decisions already happen.
- **Never in the reader's Today view.** The reader is a display surface for judging *content*. Administering the user model inside it would rebuild exactly the control surface the philosophy removes. (A read-only "what Focu has learned" view may later hang off the Archive view; it is not required by any phase below and adds no button to Today.)
- **Always inspectable on demand:** `focu learn show` prints the full preference record and all pending proposals with their evidence. The record is a markdown file in the repo; opening it directly is equally supported.

### 2.2 The attention budget for proposals themselves

Proposals cost the very resource the system exists to return, so they are budgeted like content — on the article's own ladder:

- **At most one batch per week. At most 3 proposals per batch.** If the engine has more, it ranks by expected attention returned and holds the rest; held proposals are not lost, they re-compete next week.
- **Each proposal must be judgeable in ≤ 10 seconds**: one line stating the change, one line of evidence, three actions. If the evidence cannot be stated in one honest line, the proposal is not ready and is not sent.
- **Global budget: ≤ 30 seconds of owner attention per week** for all learning combined. The engine tracks what it has asked; a week that spent its budget sends nothing further, however good the next proposal looks.

### 2.3 Proposal shape and semantics

Every proposal carries: an id (`prop-YYYYMMDD-N`), the exact change it would make, the evidence line (with window and n), the expected attention returned (est., labelled), and an expiry (proposals die at the next batch; a dead proposal is not silently renewed — its evidence must re-qualify).

- **Accept** — applies exactly the stated change: one entry written to the preference record (provenance `owner-accepted`, proposal id cited), one changelog line. Nothing adjacent is changed; accepting a pause for source A says nothing about source B.
- **Edit** — the owner adjusts the parameter before accepting ("don't pause it, cap it at 1/day"). The *edited* change is what is recorded; provenance notes it was edited. Edit is a first-class path, not a negotiation: the agent restates the edited change once, the owner's yes applies it.
- **Dismiss** — no change, and the dismissal is recorded with a scope the owner picks by wording: *"not now"* (this proposal class + target snoozed **60 days** for source pauses/caps, **30 days** for weight changes) or *"never for this"* (that target is exempt from that proposal class until the owner re-opens it). Snoozes are data the engine must honor; re-proposing inside a snooze is a bug, tested as such.
- **Ignore** — no reply is treated as dismiss-with-snooze when the batch is superseded. **Silence never applies anything.** There is no "expires into acceptance," no default-yes, no pre-ticked box, anywhere in this design.

### 2.4 Inspecting and deleting what was learned

- `focu learn show` (or opening `references/learned-preferences.md`) lists every active entry: statement, kind, target, value, provenance, evidence, dates, review date. There is no other store; if it isn't in the record, it isn't learned.
- **Delete** = remove the entry, by chat instruction or by editing the file. The file is the source of truth, so a hand edit is legal; the loader detects external edits via the record's version/hash (the `audience.py` pattern) and the deletion takes effect from the next run, changelogged like any other change.
- **"Forget everything learned"** = one command/instruction that removes all `owner-accepted` entries at once. `owner-stated` entries are the owner's own declared profile and are removed only by his explicit per-entry word — the system does not let a bulk forget erase what he deliberately stated.
- Deleting an entry that is currently affecting selection is announced in the next delivery ("X is back at its registry priority — you removed the learned cap"), once, in one line. The user should never have to wonder whether a deletion took.

---

## 3. Data model

### 3.1 The preference record

`references/learned-preferences.md` — sibling to `audience-profile.md`, same pattern: human-readable markdown, a YAML block as the machine-readable source of truth, a version header, a dated changelog, and a loader in the `focu/audience.py` style that **fails closed**: unknown provenance, malformed entries, or a hash mismatch with unparseable edits → the record is treated as *empty* (no learned influence) and the failure is surfaced. Learned influence that cannot be validated does not run.

Entry fields:

```yaml
- id: lp-007
  kind: source_cap            # source_pause | source_cap | source_weight | topic_weight | standing_note
  target: src_9f3…            # source_id from the registry (stable_id), or a topic tag
  value: 1                    # cap per day | multiplier | note text for standing_note
  statement: "Cap LinkedIn Feed at 1 unit/day — most days its digest goes unfinished."
  provenance: owner-accepted  # owner-stated | owner-accepted  (loader rejects anything else)
  evidence: "prop-20261124-2 · 4 of 19 units completed, 30d window"
  created_at: 2026-11-24
  review_after: 2027-02-24    # see §3.4
  status: active              # active | superseded (history is kept, influence is not)
```

`standing_note` entries capture owner statements that aren't numeric ("prefer primary sources on geothermal policy") — they are shown to the agent at briefing time as context, and carry **no** scoring effect; giving prose a hidden numeric effect is how silent learning starts.

### 3.2 The proposal store

Proposals are working state, not part of the record: a `proposals` table (or JSONL beside the feedback ledger in the same SQLite DB) with `id, kind, target, proposed_value, evidence_json, state (proposed | accepted | edited-accepted | dismissed | expired), snooze_until, created_at, decided_at`. Only an `accepted` / `edited-accepted` proposal may write to the preference record, and the write cites the proposal id. The audit chain is therefore: evidence → proposal → owner decision → record entry → frozen selection factor (§3.3), every link inspectable.

### 3.3 How learning feeds selection — bounded, or not at all

Selection today (`focu/daily/store.py: select()`): `score = priority / (1 + age_days)` from per-source subscription settings, sorted with gate rank, subject to a per-source daily cap and a per-channel word budget; selections are frozen once per run. The decision gate already establishes the governing precedent: it *"only reorders revision-matched candidates; it never deletes, suppresses or claims coverage for a source."* Learned influence is held to the same standard, in three hard rules:

1. **Explicit beats learned, always.** A learned entry can never enable a disabled source, add a source, change a channel, or override an explicit registry value — it modulates within a band around it. `source_weight` multipliers are clamped to **[0.5, 1.5]** and applied *after* the registry priority. `source_cap` may only lower a cap, never raise it above the registry value. `source_pause` exists only as an accepted entry kind — pausing is an owner's act recorded in the record, never an inference the engine applies.
2. **Inference may demote; only the owner's own marks may promote.** Statistics-derived proposals (completion rates, abandonment patterns) may propose only multipliers ≤ 1.0, caps, or pauses. A promotion proposal (> 1.0) requires explicit positive evidence: `useful` feedback events from the owner. Completion counts can never justify promotion — finishing is not endorsing (§1.3), and promotion-from-engagement is precisely the platform dynamic this system exists to refuse. This is the hard boundary PRD §4 Q8 asks for: the user model can make the user's own registry *quieter*; it cannot make it *louder* on its own initiative.
3. **Every influence is frozen and explainable.** When `select()` applies a learned factor, the frozen episode item gains `learned_factors: [{preference_id, kind, value}]`. `focu learn explain <content_id>` answers "why is this here, ranked here?" from the frozen record: registry priority, age, gate decision, and each learned factor by id — or the sentence "no learned preferences affected this item." An influence that cannot be explained from the frozen record may not be applied.

With an empty (or invalid) preference record, selection output is **identical to today** — this is a regression test, not an aspiration (§5, Phase 3).

### 3.4 Staleness is handled by review, not by silent decay

Entries do not quietly fade (a silent multiplier drift is silent learning with extra steps). Each entry carries `review_after` (default 90 days for weights/caps; pauses carry one too). Past that date the engine may include a *renewal proposal* in a weekly batch — "the cap on X is 90 days old; its completion rate since is 61%. Keep, adjust, or remove?" — which costs budget like any proposal and changes nothing by itself. The record's `show` output always prints entry ages, so staleness is visible even if no proposal is sent.

---

## 4. Tool evaluation

Measured live via the GitHub API on **2026-11-17** (stars, license, last push):

| Tool | Stars | License | Last push | What it actually is |
|---|---|---|---|---|
| mem0 (`mem0ai/mem0`) | 69,094 | Apache-2.0 | 2026-11-17 | Memory layer for agents: LLM-extracted facts into a vector store, semantic recall over conversation history |
| cognee (`topoteretes/cognee`) | 33,361 | Apache-2.0 | 2026-11-17 | AI memory platform: ingest → knowledge-graph construction pipelines |
| Graphiti (`getzep/graphiti`) | 32,873 | Apache-2.0 | 2026-11-15 | Temporal knowledge graphs for agents; requires Neo4j/FalkorDB |
| Khoj (`khoj-ai/khoj`) | 38,157 | AGPL-3.0 | 2026-08-02 | A self-hosted "second brain" *application*, not a component |
| Letta (`letta-ai/letta`) | 25,467 | Apache-2.0 | 2026-10-18 | A stateful-agent *platform/runtime* (MemGPT lineage) with its own server |
| Basic Memory (`basicmachines-co/basic-memory`) | 4,610 | AGPL-3.0 | 2026-11-16 | Conversation memory as plain markdown files (MCP) |
| LangMem (`langchain-ai/langmem`) | 1,773 | MIT | 2026-11-16 | Memory SDK coupled to LangChain/LangGraph |

Judged against Focu's actual scale and constraints — **one user, ~10–25 items/day, a preference state that fits in one markdown file, local-first, no new credentials (PRD non-goal), every learned item inspectable and deletable by the owner**:

- **mem0** is the strongest of the set and still a mismatch. Its core loop (LLM extraction + embeddings) wants an LLM/embedder key — a new credential this run forbids — and stores memory as vector records retrievable by API, not as a file the owner reads and edits. It solves *recall over thousands of conversational facts*; Focu needs ~tens of accountable preference rows.
- **Graphiti / cognee** bring a graph database and LLM extraction pipelines to store what is, at the limit, "cap this source at 1/day, because the owner said yes on Nov 24." The operational weight exceeds the entire daily pipeline's. Rejected on fit, not quality.
- **Letta** is an agent runtime; adopting it means re-platforming Focu's agent loop, not adding memory. Out of scope by construction.
- **Khoj** is an application, AGPL, and the stalest of the set (no push since 2026-08-02). Not a component.
- **LangMem** is young (1,773★) and LangChain-coupled; Focu has no LangChain anywhere. Rejected.
- **Basic Memory** deserves an explicit honorable mention: markdown files as the memory store is exactly the right instinct, and its existence validates this design's file-first choice. But it is an MCP conversation-notes tool (AGPL) — it stores *what was discussed*, not *preference decisions with provenance and evidence*, and adopting it would add a dependency to get a worse fit than the pattern Focu already has in `audience-profile.md`.

**Verdict, plainly: a plain, well-designed local store beats every framework here, and it isn't close.** The frameworks optimize for *recall* — finding relevant memories in a large unstructured pile. Focu's problem is *accountability* — a handful of preference entries, each carrying its evidence, its provenance, and the owner's decision, in a file he can read, diff, and delete. Focu already owns the two hard parts: an explicit feedback ledger built "without autonomous policy changes" (`focu/feedback.py`) and a provenance-enforcing versioned profile (`focu/audience.py`). The learning loop is wiring and restraint, not infrastructure. If Focu ever becomes multi-user or gains genuine conversational memory, mem0 is the first candidate to re-evaluate (largest community, Apache-2.0, actively maintained).

---

## 5. Phased implementation plan

Run window remaining at design time: ~23 hours, most of it committed to P0/P1. Phases 1–2 are sized to fit this run after P1; Phase 3 is first-in-line next run unless P1 finishes early; Phase 4 is explicitly later. Acceptance criteria are line-checkable, per the PRD's Definition of Done; every phase also inherits it (tests green ≥ baseline, dev-main commit, README updated).

### Phase 1 — The record, the ledger wiring, and proposals with no teeth (this run, ~2 cycles) — Owner: BE (PM owns the UX contract in §2)

Build: `references/learned-preferences.md` (valid, empty of learned entries, with the standing-note the owner has already effectively stated if he confirms it); a loader in the `audience.py` style (provenance enforced, fail-closed); `focu/learn.py` + CLI (`show`, `proposals`, `accept`, `dismiss`, `explain` stub) computing per-source statistics from the **feedback ledger and selection history only** (both on-VM today); the proposals store (§3.2) with snooze semantics. **No selection code is touched in this phase.**

Acceptance:
- Loader rejects an entry with provenance other than `owner-stated` / `owner-accepted`, and a corrupted record yields *zero* learned influence plus a visible error — tested.
- Fixture history (seeded feedback + selection rows) produces exactly the expected proposals, each with a one-line evidence string naming window and n; **empty history produces an empty proposal list** — tested.
- A dismissed proposal does not reappear before its snooze date, and a "never for this" dismissal permanently exempts that target+class — tested by advancing the clock in fixtures.
- Accepting a proposal writes exactly one record entry citing the proposal id, and bumps the record version with a changelog line — tested.
- No code path exists from statistics to `sources.yaml`, subscription settings, or selection: verified by grep-level review in the cycle log (the only writer of the record is the accept path).

### Phase 2 — Transport and an unambiguous negative act (this run if Phase 1 lands clean, else next; ~2 cycles) — Owner: UI (reader) + BE (ingest)

Build: reader gains two explicit per-item acts — **Useful** and **Not for me** — stored as feedback events in the local store (kinds mapped to the ledger's `useful` / `not_useful`); a **Share reading summary** action exporting the consumption store as JSON; `focu learn ingest` on the pipeline side (idempotent, validates the export contains store fields and nothing else); completion-rate statistics join the proposal engine once real consumption data exists.

Acceptance:
- The export contains exactly the consumption store's fields (content_id, status, via, updated_at, positions) — a test diffs the key set; nothing else leaves the device.
- Ingesting the same export twice changes no statistic (idempotency test); a hand-corrupted export is rejected whole, not partially applied.
- `via: "manual"` remains excluded from evidence even after ingest (§1.3); `Not for me` events are the negative signal and are counted as such — tested with a fixture mixing both.
- Reader Today view gains no persistent chrome: the two acts live on the item view, the share action in the Archive view — verified against the UI audit's control-surface rules.
- First real-data proposal batch is generated and shown to the owner in chat; whether he accepts any is his business — the phase is done when the batch is *correct*, not when it is accepted.

### Phase 3 — Bounded influence on selection, with the explain view (next run; ~2 cycles) — Owner: BE

Build: `select()` consults the preference record under §3.3's three rules; frozen items gain `learned_factors`; `focu learn explain <content_id>` ships for real; renewal proposals (§3.4) join the weekly batch.

Acceptance:
- **Empty-record regression:** with an empty preference record, selection output for a fixture registry is byte-identical to the pre-change engine — tested in CI, not eyeballed.
- Clamp tests: a `source_weight` of 3.0 in a hand-edited record is applied as 1.5 and the clamp is visible in `explain`; a learned cap above the registry cap is applied as the registry cap.
- A statistics-derived proposal for a multiplier > 1.0 cannot be generated (engine-level test); a promotion proposal exists in fixtures only where `useful` events support it.
- `explain` on a fixture item names registry priority, age component, gate decision, and each learned factor by preference id — or states that none applied.
- An accepted `source_pause` removes the source from selection *and* the next briefing's status line says so in one line ("Paused by you on Nov 24: X") — removal is never silent even when it is authorized.

### Phase 4 — Proposal quality loop (later; design only here) — Owner: PM

Track per-proposal-class precision (accepted / decided) over rolling 90 days. A class below 1-in-3 precision for two consecutive windows stops being generated until its evidence rule is redesigned — the system learns *what not to ask*, which is the one form of meta-learning this design permits without an owner decision, because it only ever reduces what the system asks of him. Acceptance: the weekly batch header reports its own trailing precision in one line ("last 12 proposals: 7 accepted, 3 dismissed, 2 ignored"), so the loop's manners are themselves inspectable.

---

## 6. Failure modes and designed countermeasures

1. **The narrowing spiral.** Demote a source → it is selected less → fewer completions → stronger demotion evidence → pause → the registry quietly shrinks to what already worked. *Countermeasures:* demote-only inference with a 0.5× floor (§3.3 rule 2); a source may be demoted by at most one accepted step per 90 days; learning reorders and caps *within* the owner's registry and can never shrink it silently — every pause is an accepted, announced, one-action-reversible act (§3.3 rule 1, Phase 3 acceptance); and a standing quarterly proposal asks about long-paused sources ("paused 90+ days: restore, keep, or remove?") so pauses cannot become invisible permanent deletions.
2. **Training on absence and noise.** A podcast-first owner generates few reader events; a vacation week looks exactly like disinterest. *Countermeasures:* minimum evidence floors (no source proposal below **10 delivered items and 30 days** in-window; no topic proposal below the same across sources); owner statements in chat are first-class evidence (§1.2(3)), so the loop never depends on reader taps; below the floors the engine emits nothing and says why ("insufficient data: 6 of 9 sources below evidence floor") — an honest empty report, per PRD §4 Q7.
3. **Proposal fatigue.** A system that asks weekly forever becomes the notification it replaced. *Countermeasures:* the §2.2 budget (≤ 3 proposals, ≤ 30 s, weekly at most); snooze-on-dismiss with owner-chosen scope; ignore = dismiss; Phase 4 retires low-precision proposal classes automatically. The loop's success metric includes *questions not asked*.
4. **Stale preferences ruling forever.** A cap accepted in November governs March's different life. *Countermeasures:* `review_after` on every entry (§3.4); renewal proposals that show the *current* evidence ("completion rate since the cap: 61%") so renewal is a fresh judgment, not a rubber stamp; ages printed in `show`. Nothing decays silently — but nothing is immortal without being re-seen either.
5. **Ambiguous-signal contamination.** The reader's Archive button conflates completion and dismissal (§1.3). *Countermeasures:* `via: "manual"` is excluded from all evidence until Phase 2's **Not for me** act exists; Phase 2's acceptance includes a mixed-fixture test proving the two are counted differently. Until then, the engine works with less data rather than with wrong data.
6. **Misattribution weeks.** Illness, travel, a deadline — behavior dips for reasons that are not taste. *Countermeasures:* 30-day minimum windows (a bad week is ≤ ¼ of any evidence base); every proposal states its window so the owner can discount it himself ("that was the conference week" → dismiss, "not now"); restores (§1.2(4)) actively veto negative proposals for a source in-window.
7. **The user model becomes an editor.** Re-weighting selection is editorial power; accumulated small demotions could bury a source the owner values for reasons his behavior doesn't show (he reads it in print, or values it precisely because it is uncongenial). This is PRD §4 Q8 and it is the deepest risk here. *Countermeasures:* the hard boundary of §3.3 (demote-only inference, no additions, no enable-overrides, clamps); the explain view making every influence auditable after the fact; and the record itself — the complete user model is one readable file, so "an agenda the user can't see" has nowhere to live.
8. **Record rot and conflicting edits.** The owner hand-edits the file; the agent writes an entry; versions skew. *Countermeasures:* the audience-profile pattern — version header + hash-checked loader that fails closed to *no learned influence* and surfaces the problem, rather than guessing. A broken user model must degrade to "the system as it was before learning," never to "the system behaving strangely."

---

## Appendix — grounding index

- Reader store, completion vias, positions: `experiments/muse-artifact-reader/index.html` (`STORE_KEY`, `markDone`, `readingTick`, `saveAudioPosition`, `noteArticlePosition`).
- Selection scoring, caps, frozen episodes, gate precedent: `focu/daily/store.py` (`select()`); gate policy: `focu/decision_gate.py` (POLICY_VERSION `gate-v1`).
- Registry shape and priority validation: `focu/daily/config.py` (`load_config`, priority default 1, must be positive).
- Feedback ledger: `focu/feedback.py` (`FeedbackStore`, kinds/targets, module CLI).
- Profile precedent: `references/audience-profile.md`, loader `focu/audience.py` (provenance enforcement).
- PRD items designed here: P2-1 (pruning proposals), P2-2 (feedback → selection, explain view), P2-3 (instrumentation — the ingest/export of Phase 2 is its transport); self-iteration Q7 (sparsity) and Q8 (editor boundary) answered in §6.2 and §6.7.

---

## Addendum — the `source_cap` proposal class: evidence design (wave 39, 2026-11-17)

The record schema, the validator, the snooze table (§2.3: 60 days for caps), the statement builder, and the Phase-3 seam have supported `source_cap` entries since Phase 1, but the engine never drafted one: Phase 1 deferred the class because "the completion-rate statistics needed Phase-2 transport." That transport has existed since the reader export shipped, and selection now writes its own accounting (the `selection_accounting` stage row: per source, per run, what was considered, selected, and withheld — and why). The deferral's premises are gone. This addendum is the evidence design the class was waiting for; it invents no new signal, only reads what the system already records.

**What counts as evidence.** Three recorded facts, jointly:

1. **Cap pressure.** The selection accounting's `over_cap` withholdings: candidates selection scored, wanted, and turned away *solely because the source had already filled its effective daily cap*. A source with sustained `over_cap` withholdings is a source whose registry cap is the binding constraint on its presence in the briefing — the pipeline is admitting it at the maximum rate the registry allows.
2. **Rarely finished.** The attributed completion rate (Phase-2 transport: completions are ledger kind `other`, manual archives excluded per §1.3) is low — but **nonzero**. Zero completions is the pruning pause's shape (§1.2(1), Phase-1 addendum constants `PAUSE_MIN_DELIVERED` / `PAUSE_MIN_DAYS`), and a cap value cannot be derived from zero observed consumption; the honest proposal there is the pause. A cap is proposed when the owner finishes *some* of the source's items — just far fewer than the cap admits.
3. **No contradiction.** Any `useful` mark in the window vetoes the proposal outright, as it vetoes the pause: the owner's explicit endorsement cannot coexist with an inference that the source should shrink. A demote-shaped source (negative-feedback floors met) gets the gentler demotion instead, as with the pause.

**Floors** (named constants in `focu/learn.py`, stricter than the weight floors on every shared axis — a cap rewrites how much of a source may appear *every day*, so it is held to pause-grade evidence):

| Constant | Value | Rationale |
|---|---|---|
| `CAP_MIN_DELIVERED` | 20 delivered | The pause's volume bar; double the weight floor (10). |
| `CAP_MIN_DAYS` | 10 delivery days | The pause's spread bar: pressure and neglect must be a pattern, not a burst. |
| `CAP_MIN_OVER_CAP` | 10 withholdings | At the minimum shape (10 delivery days) the cap must bind roughly daily — ≥ 1 turned-away candidate per delivery day — not once. |
| `CAP_MAX_COMPLETION_RATE` | 0.25 | At most a quarter of admitted items finished; above that, the cap is not the problem. |
| (veto) | `useful == 0`, `completed >= 1` | Endorsement contradicts shrinkage; zero completions is the pause's evidence, not the cap's. |

**The proposed value** is derived from observed consumption, never invented: `ceil(completed / days)` — the owner's observed finish rate per delivery day, rounded up — at least 1 (the record's own validator floor), and proposed **only when strictly below the registry cap** read from the newest in-window frozen run config (the config `load_config` normalized, so the cap is always a stated registry value, default 5). If observed consumption rounds up to the registry cap, the cap is not what ails the source and the engine is silent; if the registry cap is unknown (the source appears in no usable frozen config in the window), a lowering cannot be proven and the engine is silent. Accepting writes the entry; the seam already applies `min(registry, learned)`, so an accepted cap can only ever lower — §3.3 rule 1 holds by construction.

**Stop-rule treatment.** Cap proposals are **not** gated by the attributed-events stop rule (`MIN_ATTRIBUTED_EVENTS`), consistent with the pruning pause and for the same reason: their evidence is delivered/completion accounting plus selection accounting, not feedback-event volume. The stop rule exists because a *weight* proposal can pass its per-source floors on a bare minimum of feedback events (3 negative marks) while the window around it is silent — the totals contradict the pass. A cap proposal cannot pass on a bare minimum of anything: its floors are ≥ 20 delivered, ≥ 10 days, ≥ 10 cap withholdings, and ≥ 1 attributed completion. The accounting volume *is* the evidence, and it is large by construction. Gating it on unrelated sources' feedback totals would be the same category error the pause exemption already rejects.

**Batch discipline.** One statistics proposal per source per batch, as today. Precedence by gentleness and certainty: demotion (feedback-shaped) → pause (a fully dead source's tax is total) → cap (an over-admitted source's tax is partial) → promotion. The cap branch requires `not demotes`, like the pause branch, so a demote-shaped source in a stop-rule-shut window gets neither this batch. Dismissal snoozes the class for 60 days (§2.3, already in `SNOOZE_DAYS`); the 90-day step rule applies as it does to every kind+target.

**Accounting.** The sparsity block gains the cap gates in the same count-beside-floor form as every other gate (wave 25): `over_cap` beside `CAP_MIN_OVER_CAP`, `completion_rate` beside its ceiling, plus the two facts the value derivation reads — `registry_cap` and the derived `cap_value` — so "why no cap proposal for this source" is answerable from the batch result alone, including when the answer is "the derived value is not a lowering."
