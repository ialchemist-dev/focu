# RFC — Focu: Agent-Native Information for Attention Sovereignty

**Status:** Draft for owner review; not an implementation authorization
**Version:** 0.3 (2026-11-06)
**Scope:** Product architecture, decision rules, interfaces, and acceptance criteria
**Repository:** ialchemist-dev/focu
**Intended deployment:** Open-source, self-hostable, independently configured per person; no monetization requirement

## 0. Core definition

> Focu is an agent-native information gateway working on behalf of one person. It seeks the most **useful** information, not the content most likely to attract that person's attention. It continuously investigates original evidence, compares external views, connects findings to an evolving personal knowledge base, and delivers high-signal briefings and deeper research only when the expected benefit justifies the person's time.

**Attention sovereignty** means the person retains control of attention, objectives, personal context and final judgments. The agent is a delegated intermediary, not an engagement optimizer.

**Core distinction:** Predicting what a person *likes to consume* is different from identifying what is *worth knowing*. Utility must include consequential new evidence, useful disconfirming information, and knowledge gaps even when these are not entertaining.

This is a noncommercial, open-source, single-person-per-instance design. Focu should be easy for others to install and control, not a multi-tenant engagement platform. No tracking/advertising business model, growth metric, or addictive feed mechanic is in scope.

## 1. Vocabulary / terminology

| Context | Preferred term | Meaning |
|---|---|---|
| Public-facing prose | **person** (个体) | A human with goals, context and agency, not traffic inventory |
| Delegation / authority / API policy | **principal** (委托人) | The human on whose behalf the agent acts, and who authorizes actions |
| Deployment / security | **instance owner** | Controls data, credentials, policies, and compute for one installation |
| Reader UI | **you** | Natural second-person language |
| Source material | **source** / **publisher** | Author or origin of the information, not the principal |
| Historical code/database | existing `user` fields | Preserve backward compatibility; do not rename old schemas solely for terminology |

**Avoid** `subject` as the default: it risks making the human sound like a study subject or a data subject. Avoid imposing servile "master/boss" phrasing as a mandatory voice persona. `Principal` is a precise technical relationship, not a marketing label.

## 2. Nonnegotiable invariants (MUST)

1. **Utility, not engagement.** Never optimize dwell time, autoplay count, notifications, session length, or clicks as primary targets. Measure useful knowledge gained and attention spent.
2. **Primary evidence first.** Prefer original publications, papers, primary experiments, official documents and firsthand claims. Preserve source URLs, author, time, snapshot/hash, and evidence qualifiers. Secondary commentary is additional evidence, not a vote.
3. **Original and interpretation are distinct.** A report must visibly separate source claim, independent evidence/reactions, and Focu's own reasoned assessment. Agent judgments must never be presented as the author's claim.
4. **Critical independence.** Prior beliefs and preferences personalize relevance, never decide truth. Routinely seek serious contradictory evidence and novel adjacent discoveries.
5. **No unnecessary synthesis.** If a good primary article answers the question and Focu has no meaningful added analysis, recommend the original; do not generate a longer paraphrase merely to fill a pipeline.
6. **Cumulative knowledge.** Research updates or proposes updates to an evolving, cited LLM Wiki. Raw sources remain immutable; contradictions, provenance and revision history are preserved.
7. **Explicit customization.** The principal supplies lasting preferences; the system uses versioned, human-editable policy files. It may suggest changes but does not silently infer expertise or rewrite long-term preferences.
8. **Fail closed on content fidelity.** Missing key figures, unsupported claims, failed critical checks or incomplete audio must not be quietly delivered as verified.
9. **Attention budget.** Silence and deferral are valid successful outputs. Notifications are exceptional and bounded; no endless-scroll incentive.
10. **Open and portable.** Data, sources, reading states and knowledge remain exportable. Optional paid models/providers are replaceable. An initial self-hosted installation must have an understandable minimal setup.

## 3. Distinguish source, research, and lasting knowledge

### 3.1 Original source
The original article, dataset, paper, thread, company announcement, etc. Display a direct original link. Snapshot/source hashes are stored where rights and access permit. Do not silently edit saved raw evidence.

### 3.2 Independent investigation / research report
Commissioned research **must add information beyond the original**: verify claims, inspect methodology/controls, find relevant follow-ups and independent reactions, contrast alternative results, and link to prior knowledge. Explicitly distinguish evidence-supported criticism from popular opinion or unsupported community commentary.

