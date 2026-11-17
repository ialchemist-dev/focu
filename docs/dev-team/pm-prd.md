# Focu 24h Run — PRD (Project Manager)

- Run window: 2026-11-17 ~01:50 → 2026-11-18 01:45 America/Denver. Hard stop.
- Branch: **dev-main** only. Framework SOP: PM → Infra/Architect → Backend/UI → Integrator (MetaGPT roles, per STATE.md).
- Governing document: `~/workspace/focu-dev/attention-sovereignty.md` (the owner's article). Where this PRD and the article disagree, the article wins.
- Companion docs: `docs/READER_MARKETPLACE_PLAN.md` (existing product contract — this PRD prioritizes it, it does not replace it), `~/workspace/focu-dev/BACKLOG.md` (seed backlog — this PRD re-orders and sharpens it; proposed backlog edits are in §6, to be applied by the integrator only after owner/PM sign-off in-cycle).

---

## 1. Objectives, in the philosophy's terms

Focu exists to return attention, not to capture it. Every objective below is therefore stated as **attention returned** or **sovereignty gained**, never as engagement, time-on-app, or content volume.

**The success metric for this run.** For each shipped item we estimate *attention returned per day* for a user running the daily briefing, using the article's own compression ladder as the accounting unit: most items should cost the user **0.5s** (a one-line gist, correctly triaged), a few **10s** (a paragraph worth reading), and roughly one a day earns a **full read**. A feature "works" when it moves items down that ladder without moving any item the user would have wanted *up* it. Where an estimate is a guess, it is labelled (est.) and the cycle that ships the item must say how it would be measured for real.

**Objectives for the 24h run:**

1. **A source-pack library a stranger can use in one sitting.** A new user (or their agent) can browse curated packs, inspect every member's identity evidence and collection readiness *before* subscribing, and install a pack into `sources.yaml` with one explicit action and a preview diff. No account, no popularity ranking, no auto-subscription — the site catalog's stated principle, enforced in code, not just copy.
2. **People packs, built the honest way.** Anthropic and OpenAI packs v1: employees with *author-owned* sites/blogs, each entry carrying affiliation evidence, a feed that was actually fetched, and an observed update cadence. Coverage is stated as "N of M found, method X" — never implied to be a census. This is "follow people, not platforms" made installable.
3. **A reader that taxes less attention than it did yesterday.** Implement the UI audit's top simplifications on dev-main. Target: the Today view answers "what deserves my attention today?" in one glance — title, one-line gist, source, time cost — with zero control-surface chrome between the user and that judgment. Look. Understand. Judge. Leave.
4. **Ingestion breadth without sovereignty loss.** Adapter designs (and one prototype) for RedNote, Instagram, Facebook, YouTube that follow the LinkedIn reader's established pattern: the user's *own* feed, their *own* logged-in session, human pace, fixed daily budget, stop on first platform challenge. Breadth is worthless if it converts Focu into a scraper; the constraint is the feature.
5. **A system that visibly learns its user — with permission.** Close the loop from explicit feedback (complete / save / like / dislike — never scroll inference, per the existing product contract) to *proposed* source and selection changes. The system suggests; the user disposes. Learning that silently changes what reaches the user is recommendation wearing a new hat, and it is out of scope by definition.

**Scope.** Dev checkout on dev-main: reader UI, source-pack schema/import, pack content (Anthropic, OpenAI; drafts for Silicon Valley startups and geothermal), adapter designs + one prototype behind the existing source interface, feedback-loop design + minimal wiring. README updated every cycle.

**Explicit non-goals (hard constraints, not aspirations):**

- **No production changes.** `~/workspace/focu-live`, `~/focu-runtime`, the `focu-daily-briefing` job, and the live Focu reader artifact are read-only reference. Nothing in this run touches them.
- **Nothing merges to `main`.** All commits land on dev-main via the Git Data API route in the RUNBOOK. The owner merges, later, on his word.
- **No mass scraping.** No bulk profile harvesting, no follower-graph crawls, no logged-out scraping at scale, no CAPTCHA solving, no anti-detection tooling. Ingestion = the user's own feeds, own session, human pace, hard daily caps — the LinkedIn pattern. Discovery for people packs uses public pages at reading pace, cross-checked, with failures retained and reported (per READER_MARKETPLACE_PLAN step 4).
- **No engagement mechanics.** No streaks, no unread-count anxiety badges, no infinite scroll, no "trending in this pack," no popularity sort. If a UI element exists to make the user stay longer, it is a bug.
- **No silent learning.** The user model never changes selection, sources, or ranking without an explicit, reviewable proposal the user accepts. No exceptions "just for obvious wins."
- **No new subscriptions by implication.** Installing Focu, importing one pack, or accepting a pruning suggestion never enables any other source.
- **No paid services, no new credentials.** The run uses what the VM already has. Anything needing an API key or account action is designed, documented, and parked — not improvised.

---

## 2. Prioritized backlog

Owners are roles, not people: **PM** (this role), **INFRA** (infra designer), **BE** (backend developer), **UI** (UI developer), **INT** (integrator). Estimates of attention returned assume a user running one daily briefing with ~15–25 items/day; all are (est.) until the feedback instrumentation in P2-2 exists to measure them.

### P0 — foundations (nothing else starts until these are green)

**P0-1. Wave-1 design set complete** — Owner: PM + INFRA + BE + UI (each owns their doc).
Acceptance: `team/pm-prd.md`, `team/infra-design.md`, `team/backend-design.md`, `team/ui-audit.md` all exist; backend-design's pack schema is checked field-by-field against `site-source-catalog.json` and `site-pack-anthropic-personal-blogs.json`; ui-audit names at least 5 concrete attention taxes in the current reader, each with a screenshot-level description and a proposed removal.
Attention returned: 0 min/day directly — this is the tax we pay so later cycles don't rebuild. Capability gained: a shared contract; every later acceptance test traces to it.

**P0-2. MetaGPT install verified on this VM (or fallback declared)** — Owner: INFRA.
Acceptance: `python -c "import metagpt"` (or the framework's documented smoke test) passes in a venv under `~/workspace/focu-dev/`, with the exact install commands recorded in `team/infra-design.md`; if it cannot install within one cycle, INFRA declares the CrewAI fallback in STATE.md with the reason — no silent drift, no second retry cycle burned.
Attention returned: n/a. Capability gained: the multi-agent SOP the owner asked this run to prove.

**P0-3. dev-main hygiene: tests green at base, README skeleton for the run** — Owner: INT.
Acceptance: full focu test suite passes on the dev checkout at dev-main base (record the count in STATE.md); README gains a "24h dev run" section stub (philosophy, branch, where the team docs live) that later cycles extend — README is updated *every* cycle per §5, this item just opens it.
Attention returned: n/a. Capability gained: a trustworthy baseline; a red suite later in the run then means *we* broke it.

### P1 — the library (working name resolved in §3)

**P1-1. Source-pack schema v1, aligned with the site Source Library** — Owner: BE (INFRA reviews).
Acceptance: schema (JSON Schema or equivalent validator + `focu`-side loader) accepts the existing site packs unchanged — `anthropic-personal-blogs` v0.1.0 validates as-is or via a lossless, scripted migration; every source entry carries `id, name, type, site_url, feed_url/collector, affiliation_evidence, affiliation_status, readiness, verified_at, cadence` (cadence may be `unknown`, never absent); pack carries `id, version, name, description, categories, coverage` (coverage is mandatory and free-text-honest); validator rejects a pack whose coverage claims completeness ("all employees") — that string class is a lint error, not a style preference. Unit tests cover: valid pack, missing evidence field, duplicate source id across packs (must dedupe by canonical locator, per the existing plan).
Attention returned: 0 directly. Capability gained: packs become data anyone can author, diff, and version — the precondition for every pack below and for third-party packs later.

**P1-2. Pack: Anthropic people v1 (refresh and complete the site prototype)** — Owner: BE, with INFRA on discovery method.
Acceptance: starts from the site's v0.1.0 pack (6 authors, verified 2026-10-28 — already 3 weeks stale at run start, which is itself finding #1 for §4); every retained entry re-verified this run (feed fetched, HTTP status + entry count recorded, `verified_at` = run date); discovery pass over public sources (official bios, author sites, public LinkedIn where accessible at reading pace) adds candidates with the same evidence bar; each entry has an observed cadence (last-post date + posts in trailing 90 days, or `cadence: unknown` with reason); rejected candidates and dead feeds are listed in the pack's build notes with reasons — not silently dropped; final count and coverage statement written in the pack's `coverage` field ("verified collection of N authors found by method X; not a directory").
Attention returned: (est.) 3–6 min/day for a user who would otherwise check these blogs individually or miss them in a platform feed; more importantly it converts ~6 scattered checking habits into 0.5s gist triage.

**P1-3. Pack: OpenAI people v1 (same method, no shortcuts)** — Owner: BE.
Acceptance: identical evidence bar to P1-2 (author-owned site, affiliation evidence URL, fetched feed, cadence observed or honestly `unknown`); built independently — copying the Anthropic pack's author list across companies is an automatic fail; coverage statement names the discovery method and its blind spots (e.g. employees who write only on X are *listed as known gaps* if the pack's collector can't take them, not silently omitted).
Attention returned: (est.) 3–6 min/day, same mechanism as P1-2.

**P1-4. Import flow: one action, preview first** — Owner: BE (UI reviews the preview surface).
Acceptance: `focu reader`-side command (or the existing subscribe path, extended) that, given a pack file or URL: prints a diff of exactly which sources would be added/changed in `sources.yaml`, flags any source whose `readiness` is not "verified" and excludes it unless explicitly overridden per-source, writes nothing until confirmed, is idempotent on re-run, and pins the pack version in the subscription record (per the existing plan: updating versions is a separate explicit act). Round-trip test: import Anthropic pack → export sources → matches pack membership minus unverified entries; remove pack → sources required by another installed pack survive.
Attention returned: (est.) 10–20 min *per pack install* vs hand-editing `sources.yaml` — and it removes the entire class of "I never got around to adding those blogs" attention debt.

**P1-5. Reader UI: implement the audit's top changes** — Owner: UI (INT verifies against audit).
Acceptance: the top 3 changes from `team/ui-audit.md` implemented in the reader on dev-main; each change is stated as "removed X / collapsed Y" — a change that *adds* a persistent UI element needs PM sign-off recorded in the cycle log; Today view still satisfies the existing contract (finite batch, explicit end state, completion removes from inbox not storage, completion reversible); no new badges, counters, or sorts by popularity; existing reader tests pass plus one new test per changed behavior.
Attention returned: (est.) 1–3 min/day in reduced triage friction — small per day, but it is the only item on this list the user pays or saves on *every single session*, so it compounds past the packs within a month.

**P1-6. Pack drafts: Silicon Valley startups; geothermal industry** — Owner: BE.
Acceptance: *draft* packs (version 0.x, `coverage` says "draft") following the P1-1 schema; startups pack = official company blogs/engineering blogs + named founders'/engineers' author-owned sites, same evidence bar; geothermal pack = industry publications, company blogs (e.g. the owner's sector: EGS developers, labs, trade press), each with fetched-feed readiness; drafts are explicitly *not* marked verified beyond per-source feed checks, and are not offered by the import flow's default path until promoted.
Attention returned: (est.) 2–5 min/day each for the owner specifically (geothermal is his industry; the unified daily briefing already tracks it by hand — this makes it a pack anyone in the sector could install).

### P1 — platform ingestion (designs for all four; one prototype)

**P1-7. Per-platform adapter designs: RedNote, Instagram, Facebook, YouTube** — Owner: INFRA (BE reviews against the source interface).
Acceptance: one design doc (in `team/infra-design.md` or a sibling) per platform covering: the mature, community-recognized open-source tool chosen (named, with repo, license, maintenance status, and the runner-up rejected *with reason*); how it maps onto Focu's existing source types/collectors; the session model (user's own login, own feed only); the pacing budget (items/day cap, session shape, jitter — modeled on the LinkedIn reader's plan: sessions of 5–10 items, randomized within waking hours, summing to a hard cap); the stop conditions (first CAPTCHA/checkpoint/429 → stop, surface to user, never retry-loop); and the platform's terms posture stated factually. A design that requires violating the non-goals in §1 is rejected at review, however good the tool is.
Attention returned: 0 until prototyped. Capability gained: four platforms become *decided*, not perpetually "we should look into."

**P1-8. First adapter prototype (YouTube recommended)** — Owner: BE.
Acceptance: prototype behind the existing source interface (a new `type:` in sources.yaml works end-to-end in the dev checkout: collect → unit → briefing-eligible); recommended first platform is YouTube because the pipeline already has a YouTube transcript path in production (lowest new-risk), letting this item test the *adapter contract* rather than a new platform's defenses; if INFRA's P1-7 analysis says otherwise, PM records the substitution and reason in STATE.md. Prototype obeys a hard daily cap and emits the same unit shape as existing collectors; failure modes (no captions, region lock) land as withheld/pending states, never as crashes or silent empties.
Attention returned: (est.) 2–4 min/day per followed channel moved from app-checking to gist triage.

### P2 — smarter over time (design + minimal wiring only; this is where runs like this usually over-promise)

**P2-1. Reading-feedback → pruning suggestions** — Owner: BE (PM owns the proposal UX contract).
Acceptance: a report (CLI or reader surface) that, from explicit signals only (completions, saves, explicit dislike — per the product contract, scroll and dwell are *not* feedback), lists sources with sustained zero-completion over a stated window and *proposes* pausing them; accepting a proposal is one explicit action; rejecting it suppresses re-proposal for a stated period; the report shows its evidence per source ("0 of 14 items completed in 30 days") so the user judges, not obeys. No source is ever paused, demoted, or re-ranked without that acceptance. Test: fixture history → expected proposals; empty history → empty report, no invented suggestions.
Attention returned: (est.) the highest-leverage number on this list if it works — every dead source in a briefing taxes 0.5s × every day forever; pruning 3 dead sources ≈ 1–2 min/day returned *and* raises the hit-rate of everything that remains.

**P2-2. Explicit like/dislike wired into selection, visibly** — Owner: BE.
Acceptance: like/dislike on an item is stored against its source and topic tags; the daily selection's scoring change from feedback is *inspectable* — a debug/explain view can answer "why is this item here / ranked here?" with the feedback-derived factors named; feedback never *adds* sources and never promotes content from sources the user didn't choose (it re-weights within the user's own registry only — de-recommendation means the user's agent filters the user's chosen sources, not that it goes shopping); the versioned audience profile remains the durable record and is updated only through this explicit path.
Attention returned: (est.) 1–2 min/day via fewer 10s-items that should have been 0.5s-items. Capability gained: the "explain why" view is also the audit surface that keeps the learning loop honest in every future cycle.

**P2-3. Feedback instrumentation for the estimates in this PRD** — Owner: INFRA.
Acceptance: a lightweight, local-only counter set (items delivered / completed / saved / opened-full per source per day) written by the reader, with a one-command summary; explicitly *not* analytics — no network egress, no third party, data stays in the user's store; this is what converts every "(est.)" above into a measured number in a later run.
Attention returned: 0. Capability gained: the run's own success metric becomes falsifiable.

---

## 3. Marketplace naming

The thing being named: a browsable collection of curated, versioned source packs that a user (or their agent) inspects and explicitly installs. The site's catalog already states its principle: *"No popularity ranking, account, or auto-subscription."* The name must not promise what the philosophy forbids.

Candidates, judged against (a) the philosophy, (b) the owner's existing vocabulary — **Focu** (the product), **The View** (his name for his recommendation philosophy: title-first, follow people not platforms), **Source Library** (the live section on his site, aipraxislab.com, already shipping packs), **attention sovereignty** (the纲领):

| Name | For | Against |
|---|---|---|
| **Focu Exchange** (working name) | "Exchange" hints at a two-way flow — users can contribute packs back, not just take. Short, ownable, clearly Focu-branded. | An exchange is a *market*: it implies trading, liquidity, counterparties, and by extension ranking by volume. It primes exactly the platform-economics frame the article argues against. Also implies other people's packs arrive with market dynamics attached. |
| **Source Library** | Already the owner's live vocabulary — the site section and catalog exist under this name today, so the run *extends* his language instead of coining a rival. A library is quiet, finite, curated, and borrowing is deliberate; nothing in the word suggests ranking, feeds, or retention. Matches the packs' actual behavior (inspect, check out, return/remove). Zero learning cost for anyone who has seen his site. | Less distinctive as a product name; "library" undersells that packs are versioned, living data. Generic enough that it won't trademark well — acceptable for a personal open-source system. |
| **The View** | It is his philosophy's own name — de-recommendation, follow people not platforms. Maximum conceptual continuity: the packs are The View, operationalized. | Already taken — by him, for the philosophy/essay layer, and by a well-known TV show for everyone else. Using it for the pack collection collapses two distinct things (a stance vs. a catalog) and would confuse his own site's structure. |
| **Focu Packs** (plain) | Brutally clear: the unit is the pack, the brand is Focu. Works as UI copy ("Browse packs", "Install pack") with no metaphor to maintain. | Names the container, not the place; gives a new user no sense of curation or trust. As the collection grows across authors it reads like a file format, not a destination. |
| **Attention Market** | Directly invokes the纲领's central term. | The worst offender of the five: it names the *problem* (attention as a traded commodity) as if it were the solution. Included to mark the boundary — any name of the form "attention + market/exchange/trade" is rejected on principle. |

**Recommendation: Source Library.** It is the only candidate that is simultaneously (1) already the owner's word, in production on his site, attached to these exact packs; (2) semantically aligned — libraries don't rank by popularity, don't have accounts pushing engagement, don't auto-anything; and (3) honest about the interaction: you browse, you inspect, you deliberately take something home. "Exchange" can be revisited *if and when* third-party pack contribution becomes real and needs a name for the contribution act — and even then it should name the contribution flow, not the library. The unit stays the **pack** in all UI copy ("Install this pack"), which keeps Focu Packs' clarity where it matters. The owner can veto; if he does, the fallback is Focu Exchange, and the catalog copy must then carry the no-ranking principle in its first line to counteract the name.

---

## 4. Self-iteration: problems to hunt

Each item is phrased as a question a later cycle can pick up, investigate with evidence, and close with a change or a documented "not a problem because…". Whoever closes one appends the finding to the cycle log and, if it changes scope, proposes the backlog edit per §6.

1. **Where exactly does the current reader tax attention?** Walk the Today → detail → complete path and count every element that is a control surface rather than a display surface (per the article's distinction). Which three removals return the most per-session attention, and did P1-5 pick the right three?
2. **What breaks when a pack goes stale?** The seed Anthropic pack was verified 2026-10-28; by run start its `verified_at` is 3 weeks old. What is the actual half-life of a pack entry — how many feeds moved, died, or went dormant in those 3 weeks? What should re-verification cost, how often, and who (which role/cron) owns it before "stale pack" becomes "user's briefing silently thins out"?
3. **Affiliation rot:** people leave companies. An "Anthropic people" pack entry whose author moved to a competitor is mislabeled attention. How would we *notice*? Is periodic affiliation re-checking worth its cost, or should packs carry an explicit "affiliation as of" date and let age be visible instead of hidden?
4. **Cadence vs. value:** a pack member who posts daily low-signal links can tax more attention than the pack returns. Should cadence data (collected in P1-2/P1-3) feed a per-source item cap, a "quiet member" flag in the pack UI, or nothing at all? Where is the line between curation and the library silently editing someone's writing out?
5. **The empty-briefing failure mode:** if collectors fail or a platform challenges a session, the user gets a thin or empty day and no signal about *why*. What is the minimum honest status surface ("LinkedIn stopped at a checkpoint — your action needed" vs "nothing new") that informs without becoming another inbox to manage?
6. **Dedupe pressure as packs overlap:** the same person will appear in "Anthropic people", "Interpretability notes", and a future "AI labs" pack. The plan says dedupe by canonical locator and preserve memberships on removal — does the implementation actually hold when the same person has *different* locators (site root vs feed URL vs Substack mirror)? Construct the failing case before a user does.
7. **Feedback sparsity:** P2 assumes explicit signals, but a user who mostly listens to the podcast may generate almost none. What is the minimum viable signal set that keeps the learning loop honest (rather than training on absence), and at what sparsity should the system *stop proposing* instead of proposing from noise?
8. **Where does "learns the user" collide with reporter-only fidelity?** The briefing's stance is reporter/summarizer, not editor. If the user model starts re-weighting selection (P2-2), at what point has the system become an editor with an agenda the user can't see? Is the "explain why" view sufficient, or does selection need a hard boundary (feedback may demote, never promote; may prune, never add)?
9. **Import trust:** a pack is executable configuration — it points collectors at URLs. What does a malicious or sloppy third-party pack do to a user's system (SSRF-ish fetches, 10,000-item sources, a "pack" that is one person's marketing funnel)? What is the review checklist/sandbox the import flow (P1-4) owes the user before packs circulate beyond the owner?
10. **The one-full-read budget:** the article's ladder ends with "perhaps one makes me stop and read the original." Does the current reader do anything to make that one deep read *good* (clean original, no interstitial junk), or does it optimize the 0.5s layer and abandon the user at the exact moment attention is most deliberately spent?
11. **Cold start for a stranger:** onboarding today is six questions and hand-pasted starter packs. With a Source Library, what is the smallest first-run that gets a new user to a *good* first briefing — and does recommending starter packs at install violate de-recommendation, or is it legitimate because the user asked their agent to choose? (Whose objective does a default serve?)
12. **Podcast vs. reader divergence:** the same item exists as text and audio with one consumption identity (per the plan). When a user completes the audio, does the reader know? Where the two surfaces disagree about state, which one is lying to the user about what they've consumed?

---

## 5. Definition of Done — per cycle

A cycle is DONE only when **all** of the following are true. Partial is not done; it is "carried over," and the cycle log says so in those words.

1. **Tests green.** The full focu test suite passes on the dev checkout (`Ran N tests … OK`), with N ≥ the P0-3 baseline, plus new tests for any new behavior. A red suite blocks the commit, not the report.
2. **Acceptance checked, not vibes.** The cycle's backlog item is checked line-by-line against its acceptance criteria in §2; the cycle log entry quotes the result per criterion (pass / fail / carried).
3. **Commit on dev-main.** Changes are pushed to `dev-main` via the Git Data API route and the remote ref is read back and verified. The commit SHA goes in the cycle log. Nothing is committed to `main`; nothing in production paths is modified.
4. **README updated.** The README's run section reflects reality after this cycle: what the feature is, how to use it, current status. A feature that isn't in the README isn't shipped.
5. **State files updated.** `STATE.md` cycle log gains one line (time, item, result, commit SHA); BACKLOG.md checkboxes are updated *by the integrator* to match reality (status only — re-prioritization follows §6).
6. **Philosophy check.** The cycle log entry answers one question in one sentence: *what attention does this return, or what sovereignty does it protect?* If the honest answer is "none," the item is flagged for PM review before the next cycle starts.

## 6. Proposed backlog changes (for integrator to apply on PM/owner sign-off)

1. Rename the P1 heading "marketplace (Focu Exchange)" → "Source Library (packs)" if the owner accepts §3; keep "Focu Exchange" as the recorded working name until he rules.
2. Add P0-3 (baseline test count + README run-section stub) — the seed backlog assumes a green base that has not yet been recorded.
3. Promote "pack staleness / re-verification" from an implicit property of P1-2 to a tracked self-iteration item (§4 #2), with the 2026-10-28 Anthropic pack as the first test case.
4. Split the seed's single "per-platform OSS tool choice + adapter design" line into P1-7 (designs) and P1-8 (one prototype), so a design delay cannot silently eat the prototype's cycle.
5. Seed the self-iteration list with §4's twelve questions, replacing the current `[ ] ?` placeholder.
