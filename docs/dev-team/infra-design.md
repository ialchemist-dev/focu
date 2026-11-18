# Infra Design — Focu 24h Multi-Agent Run

Author: Infra Designer agent. Date: 2026-11-17 (America/Denver).
Scope: (A) multi-agent framework verification + how the team's SOP maps onto it;
(B) platform ingestion survey for the owner's own feeds, following the LinkedIn
reference pattern (`~/focu-runtime/linkedin/RUNBOOK.md`: own logged-in session,
randomized human-paced sessions, hard daily cap, dedupe by URL, stop on any
owner-only step — never mass scraping).

All star counts, push dates, and license claims below were looked up live in
this run on 2026-11-17 (~08:47 UTC) via the GitHub API and repo pages.

---

## A) Multi-agent framework: MetaGPT — verified installed

### A.1 Verification result

**MetaGPT 0.8.1 is installed and import-verified** in
`~/workspace/focu-dev/framework/venv`:

- `import metagpt` → OK; version **0.8.1** (via `importlib.metadata.version`;
  the package exposes no top-level `__version__`).
- `from metagpt.team import Team` and `ProductManager, Architect,
  ProjectManager, Engineer, QaEngineer` from `metagpt.roles` → all import OK.
- `from metagpt.software_company import generate_repo` → OK.
- Venv: Python **3.11.18** (uv-managed CPython), **183 packages** installed.
- Repo facts (measured this run): FoundationAgents/MetaGPT, **71,319 stars**,
  MIT license, 6,367 commits, not archived.

The CrewAI fallback was **not** needed.

### A.2 What it actually took (honest install log)

A stock `pip install metagpt` does **not** work on this VM. Failure chain,
in order (logs: `~/workspace/focu-dev/framework/install-attempt1..4.log`):

1. **Python 3.12 is impossible.** Every PyPI release of MetaGPT (0.1–0.8.1)
   hard-pins `faiss-cpu==1.7.4`, which ships no CPython 3.12 wheels; pip's
   resolver fails with `ResolutionImpossible`. MetaGPT's own README states
   Python ≥3.9, **<3.12**. The VM ships only Python 3.12.3.
2. **Fix:** installed `uv` (0.13.8, in `framework/uv-venv`), fetched a
   standalone **CPython 3.11.18** with `UV_NATIVE_TLS=1` (system cert store,
   which includes the egress proxy CA at `/run/hatch/egress-tls/ca-bundle.pem`),
   and rebuilt `framework/venv` on 3.11.
3. **Second blocker:** MetaGPT 0.8.1/0.8.0/0.7.7 also pin `lancedb==0.4.0`,
   for which uv finds **no usable distribution** for this platform at all.
   An unpinned install silently backtracks to MetaGPT 0.1 and then dies
   building pandas 1.4.1 from source — pinning the version explicitly is
   what surfaced the real cause.
4. **Resolution:** installed `metagpt==0.8.1 --no-deps`, then installed its
   full pinned dependency set (51 requirements, frozen in
   `framework/metagpt-deps.txt`) **minus exactly two packages**:
   `faiss-cpu==1.7.4` and `lancedb==0.4.0`. Both serve only MetaGPT's
   RAG / long-term-memory vector-store subsystems, which this run does not
   use; the SOP role pipeline (Team, roles, actions) imports and loads
   without them.
5. **Config requirement:** importing `metagpt.roles` validates a global
   Config at import time and refuses to load without an `llm:` section.
   A placeholder `~/.metagpt/config2.yaml` (dummy key, never called)
   satisfies the import. **Executing** a Team run requires a real LLM API
   key, which has not been provisioned for this run — see A.4.

### A.3 SOP mapping: our team on MetaGPT's model

MetaGPT's core idea is `Code = SOP(Team)`: roles communicate through
structured artifacts (PRD → system design → task list → code → test
report), not free-form chat. That maps onto this run's SOP one-to-one:

| This run (STATE.md SOP) | MetaGPT construct | Artifact contract |
|---|---|---|
| Owner (Jerry): one-line intent, veto | `Team.invest` / requirement input | The brief in STATE.md |
| PM agent | `ProductManager` (WritePRD) | `team/pm-prd.md` — PRD, backlog, acceptance criteria |
| Infra Designer / Architect | `Architect` (WriteDesign) | `team/infra-design.md`, `team/backend-design.md` — system design, interface contracts |
| Backend developer | `Engineer` | Code on branch `dev-main` (Git Data API pushes) |
| UI developer | `Engineer` (frontend actions) | `team/ui-audit.md` + reader/UI code on `dev-main` |
| Integrator + QA pass | `ProjectManager` (task breakdown) + `QaEngineer` (review/test loop) | STATE.md cycle log lines, test results, README updates |

Rules the team keeps from MetaGPT's SOP, as conventions:

