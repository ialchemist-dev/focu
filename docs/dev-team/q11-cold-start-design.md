# Q11 — Cold Start: the first two weeks on an empty registry

- When: 2026-11-17 (wave 30, PM). Design only — no code. Implementation is deferred to the promotion decision, per pm-plan-3.md Wave 30.
- Question (PRD §4, Q11): how does Focu serve a brand-new user — or this owner on a fresh registry — before any feedback history exists, when the learning loop is silent by design and the preference record is empty by rule?
- Grounding: every number below is a shipped constant or a measured pack figure, cited to its file. Nothing in this design requires a new mechanism; it assembles surfaces the run already built (packs, day-status, sparsity) into an honest first-run shape.

## 1. The answer in one paragraph

Cold start is not a problem to be filled; it is a state to be *narrated honestly*. On day 0 the user states an interest and installs **exactly one** starter pack, chosen from that interest, through the same preview → install path as any pack — the preview already prints the pack's total attention cost, so the commitment is made with its price visible. From day 1 the system produces real briefings and a real day-status record every run; what it does not produce is proposals, and the design's job is to make that absence read as what it is — evidence accumulating toward named floors — rather than as a broken feature. The sparsity block (wave 25) is the cold-start surface: it shows each source's delivered count beside the floor it must clear and states the stop rule's reason verbatim. The first honest proposal appears when the math below first permits it, and not one run earlier; nothing is seeded, inferred, backdated, or simulated to make week 1 feel smarter than it is.

**Whose objective does a default serve?** The user's, when — and only when — the user asked their agent to choose. De-recommendation subordinates recommendation to human intent; an explicit "set me up" *is* intent, and a starter pack chosen under it is the user's own delegation, revocable in one action. A default installed without that ask would serve the system's objective (looking alive), and is prohibited by §6.

## 2. The shipped constants that decide cold start

These are not tunable ambience; they are the physics of the first two weeks. All from dev-main as of wave 29.

| Fact | Value | Source |
|---|---|---|
| Statistics window | `WINDOW_DAYS = 30` | `focu/learn.py:113` |
| Per-source delivery floor for any statistics proposal | `MIN_DELIVERED = 10` | `focu/learn.py:114` |
| Demotion gate | `MIN_NEGATIVE_EVENTS = 3` at `MIN_NEGATIVE_RATE = 0.2` → weight 0.7 | `focu/learn.py:116–118` |
| Promotion gate | `MIN_USEFUL_EVENTS = 3` owner marks → weight 1.25 | `focu/learn.py:119–120` |
| Window stop rule | `MIN_ATTRIBUTED_EVENTS = 4`; below it the engine states `insufficient attributed signal: N events in 30 days` | `focu/learn.py:134`, engine text at `:684` |
| Pruning-pause gate | `PAUSE_MIN_DELIVERED = 20` across `PAUSE_MIN_DAYS = 10` distinct days, zero completions, zero useful marks | `focu/learn.py:148–149` |
| Proposal budget / snooze | ≤3 per batch; dismissal snoozes 30d (weight) / 60d (cap, pause) | `focu/learn.py` constants block |
| Preference record | ships valid and **empty**; loader is fail-closed and provenance-enforced (`owner-stated` / `owner-accepted` only); the accept path is the record's only programmatic writer | `references/learned-preferences.md`, `focu/learn.py` |
| Pack attention costs (enabled sources) | Anthropic people 6.1/mo · OpenAI people 0.9/mo · Geothermal 92.4/mo · Silicon Valley startups 127.3/mo | `focu/source_packs/*.json` (`attention_estimate`) |
| Fastest people-pack source | Import AI ≈4.3/mo; most Anthropic-pack sources ≤0.6/mo | pack cadence fields |
| Pack freshness policy | pack due at `REFRESH_DUE_PACK_DAYS = 14`; source due at 30; affiliation stale >90d; `STALE_DAYS = 180` (recorded non-change) | `focu/packs.py:58,68,69,76` |
| Day-status | one reconciled record per run; `focu daily day-status` prints it; a missing record prints one explicit line and exits 0 | `focu/daily/pipeline.py`, `focu/daily/cli.py` (waves 23/26) |

Two consequences fall straight out of the table:

1. **A people pack cannot produce a statistics proposal in the first two weeks — or the first two months.** The fastest people source (Import AI, 4.3/mo) needs ~2.3 months to reach `MIN_DELIVERED = 10`; a 0.3/mo source needs ~33 months. Any design that promises a new people-pack user a proposal in week 2 is promising a fabrication.
2. **The binding constraint is the owner's marks, not the system's patience.** Even on a firehose source, demotion needs ≥3 attributed `not_useful` marks at ≥20%, promotion needs ≥3 `useful` marks, and the window needs ≥4 attributed events before statistics drafting opens at all. Cold-start silence is the owner not yet having spoken, recorded faithfully.

