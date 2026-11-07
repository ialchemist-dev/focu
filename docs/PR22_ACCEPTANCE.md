# PR #22 implementation and acceptance evidence — 2026-11-05

**Base:** main at df1e0cb744d564c42c40c765392f369edafb36bd.
**Branch:** feat/manual-archive-secretary-briefing.
**GitHub CI:** https://github.com/ialchemist-dev/focu/actions/runs/41987739641
**Status:** Draft; code CI PASS, Muse runtime deployment UNVERIFIED.

## A. Manual Archive / Restore

- Separate one-tap Archive action on every Inbox card and in the article
  reader toolbar; no automatic completion checks are called.
- Both use the existing localStorage key focu:content-consumption:v1 and the
  existing markDone(id, 'manual') schema with ISO update time.
- Archive cards expose Restore; an archived article view exposes Restore in
  the same toolbar. Restoring uses markUnread and rerenders immediately.
- Reader closes on manual Archive, pausing current media when applicable.
- No new storage keys, back-end service, or user account logic.
- Node simulated behavior confirms card Archive, reader Archive, Restore in
  both views, state survival across simulated reload and non-resurrection
  after rerender. Existing audio, reading and device-speech tests still pass.
- iPhone visual check and cross-rebuild persistence remain UNVERIFIED.

## B. One editable secretary style

- references/briefing-style.md is the only owner-editable style specification
  (version 2026-11-05.1, YAML controls, voice/content guidance and changelog).
- focu.briefing.read_style compiles that exact file. The daily composer
  actually reads it for new episodes, writes a QC JSON receipt, and blocks
  TTS finalization unless QC passed and matches the frozen script hash.
- The deterministic composer preserves every selected unit, its exact
  numeric facts and source text by default. It orders registered sources,
  explicit requests, then interest follow-ups.
- The Open Notebook generation CLI can build the provider prompt from that
  same style with --briefing-units. QC-gated delivery with --briefing-units
  checks the actual provider transcript before delivering media.
- Automated QC checks literal section headlines, source attribution,
  numeric tokens in the correct section, order and banned show phrases.
  It fails closed. Automated matching is not a substitute for factual
  review of paraphrases.
- Length estimate is recorded; shorter/longer reports are reported, never
  silently truncated to fit the 5–8 minute daily target.

## Style-before/after evidence

The unit test
test_editing_style_file_changes_both_script_and_prompt_without_code
uses a disposable file copy; source and Python implementation are unchanged.

Before style setting:
    opening: "Here's what came in."
    => Host: Here's what came in.

After owner-style edit and dated changelog entry:
    opening: "A brief update for you."
    => Host: A brief update for you.

The entire provider prompt also changes and gets a different style SHA-256.
All source items and numbers still pass QC. This test demonstrates an
actual style-driven output change, not merely a markdown file existing.

## Sample episode under the new style

- Input: examples/secretary-briefing-demo-units.json
- Generated, committed script:
  examples/secretary-briefing-demo-script.txt
- Five **synthetic** items cover registered sources, user request and an
  interest follow-up; all preserve figures 948, 20, 5,034, 32, $1.2M, 17%.
- The committed sample script matches the renderer output byte-for-byte in
  test_five_item_sample_episode_matches_golden_script_and_qc.
- No audience greeting, branding, dialogue theater or show sign-off.
- This is a short structure/coverage proof, **not** a claimed 5–8 minute
  paid audio episode. Real Open Notebook voice generation remains UNVERIFIED
  without Muse access.

## Failure injection

Tests block:
- A missing report item even when the script contains smooth prose.
- A missing 5,034 figure from the requested research section.
- Forbidden show phrase.
- A generated Open Notebook transcript missing its required briefing item;
  the delivery command fails before writing an MP3.
- Duplicate article headlines from different sources are supported via
  sequential section matching rather than incorrectly rejecting both.

## CI and change scope

Latest checked run: 135 Python tests PASS (2 skipped), 4 HTTP fixture tests
PASS, 20 Muse publisher tests PASS, JavaScript inline syntax PASS, simulated
reader behavior PASS. External live-web tests were skipped by workflow rules.

Changed-file review: no changes to examples/sources.yaml, no modifications
to the production podcast Artifact, no DB/data/evidence files committed.

## Outstanding Muse VM-only work

- The actual long-lived checkout at ~/workspace/focu has not been accessed
  from this GitHub development connection. No claim of switching branches
  is made. Follow docs/MUSE_SECRETARY_BRIEFING_HANDOFF.md to verify it is
  clean, switch to main and fast-forward without destroying local data.
- The actual 06:14 America/Denver cron command must be inspected. The
  repository daily path is wired; if the host uses Open Notebook directly,
  its job must be updated to use --briefing-units and QC-gated delivery.
- Generate one real 5–8-minute solo-voice briefing in Muse from an actual
  full source report, save its transcript/QC, verify all items and figures
  then listen to the result. Do not modify production Artifact in this task.