- **Artifacts over chat.** A role's output is a file or a commit, never a
  claim in a message. Downstream roles read the artifact, not the chat.
- **Publish-subscribe by file.** `team/*.md` + STATE.md are the message
  pool; the cycle log in STATE.md is the run's event ledger.
- **QA is a separate pass with veto.** The integrator does not mark a
  cycle done; the QA/reviewer check against the PM's acceptance criteria
  does — the same separation as MetaGPT's QaEngineer loop.
- **Fail-closed handoffs.** If an artifact is missing or fails its
  contract, the cycle stops and is logged, exactly as a MetaGPT role
  raises on a malformed upstream document.

### A.4 Used vs mirrored — stated honestly

**Actually used:** the installed package as the reference implementation
and vocabulary; its role decomposition and artifact types (PRD, design
doc, task list) as the team's document conventions; the verification
above that the framework genuinely runs on this hardware.

**Mirrored as conventions, NOT executed:** MetaGPT's runtime
(`Team.run()`, `generate_repo()`). Three reasons:

1. Executing it needs a live LLM API key in `~/.metagpt/config2.yaml`;
   none is provisioned for this run (only a placeholder for import
   verification).
2. The executors in this environment are Muse subagents dispatched by
   the main agent. They already have the tool integrations this run
   depends on — Git Data API pushes to `dev-main`, the browser, the focu
   test suites — which MetaGPT's Engineer role would each need custom
   actions to reach.
3. Two of MetaGPT's pinned subsystems (faiss/lancedb RAG memory) are not
   installable on this VM at all (A.2), so a full-fidelity MetaGPT run
   is not even available here today.

If the owner later provisions an OpenAI-compatible key for the framework
venv, the right first experiment is one bounded feature run through a
real MetaGPT Team, scored against the subagent pipeline on the same
acceptance criteria. Until then, claiming "we run MetaGPT" would be
false; we run its SOP.

---

## B) Platform ingestion survey — the owner's own feeds

### B.0 The constraint every route is judged against

From the LinkedIn reference implementation (RUNBOOK.md) and the design
纲领 (`attention-sovereignty.md`): the agent reads the owner's **own**
feed, in the owner's **own session**, at **human pace**, under a **hard
daily cap** (LinkedIn: 50 items/day in randomized sessions of 5–10,
09:00–24:00 local), dedupes by canonical URL, skips the owner's own posts
and ads, captures author + ≤30-word factual gist + permalink, and **stops**
on CAPTCHA / checkpoint / any owner-only step. Volume is deliberately
tiny; the product is attention compression, not data acquisition. Routes
designed for bulk crawling, account matrices, or publishing are
disqualified as primary routes no matter how popular they are.

A cross-cutting finding first: **DIYgod/RSSHub** (47,068 stars, AGPL-3.0,
pushed 2026-11-17 — same day as this survey; route files verified in-tree)
is the best *per-creator* feed layer: `xiaohongshu` (user notes, boards),
`instagram` (user), `facebook` (page, group, photos, reels), `youtube`
(channel, user, playlist, subscriptions). But RSSHub's model is
per-creator/per-page surfaces, several cookie-assisted — **it has no
personalized home-feed route for any of the four platforms**. It fits
Focu Exchange source packs (lists of named creators) excellently; it does
not replace the own-feed session pattern. Recommendations below are for
the own feed; RSSHub is the standing complement for pack-style sources.

### B.1 小红书 / RedNote

| Candidate | Stars | Last push | License | Notes |
|---|---|---|---|---|
| NanmiCoder/MediaCrawler | 71,253 | 2026-11-17 | **Non-Commercial Learning License 1.1** (verified from LICENSE file) | Multi-platform (XHS/抖音/快手/B站/微博/贴吧/知乎）; supports HomeFeed; default CDP mode drives the owner's **existing Chrome with its existing login** |
| cv-cat/Spider_XHS | 8,502 | active (changelog through 2026-09) | **No LICENSE file** (README badge claims MIT; legally all-rights-reserved) | Reverse-engineered signing (x-s/x-t/…); cookie/QR/phone login; home feed + user notes + search — but design center is bulk ops: account matrices, publishing, KOL marketing |
| ReaJason/xhs | 2,239 | 2025-07-01 (~16 months stale) | MIT | Thin signing SDK; maintenance has lapsed |
| RSSHub `xiaohongshu` | (above) | (above) | AGPL-3.0 | User notes + boards with owner cookie; no home feed |

**Recommendation: MediaCrawler, CDP mode, as an external local tool.**
It is the only candidate whose operating shape *is* the LinkedIn pattern:
it attaches to the owner's real Chrome session (real login, real cookies,
real fingerprint), reads the home feed, and is by far the most actively
maintained option in this space (pushed the same day as this survey).
Focu must consume it the way `focu/collectors.py` already consumes
LinkedIn exports — MediaCrawler runs outside Focu and hands over an
export payload; Focu only normalizes and validates it (B.5). **It must
not be vendored**: its license permits non-commercial learning use only
and expressly forbids large-scale crawling, so it can be an owner-run
local tool, never a bundled component of the Focu distribution.

