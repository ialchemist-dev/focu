# Focu 竞品与开源生态调研 — Attention Sovereignty Landscape

**Date:** 2026-11-06
**Status:** Desk research based on official documentation and canonical GitHub repositories; NOT a hands-on installation benchmark
**Scope:** AI feed/news intelligence, research agents, personal knowledge management, audio briefings, and reusable infrastructure
**Related RFC:** [Attention Sovereignty Vision](../rfc/ATTENTION_SOVEREIGNTY_VISION.md)

## 0. Executive takeaways

**Main finding: Focu is entering a real, increasingly crowded product space.** It would be false to claim that no other product combines AI news triage, personalization, feeds, knowledge search, daily briefs or audio. Several already do, and some are mature open-source systems.

The strongest direct comparisons are **NewsBlur, Folo, Inoreader and Readwise Reader**. The strongest adjacent personal-agent/knowledge comparisons are **Khoj, Open Notebook, SurfSense, GPT Researcher and AnythingLLM**. For ingest/archive infrastructure, inspect **RSSHub, Miniflux, FreshRSS and Karakeep**.

The plausible *distinctive direction* of Focu is the **explicit combination** of:
- Optimizing *utility per minute of the principal's attention*, not session engagement;
- Source-first, independently critical research rather than automatic paraphrase;
- Using the person's existing **evolving, evidence-backed LLM Wiki** to estimate **marginal knowledge gain**, contradictions and missing knowledge;
- An auditable **information gate** that can recommend the original, investigate, defer or say nothing;
- A single-person self-hosted/open-source system, with natural-language feedback that updates approved versioned policies rather than hidden behavioral profiles;
- Integrated original → brief → research article → optional high-fidelity audio/video, with one content identity.

**This is a product hypothesis to test, NOT a proven unique capability.** Related projects already address some or many of these features. We must compare actual behavior on a shared benchmark.

## 1. Research method and interpretation

1. **Feature evidence:** product-owned websites/docs and canonical GitHub READMEs, checked on 2026-11-06. Statements about what products lack mean *not established in the reviewed primary documentation*, not proof of impossibility.
2. **Popularity:** GitHub repository metadata retrieved from GitHub API; stars/forks are a snapshot (change daily). Verify canonical repo carefully: forks and similarly named mirrors can have 0 stars and misleading descriptions.
3. **No installation benchmarking** was performed. Reliability, exact prompt fidelity, quality of actual audio, pricing, real cross-device persistence and self-host installation friction are **UNVERIFIED** unless official documentation supports a narrow statement.
4. **Stars ≠ quality, suitability or sustainability.** Check release activity, documentation, licenses, open issues, long-term maintainability, and test with representative tasks before reuse.

## 2. The closest products — detailed comparison

### 2.1 NewsBlur — probably the closest *open-source information gate*

**Official:** https://www.newsblur.com/  
**Repo:** https://github.com/samuelclay/NewsBlur

Verified official capabilities: user-trained article classifiers by author/title/tag/text, duplicate article clustering, daily briefings, story playback/read-aloud, AI questions, multiple native clients, self-host via Docker, MCP/CLI integration, full-text archive, no ads/tracking/algorithmic social feed as stated by its site. See https://www.newsblur.com/features and https://www.newsblur.com/.

**Why this matters:** Do **not** claim Focu is the first open-source, self-hostable, AI-assisted information filter focused on saving reading time. NewsBlur is already strong evidence to the contrary.

**Focu opportunity to test:** Can Focu explain relevance using the principal's structured knowledge gaps, independently evaluate claims and update an evidence-backed Wiki more effectively than a classifier + summarizer? NewsBlur's current public docs do not establish this precise cumulative evidence-graph workflow, but absence from docs is not proof it has no equivalent.

**What to learn:** simple RSS UX, trainable relevance controls, duplicate grouping, archive reliability, MCP interoperability.

### 2.2 Folo — highly competitive AI feed and scheduled digest system

**Official repo:** https://github.com/RSSNext/Folo

