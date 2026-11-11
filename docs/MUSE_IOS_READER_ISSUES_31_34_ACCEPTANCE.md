# Muse iPhone acceptance: Reader and long MP3 playback (Issues #31–#34)

**Status:** execution handoff. GitHub CI cannot establish audible sound in an iOS WKWebView.

For the **private test Artifact only**. Never overwrite the production Artifact or delivered source audio in troubleshooting.

## Prepare one test snapshot with an actual 24-minute episode

1. Fetch the PR branch (or merged main) into a clean, isolated worktree. Keep the original Nov 9 VBR MP3 and its checksum intact; verify it still decodes fully with ffmpeg and ffprobe.
2. Use the updated publisher to build a **new** immutable output directory:

~~~bash
python experiments/muse-artifact-reader/publish.py \
  --deliveries "$ISOLATED_DELIVERIES" \
  --output "$NEW_PRIVATE_TEST_BUNDLE" \
  --limit 15 \
  --ios-compatible-audio
~~~

3. This flag emits 128 kb/s mono 44.1kHz CBR MP3 **inside the bundle**, without modifying the source VBR delivery. It requires source and destination full-decode duration audits. Confirm the build-report's audio_transforms has both hashes, CBR profile and comparable decoded durations. No paid model calls.
4. Publish only to the private test Artifact. Verify its embedded manifest, checksums and stable content IDs.
5. Record old/new audio hashes, file sizes, stream settings, decoded durations and app/device version.

## Owner iPhone verification

- **#31:** Daily Briefing shows only compiled briefs plus any as-yet uncompiled official updates, newest first. Research shows completed commissioned reports and pending request status. From the briefing, open covered source articles then Back; confirm Archive/Restore, scroll restoration and background audio across tabs.
- **#32:** Daily article and script must have no dangling Figure/Table/Chart N references. Inspect preserved measured figures and original citation links.
- **#33:** The player sits clear of Muse bottom chrome and the home indicator. Play and seek controls have touch targets at least 44px tall. Test taps and drags before/after 04:30. If layout clearance is wrong, use the bounded player-clearance query parameter 0 to 160px as a diagnostic, then tune CSS from measured screenshots.
- **#34:** Listen audibly to the Nov 9 24:02 episode, including minutes 4–8 and later sections; a moving clock alone is not a PASS. Try pausing/resuming, seeking, and briefly backgrounding/foregrounding. If audible sound stops while time advances, tap **Recover audio**, then note whether it resumes from the earlier timestamp and sound returns. Only actual on-device continuous audible playback to the end counts as resolved.

## Limitations and diagnostics

- Full ffmpeg decode and loudness scans already show the original episode has non-silent sound. Do not regenerate narration or weaken editorial QC for this bug.
- CBR encoding is a targeted compatibility experiment, **not confirmed** to fix the WKWebView silent-output bug.
- HTMLMediaElement currentTime and timeupdate cannot prove real audible output. The reader does not claim to detect silent sound. Recover resets the audio decoder using the existing media URL, then seeks after metadata; it does not count the seek as listening or auto-archive.
- If the output still stops, collect player events (playing, waiting, stalled, pause, error, ended), media clock, audio route / interruption status, and whether locking the screen or switching apps mattered. Keep any host-specific fix separate.
- Source audio is unchanged. Report source/published hashes and decoded durations.
- If the device is unavailable, report iPhone behavior **UNVERIFIED** even when CI is green.

Do not change the 06:14 production schedule, source list, personal Wiki or everyday Podcast Library. Publish owner-observed results in a separate Draft documentation PR.
