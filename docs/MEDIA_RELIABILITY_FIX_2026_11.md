# Focu playback / completion reliability — 2026-11

**Change:** PR #21, branch `fix/media-completion-reader-stability`.

## User-observed symptoms versus verified findings

1. **Podcast UI reports ~6–7 min but stops early.** The actual private
   production MP3 and Muse iPhone playback are not accessible in this GitHub
   development environment, so the specific incident remains **Unverified**.
   Code inspection found that the publisher only checked that copies had
   matching SHA-256 and that Open Notebook wrote raw downloads directly into
   the final filename. Neither guaranteed full decodability or consistency
   between metadata duration and decoded playback duration.
2. **User-initiated research articles have no Listen button.** Confirmed:
   the publisher intentionally supports article-only content and the reader
   previously hid Listen whenever `formats.audio` was absent. This is now
   supplemented by opt-in **device-native Read aloud**, which uses the iOS/
   browser speech engine rather than paid API calls. A proper MP3 (when
   present) is always preferred.
3. **Consumed stories remain in Inbox.** The previous reader required
   article-end visibility *plus* a >=70% document-scroll metric, and audio
   required a native ended event plus >=80% played coverage. The scroll
   metric was fragile in embedded WebViews. Article completion now uses a
   visible end marker plus a minimum amount of foreground reading time.
   Legacy `article.html` without `research.md` also gets safe, structured
   native reader blocks. The consumption-state key is unchanged, but survival
   across Muse Artifact rebuilds is **not yet established**.

## Integrity changes

- Shared `focu.media_integrity.inspect_mp3` uses ffprobe metadata AND ffmpeg
  actual decoded output duration, rejecting missing, corrupt, non-MP3 and
  inconsistent MP3 audio. The tolerance allows encoder delay and up to 3%
  duration rounding, but not gross truncation.
- Open Notebook downloads are staged and validated before atomic replacement
  so an incomplete response cannot overwrite an existing verified file.
- The recurring audio pipeline uses the same validator.
- `publish.py` **CLI validates audio by default** and writes decoded
  durations and audit results to `build-report.json`. Direct Python
  `build()` callers must pass `verify_audio=True`; only test fixtures may
  use the CLI `--skip-audio-audit` override.
- `focu.media_integrity` includes an audit command that can scan all
  existing private delivery MP3s before choosing which need repair.
- The player compares native duration with audited duration and displays
  clear warnings about premature playback. It does not mark a prematurely
  ended podcast consumed.

## Cost decision

- Already-generated podcast: reuse cached MP3 (zero regeneration cost).
- Article only: show **Read aloud** and speak the content on the device.
  Focu does not call an external TTS API and charges no model tokens.
  Web Speech availability, audio behavior with the screen locked and
  long-reading stability in Muse iOS WKWebView require real-device tests.
  When unavailable, show an explanatory message; do not pretend an MP3
  exists.
- High-production-quality podcast for one selected article: let the user
  request generation via Muse, using the existing optional TTS/Open Notebook
  pipeline with explicit cost/credential consent, and cache the resulting
  MP3 for subsequent plays. Never auto-generate paid audio for every
  article simply because it appears in Inbox.
- Static Artifact cannot create and persist a new MP3 when a reader taps
  a button. A high-quality new podcast requires a Muse host task and a
  subsequent private Artifact rebuild.

## VM audit / acceptance protocol

Use a separate git worktree or checkout for PR #21; do not reset the
production workspace or overwrite validated bundles. Commands (adjust
the actual installation path):

```bash
cd ~/workspace/focu
.venv/bin/python -m focu.media_integrity \
  --deliveries data/deliveries \
  --output data/media-audit-v04.json

# After fixing all invalid source audio files, stage an immutable version:
.venv/bin/python experiments/muse-artifact-reader/publish.py \
  --deliveries data/deliveries \
  --output data/focu-artifact-builds/v04-reliability-test \
  --limit 15
```

This should **not** rewrite MP3s without a separate confirmation of paid
generation or remediation. Do not commit private audio or personal reports.

Check each failed audit item by inspecting the source and local playback,
then compare the bundled MP3 and original SHA-256. If local decoding is
correct but Muse iPhone playback stops, capture the exact item ID, audited
duration, native `audio.duration`, stop point and UI error/waiting events
so the remaining problem can be localized to Muse's asset serving or WebView.

### iPhone manual checks

- Open an article-only, user-initiated item. Confirm **Read aloud**
  appears, starts, can pause/resume, and only archives on successful full
  completion; no paid TTS call occurs.
- Open a real MP3 item. Confirm Listen uses the cached file, seeking works,
  and completing genuine playback archives it.
- Open an article and read to its actual end. Stay on screen long enough,
  return to Inbox and verify the item is gone; Archive contains it.
- Fast scroll to end and immediately exit; it should remain unread.
- Reopen and force-quit Muse, then repeat. Test an update-in-place of the
  **same private Artifact entry** preserving content IDs. If localStorage
  resets under the changed WebView origin, record **Fail** and do not
  claim persistence is solved.
- Check new UI spacing on a physical iPhone; the static preview is not proof
  of native rendering. Do not modify `focu-podcast-library` until verified.

**Release boundary:** CI passing confirms unit tests only. This branch is
not a complete production fix until actual MP3s and Muse iPhone behavior
have been inspected.
