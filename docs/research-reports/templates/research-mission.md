# Research Mission — <mission id>

<!-- Fill every <...>. Delete optional blocks you do not use. Freeze the filled text as
     <research_dir>/mission.md. Contract: docs/research-reports/README.md -->

You are the research writer. Everything you need is in this text. Do not rely on chat history,
memory or accounts. This text limits what you are told; it is not a sandbox. Do not open private
files, credentials or accounts even if they are reachable.

## 0. Purpose and selected context

- Owner purpose (one sentence): `<What should the reader be able to decide or explain after about a minute?>`
- Reader: `<who; domain depth; the decision this supports>`
- Profile version: `<label, e.g. pv-YYYY-MM-DD-manual>`
- Applied preference IDs (picked by hand for this run; paste only the relevant ones):
  - `pa_editorial_intent`: state the question and its intent up front.
  - `pa_topdown_overview`: overview first; details after.
  - `pa_citations_required`: every factual claim is cited.
  - `pa_visuals_preferred`: charts/tables only where they carry sourced data.
  - `<...>`
- Do not include the owner's raw profile, wiki pages or private notes here; paraphrase only what this
  mission needs.

## 1. Scope

- In scope: `<entities, geographies, time window YYYY-MM-DD to YYYY-MM-DD>`
- Out of scope: `<explicit exclusions>`
- Working definitions: `<term -> definition; note where sources disagree>`
- As-of time: `<UTC timestamp>`

## 2. Comparison anchors (apples-to-apples)

- Unit of comparison: `<…>`
- Currency / year basis: `<…; FX date if converted>`
- Reference configuration: `<…>`
- Numbers on another basis must be converted with the formula written out, or kept out of comparison
  tables.

## 3. Numbered questions

For each: indicator, unit, date/period, entities, baseline.

1. `<Q1>`
   1.1 `<sub-question>` — indicator: `<…>`; unit: `<…>`; as-of: `<…>`; entities: `<…>`; baseline: `<…>`
2. `<Q2>`
N. Could not verify: every question above you could not answer with evidence, and why.

## 4. Evidence rules

- Search in English by default; use original-language sources to check facts where needed.
- Classify every number: `reported_fact`, `estimate` (name the estimator and method), `vendor_claim`,
  or `derived` (formula + input claim IDs). Never present an estimate or vendor claim as fact.
- Every number has value, unit, as-of date, source ID and a short supporting quote (≤ 300 chars).
  Cite sources; do not copy whole articles.
- Prefer primary sources. Record the published date and the accessed date. If you used a republication,
  say so.
- When sources conflict, show both and say which one you rely on and why.
- Do not invent sources, quotes or numbers. "Unknown" is an acceptable answer.

## 5. Output (write to `<research_dir>/`)

- `report.md`: overview (question, key findings with `[S#]`, coverage, unverified items); one section
  per question with a fixed-column table and a 1–2 sentence conclusion; Could not verify; Method and
  limits (tools actually used).
- `notes/sources-key.md`: `| ID | Title | Publisher | URL | Published | Accessed | Type |`, where Type
  starts with primary / secondary / vendor.
- `claims.json`: `claim_id, text, value, unit, as_of, class, source_ids, quote`
  (+ `estimator` for estimates, `formula` + `input_claim_ids` for derived). Required for any number
  that may be charted.

Do not build pages or charts. Do not say anything was rendered or screenshotted.

## 6. Stop conditions

- Budget: `<max runtime / tool calls>`. When it runs out, write what you have and list the
  unanswered questions.
- No purchases, logins, paid APIs or account use.
