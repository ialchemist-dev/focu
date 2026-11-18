# Promotion Rehearsal — the composed dev-main system, end to end (wave 32, 2026-11-17)

> Status (2026-11-17, wave 37): point-in-time record of the wave-32 live-data rehearsal; the body below is unchanged. Two of its three open checklist decisions were overtaken within hours — D1 and D2 were resolved by fixing them (wave-33), and Q11 cold start was implemented (wave-34). Read the checklist at the end together with "Checklist status since the rehearsal" immediately below; items 3, 4, 5, 8, and 9 still stand as written.

## Checklist status since the rehearsal (2026-11-17)

- **Item 1 (D1) — RESOLVED by fixing (wave-33), no longer an owner decision.** The pack fetch guard now treats resolver answers in the benchmarking range (198.18.0.0/15) as *indeterminate*: the fetch proceeds and liveness records the verdict, instead of refusing every hostname behind proxied DNS. Literal private targets and private redirect hops are still refused, so installs with liveness no longer silently disable every feed source on this host.
- **Item 2 (D2) — RESOLVED by fixing (wave-33), no longer an owner decision.** `focu/briefing.py` now applies one version-token rule (`VERSION_REF`) shared by the figure extractor and the presence checker, so names like "Kimi K3.1 Pro" no longer make the deterministic compose path unpassable; and a run that fails mid-pipeline still gets its day-status record, with the failing stage named — the Q5 surface now exists on failed days too.
- **Item 11 (Q11) — IMPLEMENTED (wave-34).** Cold start shipped on dev-main: the first briefing's day-status names the installed starter pack and its removal command, backed by the design's acceptance battery (`tests/test_cold_start.py`). Wiring it into production remains part of the promotion itself.
- **Still standing, exactly as written in the checklist below:** item 3 (port the production registry's comments into source notes before the first promoted install), item 4 (land dev-main in the production checkout and run the full suite against it), item 5 (dry-run the production config under the new loader), item 8 (the owner's iPhone listen-through — the one device check no rehearsal can do), and item 9 (assign the refresh-due cadence, Q2's open decision). Items 6, 7, and 10 stand as rehearsal-verified.

Plan-4 direction 1 (pm-plan-3-closeout §4.1), executed by the integration-engineer agent. Everything ran on a scratch runtime under `~/workspace/focu-dev/rehearsal/` (own config, two daily data dirs, learn store, deliveries staging, bundle output) using the dev checkout's venv (`~/workspace/focu-dev-checkout/.venv/bin/focu`). Production was touched only as a read-only copy source for delivery folders (step 3); `~/focu-runtime` was never written, `~/workspace/focu-live` never touched, no artifact deployed, no cron changed, nothing pushed, and no product code was fixed — defects are recorded, not repaired.

## Verdicts

| Step | Verdict | One-line result |
|---|---|---|
| 1. Pack → registry | **PASS with a blocker-class defect (D1)** | Install/uninstall mechanics exact; liveness is unusable in this DNS environment |
| 2. Daily pipeline | **PASS (isolated run) / FAIL (full registry)** | Full cycle + reconciled day-status with one source removed; the full registry aborts deterministically at compose (D2) |
| 3. Publisher | **PASS** | 7 real+synthetic items, gist 7/7, agenda gist correct, `source_name` and `original_url` pass through |
| 4. Learning round trip | **PASS** | Fan-out attributes exactly, ingest idempotent, sparsity makes the silence legible |
| 5. Reader behavior suite | **PASS** | Behavior suite exit 0 (24 pass blocks, waves 2–11); publish tests 48/48 |

## Step 1 — Pack → registry

Starter registry: one channel (`research`, 35 min × 150 wpm), zero sources, `output_mode: text_only`, timezone America/Denver.

**First attempt — with liveness (the default):** `focu pack install anthropic-personal-blogs --config … --yes` applied, but **all 8 feed-enabled sources were installed disabled**. Every liveness probe was refused by the wave-19 fetch guard: `fetch refused: host felixrieseberg.com resolves to non-public address 198.18.190.209` (jack-clark.net → 198.18.190.210, colah.github.io → .211, askell.blog → .212, …). This sandbox's DNS maps public hostnames onto 198.18.0.0/15 (the benchmarking range, `is_global == False`), so the guard refuses *every* hostname here. The install "succeeded" and recorded the reason per source in its notes — a quiet, total disable. → **Defect D1.** Uninstalled cleanly (11 removes, 0 keeps) and reinstalled with `--no-liveness`, per the wave brief's sandbox provision.

**With `--no-liveness`:** anthropic installs 11 sources (8 enabled); `load_config` accepts. Geothermal installs on top: 23 sources, 15 enabled; `load_config` accepts (enabled set exactly the packs' enabled sources). Uninstalling geothermal then restored the anthropic-only registry **byte-identically** (sha256 `1584ecae…` before and after; 12 removes, 0 keeps). Reinstalling geothermal reproduced the two-pack file byte-identically (`e186df89…`).

Two qualifications, both evidenced:

- **The byte-restore is serializer-to-serializer only.** The starter file (hand-written) did *not* come back byte-identical after an install+uninstall round trip: the pack writer re-serializes the whole YAML in its own style (quotes dropped, list indent changed). Semantic content identical; bytes not.
- **Install strips all comments (Friction F1).** A control config carrying a header comment and an inline comment lost both on install (grep count 0/0 after). The registry convention in `examples/sources.yaml` is comment-rich; a first promoted install would silently strip the production registry's comments. A timestamped backup is written (`sources.yaml.bak-…`) and `focu pack restore` exists, so the loss is recoverable — but nothing in the install output mentions it.

## Step 2 — Daily pipeline

**Run 1 — full two-pack registry** (`focu daily run --config sources.yaml --data-dir daily --date 2026-11-17 --text-only --json`): collection over the real network worked — **290 items discovered, 14 of 15 sources `success`, 1 `error`** (Chris Olah, `HTTP Error 404` — the exact rot the pack's readiness notes record; the composed system reproduced it live). Selection froze 7 items (5 ThinkGeoEnergy at cap, 1 Jack Clark, 1 XGS); selection accounting was written. The run then **aborted at compose, exit 4**:

```
{"status": "error", "errors": [{"code": "briefing_qc_failed", "retryable": true,
 "message": "briefing script omitted source items or figures:
  [{\"id\": \"cnt_486cf57b…\", \"issue\": \"missing_key_figures\", \"values\": [\"1\"]}]"}]}
```

Root cause, isolated by reproduction against the frozen units: the Jack Clark item (Import AI 481) discusses the model **"Kimi K3.1 Pro"**. `key_figures` (focu/briefing.py) extracts a bare `"1"` from "K3.1" — the NUMBER regex matches the digit after the dot, because the integer part is blocked by its letter prefix, and `VERSION_REF` only strips versions with ≥2 dot segments. `validate_script`'s presence check `(?<![\d,.])1(?!\d|[,.]\d)` refuses to count a dot-preceded "1" as present in the script. Extractor and checker disagree about version-shaped numbers inside alphanumeric names, so the deterministic `render_script` path can *never* pass QC for such an item — re-running reproduces the identical failure (`retryable: true` is misleading for this class). → **Defect D2.** Blast radius: the run row stays `pending` forever, no compose stage row is written, and **no day_status is assembled** (assembly sits downstream of finalize) — the Q5 surface has nothing for exactly the days that fail. Asking the surface confirms the gap, with a misleading diagnosis (**Friction F3**): `focu daily day-status` prints `No day-status record for 2026-11-17. The run predates day-status assembly.` — the run does not predate assembly; it never reached it. Production escapes D2 only because its scripts are host-authored; any fallback-rendered day containing an Import-AI-style item (model names like K3.1, Qwen2.5-era shapes) is exposed.

**Run 2 — same system, Jack Clark disabled** (config copy `sources-nok3.yaml`, fresh data dir `daily2`): the full cycle completes, exit 0, run status `degraded` (the Olah failure), episode `finalized`. `focu daily day-status` prints the honest account, and the record reconciles under independent re-computation:

- Summary: `7 item(s) selected for 2026-11-17; 1 collector(s) failed (Chris Olah); 18 item(s) withheld (18 over_cap); 255 item(s) not ready (255 expired).`
- Outcome `partial_failure` (the named collector failure), **`discrepancies: []`**.
- Independent check from the `selection_accounting` stage row: considered 25 = selected 7 + withheld 18, per-source and in total, zero mismatches. CLI `--json` output is byte-equal to the stored stage record.
- Audio roll-up: `0 synthesized, 0 text-only, 1 not attempted` with the recorded reason `run output mode is text_only`.
- Per-source lines name everything: ThinkGeoEnergy collected 50 → considered 23 → selected 5, 18 over_cap, 27 expired; the long tail of pack blogs (Jermyn 94, Carlsmith 20, …) collected fine and were withheld as `expired` — their newest posts predate the 7-day retention. A packs-only registry produces a thin day (7 items, 3 sources), honestly reported: the Q11 cold-start premise, confirmed empirically.

One parser divergence worth noting (**Friction F4**): Felix Rieseberg's feed is rejected as malformed by the pack liveness parser (`parse_feed`) but the daily collector (feedparser) fetched it successfully (15 items, `success`). Liveness verdicts and collector reality can disagree about the same document.

## Step 3 — Publisher

Staging (copies only): the production compilation `briefing-2026-11-16` + its 4 covered registered items (LVMH, LinkedIn digest, King's Trust, OpenAI science blog — all carrying `source_url`), the Musk research delivery (`podcast_mode: single`, with MP3), and one synthetic registered delivery carrying `source_name: "Rehearsal Gazette"` and a `source_url`. Published with the dev publisher: `publish.py --deliveries staging --output bundles/bundle-rehearsal-1 --ios-compatible-audio --limit 100` → `Built 7 content items`, build warnings empty.

Verified against `assets/episodes.json`:

- **Gist coverage 7/7.** Every item — real and synthetic — carries a gist.
- **Agenda gist correct:** the compilation's gist is `"Four items today: LVMH's Media Division announces strategic partnership with OpenAI…"` — drawn from its agenda, not the formula lead (the compilation's `summary` remains `"Here's what came in"`, unchanged by design; the gist is the card layer).
- **Bullet fallback works on the real LinkedIn digest:** gist = `Howie Xu — In his Stanford "Rethink Agents" keynote, he shared 12 contrarian views on AI's…` — first entry, no URL leaked.
- **`source_name` pass-through:** the synthetic item's bundle `source` is `"Rehearsal Gazette"` (the four real registered items, whose deliveries record no name, keep `"Focu"`).
- **`original_url`:** present and exactly equal to the recorded `source_url` on all 5 staged deliveries that carry one; absent on the compilation and the Musk item, which record none.
- **Audio:** the Musk MP3 passed the strict audit and was transcoded to the iOS CBR profile (`mp3_cbr_128k_mono_44100`, source/published hashes and decoded durations recorded in `build-report.json`).

## Step 4 — Learning loop round trip

Export hand-built to the reader's format-v1 contract, using the real episode from step 2 (`ep_f31d34e7…`): a Useful mark on the compilation with `covered_content_ids` = one unit each from ThinkGeoEnergy, Fervo, XGS; a Not-for-me on a second ThinkGeoEnergy unit.

- `focu learn ingest` → `events_recorded: 4` (`useful: 3`, `not_useful: 1`), `fanned_out_compilations: 1`, `conflicts: []`. The ledger shows exactly 3 `useful` observations, one per covered unit, each noted `via compilation ep_f31d34e7…`, plus the standalone `not_useful`.
- **Idempotent:** a second ingest of the same file records 0, reports 4 already recorded.
- `focu learn proposals` → `proposals: []`, `signal_reason: null`, `record_error: null`, `unattributed_feedback: 0`. The stop rule is *open* (attributed_events 4, exactly the floor 4) and the silence is per-source legible in the sparsity block: ThinkGeoEnergy delivered 5/10, negative 1/3 at rate 0.2/0.2, useful 1/3; Fervo and XGS delivered 1/10, useful 1/3. Zero proposals is the correct answer, and the surface proves it is a *healthy* silence rather than lost signal — the exact property waves 25/F1 were built for, now observed in the composed system.

## Step 5 — Reader behavior suite

`node test_reader_behavior.js` (node v24.22.1) in the dev reader: **exit 0**, 24 pass blocks covering waves 2–11 (one-tap play/resume, gist layer, Not-for-me/Useful acts and the export contract, F1 covered-ids, F4 Original door, N1–N3, F8 automatic voice fallback, wave-11 bullet gist rendering). `python -m unittest test_publish`: **48/48 OK**.

## Defect & friction list

- **D1 (blocker on this host): pack liveness is blind under fake-IP DNS.** The wave-19 fetch guard resolves hostnames itself and refuses non-public answers; this environment's DNS returns 198.18.0.0/15 for public hosts, so every guarded fetch is refused. Consequences: `pack install` with liveness silently disables every feed source; `refresh-check`/`show` liveness can never observe a live feed from here (its "unverifiable from here" verdict becomes permanent). The daily collector is unaffected (unguarded fetch through the proxy). Production runs on this same VM/DNS, so D1 is a promotion blocker for the pack workflow, not a sandbox curiosity.
- **D2 (blocker for the deterministic daily path): briefing-QC extractor/checker asymmetry on version-shaped numbers in alphanumeric names** ("K3.1" → required figure "1" that the presence check cannot count). Deterministic compose abort; run left `pending`; no day_status for failed days. Production's host-authored scripts mask it; the fallback renderer cannot carry such items.
- **F1: pack install rewrites `sources.yaml` wholesale** — serializer formatting replaces hand formatting and **all comments are stripped**, silently. Backup + restore exist; the plan output does not mention the loss.
- **F2: uninstall byte-precision is serializer-to-serializer only** — a hand-written registry does not regain its original bytes after an install/uninstall round trip (content identical, formatting normalized).
- **F3: the day-status missing-record message misdiagnoses failed runs** — "The run predates day-status assembly" is printed for any run lacking the record, including runs that failed before assembly.
- **F4: two feed parsers disagree** — pack liveness (`parse_feed`) rejects Felix Rieseberg's feed as malformed; the daily collector (feedparser) reads it fine. Liveness can mark a source dead that collection would happily use.

## Promotion checklist (in order)

1. **Decide D1 before any promoted pack install on this host** — fix the guard's treatment of proxy-mapped ranges, or adopt a standing rule (installs run `--no-liveness` here; freshness owned via refresh-due with the caveat in item 9). *[still-unverified — owner decision]*
2. **Decide D2 for the daily job** — keep host-authored scripts as the standing production path (status quo), or fix the figure extractor/checker asymmetry in `focu/briefing.py`; until decided, a fallback-rendered day containing a version-named model aborts with no day-status. *[still-unverified — owner decision]*
3. **Back up the production registry and runtime DBs; expect comment loss (F1)** — if the production `sources.yaml` comments carry meaning, port them into source notes before the first promoted install. *[rehearsal-verified behavior]*
4. **Land dev-main in the production checkout and run the full suite** (589 tests at wave 31) against it before switching the runtime. *[suite verified per wave; the merge/switch itself still-unverified]*
5. **Dry-run the production config under the new loader first**: `focu daily run --dry-run` against a copy of the production `sources.yaml` (the rehearsal verified `load_config` on pack-written registries; production's own file under the new loader is untested). *[still-unverified]*
6. **Run one production day and read `focu daily day-status` before enabling anything new** — the surface is verified end to end on scratch, including its reconciliation. *[rehearsal-verified]*
7. **Install packs one at a time, preview first**, verifying with `focu pack list` and the next day's day-status; expect a thin first day from pack sources alone (retention withholding dominates). *[rehearsal-verified]*
8. **Publish the reader from dev-main's publisher and deploy the bundle in place**; the publisher is verified against real deliveries (gist, agenda, names, originals, iOS audio). The owner's iPhone listen-through remains the one device check no rehearsal can do. *[publisher rehearsal-verified; device still-unverified]*
9. **Assign the refresh-due cadence (Q2's open decision)** — noting D1: until it is decided, refresh-check on this host reports "unverifiable from here" rather than feed health. *[still-unverified]*
10. **Wire the learning transport into the routine**: owner exports from the reader Archive → `focu learn ingest` → `focu learn proposals` reviewed before any accept. The round trip, fan-out, idempotency, and sparsity legibility are all verified. *[rehearsal-verified]*
11. **Q11 cold start is not part of this promotion** — it remains a design with acceptance criteria, to be implemented as the first promotion-gated feature. *[still-unverified]*

## Appendix — rehearsal artifacts

All under `~/workspace/focu-dev/rehearsal/`: `config/` (starter, both-pack, no-K3, and comment-test registries + backups + `packs-installed.json`), `snapshots/` (A/B registry states), `daily/` (failed run 1 store), `daily2/` (completed run store + episode script/QC artifacts), `staging/` (6 copied production deliveries + the synthetic gazette), `bundles/bundle-rehearsal-1/` (the published bundle + `build-report.json`), `learn/` (feedback ledger, export, record copy), `logs/` (every command's captured output: step1 installs/uninstalls, step2 runs + day-status text/JSON, step3 publish log, step4 ingest/proposals JSON, step5 behavior log).
