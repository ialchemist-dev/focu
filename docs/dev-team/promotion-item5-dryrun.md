# Promotion checklist item 5 — production config under the dev loader (wave 41, 2026-11-17)

**Verdict: PASS.** The production registry loads unchanged under dev-main code, resolves to the same source identities production computes today, and the dry run writes nothing anywhere.

## What was run

- Copied `~/focu-runtime/config/sources.yaml` → `~/workspace/focu-dev/rehearsal2/config/sources.yaml` (copy sha256 `a40a24f0da2e715071d96aad88eaa3ed39bf8a3ba6d2feba82dbab8463f3e6e0`, identical to the original before and after; the original was never opened for writing).
- Dev checkout CLI, exactly as the checklist prescribes:
  `focu daily run --config <scratch copy> --data-dir ~/workspace/focu-dev/rehearsal2/data --dry-run --json`
  → exit 0, `{"status": "validated", "date": "2026-11-17", "mode": "audio", "config_hash": "8e05e135ef040b09702fa1745e6113d01476a84534ab79083a93151f7b2fc7d8", "composer": "secretary_briefing_v1", "style_version": "2026-11-16.1", "style_sha256": "8638bb46…"}`.
  (`--dry-run` exists in the dev daily CLI in its current form — cli.py line 37, handled at line 103, returning before any Store/run_lock creation — so no fallback path was needed.)

## Source resolution under the dev loader (in-process `load_config` dump)

Registry level: version 1, timezone America/Denver, output_mode `audio` (defaulted — the production file omits it, same default as production's loader), one channel `research` (35 min × 150 wpm). All 4 sources enabled, channel `research`, priority 1 and retention_days 7 (both loader defaults, unset in the file):

| Source | Type | source_id | Canonical URL | Cap/day |
|---|---|---|---|---|
| OpenAI Official | rss | src_69d1bca69a1eb9936340b5f44cc3e69db1072094c2c1620f7c9ac1736b371152 | https://openai.com/news/rss.xml | 10 |
| Anthropic Official | blog | src_297f0fdf05016b2dfdbd57b36772ebcc4e3073f31151a223944eaae34be2df33 | https://www.anthropic.com/news | 10 |
| 硅谷101 | youtube | src_647675fe5dc51bbb713cc65f132406e984bb0fee0241bcc64b16a24d94995264 | https://www.youtube.com/channel/UCKV2yWPB3wn0RTZh3cTD8YA | 2 |
| LinkedIn Feed | linkedin | src_5c95417d8bdf5752d0208e95eb358c25cd2fdb9b4ac6b62e27c1a7c636d01713 | https://www.linkedin.com/feed/ | 1 |

Production-only fields the loader is not required to know (`notes`, `handle`, `channel_id`) are accepted without error or warning — the loader does not reject unknown keys, and `channel_id` drives the YouTube canonical URL as production expects.

## Why this resolution is provably production's own

- `diff` of `focu/daily/config.py` (production `~/workspace/focu-live` vs dev checkout): the **only** difference is `KNOWN_TYPES` — dev adds `instagram`, `rednote`, `facebook` (the wave-17 adapter registration). Validation, defaults, identity assignment, and `config_hash` computation are byte-identical.
- `focu/daily/identity.py` (`source_url`, `stable_id`, `canonical_url`): **byte-identical** between the two checkouts.
- Therefore the identities and the `config_hash` above are exactly what production's loader computes for this file today: promoting the loader cannot re-key the four registered sources or invalidate frozen episode records for this registry. The three added types are inert here — no production source uses them.
- The dry run's `style_sha256` (`8638bb46…`) equals the sha256 of production's own `references/briefing-style.md` (the two checkouts' style files are byte-identical, v2026-11-16.1), so the validation ran against the same style production uses.

## Behavioral notes (expected, not defects)

- Mode resolved to `audio`: the file omits `output_mode` and both loaders default it to `audio`, matching production's frozen per-run behavior. The dry run exercised the audio branch: with no `tts_argv` in the config, the `missing_tts` case is tolerated by design (the built-in route records a skip at finalize).
- No validation errors, no warnings, nothing on stderr.

## Write-safety evidence

- Scratch data dir after the run: **empty** (the dry-run branch returns before Store creation; confirmed in code and on disk). Scratch config dir contains only the copied `sources.yaml` — no manifest or side files appeared; the copy's checksum is unchanged after the run.
- Production untouched: recursive sha256 listing of `~/focu-runtime/config/` (both files) is **identical before and after**; `sources.yaml` mtime/inode/size unchanged (2026-11-13 06:30:03 UTC, inode 340150, 2385 bytes). Nothing was written under `~/focu-runtime` or `~/workspace/focu-live` (production code was only read, for the diffs above).

## Promotion impact

None adverse. Checklist item 5 is now **rehearsal-verified**: the production registry can be carried over a dev-main promotion byte-for-byte, with source identities, caps, and config hash preserved. No defect found; nothing to fix.