A report that restates only the primary article has near-zero research-added value and should recommend the original instead. The principal may always request a deep dive regardless of automatic ranking.

### 3.3 Long-lived LLM Wiki
Use the existing ialchemist-dev/llm-wiki contract, especially SCHEMA.md:
- `raw/`: immutable input and evidence; preserve provenance.
- `wiki/`: maintained pages for `source`, `entity`, `concept`, `comparison`, and `synthesis`.
- `wiki/index.md`, `wiki/log.md`: navigation and append-only record.
- Obsidian wikilinks for navigable relationships; no unsourced claims.
- Contradicting claims are flagged, not silently overwritten.
- Agent can autonomously do clerical cross-linking, but material meaning-changing interpretations require explicit review.

Do **not** create a parallel source-of-truth knowledge database. Focu deliveries are historical, versioned *research outputs*; Wiki pages are living *knowledge syntheses*. A later Wiki revision does not rewrite historical articles.

Relationship types proposed (grounded links only): `supports`, `contradicts`, `extends`, `compares_with`, `depends_on`, `addresses_question`. Each relationship carries evidence refs, creation time and confidence; semantic similarity is insufficient to assert a causal or dependency edge.

## 4. Separate two graphs

**Knowledge graph:** Evidence-backed concepts, claims, entities, research and their typed relationships.

**Personal relevance graph:** Explicit interests, unresolved questions, current work goals, areas of expertise/novice knowledge, active research intents, and time-sensitive concerns.

A relevance relation answers **why this matters to this principal**, not whether the underlying claim is true. Reading and listening behavior may inform *ephemeral interest hypotheses*, but must not silently turn into a stable expertise statement or philosophical stance.

## 5. The information gate: explicit output decisions

For every source candidate, build a short, auditable decision record. The decision options are:

| Action | When appropriate | Principal experience |
|---|---|---|
| `suppress` | Duplicate, spam, low-information or untrusted content | No interruption; decision remains auditable |
| `index_only` | Legitimate fact, low immediate relevance | Update evidence/knowledge; no Inbox item |
| `recommend_original` | Original provides high value with little need for synthesis | Original link + one grounded reason |
| `briefing_candidate` | Important change, high expected knowledge or decision impact | One compressed but faithful daily segment |
| `investigate` | Consequential and uncertain; cross-checking likely adds value | Evidence-based report, subject to budget/approval |
| `time_sensitive_alert` | Explicitly important and urgent, within configured alert cap | Rare interruption with clear reason |

This is a **proposal** for the next decision engine, not a claim that these states already exist in the repo.

### Ranking rubric (initially transparent, not a black-box engagement model)
- **Marginal knowledge gain:** How different is this from what is already in the Wiki?
- **Decision / goal relevance:** Does it affect the principal's currently stated questions or work?
- **Evidence strength:** Original source quality, independent confirmation and scope.
- **Consequence / surprise:** Does it meaningfully update or challenge an existing belief?
- **Timeliness:** Would delayed delivery materially reduce usefulness?
- **Attention cost:** Minutes of listening/reading, repetition and cognitive overhead.
- **Diversity and exploration:** Ensure important contrarian/cross-domain evidence is not suppressed merely for being outside recent interests.

Scores are heuristic, auditable recommendations, **not estimated truth probabilities**. Initially prefer reason codes and coarse levels to arbitrary pseudo-precise weighted sums. Differentiate `low relevance` from `low confidence`; the latter can be a *reason to investigate*, not to ignore.

Every decision stores the primary URL, selected action, reason codes, uncertainty, policy version, and what was rejected. Periodically sample suppressed candidates to audit missed high-value information. Never learn a preference only from a click.

## 6. Daily briefing and depth ladder

**Daily Briefing:** one integrated 30–40 minute *target* audio report and a readable companion outline. It includes valuable registered-source updates, completed principal-requested research findings, and warranted follow-ups/knowledge changes. This is NOT an invitation to generate a separate long-form audio for every article.

Use the 30–40 minute target as an **attention budget, not a quota**. Deliver a shorter report when content has low value; record over-budget material as deferred with reasons. Avoid padding, repetition, theatrical show packaging and invented transitions. Make each segment traceable to source items and Wiki/claim IDs; use chapters and "open original / read research" navigation when feasible.

