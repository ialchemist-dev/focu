# Muse-native Focu Artifact: end-to-end acceptance

This branch is a **Muse-only validation**, not a production sync or hosting deployment. Reuse the existing image-first Focu reader design when integrating; do not create a parallel product. No Tailscale, Google Drive, public MP3 URLs, or external website is required **if** Muse can package local audio as Artifact assets.

## Components
- `index.html`: standalone, responsive two-column cards and native HTML audio seeking. It tries `episodes.json` on refresh and falls back to the embedded snapshot when network/fetch is unavailable.
- `episodes.json`: manifest with stable episode IDs; starts empty. Fill from *existing* Focu deliveries, not mock titles.
- Local MP3s and optional original covers must be **accessible inside the Artifact's browser origin**. A VM filesystem path (e.g. `/home/muse/episode.mp3`) is **not** a browser URL. Relative URLs only work if Muse actually bundles or serves the referenced files. A `file://` URL is intentionally unsupported.

## Muse agent instruction (copy all)

Work on the existing Focu checkout and preserve all current deliveries, databases, credentials, and existing reader UI. Use branch `experiment/muse-artifact-static-reader` (PR #17) as the validation fixture. Do not install Tailscale, configure Google Drive, create public links, deploy a website, or regenerate podcasts.

1. Find 2–5 already generated podcast MP3s and associated titles, timestamps, source names and original cover images, if present. Never fabricate entries. Confirm file sizes are nonzero.
2. Make a **persistent native Muse Artifact** using the reader HTML. Try bundling MP3s and images as local Artifact assets. Set each `audio_url` and `cover_url` to a browser-resolvable relative path. Create `episodes.json` with stable IDs. If Muse does not support multi-file Artifact assets, embed a small manifest into the `embedded-episodes` JSON script in the HTML and report the limitation; do **not** inline large MP3 files as base64 without explicit approval.
3. Open the Artifact inside the Muse mobile app. Verify covers, English UI, audio play/pause, seeking to the middle, completion, and switching episodes. Verify no external media origin is used.
4. Close/reopen the conversation and restart the app. Open the **same Artifact**; record whether media still works and whether its entry point remains stable.
5. Add one *existing* episode to `episodes.json`, without rebuilding the HTML. Press Refresh or reopen. Record whether the same Artifact shows it. If not, determine whether the Artifact is a frozen snapshot or its manifest is dynamically accessible. Do not report auto-refresh as passing merely because a newly generated Artifact contains the new entry.
6. Test missing MP3, missing cover, invalid manifest, duplicate ID, and empty list. Confirm graceful UI errors. Restore the original manifest afterward.
7. Return a concise pass/fail report with exact Artifact entry point, asset paths (not private tokens), media origin, refresh mechanism, failures, and screenshots if possible. Never claim cross-device state sync or playback-position persistence unless explicitly tested.

Acceptance gate: same Artifact opens after restart; 2+ real MP3s play and seek; missing assets fail visibly; one new entry appears without rebuilding HTML. If the update gate fails, document the limitation and propose a minimal host-side publishing mechanism, without deploying it.

## Security and limitations
The reader stores no credentials and does not send playback events to a server. It does not currently persist progress, saved/read/archive state, or sync between devices. `episodes.json` fetch can fail inside sandboxed Artifacts; in that case the embedded snapshot is displayed with a warning. The fallback is **not** dynamic updates. A static Artifact alone cannot guarantee visibility of future VM files or their URL mapping. Verify these properties in Muse before declaring the end-to-end flow complete.
