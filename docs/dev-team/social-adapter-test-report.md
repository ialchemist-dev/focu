# Social adapter test report — P2-5 (2026-11-18)

Scope: the four platform adapters in `focu/adapters/` (YouTube, Instagram,
RedNote, Facebook) plus the LinkedIn reference contract they are modelled
on. Everything below was executed WITHOUT the owner logging in anywhere:
YouTube is public-only by design; Instagram was tested with no session
and with fixture loaders only (no real login was attempted, per plan);
RedNote and Facebook consume local export files only, tested on
synthetic fixtures. Environment: dev checkout venv on the dev VM,
America/Denver day 2026-11-17 as the reference day, egress via the
sandbox proxy (TLS CA bundle), yt-dlp POT provider server running for
the live ladder work.

Fixture suites (final counts, all passing): youtube 21, instagram 23,
rednote 30, facebook 29, adapter-source-registration 6, collectors 4.
Full suite result at the end of this report.

## YouTube — LIVE public-channel test

Method: the adapter's own code paths against the real platform, no
fakes — `fetch_feed_bytes` + `parse_feed` for RSS discovery, the real
transcript ladder (`fetch_transcript`, and each rung separately), and
full `emit()` runs. Channels: 3Blue1Brown (`UCYO_jab_esuFRV4b17AJtAw`)
and 硅谷101 / Silicon Valley 101 (`UCKV2yWPB3wn0RTZh3cTD8YA`), both
from the followed-people pack.

Results:

- RSS discovery: PASS, live. Both feeds fetched and parsed (15 entries
  each; newest items dated 2026-11-17 in America/Denver for both
  channels, matching the pack's 2026-11-17 verification).
- Transcript ladder, rung detail (newest 3Blue1Brown video
  `qbsb9DpdZ6s`): API rung returned 40,084 chars in ~2s. The yt-dlp
  rung as originally written returned 0 chars — see the defect below.
- Full emit, 3Blue1Brown, day 2026-11-17: candidates 2 (the hard cap
  of 2 enforced against the live feed), included 1, pending 1 on the
  first run; after the rung fix (and once a transient API-rung failure
  cleared), included 2, pending 0, one unit with a 42,715-char body.
- Full emit, 硅谷101, day 2026-11-17: candidates 1, included 1,
  transcript via `yt-dlp-android` (13,359 chars) — the API rung failed
  for this Mandarin video and the fixed yt-dlp rung rescued it, live.
- pending_transcripts behaviour: PASS, demonstrated three ways —
  (a) live: video `0IZcjWtWmDA` went pending when both rungs failed
  (a transient API failure plus the yt-dlp defect), was reported in
  `pending_transcripts` with id/title/source, and was never emitted
  title-only; (b) a forced-threshold emit (min_transcript_chars set
  unreachable) reported both candidates pending and emitted no unit;
  (c) the fixture suite's PendingTests cover the same contract offline.
- Failure isolation: PASS, live. A bogus channel id produced a
  `failures` entry (`HTTPError`) and an empty units file; `emit` did
  not raise.

### Defect found and fixed: yt-dlp rung discarded usable transcripts

One yt-dlp invocation was asked for all subtitle languages at once
(`zh-Hans,zh-Hant,zh.*,en.*`). yt-dlp downloads an invocation's tracks
in order and aborts the invocation on the first HTTP 429 — from this
datacenter egress, rate limits on subtitle tracks are routine, and
the first tracks attempted are auto-translated variants the adapter
does not need. Live reproduction: for `qbsb9DpdZ6s` the combined
invocation wrote no file at all (429 on `zh-Hans`); an `en.*`-only
invocation wrote the full English VTT (72,859 bytes) before a later
variant 429'd. Net effect: whenever the API rung also failed —
transiently, as observed live for `0IZcjWtWmDA` — a video with
perfectly good captions went pending.

Fix (`focu/adapters/youtube.py`): the rung now attempts its language
groups in separate invocations (`SUB_LANG_GROUPS`: zh group first,
then `en.*`), returning the first file that clears
`MIN_TRANSCRIPT_CHARS`; one group's failure can no longer poison the
next. Preference order is unchanged. Regression tests:
`YtdlpRungTests` (4 tests, subprocess faked). Live re-verification:
the fixed rung returned full transcripts for both probed videos
(40,084 and 2,415 chars, identical to the API rung's text), and the
硅谷101 emit above was rescued by it end-to-end.

Remaining untestable / not covered: members-only channel content
(e.g. 北美王路飞's course videos) is absent from public RSS by design;
sustained-rate behaviour over a full multi-channel morning run was
not exercised (two channels, one day only); the production POT-token
wiring lives in the runtime toolchain, not in this adapter.

## Instagram — no session + fixtures only

Method: NO real login attempted and no session file created from real
credentials. (a) CLI emit with a nonexistent session path; (b) the
existing fixture suite (fake loaders, duck-typed posts); (c) probe
results in the fixture-findings appendix of this pass.

Results:

- No-session fail-closed: PASS. `focu instagram-adapter emit` with a
  missing session file exits 0, writes `[]` as the units file, and
  reports `failures: [{source: "Instagram Feed", error:
  "SessionFileNotFound"}]` — the day aborts cleanly, no partial unit,
  no traceback, and the briefing is never blocked. (The plan's
  shorthand for this was "needs_auth"; the adapter's actual tokens are
  `SessionFileNotFound` for a missing file and the `login_required`
  stop reason when a present session is rejected — same fail-closed
  semantics.)
- Stop conditions: PASS (fixtures). Checkpoint / challenge /
  login-required / two-factor / rate-limit exceptions — raised at load
  time or mid-iteration — abort the day into the report's `stopped`
  list with nothing emitted, including no partial digest for posts
  already consumed (StopTests).
- Session-file handling: PASS (fixtures). Only the path is consumed;
  the username is derived from the `session-<username>` filename
  convention; normalization, own-post skip, cap (20), pacing hook,
  Denver day boundary, gist truncation and per-day URL identity are
  all covered by the 26-test fixture suite.
- Probe round (fixture gap-hunt, this pass): an existing but EMPTY
  (zero-byte) session file with a fake loader raising login-required
  (class-name and message-marker variants) lands in `stopped` with
  `reason=login_required` and emits nothing — PASS. Session-name
  parsing edges probed: `session-` → None, hyphenated names preserved,
  unrelated names → None — and one defect, below. The CLI with an
  existing session file in this dev environment records a clean
  `ModuleNotFoundError` failure entry (Instaloader deliberately not
  installed here), never a traceback.

### Defect found and fixed: dotted usernames truncated

`username_from_session_path` used `Path.stem`, which strips
everything after the last dot as an "extension" — but Instaloader
session files are extensionless, and Instagram usernames legitimately
contain dots, so `session-jerry.94242` derived `jerry`. That wrong
username would be handed to the production session load and would
break the own-post skip (the owner's own posts would enter their own
digest). Fix: derive from the full file name. Regression coverage:
the existing session-path test now also pins dotted, hyphenated, and
empty-suffix names.

### Defect found and fixed: gist character ceiling (all three adapters)

See the RedNote section — the identical `truncate_words` defect was
reproduced with a 1 MB single-token caption here (unit body
1,048,623 chars before the fix) and is fixed by the same
`MAX_GIST_CHARS = 500` ceiling, pinned by
`test_single_token_caption_is_char_capped`.

Remaining untestable without the owner: everything past the session
boundary — whether a real owner-created Instaloader session loads,
whether Meta serves the feed to it, real checkpoint behaviour, and
the pinned-Instaloader smoke test. Those are production-wiring steps
1–2 in the adapter's docstring and remain owner-only: the owner
creates the session interactively; Focu never logs in.

## RedNote — export-file round-trip (synthetic fixtures)

Method: the adapter consumes only a local JSON export; probes drove
`emit()` and the CLI on synthetic exports (valid, malformed-mixed,
empty list, zero-byte, non-list, oversized) plus the 25-test fixture
suite.

- Valid multi-record: PASS (module + CLI) — 3 records → 1 unit,
  3 body lines, exact LinkedIn-shaped keys, correct `?day=` URL and
  Denver `published_at`.
- Empty list `[]`: PASS — units file `[]`, no failures; an empty day
  is not an error.
- Zero-byte file: PASS — units file `[]`, one `ExportParseError`
  failure, CLI exit 0, no traceback. Now pinned by a regression test.
- Malformed mixed with valid: PASS — probe payload of 10 entries
  (including `[]` and `{}` entries) → `malformed=8, included=2`,
  one unit with exactly the valid lines.
- Oversized: PASS — 5,000 valid records → cap enforced exactly
  (`included=30, over_cap=4970`, ~0.04 s in-process, ~0.15 s via
  CLI), one digest unit with 30 lines. Now pinned by a regression
  test. (Ordering at scale was probed with identical timestamps;
  distinct-timestamp newest-first ordering is covered at small
  scale by the existing suite.)
- 1 MB single field, many-words variant: PASS — the 30-word rule
  truncates it to a ~206-char body.

### Defect found and fixed: gist truncation had no character bound

The many-words result above hid a hole: `truncate_words` capped word
COUNT only, so a single whitespace-free 1,048,576-char token — a
base64 dump, a long URL, an unspaced CJK run (`str.split()` treats it
as one word) — passed through untruncated: emitted unit body
1,048,633 chars, units file ~1.05 MB, silently `included=1`. The
identical defect was reproduced in all three gist adapters
(RedNote, Facebook, Instagram). Fix: `truncate_words` in each
adapter now also applies `MAX_GIST_CHARS = 500` (the adapters carry
mirrored copies of the helper by design; all three were patched
identically). Regression tests: one per adapter
(`test_single_token_*_is_char_capped`).

Remaining untestable without the owner: the exporter itself
(MediaCrawler in CDP mode on the owner's own Chrome, under its own
non-commercial licence — never vendored into Focu) and whether its
real output matches the documented export contract field-for-field;
风控 (risk-control) behaviour on the platform side.

## Facebook — export-file round-trip (synthetic fixtures)

Method: as RedNote — local export fixtures only; the adapter contains
zero platform code. 25-test fixture suite plus probes.

- Valid / empty / zero-byte / malformed-mixed: PASS, mirroring
  RedNote exactly (same probe payloads; malformed 8 of 10,
  included 2; zero-byte → `ExportParseError`, exit 0, no traceback).
- Oversized: PASS — 5,000 records → `included=15` (the lowest cap of
  the four platforms), `over_cap=4985`, ~0.03 s in-process; one
  15-line digest unit. Now pinned by a regression test.
- 1 MB field: many-words variant PASS (~210-char body); the
  single-token variant reproduced the shared gist defect (body
  1,048,637 chars) — fixed by the same `MAX_GIST_CHARS = 500`
  ceiling, pinned by `test_single_token_text_is_char_capped`.

Remaining untestable without the owner: the owner-side browser-session
exporter (checkpoints and login demands inside it are owner-only stop
conditions by design) and any real export's fidelity to the contract.

## LinkedIn — contract re-verified via the existing suite

Method: LinkedIn is the production-proven reference implementation
(the daily briefing runs it); this pass re-ran its contract tests
rather than any live collection.

- `tests.test_collectors` (LinkedIn export normalization incl. the
  linkedin.com URL allowlist, export dedup/persistence): PASS (part
  of 10 tests run together with registration).
- `tests.test_adapter_source_registration`: PASS — adapter-type
  sources (the shape LinkedIn/Instagram/RedNote/Facebook register
  under) are accepted with a profile URL, rejected without one,
  ingest persists an adapter unit under the registry source id and
  refuses unconfigured or disagreeing units, and two days receive
  distinct content identities (the 2026-11-15 incident regression).
- The full test suite (which includes the briefing/pipeline tests
  that consume LinkedIn-shaped units) is green — see the suite line
  at the end of this report.

Remaining untestable: nothing in the adapter contract; live LinkedIn
collection is production behaviour, out of scope for dev-main.

## Summary

- Tested live: YouTube RSS discovery, transcript ladder, caps,
  pending, failure isolation — PASS after one real defect fixed.
- Tested fail-closed: Instagram with no session — PASS.
- Tested by fixture round-trip: Instagram session parsing, RedNote
  and Facebook exports (valid / malformed / oversized / empty) —
  PASS after two further defects fixed (gist character ceiling in
  all three adapters; Instagram dotted-username derivation).
- Re-verified by suite: LinkedIn contract — PASS.
- Untestable without the owner (unchanged, by design): any real
  Instagram session, the RedNote and Facebook exporters, and
  members-only YouTube content.
- Full test suite after all fixes: 676 tests, OK (665 at the start
  of this pass + 11 new regression tests: 4 yt-dlp rung, 1 + 3 + 3
  gist/scale/session-path across the other adapters).
