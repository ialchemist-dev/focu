# Research reports: recipe, contract and kit

Status: canonical **manual** workflow for intentional research reports and Daily-style briefings
delivered as a single responsive HTML page. It is a documented procedure plus a small kit. It does
**not** change the scheduled Daily pipeline, the Reader, delivery, or any provider prompt
(see [Integration boundary](#integration-boundary)).

Origin: three example reports (memory mechanism, habit apps, 7-day geothermal brief) were built
with this flow and the owner approved their quality. That approval covers those three samples; it
does not mean every future output is accepted. Each new report still needs its own review.

| File | Purpose |
|---|---|
| [templates/research-mission.md](templates/research-mission.md) | Self-contained English mission for the research writer |
| [templates/page-builder-brief.md](templates/page-builder-brief.md) | English brief for the page builder |
| [kit/template.html](kit/template.html) | Buildless, self-contained HTML page template (inline CSS/JS, chart renderer) |
| [kit/check_report.py](kit/check_report.py) | Stdlib structure / citation-integrity checker (QA layer A) |
| [kit/render_qa.mjs](kit/render_qa.mjs) | Optional browser render check (needs an existing Playwright) |
| [fixture/sample/](fixture/sample/) | Complete, fictional research directory that passes the checker |
| [muse-instruction.zh.md](muse-instruction.zh.md) | Copy-paste instruction for Muse (Chinese) |

## 1. Flow

```
owner purpose / question
  + selected scope and preference context (picked by hand for this run)
        │
        ▼
English research mission (templates/research-mission.md, frozen as mission.md)
        │  research writer
        ▼
report.md + notes/sources-key.md + claims.json   ── freeze ──► frozen.sha256
        │  page builder (only registered facts; additions go to addenda/addendum-N/)
        ▼
page/index.html  (one-minute top-down overview, tables/charts/diagrams, citations, limits)
        │
        ▼
QA: A structure (check_report.py) + A render (render_qa.mjs, if available)
    B semantic spot-check (reviewer named) · C owner reading
```

The **HTML page is the default deliverable** for this workflow. `report.md` is an internal research
record; do not send it to the owner as the result unless asked.

## 2. Research directory contract

```
<research_dir>/
  mission.md                 frozen  — the exact mission text the writer received
  report.md                  frozen  — writer's report (internal)
  notes/sources-key.md       frozen  — source registry (table below)
  claims.json                frozen  — structured claims; MANDATORY when any number is charted
  frozen.sha256              shasum -a 256 of the frozen files (not page/, addenda/, run.json)
  addenda/addendum-N/        optional builder additions: report.md, sources-key.md, claims.json
  page/index.html            deliverable (copied from kit/template.html)
  run.json                   provenance + honest QA states
```

Keep this directory outside the FOCU Git repo (owner data, snapshots and screenshots are not source).
Only the fictional `fixture/` lives in Git.

**sources-key.md** — one Markdown table row per source:

```
| ID | Title | Publisher | URL | Published | Accessed | Type |
| S1 | … | … | https://… | 2026-11-09 | 2026-11-14 | primary |
```

`Type` starts with `primary`, `secondary` or `vendor` (free text may follow).

**claims.json** — array of objects:

| field | rule |
|---|---|
| `claim_id` | unique across base and addenda |
| `text`, `value`, `unit` | `value` may be a number, string, null, or an object of named numbers |
| `class` | `reported_fact` · `estimate` (name `estimator` or method in `note`) · `vendor_claim` · `derived` |
| `as_of` | required except for `derived` |
| `source_ids` | non-empty; every ID registered in sources-key (base or addendum) |
| `quote` | short supporting excerpt (≤ 300 chars). Cite sources; never copy whole articles |
| `formula`, `input_claim_ids` | required for `derived` (e.g. `"C1 - C2 = 120 - 80 = 40"`) |
| `added_by` | `"builder"`, required for addendum claims |

**Freezing.** After the writer finishes, run
`(cd <research_dir> && shasum -a 256 mission.md report.md notes/sources-key.md claims.json > frozen.sha256)`.
Frozen files are never edited. If the builder needs a fact the report lacks, it creates
`addenda/addendum-N/` with its own `report.md` (what and why), `sources-key.md` (new sources) and
`claims.json` (`added_by: "builder"`). Corrections to the research itself are a new attempt
directory that links the previous one.

**run.json**

```json
{
 "slug": "…",
 "profile_version": "…",
 "applied_preference_ids": ["…"],
 "preference_source": "manual_current_context",
 "tools_actually_used": ["…"],
 "builder_addenda": [],
 "qa": {
  "render":   {"state": "passed|failed|not_run", "evidence": "<path to render-qa.json or null>"},
  "semantic": {"state": "passed|failed|not_run", "reviewer": "independent|same_worker|none"},
  "owner":    {"state": "pending|accepted|rejected"}
 }
}
```

`preference_source` is `manual_current_context`: preference IDs are chosen by hand for this run from
the owner's stated preferences. FOCU has **no** automatic preference memory today. Deleting a
preference stops it from being applied as a constraint, but similar behaviour may still appear when
another rule requires it on its own.

## 3. Page contract (kit/template.html)

Copy `kit/template.html` to `<research_dir>/page/index.html` and fill the `{{…}}` slots.

- **Self-contained.** Inline CSS/JS only. No external scripts, stylesheets, fonts or images
  (`data:` URIs are fine). No local filesystem paths.
- **Required ids:** `overview` (one-minute top-down summary: question → answer → cited takeaways →
  scope), `limits` (could-not-verify + method), `sources`, `provenance` (footer).
  "One minute" is a reading target; do not claim the overview fits one screen.
- **Citations:** `<a class="cite" href="#src-S1">S1</a>`. Each source is
  `<li class="src" id="src-S1">` in `<ol class="sources">` and links the URL exactly as registered.
- **Claim labels:** `<span class="tag estimate" data-claim="C2" data-class="estimate">估计</span>`.
  `data-class` must equal the class in claims.json.
- **Numeric charts:** declare data, the inline script draws a bar chart:
  ```html
  <figure>
  <script type="application/json" data-chart>
  {"type":"bar","title":"…","unit":"MW","series":[{"label":"Q2","value":658,"claim":"G5","key":"q2_2026"}]}
  </script>
  <details><summary>数据表</summary><table>…same numbers…</table></details>
  <figcaption>数据：claims.json G5 <a class="cite" href="#src-S1">S1</a>；派生值写公式</figcaption>
  </figure>
  ```
  Each `value` must equal the claim's value (`key` selects a field of an object value).
  Hand-drawn SVG is fine for **non-numeric** diagrams (timelines, flows, comparisons of concepts).
  If you hand-draw a numeric figure, cite its claim IDs in the caption; the checker cannot verify it.
- **Tables:** `class="cards"` with `data-label` on each `td` stacks into cards below 640px.
- **Narrative synthesis** (connective reading across items) goes in
  `<div class="synthesis"><span class="tag synthesis">叙事综合</span>…</div>`, cites the items it
  connects and adds no new facts.
- There is no fixed number of takeaways, sections or charts. Use what the question needs.

## 4. QA layers (none substitutes for another)

| Layer | Tool | Proves | Does not prove |
|---|---|---|---|
| A structure | `python3 docs/research-reports/kit/check_report.py <research_dir> [--json out.json]` | citations resolve; page URLs match registry; chart numbers equal claims; class labels match; frozen files unchanged; addenda versioned and registered; no external assets or local paths; run.json states are consistent | that a quote supports a claim; source quality |
| A render | `node docs/research-reports/kit/render_qa.mjs <url> <out-dir>` | 390px / 1440px, light/dark: no overflow, no console errors, no external requests, charts drawn, anchors land | content correctness |
| B semantic | a reviewer reads central claims against sources | support within the sample read | anything outside the sample |
| C owner | the owner reads the page | usefulness and intent | — |

Record each layer honestly in `run.json`. A check that did not run is `not_run`. Record
screenshots only when they were taken, and keep them outside Git. A semantic check by the same
worker that wrote the report is `same_worker`. It is weaker than an `independent` review and must be
labelled as such.

Render QA needs a Playwright that is already installed, and a browser. Nothing is installed by the
kit. Serve the page with a short-lived local server and stop it afterwards:

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory <research_dir>/page &
PLAYWRIGHT_MODULE_DIR=<dir containing node_modules/playwright> \
CHROME_PATH=<optional browser executable> \
node docs/research-reports/kit/render_qa.mjs http://127.0.0.1:8765/index.html <out-dir-outside-git>
kill %1
```

If Playwright is not available in your environment, write `"render": {"state": "not_run"}`. Whether a
given host (for example Muse) has these tools is unknown until checked there. Unknown does not mean
absent, and it does not mean present.

## 5. Roles and isolation

- **Research writer** answers the numbered questions and registers every source and number.
- **Page builder** lays out, charts and checks. It may not add facts except through an addendum.
- The same agent may play both roles in sequence. That is a separation of files and phases.
  It is **not** a sandbox. A self-contained mission prompt limits what the writer is *told*. It does
  not stop a full-access CLI from reading the filesystem, credentials or accounts. Do not claim
  isolation unless a separately enforced sandbox was used.

## 6. Daily light variant

For a recurring brief, reuse the same contract with a smaller mission:

- **Cover every collected item** under the existing Daily coverage rules. Nothing is invented,
  and every number is cited and classified. Whether low-relevance items may be grouped into a short
  "other items" list is still an open owner decision. Until the owner decides, do not group them.
- Connective narrative across items is allowed only as marked `synthesis` grounded in cited items.
- Skip parallel fetching, calculators and multi-round research. Run layer A, plus a citation
  spot-check.
- When a topic keeps recurring, or the owner names it, open a separate deep-research mission.

## Integration boundary

- This is a manual, agent-followed workflow. Nothing here is wired into `focu daily`, scheduled
  generation, `references/briefing-style.md`, the Reader, delivery, or podcast generation.
  Changing those needs its own issue and PR.
- `check_report.py` and `render_qa.mjs` are standalone tools under `docs/`, not part of the `focu`
  package. The unit test `tests/test_research_report_kit.py` guards the checker.
- Hosting or publishing a page is outside this kit. Use an existing, authorized channel.
- Owner profiles, wiki content, research snapshots and screenshots stay outside this repository.
