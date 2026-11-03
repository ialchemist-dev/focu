# Muse Artifact static reader spike

This is an **experiment**, not proof that Muse hosts persistent Artifacts.

## Goal
Render existing MP3s in a responsive, Xiaohongshu-inspired static library **inside Muse**, with cover images and native HTML audio seeking. No database, build step, cloud credentials, or external hosting required for the initial test.

## Files
- `index.html`: standalone static UI; reads `episodes.json` from the same directory.
- `episodes.json`: example manifest; replace with **real** media URLs or relative paths available to the hosting origin.

Manifest shape: `{"episodes":[{"id":"unique-id","title":"Title","date":"2026-11-02","source":"Source","cover_url":"https://.../cover.jpg","audio_url":"https://.../episode.mp3"}]}`.

## Muse acceptance procedure
1. Copy `index.html` and `episodes.json` into Muse's persistent workspace. Replace example entries with 2–5 **already generated** MP3 files and optional original cover images.
2. Ask Muse to create/open an in-app Artifact/web preview from `index.html`. If it requires a server, use `python3 -m http.server 8765` in this folder; **do not assume localhost is accessible from the iPhone**.
3. In Muse iOS, open the preview/Artifact; verify cards, audio playback, seeking, cover loading, and reload.
4. Close the conversation, reopen the **same** Artifact from the Muse library, and repeat after an app restart.
5. Add one episode to the manifest without rebuilding the UI. Reload the existing Artifact; record whether it reflects the update.
6. Repeat the following day. Capture the stable entry point (if any), whether it persists, and whether media files remain accessible.

## Limitations
- A static page cannot read arbitrary private VM paths; files must be served by the same origin or have browser-accessible URLs. Cross-origin audio must be accessible to the browser, and seeking depends on the media server supporting range requests.
- No read/archive synchronization, upload API, or authentication in this spike.
- Do not expose private MP3s through public URLs merely to make the demo work.
- Muse's in-app Artifact persistence and automatic refresh are **hypotheses to test**, not guaranteed platform features.
