# Issue #46 — "World Models for Active Measurement" (Olivier & Muir): which numbers come from where

**Issue:** [#46](https://github.com/ialchemist-dev/focu/issues/46) (created 2026-11-16T21:37:29Z)
**Sources accessed:** 2026-11-16 (UTC), public pages only, no login.
**Status:** desk verification. The paper's full PDF could **not** be read (see [Not verified](#not-verified)). No code changes.
**Report (Chinese, self-contained HTML):** [`evidence/issue-46-report/page/index.html`](evidence/issue-46-report/page/index.html). Registered claims: [`claims.json`](evidence/issue-46-report/claims.json). Sources: [`notes/sources-key.md`](evidence/issue-46-report/notes/sources-key.md). Provenance and QA states: [`run.json`](evidence/issue-46-report/run.json). Frozen hashes: [`frozen.sha256`](evidence/issue-46-report/frozen.sha256).

## Answer to the follow-up

The **89% (vs. geostatistics)** and **~40% (vs. Claude)** figures come from Fleet's blog post
[*Beyond prediction: Subsurface World Models*](https://www.fleetspace.com/newsroom/beyond-prediction-subsurface-world-models)
(Fleet newsroom, 2026-11-13), in the section "Closing the sim-to-real gap". The
[LinkedIn post](https://www.linkedin.com/feed/update/urn:li:share:7527896018252681216/) repeats them and links to the blog.
They measure something else from the paper abstract:

- **Sample:** "two large real porphyry copper deposits", held-out drill holes. The deposits are not named.
- **Metric:** error in copper metal above a 0.2% Cu cut-off. The error definition and the number of held-out holes are not disclosed.
- **Model:** Fleet's "Tau". The blog does not say how Tau relates to the paper's reader.
- **Comparisons:** about 89% less error than conventional geostatistics. About 40% less than Claude Opus 5.5 and Claude Fable 5.1, and matched Claude Fable 5.2. At a 0.35% Cu cut-off: 55% less (Fable 5.1 and 5.2) and 64% less (Opus 5.5).
- **Same blog, synthetic deposits:** about 47% less error than geostatistics, and 25 / 33 / 47% less than Fable 5.2 / Opus 5.5 / Fable 5.1.

The [NeurIPS 2026 poster page](https://neurips.cc/virtual/2026/175843) abstract (Workshop on World Models in Physical AI, a **workshop poster**, not the main conference) reports **synthetic results only**. It calls transfer to field settings "the next step". The 89% and ~40% figures are not in that abstract.

**Classification:** these figures are confirmed in the blog and post. Whether the paper itself contains them is **unknown**, because the full text was blocked. This is not evidence that the figures are false.

## What the paper abstract supports (synthetic worlds)

| Claim | Value | Sample / split | Source |
|---|---|---|---|
| Cu-mass IoU, no drilling → 20 holes | 0.071 → 0.308 | 400 synthetic diagnostic worlds | NeurIPS abstract |
| Shuffled measurements (control) | 0.028 | same | NeurIPS abstract |
| Mean Cu-mass IoU gain, common region outside all policies' drilling neighbourhoods, 5 holes, reader frozen: learned ranker / predicted-copper / random | 0.0564 / 0.0464 / 0.0276 | 1,536 held-out worlds | NeurIPS abstract |
| Ranker vs predicted-copper | 21.6% (derived: 0.0564/0.0464 − 1) | — | derived; matches #46 |
| Total-copper MAE ~75% lower than local ordinary kriging | ~75% | 96 synthetic worlds | **only in #46's transcription** of the OpenReview abstract. Not in the NeurIPS-page abstract. Unverified |

## Related: Tau 3.8 press release (a separate scope)

[PR Newswire, 2026-11-11](https://www.prnewswire.com/apac/news-releases/ai-trained-on-ten-million-synthetic-earths-outperforms-conventional-copper-estimates-at-tsxv-listed-atexs-valeriano-project-302934698.html), company-reported:

- Tau 3.8 was trained on ten million synthetic geological worlds.
- At ATEX's Valeriano project, copper-**grade** error on held-back drillholes was 38% lower than kriging built from the same drilling.
- On the deepest step-out holes, error was "up to 67%" lower.

This is a single project with a different metric and sample from both the blog's 89% and the paper. Do not combine these figures.

## Relevance to subsurface ML / geothermal (inference)

The paper treats the hidden state as static and actions as revealing evidence. That framing could carry over to geothermal temperature and permeability exploration. However, the abstract says the benefits are strongest for the copper-mass objective used in training, and the generator targets porphyry Cu-Mo systems. Transfer to geothermal is **not demonstrated**. The parts most worth reusing are the evaluation design: a shuffled-measurement control, and comparing gains on a common region outside the drilling neighbourhoods.

## Not verified

1. **Full paper and appendix.** The [PDF](https://openreview.net/pdf?id=iHAZ79hNuM) and [forum](https://openreview.net/forum?id=iHAZ79hNuM) return an OpenReview browser-verification challenge, and the API returns 403 `ChallengeRequired`. The challenge was not circumvented and no login was used. An arXiv author search found no copy. No page, table or appendix citations are possible.
2. **The 96-world / ~75% kriging claim.** It appears only in the #46 text.
3. **Whether the 89% and ~40% figures appear in the paper or slides.** No public slides were found.
4. **Methods for the blog's real-deposit test.** Not disclosed.

Licence: #46 states that OpenReview lists the paper as CC BY 4.0. This could not be confirmed on OpenReview. This note uses short quotes with attribution only.

QA: structure check passed. Render check passed at 390 px and 1440 px, light and dark, using an existing Playwright and system Chrome; screenshots are kept outside Git. Semantic check is `same_worker`: quotes were verified against local snapshots, with no independent review. Owner acceptance is pending. A passing render check does not mean the content is correct.
