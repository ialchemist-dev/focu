# Focu Muse-native Podcast Library

## Verified acceptance (November 2, 2026)

The private static Muse Library entry `focu-podcast-library` was updated **in place** v1 → v2 → v3. The v3 library was opened and used on the user's iPhone. It remains a private static Artifact, with no server actions, database, external hosting, Tailscale or Google Drive.

Muse static Artifacts are **immutable build-time snapshots**. Workspace changes to `episodes.json` cannot update an already deployed Artifact. Each content change requires a new publisher staging bundle and a **new build of the same Library entry**, not a new Library entry.

Muse serves `index.html` and `assets/`, not root-level `episodes.json`. The manifest embedded in `index.html` is authoritative in Muse; HTTP fetch of `assets/episodes.json` is a progressive enhancement for compatible hosting contexts. The v3 loader fix allows relative media paths on the Muse iOS non-HTTP scheme and catches all manifest failures (including invalid URL), showing a labelled embedded-snapshot fallback.

The deployed reader has been checked for malformed-entry rejection, duplicate-ID rejection, visible audio-unavailable errors, and the optional `cover_url` image branch. **Covers: No data** (no source delivery had an image; placeholder path exercised). **Force-quit/reopen: Unverified. Background playback: Unverified.** Do not upgrade these without controlled physical-device tests.

Publisher validation: 2/2 original unit tests passed in Muse; 15/15 bundled MP3s matched the original delivery files and `build-report.json` by SHA-256. Date parsing and newest-first ordering have since been corrected in the repository; run the updated tests and rebuild to verify these changes separately.

## Files

- `index.html`: standalone responsive Muse reader with embedded manifest, validated media references and visible error states.
- `publish.py`: stages an immutable private bundle, copies existing MP3s byte-for-byte, optionally copies `cover.jpg/jpeg/png/webp`, parses trailing `YYYYMMDD` dates and selects the newest episodes before applying `--limit`.
- `test_publish.py`: publisher and chronological-ordering regression tests.
- `assets/episodes.json` inside each staged bundle: audit copy of the embedded manifest.
- `build-report.json` inside each staged bundle: checksums and count for operator verification.

## Stage a new version

```bash
cd experiments/muse-artifact-reader
python3 -m unittest -v test_publish.py
python3 publish.py \
  --deliveries ~/workspace/the-few-focu-test/data/deliveries \
  --output ~/workspace/focu-artifact-builds/library-NEW-VERSION \
  --limit 15
```

Confirm chronological order, ISO dates and original-file SHA-256 equality before deploying. Update the **existing** private `focu-podcast-library` Library entry with the resulting `index.html` and `assets/`. The publisher does not call Muse's build/update API, alter production cron, or touch original deliveries.

## Mobile table check (P2-3)

Owner report (2026-11-18): article tables overflowed the right edge on
phone-width screens and forced page-level horizontal scrolling. The fix
keeps the overshoot inside the table's own container:

- every table renders inside `.table-scroll` (full-width block,
  `overflow-x:auto`, `overscroll-behavior-x:contain`);
- the layout chain (`main`, `#reader`, `#articlebody`) carries
  `min-width:0; max-width:100%`, and `html,body` are guarded with
  `overflow-x:hidden; overflow-x:clip` (clip does not break the sticky
  header; hidden is the fallback);
- at ≤480px, table cells step down (`min-width:104px`, 13px font) so
  ordinary tables need less scrolling; the article toolbar wraps.

Regression coverage: `node test_reader_behavior.js` (the "P2-3" block)
asserts the CSS contract and that a wide 8-column table renders as
exactly one wrapped table, never a bare `<table>` under `#articlebody`.

Manual verification protocol (for a device/browser session): build a
bundle whose article contains a wide table, e.g.

```bash
python3 publish.py --deliveries <fixture-with-wide-table> \
  --output /tmp/focu-wide-table-bundle --skip-audio-audit
```

open the article at a 390px viewport, and confirm
`document.documentElement.scrollWidth <= window.innerWidth` while the
`.table-scroll` element itself reports `scrollWidth > clientWidth`
(the table scrolls; the page does not). On 2026-11-18 this live-layout
step was not run in the dev environment (the managed Chromium cannot be
launched directly and the browser tool rejects loopback URLs); the
bundle markup and the CSS/behavior contract above were verified
instead. Run the protocol on the owner's phone after the next reader
rebuild ships.

## Acceptance limits

No original cover images were available. Controlled iPhone force-quit/reopen, lock-screen/background playback, and persistent playback position have not been verified. No daily automation or cross-device state sync is implemented. Static bundles must be rebuilt for new content. Do not publish private media URLs.

The original operator report from the Muse VM must be copied verbatim to `VALIDATION_REPORT.md` and extended only with the v3 outcome. Do not substitute a reconstructed summary for that source document.
