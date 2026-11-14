# Page Builder Brief

Input: a frozen `<research_dir>/` (`mission.md`, `report.md`, `notes/sources-key.md`, `claims.json`,
`frozen.sha256`). Output: `<research_dir>/page/index.html`, `run.json`, optional
`addenda/addendum-N/`. Contract: [../README.md](../README.md).

1. Copy `docs/research-reports/kit/template.html` to `page/index.html` and fill it in. Keep it
   self-contained: inline CSS/JS, no external assets, no local paths.
2. Start with the one-minute top-down overview (`#overview`): question → answer → cited takeaways →
   scope and number of unverified items. Use as many takeaways as the question needs. Do not claim
   the overview fits one screen.
3. Use only facts in the frozen files. Keep each number's class visible
   (`data-claim` + `data-class`) and cite it (`a.cite` → `#src-S#`).
4. Need a fact the report lacks? Do **not** edit frozen files. Create `addenda/addendum-N/` with
   `report.md` (what and why), `sources-key.md` (new sources) and `claims.json`
   (`added_by: "builder"`). Otherwise show the gap under `#limits`.
5. Numeric charts use `<script type="application/json" data-chart>` with values equal to
   claims.json and a data-table fallback. Derived values need a `derived` claim with formula and
   inputs. Hand-drawn SVG only for non-numeric diagrams, or with claim IDs in the caption.
6. Mark cross-item narrative as `.synthesis`, cite what it connects, add nothing new.
7. Run `python3 docs/research-reports/kit/check_report.py <research_dir>` until it passes. Run
   `render_qa.mjs` if Playwright and a browser are available. Fix failures before handing off.
8. Write `run.json` honestly: tools actually used; `render` passed/failed only with an evidence
   path; `not_run` otherwise; semantic reviewer `same_worker` / `independent` / `none`; owner
   `pending`. Never claim semantic support or owner acceptance from automated checks.