Official README describes AI questions over entries/feeds/folders, Timeline Summary, AI translation and summarization, scheduled AI tasks that write daily/weekly briefings, TTS, cross-platform apps, RSSHub integrations and actions exporting to Obsidian, Readwise, Zotero and Readeck.

**Focu opportunity:** Difference cannot be "RSS + AI + scheduled briefing + Obsidian export." It must be *ongoing source-backed judgment and evidence-aware attention gating* rather than merely organizing and summarizing incoming feeds. Verify Folo's complete independent self-hosting path separately; open client code does not automatically imply an easily self-hosted full service.

**What to learn:** multi-format intake, low-friction subscriptions, mobile UX, feed-to-briefing workflow.

### 2.3 Inoreader Intelligence — AI reports across explicitly chosen sources

**Official:** https://www.inoreader.com/features/intelligence

Verified: AI summaries and questions over articles, folder/tag/monitoring-feed reports, automated daily/weekly reports, entity mentions with histories, rules, customizable AI provider and persona. It explicitly does **not** let AI choose which feeds appear: the person chooses sources.

**Focu opportunity:** An auditable *usefulness decision* grounded in a personal knowledge base and independent research beyond the source corpus. A folder summary alone is not sufficient Focu research, but the company already addresses signal-over-noise and user control; do not portray it as purely an attention-maximizer.

**What to learn:** powerful source rules, scheduled digest defaults, provenance and explicit-source control.

### 2.4 Readwise Reader / Global Ghostreader — reading plus library-wide agentic knowledge discovery

**Official:** https://docs.readwise.io/reader/ and https://docs.readwise.io/reader/guides/ghostreader/global

Verified: RSS, articles/PDF/EPUBs and highlights; custom AI prompts, document chat, library-wide cited retrieval, searching for connections between saved documents, inbox triage, MCP/skills (2026 update), TTS with quality voices.

**Focu opportunity:** Cannot claim that connecting articles to a person's prior reading is an unoccupied niche; Global Ghostreader already covers cited, library-wide discovery. More defensible claim: Focu proposes *proactively maintaining and testing an independent evidence/claim Wiki*, and ranking new information by marginal utility instead of mainly supporting a reading library.

**What to learn:** highlighting, citations that jump to source passages, library-wide search, audio controls, stable reader UX.

### 2.5 Feedly AI — evidence that "save attention" is already a commercial goal

**Official:** https://feedly.com/ai and https://docs.feedly.com/article/764-what-is-an-ai-feed-feedly

Feedly AI explicitly markets reducing noise, tracking concepts and saving research time, especially for market/threat intelligence. AI Feeds filter topic-relevant stories instead of ingesting every source article.

**Focu opportunity:** Different principal and business model (one privately self-hosting person vs professional/enterprise intelligence), and Focu's planned *independent assessment + personal knowledge continuity*. **Not** the generic assertion that no other system aims to save attention.

## 3. Research, personal knowledge and audio competitors

### 3.1 Khoj — personal second brain + research automations
https://github.com/khoj-ai/khoj

Official docs: self-hosted personal AI; searchable private documents, web research, configurable agents and scheduled research/newsletters. Strong overlap with personalized knowledge retrieval and proactive research. Focu needs a product-level information-selection objective and structured Wiki-update/fact-check workflow, not just an agent with a persona. Borrow task/scheduling and local-knowledge connectors.

### 3.2 GPT Researcher — independent evidence-backed deep investigation
https://github.com/assafelovic/gpt-researcher

Official docs: research planner/executor, web/local documents, cited reports, iterative/deep research. It is especially relevant as **potential subsystem** rather than a direct daily-reading product. Focu should not reinvent general crawling/planning without comparing fidelity, citation quality, cost and API integration.

### 3.3 Open Notebook — research corpus + audio producer
**Canonical repo:** https://github.com/lfnovo/open-notebook

Official README: notebooks, source ingestion, citations, model-agnostic local/cloud support, audio/podcasts with configurable profiles, REST API. It already powers the current Focu prototype. Its README discusses script control, but the owner's *real acceptance* found that the installed scriptwriter rewrites the requested structure and drops required figures; **do not equate marketing claims with verified faithful-script execution**. Keep manuscript QC external to the provider until an actual exact-script mode is demonstrated.