**Main risk:** 小红书's risk control （风控） is the most aggressive of the
four platforms, and the account is bound to the owner's real-name phone
identity — a ban costs more than on any other platform here. Mitigations
are the LinkedIn ones, tightened: CDP on the owner's own browser only,
caps at or below LinkedIn's, randomized sessions inside the owner's
plausible active hours, stop on the first risk-control interstitial.
Secondary risk: the license means this route can be withdrawn from the
design at any time; the RSSHub per-creator route is the fallback.

### B.2 Instagram

| Candidate | Stars | Last push | License | Notes |
|---|---|---|---|---|
| instaloader/instaloader | 13,923 | 2026-11-01 | MIT | Read-oriented downloader/reader; login with **session-file reuse**; `get_feed_posts()` — the logged-in user's own feed — verified present in source |
| subzeroid/instagrapi | 7,159 | very active (3,017 commits, 252 releases) | NOASSERTION (custom) | Private **mobile** API client; session persistence; its own README warns private-API automation is fragile and steers account-owned production use to official APIs / hosted providers |
| RSSHub `instagram` | (above) | (above) | AGPL-3.0 | Per-user route via web API + session config; no home feed |

**Recommendation: Instaloader.** It is the conservative match: MIT,
mature, read-only in spirit, logs in once and reuses a saved session
(the LinkedIn "saved login, don't re-login in a loop" rule), and it
natively exposes the owner's own feed via `get_feed_posts()` plus
profiles/stories for pack-style sources. instagrapi is the documented
fallback if a surface Instaloader lacks (e.g. reels ordering) is ever
needed — accepting its custom license and fragility knowingly.

**Main risk:** Meta enforcement. Any unofficial-API read can trigger a
checkpoint or lock on the owner's account (`jerry94242`, his personal
account). Mitigations: session reuse only, lowest practical daily cap,
no password re-login loops, and the LinkedIn stop rule verbatim — a
challenge/checkpoint ends the session and is reported, never solved.
Note the official Instagram Graph API offers no home-feed surface at
all, so there is no zero-risk route; there is only a low-volume one.

### B.3 Facebook

| Candidate | Stars | Last push | License | Notes |
|---|---|---|---|---|
| kevinzg/facebook-scraper | 3,329 | **2024-06-22 (~17 months stale)** | MIT | 447 open issues; effectively unmaintained; never strong on the logged-in personal feed |
| RSSHub `facebook` | (above) | (above) | AGPL-3.0 | Page, group, photos, reels routes — public/Page surfaces, not the personal news feed |
| Meta Graph API (official) | — | — | — | No personal news-feed endpoint exists for third-party apps |

**Recommendation: no library — replicate the LinkedIn pattern itself.**
Facebook is the one platform where the honest answer is that no mature,
maintained open-source tool reads the owner's personal feed. The route
is the one Focu already operates for LinkedIn: scheduled agent browser
sessions on the owner's own logged-in session, producing the same export
payload shape (`author / gist / permalink`) into a platform store, then
an emit adapter (B.5). Zero new dependencies. RSSHub's page/group routes
cover the pack use case (named Pages and Groups) separately.

**Main risk:** session fragility and checkpoints — Facebook challenges
unusual-session activity aggressively, and a browser-session route is
the most brittle of the four to UI changes. Keep Facebook at the lowest
volume of the four platforms, and treat any checkpoint as a full stop
(owner-only step), per the runbook rule.

### B.4 YouTube

| Candidate | Stars | Last push | License | Notes |
|---|---|---|---|---|
| yt-dlp/yt-dlp | 208,529 | 2026-11-17 | Unlicense | Already Focu's production transcript engine (with the POT-provider + android-client fallback ladder) |
| YouTube Data API v3 (official) | — | — | — | OAuth access to the owner's own subscriptions list; documented default quota 10,000 units/day |
| RSSHub `youtube` | (above) | (above) | AGPL-3.0 | Channel/user/playlist routes; also a `subscriptions` route using the owner's cookies |

**Recommendation: keep the existing production stack; add nothing.**
Discovery via channel RSS + transcripts via yt-dlp is already the
strongest route of any platform in this survey — official RSS for
discovery, the most-maintained downloader in existence for bodies, and
Focu's selector already withholds videos whose transcripts can't be
retrieved. If an own-subscriptions sync is ever wanted, the Data API v3
with the owner's OAuth is the official surface (RSSHub's subscriptions
route is the no-new-code alternative). 

