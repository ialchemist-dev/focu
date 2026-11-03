# Focu Podcast Library — Muse Artifact Validation Report

**Date:** 2026-11-02 (America/Denver)
**Subject:** End-to-end acceptance test of the Focu podcast library as a persistent, native Muse Artifact, following `experiments/muse-artifact-reader/README.md` from focu PR #17 (branch `experiment/muse-artifact-static-reader`).
**Artifact:** `focu-podcast-library` (Muse web artifact, runtime `static`, private, `shared_publicly=false`, no server actions, no database)
**Staging source:** `~/workspace/experiments/muse-artifact-reader/` on the Muse VM (`index.html` from PR #17, populated `episodes.json`, `audio/*.mp3`)
**Scope note:** This report documents findings only. No fixes were applied. Items are labelled **[platform]** (Muse platform behaviour), **[code]** (artifact implementation), **[data]** (source data gap), or **[test]** (missing/unverifiable test evidence).

---

## 1. What was built and verified working

- The artifact bundles **5 real Focu episodes** as local assets under `assets/audio/` (no Tailscale, no Google Drive, no external hosting, no public MP3 URLs; audit shows `external_requests=[]`, `broken_assets=[]`):
  - Frontier Research Briefing — Nov 2, 2026 (414.9s, 6,639,404 bytes)
  - Frontier Research Briefing — Oct 31, 2026 (452.6s, 7,243,052 bytes)
  - Frontier Research Briefing — Oct 30, 2026 (416.3s, 6,662,060 bytes)
  - Frontier Research Briefing — Oct 29, 2026 (444.8s, 7,118,252 bytes)
  - Hunger Beats Tenure — Felix Rieseberg (Oct 28, 2026) (334.6s, 5,355,308 bytes)
- Bundled MP3 file sizes match the Focu delivery files byte-count exactly; MD5 equality against `~/workspace/the-few-focu-test/data/deliveries/*/podcast.mp3` was verified by the operator for spot-checked files before bundling. Nothing was regenerated or re-encoded.
- Rendering audit passes: navigation 200, zero console errors, mobile layout at 390px viewport with 0px horizontal overflow, no clipped or unreachable controls on desktop or mobile. Cards render English text, newest-first, with titles, dates, durations, and source links.
- Player implementation (single shared `<audio preload="metadata">`): play/pause with state updates, seek slider bound to `currentTime`, −15s/+30s buttons, next-episode autoplay on `ended`, playback-speed cycling, per-card progress, Media Session handlers. A live probe at build time drove the player successfully (load → play → two +30s seeks → time display advanced to 1:06 with progress in sync; durations matched ffprobe). See §4 for the evidence-strength caveat.
- Persistence: the artifact is a Library catalog entry independent of any chat; it was re-listed and re-rendered in a fresh session after the originating conversation. Reopening does not depend on a localhost server.

## 2. Acceptance matrix

| # | Test | Result |
|---|------|--------|
| 1 | Card layout renders correctly on iPhone (viewport) | **Pass** (390px audit; physical-device check still recommended) |
| 2 | Existing MP3s play, pause, and support seeking | **Pass** (live probe at build time; see §4 caveat) |
| 3 | Original article images appear as covers when available | **No data / not implemented** — see Finding F2 |
| 4 | Same Artifact reopenable after closing the conversation | **Pass** (catalog persistence verified) |
| 5 | Artifact survives a Muse app restart | **Unverified** — see Finding F5 |
| 6 | Adding an episode to `episodes.json` updates the UI without rebuilding | **Fail** — see Finding F1 [platform] |
| 7 | Media and UI accessible after a new Muse session | **Pass** (fresh-session re-render verified) |
| 8 | Missing-media and malformed-data handling | **Fail / not tested** — see Findings F3, F4 |

## 3. Findings

### F1 [platform] Static artifacts are build-time snapshots — manifest hot-update is impossible
- **Test performed:** the workspace `episodes.json` next to the staging `index.html` was edited to add a 6th real episode (Frontier Research Briefing — Oct 28, 2026, `frontier-20261028`, MP3 copied into staging `audio/` and MD5-verified). The artifact itself was not edited or rebuilt.
- **Result:** the served artifact still contains exactly the original 5 episodes. The published bundle is frozen at build time: the build manifest (`.space-build/manifest.json`) records a fixed asset list (6 assets: `index.html` + `episodes.json` + 5 MP3s at the time), a fixed `built_at` (2026-11-03T03:18:49Z) and content hashes. Workspace edits never propagate.
- **Implication:** the PR #17 design (page fetches `episodes.json` at runtime) only supports live updates on a mutable host. On Muse, the operating model is **one artifact rebuild per library update**. Any docs or UI copy implying live manifest updates on Muse are wrong. A daily flow must fold a rebuild into delivery, and library size growth is ~5–7 MB per episode (rolling window advisable).

### F2 [data]+[code] No original covers exist, and the cover code path does not implement `cover_url`
- **Data:** none of the 5 episodes has any cover image. Focu delivery directories contain only `podcast.mp3`, `research.md`, `transcript.json`. `assets/episodes.json` has no cover field on any entry; the bundle contains zero image files (`images.total=0` in audit).
- **Code:** `render()` in `index.html` unconditionally sets `cover.innerHTML = coverSVG(ep)` — an inline SVG date/waveform tile generated from the episode id. There is **no branch that reads `ep.cover_url`**, despite the in-page validation text claiming the markup "prefers a real cover_url when present". That claim is false as shipped and should be corrected or implemented.
- **Implication:** two separate fixes are needed before original covers can ever appear: (a) artifact code must actually branch on `cover_url` (render `<img>` when present, SVG tile otherwise) and the manifest schema must carry the field; (b) upstream, the Focu generation pipeline currently emits no cover image at all, so there is nothing to reference even with (a) in place.

### F3 [code] Missing-media (audio) failures are invisible to the user
- There is **no `error` or `stalled` event listener** on the `<audio>` element anywhere in `index.html`.
- `loadEpisode()` only catches a rejected `play()` promise to reset card state. A 404/corrupt MP3, a decode failure, or a stalled load produces no user-visible "audio unavailable" state on the affected card; the user cannot distinguish a broken file from a slow one.
- **No negative test exists:** no run with a renamed/missing MP3 was ever performed or recorded (see F6).

### F4 [code] Malformed or missing manifest is silently masked; malformed entries can break rendering
- The manifest load chain is `fetch('assets/episodes.json') … .catch(function(){ init(FALLBACK); })` — on **any** fetch or parse failure the page silently initialises from `FALLBACK`, a hard-coded duplicate of the 5-episode manifest embedded in the script. A missing/corrupt manifest is presented as stale success with no error status shown to the user.
- The `FALLBACK` duplicate is a drift hazard: it must be manually kept in sync with `episodes.json`, and already duplicates the full dataset inside `index.html`.
- `render()`/`coverSVG()` dereference entry fields (e.g. `ep.date`, `ep.id`) with **no per-episode validation guard**. One malformed entry in the manifest can throw and break rendering of the whole grid instead of being skipped and reported.

### F5 [test] "Survives a Muse app restart" was never exercised
- The in-page report labels this "By design" and defers it to the user. No force-quit/reopen test on a physical iPhone exists, and none can be produced from the build VM. Background/lock-screen playback behaviour and playback-position persistence across app restarts are likewise untested (position is kept in memory only and resets when the page closes).
- **Status:** unverified, not failed. The only valid test: on the iPhone, force-quit Muse, reopen, and open "Focu Podcast Library" from the Library.

### F6 [test] Evidence gaps in the shipped validation material
- The embedded TESTS list has 8 entries and **none covers missing-media or malformed-data handling** (acceptance item 8).
- The bundle's audit transport ledger is ~2.5 KB with no MP3 fetch, no HTTP Range (206) log, and no `timeupdate`/seek timestamps. Playback/seeking "Pass" therefore rests on the build-time live probe and code inspection, and cannot be re-verified from the archived bundle alone.
- The bundle contains **no hash comparison against the original Focu delivery files**; the page header's byte-identity claim is plausible (sizes agree across all copies) but is asserted, not evidenced, inside the artifact.
- PR #17's README is not included in the bundle, so fidelity to the PR template beyond the page's own attribution cannot be checked from the artifact alone.

## 4. Sandbox / platform limitations summary (for planning)

1. Static web artifacts are immutable snapshots; every content change is a rebuild (new build id, new version). There is no live file serving from the workspace.
2. A static artifact has no server actions and no database (`has_server_actions=false`, no app.db); any state (read position, completion) cannot persist server-side in this architecture.
3. Media must be bundled into the artifact at build time; the artifact cannot read arbitrary VM paths at runtime, and private media must not be moved to public URLs to work around this.
4. Device-level behaviours (app restart, background audio, lock screen) are not testable from the build environment; they require a physical-device pass.

## 5. Preservation requirements for any follow-up work

- Keep all bundled MP3s byte-for-byte (no re-encode, no regeneration, no mock/sample content) and keep the artifact private and static; do not convert it to a server/database artifact.
- Do not point audio at Tailscale, Google Drive, external hosting, or public URLs.
- Do not modify production Focu data, credentials, the existing Focu reader UI/service, or the daily cron/pipeline.
- Do not silently upgrade any Fail/Unverified label in the validation report to Pass without a real, recorded test (in particular F1, F5, F6 items).

## 6. Suggested remediation order (for the development agent; not yet authorized/performed)

1. F4/F3 robustness: visible manifest-error status (fallback, if kept, must be labelled as cached data), per-episode validation guard that skips and reports a malformed entry, and an `<audio>` error handler that marks the affected card "audio unavailable".
2. F2 code half: implement the real `cover_url` branch + manifest field; correct the in-page claim until then. (The data half — Focu emitting covers — is an upstream pipeline decision.)
3. F6: add recorded negative tests (renamed MP3; corrupted `episodes.json`; malformed entry) and an explicit playback log (loaded duration, play, pause, seek target, resulting `currentTime`) to the validation material.
4. F1: document the rebuild-per-update operating model wherever the library is described; do not attempt to work around the snapshot model with external hosting.
5. F5: leave marked Unverified until a physical iPhone force-quit/reopen test is done.