### 3.4 SurfSense — research across private documents and production outputs
**Canonical repo:** https://github.com/MODSetter/SurfSense
**Official docs:** https://www.surfsense.com/docs/v2

The current v2 docs emphasize private/on-disk document research, cited answers and output transformations into briefings, presentations, study assets and audio; previous self-hosted web architecture and connectors have changed. Strong overlap with source-grounded "second brain"; less directly focused on user-specific incoming news triage in current documented v2. Check feature availability and hosted/local licensing per component.

### 3.5 AnythingLLM — broad, self-hosted private agent platform
https://github.com/Mintplex-Labs/anything-llm

Document ingestion, configurable models, agent workflows, scheduled tasks, local execution and custom memory. More an **infrastructure/agent platform** than a specific daily information gate. Focu should stay small and integrate with such an agent where useful, rather than compete on having the most generic tools.

### 3.6 Google NotebookLM — source-grounded synthesis and audio reference
https://blog.google/innovation-and-ai/products/notebooklm-update-october-2024/

Source-grounded Q&A, custom Audio Overviews and adjustable focus/expertise; official docs explicitly state overviews need not be comprehensive. Compare voice quality and natural delivery, but fidelity cannot be assumed just because audio sounds professional. A proprietary alternative to owning/editing every knowledge artifact.

### 3.7 Huxe — a cautionary product-history case, NOT a current competitor
https://huxe.com/

Its official site says Huxe was wound down, removed from stores May 21, 2026, and the service stopped **May 28, 2026**. It previously advertised dynamically personalized daily audio, synchronized visual context and interruption-based questions. **Lesson:** personalization and audio UX are feasible, but portability, operating cost and lifecycle durability are core design issues. Do not list Huxe as an active service.

## 4. Reusable open-source building blocks

- **Karakeep** https://github.com/karakeep-app/karakeep — AI-tagged bookmarks, RSS intake, preserved pages, semantic search, mobile clients. Strong intake/archive reference.
- **RSSHub** https://github.com/DIYgod/RSSHub — extensive RSS routes for non-RSS sites. Integrate as a source adapter; Focu should not duplicate broad community-maintained scraping routes.
- **Miniflux** https://github.com/miniflux/v2 — intentionally minimal RSS reader; example of low-complexity feed state and retrieval.
- **FreshRSS** https://github.com/FreshRSS/FreshRSS — established self-hostable feed aggregation and API ecosystem.
- **Linkwarden** https://github.com/linkwarden/linkwarden — self-hosted preservation/bookmark management, good provenance retention ideas.
- **NewsBlur and Folo** also supply substantial potential interoperability surfaces; assess integration licenses and terms before using code.

Avoid using a complex general framework merely because it is popular. Prefer one narrowly justified adapter at a time.

## 5. GitHub activity / maturity snapshot (canonical repos)

**Snapshot:** 2026-11-06, live GitHub repository metadata (stars/forks). Counts are **not** test results and do not predict reliability.