**Main risk:** the known one — transcript availability and YouTube's
bot checks from datacenter IPs, already mitigated in production (POT
provider, android-client fallback, ASR as last resort). Lowest risk of
the four platforms.

### B.5 Adapter interface sketch — how every route plugs into Focu

Focu already has **two** seams; a new platform adapter implements both
sides of one contract and registers like LinkedIn did. No new plumbing.

**Seam 1 — daily digest (how LinkedIn Feed enters the briefing).**

1. Register the source in `sources.yaml`: `name`, a new `type` (the
   validator's known types today are `rss / blog / youtube / x /
   linkedin` — add e.g. `rednote`, `instagram`, `facebook`), `channel`,
   `max_items_per_day` (counts digest units, not items).
2. An external collector (agent session / CDP tool / library CLI) writes
   raw items into a platform store (SQLite, dedupe by canonical URL
   across all days), under a **plan contract** copied from
   `linkedin_plan.py`: seeded daily plan, sessions of 5–10, daily cap,
   active window in the owner's timezone.
3. `<platform>_to_units.py emit --day D --out units.json` adapts one day
   into **zero or one** unit of the exact shape the pipeline ingests:
   `{source, title, url, published_at, body}` where `url` carries an
   identity-disambiguating parameter (`?day=<date>` — a bare feed URL
   collapses every day into one content_id; this bug already cost one
   day's LinkedIn digest on 2026-11-15), `published_at` is a full ISO
   timestamp with UTC offset (date-only values are silently ignored by
   recency scoring), and `body` is numbered lines of
   `author — gist (permalink)`, gist ≤30 words, factual.
4. The briefing job appends the unit to `units-<D>.json` before ingest;
   **adapter failure never blocks the briefing**.

**Seam 2 — observation import (how `focu/collectors.py` already works).**

5. A focu-side normalizer `<platform>_feed_from_export(payload) ->
   list[SourceRecord]`, mirroring `linkedin_feed_from_export`:
   strict per-platform URL validation (scheme + host + post-path),
   requires a permanent permalink and non-empty text, stamps
   `platform / author / published_at / collected_at / method`.
   Records land in `ObservationStore` (dedupe + change detection).
6. **No credentials in Focu, ever** (the collectors module's stated
   contract: "No credentials are stored in Focu"; the LinkedIn
   normalizer's docstring: "never launch or automate a login").
   Collection is always external; logins live in the owner's browser /
   vault; Focu only validates what it is handed.

**Behavioral contract (from the LinkedIn runbook, applies to all four):**

7. Own session only; skip the owner's own posts and ads/promoted items.
8. Human pace: seconds between actions, randomized session times inside
   the owner's plausible active hours.
9. Enumerated stop conditions — CAPTCHA, checkpoint, phone-app approval,
   unretrievable one-time code: stop, do **not** mark the session done
   (shortfall carries forward), report the exact step demanded.
10. A saved login is used through the platform's normal login flow when
    a session expires; owner-only verification is never automated and
    CAPTCHA solvers are never used.

An adapter that satisfies 1–10 is interchangeable with LinkedIn's from
the pipeline's point of view — which is the point: the platform-specific
risk lives in the external collector; Focu's core never changes.

---

## Appendix — measurement log (all 2026-11-17, this run)

- GitHub API: RSSHub 47,068★ AGPL-3.0 pushed 2026-11-17T08:12Z;
  MediaCrawler 71,253★ pushed 2026-11-17T07:19Z, license NOASSERTION via
  API / full text read from repo = Non-Commercial Learning License 1.1;
  Instaloader 13,923★ MIT pushed 2026-11-01; yt-dlp 208,529★ Unlicense
  pushed 2026-11-17; facebook-scraper 3,329★ MIT pushed 2024-06-22,
  447 open issues; ReaJason/xhs 2,239★ MIT pushed 2025-07-01.
- Repo pages: MetaGPT 71,319★ MIT, 6,367 commits; Spider_XHS 8,502★,
  252 commits, LICENSE file 404 (badge claims MIT); instagrapi 7,159★,
  3,017 commits, 252 releases, license NOASSERTION.
- RSSHub route files verified in-tree: xiaohongshu/{user,board,
  check-cookie}.ts, instagram/{index,web-api}, facebook/{page,group,
  photos,reels}.ts, youtube/{channel,user,playlist,subscriptions,
  live,community,charts,custom}.ts.
- Instaloader `get_feed_posts()` ("Get Posts of the user's feed",
  login required) verified in `instaloader/instaloader.py` source.
- MetaGPT install: attempts logged in
  `~/workspace/focu-dev/framework/install-attempt{1..4}.log`; final
  state — metagpt 0.8.1, Python 3.11.18 venv, 183 packages, import +
  Team/roles verified 2026-11-17.
