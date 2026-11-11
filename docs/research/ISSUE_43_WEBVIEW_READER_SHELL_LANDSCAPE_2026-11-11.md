# Issue #43 — App-like reader shells for a hosted-webview static artifact: landscape, shortlist, mock plan

**Issue:** [#43](https://github.com/ialchemist-dev/focu/issues/43) (created 2026-11-11T07:43:12Z)
**Evidence captured:** activity 2026-11-11T08:45:06Z–08:46:40Z; bundle weights 2026-11-11T08:46:49Z (actual clock, JSON `captured_at`)
**Status:** desk research + API/CDN-measured data. **No installs, no local framework build, no production reader changes.** Adoption is a separate owner decision.
**Raw evidence:** [`evidence/issue-43-activity-snapshot.json`](evidence/issue-43-activity-snapshot.json), [`evidence/issue-43-bundle-snapshot.json`](evidence/issue-43-bundle-snapshot.json), script [`tools/oss_activity_snapshot.py`](tools/oss_activity_snapshot.py), configs [`evidence/issue-43-candidates.json`](evidence/issue-43-candidates.json), [`evidence/issue-43-bundle-config.json`](evidence/issue-43-bundle-config.json).

## 0. Recommendation (short)

| Rank | Candidate | Verdict | Migration shape vs publisher contract |
|---|---|---|---|
| 1 | [muxinc/media-chrome](https://github.com/muxinc/media-chrome) | **Adopt a component** (audio player controls only) — candidate to replace the hand-written `#playerbar` controls, keeping the native `<audio>` element and Focu's recovery/position logic | Keep `index.html`, `assets/episodes.json`, embedded manifest; swap player markup + one self-hosted IIFE file |
| 2 | [framework7io/framework7](https://github.com/framework7io/framework7) | **Borrow patterns / mock only** — most complete static "app shell" (iOS-style navbar, tabs, toolbar, safe-area CSS vars) but 281 KB gzip JS+CSS and a router/app model the reader does not need | Full shell rebuild that reads the *same* `episodes.json`; publisher unchanged except template |
| 3 | [ionic-team/ionic-framework](https://github.com/ionic-team/ionic-framework) (`@ionic/core` web components) | **Borrow patterns** (its `--ion-safe-area-*` variable system mirrors Focu's clearance vars); mock optional | Same as F7; lazy-loaded chunks must be self-hosted and verified |

**No candidate solves Muse host-chrome overlap.** All of them read `env(safe-area-inset-*)` (device notch/home indicator); none can know the height of *another app's* header/footer drawn over the webview. Focu's `--muse-header-clearance` / `--muse-chrome-clearance` variables (and the bounded query-parameter override) remain necessary under any framework. Framework7 and Ionic merely give the variable a standard name.

Rejected: **Pico CSS** (repository archived), **Konsta UI** (requires Tailwind build + React/Vue/Svelte; no static drop-in), **Vidstack** (active, but no GitHub releases and its CDN bundle embeds YouTube/Vimeo/Google ad-SDK hosts — heavier policy review for a no-external-request artifact than media-chrome for an audio-only need).

## 1. Baseline: the current hand-written reader (pain points from #31–#37)

`experiments/muse-artifact-reader/index.html` at `dee2e5d`: **38,631 bytes raw / 11,689 bytes gzip-9** (measured locally, includes all CSS+JS; zero absolute `http(s)://` hosts in the template). `publish.py` writes `assets/episodes.json` (`schema_version: 1`, `items`, `episodes`, `research_requests`), `assets/articles/*`, `assets/audio/*`, `assets/covers/*`, embeds the same JSON in `<script id="embedded-episodes">`, and writes `build-report.json` into an immutable versioned directory. Owner iPhone acceptance for that reader **passed on 2026-11-11 per the issue author's statement in #43** — not retested here.

| Pain point (issue) | Current bespoke fix | Media-chrome | Framework7 | Ionic core |
|---|---|---|---|---|
| Top host-chrome overlap (#37, PR #41) | `--muse-header-clearance` + query override; standalone resets to 0 | — | Navbar uses `--f7-safe-area-top` (device inset only) — still needs Muse var | `--ion-safe-area-top` (device inset; Capacitor can set `--safe-area-inset-*`) — still needs Muse var |
| Bottom chrome / home indicator (#33) | `--muse-chrome-clearance` + `env(safe-area-inset-bottom)` | — | Toolbar/tabbar `--f7-safe-area-bottom` | `ion-footer`/`ion-tab-bar` safe-area padding |
| Tabs unresponsive to taps (#37) | custom header tabs, hit-testing fixes | — | `.tabs`/tabbar components (not verified in Muse) | `ion-segment`/`ion-tabs` (not verified in Muse) |
| Sticky player + finger-sized seek (#33) | fixed `#playerbar`, 44 px controls, `touch-action:pan-x` | `<media-time-range>`, play/seek controls styled by CSS vars; audio mode documented | generic `range` component | `ion-range` |
| Audio silent while clock advances (#34) | "Recover audio" button + iOS CBR transcode in publisher | **Not addressed** (wraps the native element) | Not addressed | Not addressed |
| Scroll restoration / archive state (#31) | localStorage states, custom restoration | — | router page history (different model) | `ion-nav`/router (different model) |
| Wide Markdown tables (PR #41) | `.table-scroll{overflow-x:auto}` | — | No Markdown renderer; table CSS only | No Markdown renderer |

None of the candidates ships a Markdown renderer; Focu already renders article blocks itself.

## 2. Candidate matrix with dated activity (hard requirement)

Same definitions as the #42 document / script docstring. Window: commits since 2026-08-13T08:45:06Z; contributors since 2026-05-13T08:45:06Z; issue search dates ≥ 2026-08-13.

| Repo | License | ★ | Commits 90d | Human contributors 6mo | Last default-branch commit | Latest GitHub release | Issues opened / closed 90d (open now) | Maintainer reply in sample (median h) | Activity verdict |
|---|---|---:|---:|---:|---|---|---|---|---|
| ionic-team/ionic-framework | MIT | 52,750 | 171 | 22 | 2026-11-10 | v9.0.10 (2026-10-28) | 61 / 202 (443) | 1/15 (2.4 h) | **Active** (low comment rate in sample; triage may happen by labels/closing) |
| muxinc/media-chrome | MIT | 2,768 | 23 | 12 | 2026-11-09 | v4.19.4 (2026-10-23) | 13 / 14 (2) | 2/13 (406 h); 11/13 sampled issues closed | **Active** |
| framework7io/framework7 | MIT | 18,774 | 18 | 4 | 2026-10-30 | v9.2.0 (2026-09-28) on GitHub; npm `latest` is 9.3.0 | 7 / 9 (231) | 1/7 (144 h) | **Active, small team** (bus-factor risk; 231 open issues) |
| konstaui/konsta | MIT | 4,289 | 8 | 4 | 2026-10-15 | v5.5.0 (2026-09-28) | 3 / 2 (10) | 1/3 (577 h) | Active-but-light; rejected on static-fit |
| vidstack/player | MIT | 3,734 | 10 | 8 | 2026-10-07 | none on GitHub (npm 1.15.7) | 7 / 148 (1) | 4/6 (917 h) | Active; rejected on fit (see §0) |
| picocss/pico | MIT | 16,818 | 2 | 1 | 2026-10-04 | v2.1.1 (2025-03-15) | 1 / 1 (93) | 0/1 | **Rejected — archived** |

Vidstack's 148 closed vs 7 opened in 90 days indicates a bulk close, recorded without interpretation.

## 3. Static-bundle compatibility and weight (measured)

Bytes below are the actual files served by jsDelivr for the npm `latest` version at capture time, downloaded into memory (never executed or saved) and gzip-compressed with Python `gzip` level 9. "Hosts mentioned" is a static text scan for absolute URLs in the file — it includes comments/license links and is **not** proof of runtime requests.

| Package@version | File | Raw bytes | gzip-9 bytes | Hosts mentioned | Static use per official docs |
|---|---|---:|---:|---|---|
| media-chrome@4.19.4 | `dist/iife/index.js` | 178,115 | 43,363 | `www.w3.org` (SVG namespace) | README shows `<script type="module">` from jsDelivr; same file can be self-hosted ([README](https://github.com/muxinc/media-chrome/blob/main/README.md)) |
| framework7@9.3.0 | `framework7-bundle.min.js` | 808,365 | 209,791 | `framework7.io`, `www.w3.org` | Core is plain JS/CSS with no build requirement ([docs/app](https://framework7.io/docs/app)) |
| framework7@9.3.0 | `framework7-bundle.min.css` | 485,792 | 71,891 | `framework7.io`, `www.w3.org` | — |
| @ionic/core@9.0.10 | `css/ionic.bundle.css` | 38,657 | 6,119 | none | [CDN doc](https://ionicframework.com/docs/intro/cdn) presents CDN use "for quick testing" |
| @ionic/core@9.0.10 | `dist/ionic/ionic.esm.js` (loader only) | 25,424 | 6,314 | `ionicframework.com` | **Lower bound:** components lazy-load additional chunks relative to the loader; total depends on used components — unmeasured |
| vidstack@1.15.7 | `cdn/with-layouts/vidstack.js` | 214,664 | 57,519 | jsDelivr, YouTube/Vimeo CDNs, `doubleclick.net`, `gstatic.com` … | Provider support code; would need runtime audit |
| @picocss/pico@2.1.1 | `css/pico.min.css` | 83,319 | 11,640 | `picocss.com`, `www.w3.org` | Archived repo |
| konsta@5.5.0 | — | — | — | — | No prebuilt static bundle; Tailwind + React/Vue/Svelte build ([README](https://github.com/konstaui/konsta/blob/master/README.md)) |

Reference: current reader 11,689 bytes gzip total. Media-chrome adds ~43 KB gzip; a Framework7 shell adds ~281 KB gzip before Focu code.

**Static-webview verification status:** verified from docs + actual bundle contents only. No local static build was run (no existing local copies; installs out of scope). For Ionic, whether `ion-icon` fetches SVGs from a CDN when assets are not self-hosted is a **known unknown** to be checked in the mock with network logging.

## 4. iOS WKWebView behaviour — what is documented vs unknown

| Topic | Evidence | Status |
|---|---|---|
| Safe-area insets | Framework7 `app-vars.less` maps `--f7-safe-area-*` to `env(safe-area-inset-*)` ([source](https://github.com/framework7io/framework7/blob/master/src/core/components/app/app-vars.less)); Ionic `core.scss` maps `--ion-safe-area-*` with Capacitor override ([source](https://github.com/ionic-team/ionic-framework/blob/main/core/src/css/core.scss)) | Documented |
| Host-app chrome (Muse header/footer) | No framework can observe another app's overlay | **Unsolved by any candidate**; keep Muse clearance vars |
| `100dvh`/`svh` pitfalls | Not systematically documented by any candidate reviewed | Unknown — test in mock |
| Audio element in background / long MP3 (#34) | Media-chrome wraps the native element; no WKWebView decoder-stall handling documented | Unknown — keep Focu recovery + CBR transcode |
| Sticky positioning inside Muse scroll container | No candidate-specific evidence | Unknown — test in mock |

## 5. Aesthetics — real demos (URLs returned HTTP 200 on 2026-11-11)

- Framework7 Kitchen Sink (iOS/Material themes, navbar/tabbar/toolbar): https://framework7.io/kitchen-sink/core/ — the most "opens like a native app" of the set, but iOS-system look rather than Focu's warm editorial style.
- Ionic component docs with live previews: https://ionicframework.com/docs/theming/advanced
- Media-chrome audio player screenshot in repo: [`docs/public/assets/media-chrome-audio-player.png`](https://github.com/muxinc/media-chrome/blob/main/docs/public/assets/media-chrome-audio-player.png); themes gallery https://www.media-chrome.org/docs/en/themes
- Konsta UI: https://konstaui.com/ ; Vidstack: https://vidstack.io/

Judgement: the current reader's minimal editorial look is not inferior to these demos; the frameworks add native-chrome *conventions* (large-title navbar, tab bar, sheet transitions), not better typography. Whether that reads as "more app-like" is an owner call on the device.

## 6. Mock plan for the top candidate (plan only — not executed)

Top pick for a low-risk mock is **media-chrome** (component), with an optional second arm **Framework7** (full shell) so the owner compares both against the baseline.

1. Input: the existing 17-item acceptance bundle (same `assets/episodes.json`, articles, audio, covers). Copy read-only into a new private test directory; never overwrite the accepted bundle or the production Artifact.
2. Arm A (media-chrome): copy `index.html` to a new template; replace `#playerbar` controls with `<media-controller audio>` + `<media-play-button>`, `<media-time-range>`, `<media-time-display>` around the existing `<audio id="player">`; keep Recover-audio and position persistence; vendor `media-chrome@4.19.4/dist/iife/index.js` into `assets/vendor/` with its sha256 in `build-report.json`.
3. Arm B (Framework7): new template using `framework7-bundle.min.{js,css}` vendored locally; navbar + tabbar for Daily Briefing / Research; same embedded manifest parsing; keep `--muse-*-clearance` added on top of `--f7-safe-area-*`.
4. Static checks before device test: no `http(s)://` references in shipped HTML except article/source links; open with network inspector (Safari Web Inspector against simulator or device) and record zero third-party requests.
5. Owner iPhone checklist reused from #31–#34/#37 (tabs, header/footer clearance, 44 px targets, seek drag, archive/restore, scroll restore, wide tables, audible long playback).
6. Decision record: adopt / layout-layer only / borrow / reject per arm.

## 7. Known unknowns and limitations
- No local build, no device run; WKWebView behaviour of candidates is from docs/source only.
- Ionic total weight is a lower bound (lazy chunks). Framework7 GitHub release (v9.2.0) lags npm `latest` (9.3.0) — weights are from npm 9.3.0.
- Maintainer-response metric misses CONTRIBUTOR-association maintainers and label-only triage (Ionic shows 202 closed in 90 days despite 1/15 comment replies in the sample).
- Hosts-mentioned scan is textual; a real runtime network audit is part of the mock plan.