| Project (canonical GitHub) | Stars | Forks | License | Focu-relevant strength |
|---|---:|---:|---|---|
| [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm) | 68,015 | 7,674 | MIT | Generic private AI/agents |
| [RSSHub](https://github.com/DIYgod/RSSHub) | 46,848 | 10,280 | AGPL-3.0 | Source adapter ecosystem |
| [Open Notebook](https://github.com/lfnovo/open-notebook) | 41,705 | 4,793 | MIT | Multi-source notebooks/audio |
| [Folo](https://github.com/RSSNext/Folo) | 39,241 | 2,154 | AGPL-3.0 | AI RSS, daily digests |
| [Khoj](https://github.com/khoj-ai/khoj) | 38,030 | 2,537 | AGPL-3.0 | Personal knowledge/research |
| [GPT Researcher](https://github.com/assafelovic/gpt-researcher) | 30,524 | 4,183 | Apache-2.0 | Autonomous cited investigation |
| [Karakeep](https://github.com/karakeep-app/karakeep) | 30,372 | 1,621 | AGPL-3.0 | Bookmarks/AI tagging |
| [Linkwarden](https://github.com/linkwarden/linkwarden) | 20,333 | 893 | AGPL-3.0 | Preservation/archives |
| [SurfSense](https://github.com/MODSetter/SurfSense) | 16,796 | 1,600 | Apache-2.0 | Personal document research |
| [FreshRSS](https://github.com/FreshRSS/FreshRSS) | 16,519 | 1,339 | AGPL-3.0 | Self-hosted feed backend |
| [Miniflux](https://github.com/miniflux/v2) | 9,895 | 967 | Apache-2.0 | Minimal feed state/API |
| [NewsBlur](https://github.com/samuelclay/NewsBlur) | 7,681 | 1,047 | MIT | Trainable attention filter + briefs |

Counts are from GitHub API for the exact linked repositories; do not accidentally use forks with similar names (e.g., a low-star Open Notebook mirror). Before selecting a dependency check current repository metadata, license, release cadence and outstanding maintenance issues.

## 6. Comparative capability view — conservative assessment

Legend: **D** = documented feature; **P** = partial/adjacent; **?** = not established from primary docs checked (not "absent"); **F** = proposed Focu vision (not implemented).

| Product | Ongoing feed collection | AI prioritization/briefs | Independent deep research | Cumulative personal knowledge | Personal audio | Self-host code |
|---|---|---|---|---|---|---|
| NewsBlur | D | D | P | P | D | D |
| Folo | D | D | P | P (exports) | D (TTS) | P (verify server path) |
| Inoreader | D | D | P (reports) | P | P | ? (commercial) |
| Readwise Reader | D | D (Ghostreader) | P | D (cited library Q&A) | D | ? (commercial) |
| Feedly AI | D | D | P (intelligence) | P | ? | ? (commercial) |
| Khoj | P | D (scheduled research) | D | D (indexed docs) | P | D |
| GPT Researcher | P | P | D | P | ? | D |
| Open Notebook | P (ingest) | P | D (source Q&A) | D (notebooks) | D | D |
| SurfSense v2 | P (documents) | P | D | D (local corpus) | D | D |
| Focu vNext RFC | F | F | F | F (maintained claims/wiki) | F | F |

**Caveats:** This is a reading of product documentation, not feature certification. All systems are evolving. "Knowledge" ranges from indexed document libraries to actively maintained claim-level synthesis; the two are not interchangeable. Focu has working prototypes, but the *full vNext loop* is not implemented.

## 7. Where Focu could actually stand apart — testable theses

| Hypothesis | Existing overlap / risk | Proposed proof |
|---|---|---|
| **Useful > engaging** | NewsBlur/Feedly already reduce noise; not categorically unique | Human-annotated high-value precision + missed-critical recall + attention minutes, against a feed baseline |
| **Marginal value against personal Wiki** | Readwise/Khoj already query long-lived libraries | New-item relevance explanations grounded to exact prior Wiki claims; correct new/known/contradicts labels |
| **Source-first independent reasoning** | GPT Researcher and intelligence suites investigate | Reports must contribute meaningful external evidence beyond source, or recommend original; expert review of claim accuracy |
| **Persistent critical independence** | Many summarizers may echo source/consensus | Test seeded disputed claims and genuine counterevidence; require uncertainty and evidence diversity |
| **Auditable "do not interrupt" gate** | AI ranking and training exist widely | Every suppressed item carries reason; sample misses and show findings to principal |
| **Natural-language owner-controlled evolution** | Custom prompts and agents already exist | Feedback points to exact failure; controlled policy change produces measured benchmark improvement without hidden profile mutation |
| **Self-hostable, open, no business-optimizing engagement** | NewsBlur/Miniflux/Khoj are self-hostable | One-person installation, portable data, no tracking, cost limits, clear local/cloud boundary |

Do not use novelty claims in the README unless these behavioral tests support them.

## 8. Product strategy / reuse recommendations

**Closest products to inspect hands-on first (in order):**
1. **NewsBlur** — trainable gate, article read states, AI daily briefing, archive and agent API. Strongest counterargument to the idea that Focu's features are alone.
2. **Folo** — AI timeline summary, mobile reading, scheduled AI reports, source formats, reader UX.
3. **Readwise Reader** — library-wide cited Ghostreader, knowledge links, human annotation and premium speech UX.
4. **Inoreader Intelligence** — controlled source corpus, folder reports and entity monitoring.
5. **Khoj** — self-hosted knowledge/search + scheduled research.

**Subsystem candidates for small experiments:** RSSHub for unsupported source adapters; GPT Researcher for evidence retrieval/independent investigation; Karakeep or a light archive mechanism for saved pages; Open Notebook as research/audio integration only when its *real* output passes hard QC.

**Do not** migrate existing Focu into any of these wholesale without evaluating privacy, integration licensing and how much of Focu's attention-decision logic would be lost.

## 9. Three controlled experiments before major development

### Experiment A — The usefulness gate
Select ~30 real posts/updates (duplicates, popular but shallow pieces, technically consequential surprises, contradictory evidence). Have the principal label what was worth attention, independently of "would I click it?" Compare Focu proposal against NewsBlur or a simple keyword/feed baseline. Audit at least a sample of ignored posts for misses.

### Experiment B — Original or investigate?
Choose 5 genuinely important primary research articles. For each, assess whether external source cross-checking and Wiki context add real value. If not, the correct output is simply the source link and a short relevance statement. Record added claims and their evidence; don't count longer prose as value.

### Experiment C — Long-term accumulation
Ingest 10–20 source items across connected topics into the LLM Wiki and evaluate if subsequent briefing/research uses *correctly linked prior claims*, notices changed conclusions, and avoids elementary repetition. Include deliberate contradictions and unrelated but useful surprises. Do not auto-write expert/novice preferences from behavior.

## 10. Methodological cautions and open investigations

- **Source authority**: a primary paper can still be wrong. Always distinguish original observation from reliable conclusion.
- **Independence**: popular reposts are not multiple independent confirmations.
- **Copyright and paywalls**: original full text should not necessarily be hosted/republished. Prefer citation, metadata, licensed snapshots and links.
- **Popularity**: star/fork totals are discovery heuristics; practical reliability needs unit/integration tests and long-term maintenance.
- **Monetization / sustainability**: open source and noncommercial is a legitimate owner goal; it does not make GPU/audio costs disappear. A modular provider contract and explicit budgets matter.
- **Portability**: Muse is one current host, not an open-source prerequisite. Document an alternative publisher adapter.
- **Huxe shutdown**: concrete illustration of service lifecycle risk; do not misinterpret it as a prediction that every audio start-up will fail.
- **Reddit / community response**: can reveal criticisms and missing tests, but opinions must be weighed by evidence and independence, not vote totals.

## 11. Primary sources consulted

**Feed/intelligence:** https://www.newsblur.com/features ; https://github.com/RSSNext/Folo ; https://www.inoreader.com/features/intelligence ; https://feedly.com/ai ; https://docs.feedly.com/article/764-what-is-an-ai-feed-feedly

**Reading/knowledge:** https://docs.readwise.io/reader/guides/ghostreader/global ; https://readwise.io/reader/update-aug2026 ; https://github.com/khoj-ai/khoj ; https://www.surfsense.com/docs/v2 ; https://github.com/Mintplex-Labs/anything-llm

**Research/audio:** https://github.com/assafelovic/gpt-researcher ; https://github.com/lfnovo/open-notebook ; https://blog.google/innovation-and-ai/products/notebooklm-update-october-2024/ ; https://huxe.com/

**Infrastructure:** https://github.com/karakeep-app/karakeep ; https://github.com/DIYgod/RSSHub ; https://github.com/miniflux/v2 ; https://github.com/FreshRSS/FreshRSS ; https://github.com/linkwarden/linkwarden

**Personal knowledge design:** https://github.com/ialchemist-dev/llm-wiki/blob/main/SCHEMA.md

**Note:** Product capabilities and GitHub numbers can change. Re-run a fresh audit before adopting a new dependency or making public competitive claims.