## 3. The first two weeks, day by day

### Day 0 — the install moment (the only moment that needs design)

1. The user states an interest in their own words ("follow people at Anthropic", "geothermal industry news"). The agent maps it to **one** of the shipped packs — never a bundle, never "one of each".
2. `focu pack preview` runs before anything is written: adds, duplicates, unverified sources with reasons, cadence warnings (a ≥20/mo source or a ≥50%-dominant source is named — the geothermal pack's ThinkGeoEnergy at ~78/mo, 84% of its pack, is the standing example), and the total attention cost in posts/month. The user sees the price before committing; that is the de-recommendation contract applied to onboarding.
3. `focu pack install` applies with the existing discipline (backup → temp-write → `load_config()` gate → atomic rename; provenance in `packs-installed.json`). Installing the starter pack enables **nothing else**: no second pack, no adapter source, no learning entry.
4. The install output (and the first briefing, §3.2) states in plain words: which pack is installed, its attention cost, and the one action that removes it (`focu pack uninstall <id>`). No default is ever silent.

### Days 1–14 — the running shape

- **Briefings from day 1.** Selection needs no history: score = registry priority / (1 + age_days), per-channel word budget (`max_minutes × words_per_minute`; the production channel is 35 × 150 ≈ 5,220 words). A one-pack registry produces a thinner briefing than the owner's current four-source production registry, and that thinness is *shown*, not padded: the day-status record's summary says what was collected, selected, and withheld, in its own factual sentence.
- **Day-status from run 1.** Every run assembles its reconciled record; `focu daily day-status` is the new user's "is it working?" surface. On an empty day it says "Nothing new for <date>" — a fact, not an apology.
- **The reader acts are live from the first item.** Archive / Not for me / Useful write to the consumption store from day 1; the owner-initiated export from the Archive view is the only transport, exactly as for an established user. There is no separate "training mode".
- **Proposals: none, and the surface says why.** `focu learn proposals` on a cold store prints the sparsity block and, below the stop rule, `insufficient attributed signal: N events in 30 days`. That string is the cold-start UI for learning. It must be reachable by the agent's daily report verbatim — never paraphrased into "still learning you!" and never hidden because it looks empty.
- **The preference record stays empty.** It is not a form to fill in during onboarding. Owner-stated entries are entered by hand when the owner actually states a preference, whenever that happens — day 0 or month 3.

### Week 3 and after — what changes, and what does not

Nothing switches on at a date boundary. Sources cross `MIN_DELIVERED = 10` one by one (high-volume packs in days, people packs in months); attributed events accumulate only when the owner marks items; the first proposal arrives inside the normal ≤3-per-batch budget, ranked as usual, carrying its evidence line. The sparsity block's distance-to-floor numbers are the entire "progress bar" — the design deliberately has no other, because every other progress metaphor (percentages, levels, streaks) would be an engagement mechanic pointed at the owner.

## 4. What the sparsity report must show a new user

The wave-25 block already carries the data; the cold-start requirement is about *framing*, and it is checkable:

1. Per source: delivered count **beside its floor** (`delivered: 3/10`), attributed events by kind with their floors (`negative: 0/3`, `useful: 0/3`), so "how far, and what is missing" is answerable at a glance.
2. The window total beside `MIN_ATTRIBUTED_EVENTS` (`attributed_events: 1/4`) and the stop-rule reason verbatim when gated.
3. For the pruning path: delivered count beside `PAUSE_MIN_DELIVERED` and distinct days beside `PAUSE_MIN_DAYS`, so a daily source's approach to a possible pause proposal is visible before it fires.
4. `unattributed_feedback` stays printed. On a cold store it should be 0; if it is not, something upstream is broken (the F1 lesson: unattributed signal once pooled silently for the product's main surface).
5. The block must never render a percentage-of-profile-complete, a projected "smart by" date, or a recommended action. It is an instrument readout, not a funnel.

## 5. When the first honest proposal can appear — the bounds

Stated as bounds, not promises; all assume the pack is installed day 0 and the owner reads daily.

| Proposal kind | Earliest possible | Binding constraint |
|---|---|---|
| Pruning `source_pause` | **Day ~11**, and only for a source delivering ≥20 items across ≥10 distinct days with zero completions and zero useful marks (a ThinkGeoEnergy-shaped source qualifies on delivery by ~day 8; the 10-distinct-days term binds) | delivery accounting; not gated by the stop rule (wave-25 design), but vetoed by any completion or useful mark |
| Demotion `source_weight` 0.7 | **Week 1–2 on a high-volume source** (≥10 delivered, owner marks ≥3 not-for-me at ≥20%, window attributed ≥4); **month ~3+ on a people pack** (Import AI's delivery floor alone takes ~2.3 months) | owner's marks, then `MIN_DELIVERED` |
| Promotion `source_weight` 1.25 | Same delivery bound as demotion, plus ≥3 `useful` marks on that one source | owner's marks only — completion can never promote (Phase-1 rule) |
| `source_cap` | Not generated by the engine at all (schema-supported, engine-deferred since Phase 1) | future wave, own evidence design |
| `renewal` / `pause_review` | Not applicable at cold start — they review existing record entries, and the record is empty | an entry must exist and age first (`LONG_PAUSE_DAYS = 90` for pause reviews) |

The design's commitment: if a deployment's first proposal appears **earlier than these bounds allow**, that is a defect to investigate, not a delight to report — it means evidence was manufactured or a floor was bypassed.

## 6. What must NEVER be faked to fill the silence

Each item is a hard prohibition for any future implementation, stated so a reviewer can grep a diff for violations:

1. **No starter preferences.** The record ships empty and stays empty until an owner accept or an owner's hand edits it. No "sensible defaults" entry, no pre-seeded weight, no imported profile from another product. (The loader's provenance enforcement already rejects unprovenanced entries; a cold-start feature must not become the path that writes the first one.)
2. **No inferred profile.** Reading behavior is never converted into a stated preference, an expertise claim, or an interest tag the owner did not state — the `audience.py` precedent ("never silently infer expertise from reading behavior") applies to the whole cold-start surface.
3. **No synthetic proposals or evidence.** No demo proposal "to show how it works", no backdated deliveries, no seeded feedback events, no simulated marks. The ledger contains only events that happened.
4. **No lowered floors for week 1.** Wave 25 validated the floors as shipped (no value changed; noise fires nothing, concentrated signal fires). A cold-start wave that retunes `MIN_DELIVERED`, `MIN_ATTRIBUTED_EVENTS`, or the pause floors to make onboarding feel responsive has failed its acceptance by definition — floor changes require a named failing harness fixture, per plan-3's standing rule.
5. **No subscription by implication.** One starter pack is the whole default. Installing it must not enable other packs, adapter sources, or refresh schedules; each of those is its own explicit act.
6. **No silent default, ever.** The installed pack, its cost, and its removal action are stated at install time and in the first briefing. A default the user cannot name is a recommendation the system made for its own benefit.
7. **No padded briefing.** A thin day is reported thin (day-status summary, verbatim). The selector never reaches outside the registry to fill the word budget, and the briefing never restates withheld items as content.

## 7. Acceptance criteria for the future implementation wave

Line-checkable, in the run's established style. The wave that builds cold start (at promotion) passes when:

1. **Fresh-store walkthrough test**: from an empty registry, empty ledger, and the shipped empty record — install one starter pack via preview → run one daily cycle → assert (a) a briefing exists, (b) a `day_status` stage row exists for the date, (c) `focu learn proposals` prints the sparsity block and the string `insufficient attributed signal: 0 events in 30 days`, and (d) zero proposals.
2. **Record untouched**: the preference record's bytes are identical before and after the entire walkthrough, including the install step (`grep` also confirms the only-writer invariant still holds — `_write_record(` appears only in `focu/learn.py`).
3. **Default is stated**: the install output and the first briefing's status surface each contain the pack id and the literal uninstall command for it; a test asserts both strings.
4. **One-pack bound**: after the walkthrough, `packs-installed.json` contains exactly one entry, and the registry contains no source the pack did not name.
5. **Removal is one action and exact**: `focu pack uninstall` of the starter pack returns `sources.yaml` to its pre-install bytes (the existing uninstall semantics, asserted on the cold-start path specifically).
6. **No floor moved**: `git diff` on the constants block of `focu/learn.py` (`WINDOW_DAYS` … `PAUSE_MIN_DAYS`) is empty, or names the failing harness fixture per the standing rule.
7. **Sparsity framing**: the proposals output on the cold store shows every gate as count-beside-floor (§4.1–4.3) and contains no percentage, no projected date, and no recommended action (asserted by string absence).
8. **Thin day honesty**: a fixture day with zero collected items yields the day-status summary's nothing-new sentence verbatim in `focu daily day-status` output, and no briefing section is fabricated to fill it.

## 8. What this design deliberately does not do

- It does not design a multi-user onboarding (accounts, auth, hosted anything). Focu is a one-owner system; "a stranger" in Q11 means this owner, or a future single owner, on a fresh registry.
- It does not pick the starter pack for the user in advance of an interest statement. The catalog's four packs span 0.9–127.3 posts/month; choosing among them *is* the user's first attention decision, and the preview exists to price it.
- It does not schedule pack refresh for the new user. `focu pack refresh-due` reports; when (or whether) anything runs it is a promotion-time scheduling decision for the owner, as wave 29 recorded.