**Depth ladder:**
1. Primary source + brief relevance explanation.
2. Daily briefing segment (high-density update).
3. Independent investigation / article (demonstrable added value).
4. Optional standalone long-form spoken adaptation and, later, optional video.

The article is read-first. Standalone audio for an individual commissioned research item still requires explicit opt-in; the **daily compilation may mention its results** without granting permission to create a separate standalone audio. Preserve a single content identity and shared Inbox/Archive status for article/audio of that item.

**Open implementation decision:** PR #23's current daily policy permits *registered sources only*. This RFC proposes daily summaries of principal-initiated findings as well, while retaining explicit standalone-audio opt-in. This is a product-policy change requiring owner approval and a coherent data-model migration; do not simply merge PR #22 and #23 and assume their prior rules remain compatible.

## 7. Research, article, and audio quality contract

**Research quality:** Identify the actual claim, methods, relevant numbers and units, comparisons, caveats, independent confirmation or lack thereof, critical counterevidence, and relevance to existing knowledge. Separate verbatim citations, facts, external opinions and new inference.

**Article quality:** Apply `references/audience-profile.md` to expert/novice depth, and a proposed new `references/research-standards.md` to critical methodology. The principal authors persistent policy updates through explicit feedback, dated changelogs and version hashes.

**Briefing form:** Use `references/briefing-style.md` (if/when PR #22 is integrated); keep it responsible for *form*, not expertise or evidence adjudication.

**Audio quality:** Compose a **listenable spoken adaptation**, not a robotic word-for-word article reading and not a free rewrite that drops substance. Run structure, figure and semantic fidelity review on the spoken script **before** quality TTS; run decode, duration, ending and pronunciation checks **after** synthesis. No unapproved voice or provider becomes the default.

**QC receipt for each output:** input source IDs/hashes, model/prompt policy versions, section/figure coverage, evidence gaps, audience mismatch patterns, human-review requirements, pass/fail/blocked reasons, cost and final artifact ID. A QC pass does not imply independent factual truth.

## 8. Explicit data interface candidates (not yet implemented)

A minimal logical record for the information gate:

~~~json
{
  "candidate_id": "candidate_stable_id",
  "source_ref": "source_id_or_url",
  "principal_context_version": "v1",
  "wiki_snapshot": "commit_sha",
  "claims": ["claim_id"],
  "novelty": "new|known|disputed|unclear",
  "evidence_strength": "strong|mixed|weak|unknown",
  "decision": "suppress|index_only|recommend_original|briefing_candidate|investigate|time_sensitive_alert",
  "reason_codes": ["NEW_EVIDENCE", "CHALLENGES_PRIOR_CLAIM"],
  "attention_estimate_minutes": 2,
  "policy_version": "v1",
  "human_review_required": false
}
~~~

This is a schema proposal, not a migration or an accurate numeric prediction. Preserve existing Focu `content_id` and `intent_id` identities and older consumption states; avoid incompatible duplicate IDs.

## 9. Feedback and continuous improvement

Feedback should identify **where the process failed**, not merely whether an item was "liked":

- Selection: valuable item omitted, low-value item included, repeat delivered.
- Source quality: secondhand source mistaken for original.
- Research: unverified assumption, missing control, failure to seek contradiction.
- Personalization: too basic, too obscure, irrelevant to current question.
- Expression: poor brief density, unsuitable script, pronunciation or audio quality.
- Wiki: missed link, erroneous link, outdated/contradictory synthesis.

Preserve the principal's free-form feedback as an append-only record linked to the item, actual source, generation manifest and versions. Agent may fix mechanical issues automatically and propose policy changes, but **must not silently rewrite stable principal preferences or knowledge judgments**.

Validation of improvement requires replaying fixed benchmark inputs through the old and new policy, checking failures and regressions, not simply declaring a new prompt "better".

## 10. Architecture and ownership

Recommended simple modules:
- `focu.collect` — source monitors and one-time intents.
- `focu.gate` — evidence-aware candidate triage and attention decision log.
- `focu.research` — primary evidence retrieval and independent investigation.
- `focu.wiki_bridge` — propose/apply source-backed LLM Wiki changes.
- `focu.editorial` — personalized article and integrated daily script.
- `focu.media` — authorized, QC-gated audio and future video variants.
- `focu.reader` — immutable published snapshots, chapter links, one-item consumption/restore.
- `focu.feedback` — explicit corrections, policy change proposals and regressions.

These are *logical boundaries*, not mandates to split packages. Reuse current SQLite, Markdown, Git, and Muse Artifact publishing, and preserve the current independent server/VM arrangement. Avoid premature graph DB, vector DB, accounts, notification services and hidden cloud infrastructure.

## 11. Evaluation: what does "saves attention" mean?

Define a small, manually annotated benchmark set: genuine source articles plus principal-commissioned research, including important negations, duplicates, tempting low-value content and high-value out-of-interest findings.

**Measure**:
- Valuable-item precision in the briefing and **miss rate** in a sample of suppressed items.
- Novel evidence delivered per 10 minutes (qualitative principal judgment, not fake metric certainty).
- Rate of incorrect/unsupported central claims, missing hard figures and unnoticed contradictions.
- Research-added value vs reading only the original.
- Redundant re-explanations of known material.
- Minutes spent by principal vs estimated manual triage.
- Long-term wiki link accuracy and resolution of contradictions.
- Provider/script/audio fidelity and cost per accepted output.

Guard against self-serving benchmarks: human-approved ground truth, sampled negatives, versioned datasets, and visible failures. No optimizing solely for consumption or opening a link.

## 12. Delivery roadmap (not a day-by-day schedule)

**Milestone 0 — policy consolidation.** Review and approve this RFC. Resolve the PR #22/#23 daily inclusion conflict, define principal terminology, and set measurable invariants. No production behavior change before agreement.

**Milestone 1 — useful triage.** Implement an auditable gate with original links, source evidence, suppression sampling and `recommend_original`. Run shadow mode alongside existing briefing; compare decisions without suppressing live critical items.

**Milestone 2 — Wiki-backed research.** Integrate llm-wiki SCHEMA-based ingest/query/lint; cite claim relationships; ensure Wiki updates are reviewable and don't overwrite raw sources. Pilot on 10–20 substantive research deliveries.

**Milestone 3 — principal-calibrated editorial.** Launch an integrated, chaptered daily briefing from both approved source and research findings; use rubric and attention budget, verify references and multi-item QC. Keep individual research audio opt-in.

**Milestone 4 — feedback and improvement.** Owner speech-to-feedback captures exact item/issues, proposes versioned policy changes, and compares benchmark before/after. Optional quality voice/video only after approved media and QC.

Every milestone requires test fixtures, an independent private Muse Artifact acceptance, rollback path, and an explicit owner merge/deployment decision.

## 13. Risks / open questions

- **False negatives:** a gate that saves attention by dropping essential news is a failure. Define explicit recall audits and missed-critical alerts.
- **Feedback loop bias:** personalization can harden into an echo chamber; audit disconfirming evidence and exploration.
- **Evidence rights and trust:** original media may be paywalled or not reusable. Store legal metadata and quotes where permitted; link rather than rehost wholesale by default. Web content is untrusted input (prompt injection threat).
- **Correlated sources:** independent quotations often repeat the same claim; distinguish truly independent verification from syndicated repetition.
- **Knowledge drift:** detect contradictions and let claims change without rewriting history.
- **Expense:** daily 30–40 minute quality audio, research and media may be expensive; user-controlled model/provider/cost ceilings required.
- **Open source distribution:** some Muse-specific Artifact APIs may be nonportable. Provide a documented interface and alternative reader/publisher adapter before claiming provider-agnostic installation.
- **Audio route:** high-fidelity host-authored script + independent TTS is recommended but not yet approved/deployed; no unapproved paid service should be enabled.

## 14. Explicit owner decisions required before implementation

1. Confirm `person` (public), `principal` (technical), `you` (UI).
2. Confirm utility-over-engagement as a hard optimization constraint.
3. Confirm whether a daily briefing may include **summaries of principal-requested research** while standalone item audio remains opt-in (proposed yes).
4. Confirm a limited, transparent gate with retrospective missed-item sampling.
5. Confirm how/when the Wiki bridge may commit changes and which inferences require review.
6. Later: choose a high-quality script/TTS route and voice by listening, not by provider marketing.

**Sources:** existing Focu implementation in ialchemist-dev/focu, and the owner-maintained ialchemist-dev/llm-wiki/SCHEMA.md. Competitor context in `docs/research/COMPETITIVE_LANDSCAPE_2026-11-06.md`.

**No source code, database, registered source, production audio, or scheduled process is changed by this RFC.**
