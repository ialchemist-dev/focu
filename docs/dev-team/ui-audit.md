# Focu Reader — UI Audit & Redesign Spec

**Role:** UI Developer, 24h multi-agent dev run (dev-main).
**Scope audited:** `experiments/muse-artifact-reader/` in the dev checkout — `index.html` (581 lines, the entire app: markup, CSS, JS in one file), `publish.py` (data shape it emits), `editorial.py` (title/summary/reading-time extraction). The checkout's `episodes.json` is an empty stub (`{"episodes": []}`), so all data-shape claims come from `publish.py`'s payload construction and `index.html`'s `normalize()`. Method: static code audit; tap counts and pixel budgets are counted from the code, not from a device session.
**Yardstick:** `attention-sovereignty.md` — display surfaces yes, control surfaces no; "Look. Understand. Judge. Leave."; compression ladder (most items 0.5s, a few 10s, one earns a full read); success = attention **returned**.

**Standing constraints respected throughout:** Daily Briefing / Research tabs stay separate; iOS Safari playback (the publisher's `--ios-compatible-audio` CBR path and the single `<audio>` element) is untouched; all state stays local and private — no new network calls, no telemetry.

---

## 1. Audit findings

Each finding names the principle it violates, then the evidence in code.

### F1 — Playing today's briefing costs 2 taps + 1 scroll (best case), 3 taps (worst case). There is no play control anywhere in the feed.
*Principle: de-interface — the daily briefing is the one action the owner takes almost every day; every step between intent ("hear today's briefing") and outcome is mechanical operation, not judgment.*
- The feed card is a single open-button plus an Archive button (`index.html` render loop, ~L229–L256); no card carries a play affordance even when `audio_url` exists.
- Play lives only inside the reader: `document.getElementById('listen').onclick` at L475, on the `#listen` button in the toolbar (L107).
- The toolbar sits *below* the reader cover (`.readercover` up to 340px tall, L43), the 30–45px title, and the summary paragraph (reader markup L102–L107). On a phone, Listen is typically below the first screenful of the article — so the real path is: tap card → scroll → tap Listen.
- If the `player.play()` promise rejects, the catch sets "Tap Play to start audio" (L475 handler) and the user must tap the player bar's play/pause as a third tap.

### F2 — The cost of an item is invisible at the decision point, even though the data already carries it.
*Principle: attention sovereignty is control over **how much** attention a task may require. You cannot exercise that control if the price is shown only after you've paid it.*
- `publish.py` L248 writes `formats.audio.duration_seconds` (decoded, audited) for every audio item; `editorial.py` L274–L276 computes `reading_minutes` (words / 220). `normalize()` (L161) extracts both as `audio_duration` and `reading_minutes`.
- Neither is rendered on a feed card. `reading_minutes` appears exactly once, inside the reader toolbar (L346, "N min read") — after opening. `audio_duration` is never displayed at all; its only uses are integrity warnings after playback starts (L514–L539).
- Consequence: the owner cannot tell a 6-minute episode from a 26-minute one before committing — the exact misallocation the philosophy exists to prevent.

### F3 — There is no glance layer. The card shows ~a quarter of a summary that was written for a different surface.
*Principle: the compression ladder — most items deserve half a second. A 0.5s layer must be a single short line, not a truncated paragraph.*
- `editorial.py` L270–L271 caps titles at 82 chars and summaries at 270 chars. The card then clamps the summary to 2 lines (`.feedsummary`, L38, `-webkit-line-clamp:2`).
- Card body width on a phone is ~200px (390px screen − page padding − 92px cover − gaps), so 2 lines at 14px show roughly 55–70 characters — about 25% of the 270-char summary, cut mid-thought with an ellipsis the CSS doesn't even add (clamp hides overflow silently).
- There is no distinct gist field anywhere in the pipeline: one text is forced to serve glance, scan, and reader surfaces, and serves the glance worst.

### F4 — The first screen is spent on chrome and plumbing before any content.
*Principle: display surfaces should compress understanding; the first screen is the most expensive real estate the app owns.*
- Sticky header: 68px host clearance (`--muse-header-clearance`, L9) + 64–70px bar (`.head`, L15) ≈ 132–138px before content, holding brand + three tabs + a refresh button (L98).
- Below it, a section title (L100) and an always-visible status line (render, L217) that speaks in system voice: item counts, and on fallback "embedded snapshot (manifest unavailable)" — pipeline plumbing the owner never acts on.
- Each card's minimum height is ~134px on mobile (21px×2 padding + 92px cover, L94/L39), so roughly **3 cards** fit the first screen — and every one of them carries its own bordered Archive button (`.card-action`, L28; created per-card at L243), a control repeated at full visual weight on items the owner hasn't judged yet.

### F5 — Un-compiled source items compete at full weight inside the Daily Briefing view.
*Principle: de-recommendation — the agent is the final filter; the briefing view should present the agent's compressed judgment first, not the raw stream it filtered.*
- `render()` (briefing branch) appends every uncovered registered-source item after the briefings, under "Source updates not yet in a briefing" (L226), each rendered as a full card identical in weight to a briefing.
- These are precisely the items the system has *not* yet compressed into the briefing — the 200-posts problem reappearing inside the surface built to solve it. (They must stay reachable — the owner's rule — but reachable ≠ equal prominence.)

### F6 — Nothing resumes. All position state is in-memory; only "consumed" survives a reload.
*Principle: attention returned includes not re-paying orientation costs. Re-finding your place is pure mechanical operation.*
- Consumption status persists in `localStorage` under `focu:content-consumption:v1` (L132–L140) — good. But `feedPositions` and `articlePositions` are plain in-memory objects (L134), and audio position / `listenedSeconds` are module variables. Close or reload the artifact and every half-read article restarts at the top, every half-heard episode at 0:00, with no "continue" marker anywhere.
- The player itself has no memory: reopening an item always constructs playback from the start (Listen handler, L475).

### F7 — The player bar carries a permanent repair control and speaks in engineering diagnostics.
*Principle: control surfaces should appear when judgment is needed, not squat on the display. A rare failure's control should surface on the failure, not before it.*
- "↻ Recover audio" is always rendered in the player bar (L115; handler L485) — a decoder-reset for a rare WebKit silent-audio failure. It permanently consumes the now-playing row and truncates the episode title (ellipsis on `#nowplaying`).
- The failure handlers that *do* exist only change text — and the text is engineering speech pushed at the user: "Audio ended earlier than the verified file duration. Please report this playback problem." (L516), "Player duration differs from verified audio · Try reopening if playback cuts off" (L539). The owner is being asked to do QA reporting — attention spent on the system's problems, returning no understanding of content.
- Conversely, two controls a listener legitimately exercises judgment with are missing: there is no −15s/+30s skip and no playback-rate control; the only seek is a 1000-step range slider (L115) — fine-motor scrubbing is mechanical work, worst exactly when listening away from the desk.

### F8 — Two audio buttons make the user model the system's internals.
*Principle: de-interface — the user expresses one intent ("hear this"); which engine produces the voice is implementation.*
- The reader toolbar holds both `#listen` (cached podcast) and `#readaloud` (device speech synthesis), with visibility logic in `openItem` that swaps them based on `failedAudioId` and block availability. When audio fails, the user is presented a *different button with a different label* and a state message ("Cached audio could not load. Try device read-aloud instead.") — they must understand the two-engine architecture to proceed.

### F9 — The reader's first screen re-spends attention on what the card already showed.
*Principle: each surface should add compression or understanding, not repeat the previous surface at larger size.*
- Reader order (L102–L107): back button, cover up to 340px tall, byline, title, then the *same* summary text the card showed (now at 17px), then the toolbar. The one genuinely new thing on this screen — the article — starts below all of it.
- Note the publisher already spends effort making a cover for every item (`publish.py`: source image, AI cover, or typographic SVG fallback); in the feed, `offline_art` covers are suppressed (render, cover branch) but real covers still set the 88–92px card height that throttles F4's density.

### What already aligns — keep and build on it
- **Auto-archive on completion:** reading to the end + a length-scaled dwell (7s / 13s / 20s, L571–L572) marks an item consumed; ≥80% listened does the same for audio (L519); device narration marks done at its end. Finished items leave the feed without any filing action. This is the philosophy working — judgment happened, operation vanished.
- **Playback survives tab switches** (`setView`, L170 comment) — the display can be left without stopping the audio.
- **"You are all caught up."** empty state (L220) — the app is willing to be empty and let the user leave. Rare and correct.
- Consumption state is local-only; the whole reader is a static bundle. Privacy posture is already right.

---

## 2. Redesign spec — "simple and delightful"

Design target, in the owner's words operationalized: **open → understand today in under 5 seconds → one tap to hear it → leave.** Everything else is subordinate.

### 2.1 First-screen hierarchy (Daily Briefing tab)
1. **Slim header** (~44px + host clearance): small `focu.` wordmark and the two tabs + Archive as quiet text tabs. No refresh button (see 2.3). The header is a display of *where you are*, nothing more.
2. **Today hero — the 0.5s layer.** Today's briefing as one block, not a card among cards:
   - Line 1 (glance): `Today · 4 items · ▶ 18 min` — date, count, total audio cost, all from data already published.
   - Line 2 (agenda): the briefing's own agenda as a single flowing line of item titles (the audio already opens with this agenda; mirror it in text).
   - One large **▶ Play today's briefing** button. One tap from open to listening — the F1 fix.
3. **"In today's briefing" — the 10s scan layer.** The covered items as compact one-line rows: gist (see 2.2) + source + cost chip. Tapping a row opens that item's article. This replaces today's separate full cards for covered sources.
4. **Earlier briefings** below, as compact rows (date + item count + total duration + ▶), newest first. History is reference, not a stream competing with today.
5. **One collapsed line** for un-compiled sources: `6 source updates not yet in a briefing` — expands on tap (F5 fix). Reachable, one line, zero competition.
6. Status/plumbing text disappears from the resting UI. It appears only when it *is* the content: a failed load, or "New briefing ready" after an auto-refresh (2.3).

Research tab keeps its current shape (it is a library, not a daily habit) with two changes: cost chips on every card (F2), and "Requests in progress" demoted to compact rows in the same one-line style — a queued request is not a report and shouldn't wear a report's 20px title (render, L190–L200).

### 2.2 The compression ladder, per item
Three distinct texts, three distinct jobs. This requires one new field from the pipeline (see implementation #5); the reader work is trivial once it exists.

| Layer | Budget | Content | Where |
|---|---|---|---|
| **Glance** | 0.5s | Gist: one line, ≤ ~90 chars, written to be complete at that length (never a truncation). Plus cost chip: `▶ 6 min` or `4 min read`. | Feed rows, hero agenda |
| **Scan** | 10s | The existing ≤270-char summary, unclamped to its natural 3–4 lines, + covered-item count for briefings. | Expanded row / top of reader |
| **Read** | full | The article, unchanged typography (17px/1.9 is already good). | Reader |

Rules: a layer never shows a cut-off version of the layer below it (kills F3's silent clamp); the reader's scan summary is the article's lead, not a repeat of the card (kills F9's duplication — the card's glance gist and the reader's summary are different texts by construction once `gist` exists).

### 2.3 Control surface: removed or automated
- **Refresh button — removed.** `load()` already runs on open (L579); add a staleness check on `visibilitychange` (reload if >5 min since last successful load). The owner never operates freshness.
- **Recover audio — removed from the resting UI.** Show it only when the `stalled` handler fires or when playback time advances with no audible progress signal we can detect; auto-run the existing recovery sequence once before ever showing the button. Diagnostics text (F7) rewritten to plain language with no action requested of the owner: "Audio glitch — restarted where you left off."
- **Listen / Read aloud — merged into one Play control.** Cached audio first; on audio error, fall back to device narration automatically with a one-line note in the player bar. The two-engine architecture becomes invisible (F8).
- **Archive — kept, quieted.** It is a judgment (dismiss), so it stays one tap away, but loses its bordered-button weight on cards: small, borderless, text-only at the row's end. In the reader it stays in the toolbar as today.
- **Player bar — judgment controls in, motor controls out.** Add −15s / +30s skip buttons (judgment: re-hear, skip ahead) beside play/pause; keep the slider for coarse position display but no longer as the only seek path. On completion-archive, the bar dismisses itself after a few seconds — the app leaves when the user should.

### 2.4 Delights that cost no attention
- **Resume everywhere (the big one).** Persist per-item audio position and article scroll in the existing localStorage store. Rows show `▸ Continue · 3:12 left`; opening or pressing play restores position silently. No dialog, no setting.
- **One-tap play** (hero, 2.1) — the daily ritual becomes: open, tap, pocket the phone.
- **Position memory already works in-session** (feed scroll per tab, article scroll per item, L134/L167); extending it across reloads makes the app feel like it remembers the owner's day, not just their archive.
- **The caught-up state, kept and slightly celebrated:** when the briefing is consumed and no research is pending, the first screen is just `All caught up · Next briefing tomorrow ~05:44` and whitespace. An app confident enough to be empty.
- **No autoplay chains, no "up next," no streaks.** When the episode ends, the app ends. Leaving is the delight.

---

## 3. Ranked implementation list for dev-main

Savings estimates assume the owner's actual pattern: one briefing/day (~15–25 min audio), a few research reports/week, mostly iPhone. "Cycle" = one work cycle in this run.

### #1 — One-tap Play + duration chip on briefing cards *(single cycle)*
- **Files:** `index.html` only (render loop; reuse the L475 play path by extracting a `playItem(item)` helper used by both card and reader).
- **Behavior:** any card/row whose item has `audio_url` gets a compact `▶ 18 min` play button (duration from `audio_duration`, already normalized at L161). Tapping it starts playback and shows the player bar without opening the reader. Tapping the card body still opens the article.
- **Attention saved:** the daily path drops from tap → scroll → tap (→ tap) to **one tap, zero scroll**. Removes the single most repeated operation in the product.

### #2 — Cost chips on every card *(single cycle)*
- **Files:** `index.html` only (render loop + small CSS class).
- **Behavior:** every card shows its price before commitment: `▶ {audio_duration}` when audio exists, `{reading_minutes} min read` otherwise (both fields already in the normalized item; `reading_minutes` is already rendered in the reader at L346 — this moves the same datum to the decision point).
- **Attention saved:** prevents the worst misallocation — opening a 26-minute episode in a 5-minute gap — and lets the owner budget the whole day from the hero line (sum of chips). Zero new data, zero pipeline change.

### #3 — Persist resume state *(single cycle)*
- **Files:** `index.html` only (extend the `STORE_KEY` store; save on `timeupdate` throttled + on scroll; restore in `openItem` and in the play path); add cases to `test_reader_behavior.js`.
- **Behavior:** per-item `{audio_pos, article_pos}` survive reload. Rows with a saved position show `Continue · {remaining}`. Playback resumes at the saved position; finished items (>95% or consumed) clear their position.
- **Attention saved:** every interrupted episode/article stops charging re-orientation (re-open, re-scrub, re-find place). Estimated 30–60s returned per interruption, and it compounds with #1 (Continue becomes the fastest tap in the app).

### #4 — Auto-refresh; delete the ↻ button and the resting status line
- **Files:** `index.html` only (header markup L98, `load()` L576, `visibilitychange` handler next to the existing one).
- **Behavior:** load on open (unchanged) and again when the view becomes visible with data older than 5 minutes. The header loses the refresh button; `#status` renders only for load errors or a one-time "New briefing ready" that fades into the hero. Fallback/plumbing notes ("embedded snapshot…") move to `console` / a build-report, never the UI.
- **Attention saved:** one control and one line of system speech removed from every single open; freshness becomes the system's job.

### #5 — Add a true glance gist to the pipeline
- **Files:** `editorial.py` (emit `gist`: a complete ≤90-char shortening of the synopsis, sentence-boundary aware, never mid-word), `publish.py` (pass `info["gist"]` into the item, alongside L239–L240), `index.html` (`normalize()` + card render uses `gist`; summary moves to reader/scan), `test_publish.py` (gist presence + length).
- **Behavior:** cards render the gist as their single text line; card height becomes cover-independent — switch feed covers to a 56px thumb so a row is ~76px and 6–7 items fit the first screen (from ~3).
- **Attention saved:** creates the 0.5s layer the philosophy specifies; roughly doubles first-screen comprehension per open. This is the change that makes the ladder in 2.2 real instead of aspirational.

### #6 — Player: contextual recovery, plain-language errors, skip buttons, self-dismissal
- **Files:** `index.html` only (player bar markup L115, `stalled`/`error` handlers, recovery handler L485, `ended` handler); extend `test_reader_behavior.js` recovery cases (they currently assert the button's presence — update to assert it is hidden until invoked by a stall).
- **Behavior:** Recover button hidden by default; on `stalled`, run the existing decoder-reset automatically once, then reveal the button only if that fails. All diagnostic strings rewritten to owner language with no requested action. Add −15s/+30s buttons. When an episode completes and auto-archives (L519), the bar auto-hides after 4s.
- **Attention saved:** the now-playing title stops being truncated by a repair control; failures stop billing the owner as a QA reporter; scrubbing-by-slider during listening (the highest-friction in-episode operation) is replaced by two coarse taps.

### #7 — Reader first screen: Play before prose, cover demoted
- **Files:** `index.html` only (reader markup order L102–L107 + `.readercover` CSS L43).
- **Behavior:** toolbar (Play + read time + Archive) moves directly under the title; the summary follows as the article's lead; cover caps at 160px tall (still full-width, still skippable when absent). Net effect: Play is tappable with zero scroll on any phone.
- **Attention saved:** even for users who open the article first, the audio decision is one glance + one tap; removes F9's duplicated-summary screen tax on every open. (Pairs with #1; #1 makes this path rare, #7 makes it cheap when taken.)

### #8 — Briefing-view purity: un-compiled sources collapse to one line
- **Files:** `index.html` only (briefing branch of `render()`, L226 area; one expandable row component + CSS).
- **Behavior:** uncovered source items render as a single collapsed row — `N source updates not yet in a briefing` — expanding in place to the current full cards on tap. Covered sources keep appearing under the hero's scan layer (2.1) as one-line rows.
- **Attention saved:** the Daily Briefing tab's resting state contains only agent-compressed material — the de-recommendation boundary made visible. The raw stream costs exactly one line until the owner asks for it.

---

## Notes for the integrator
- #1–#4, #6–#8 are `index.html`-only and independently landable in any order; #5 is the only cross-layer change (publisher + reader) and should land with its `test_publish.py` cases in the same commit.
- Nothing above touches the audio pipeline, the iOS CBR transcode, `content.json` semantics, or the two-tab structure. The `focu:content-consumption:v1` store key stays the same in #3 (extend the per-item object; don't migrate).
- Deliberately **not** proposed: settings screens, notification controls, sort/filter UI, folders, search. Each would be a control surface charging rent on every open for a judgment the agent should absorb or the owner makes once in conversation, not daily in the UI.
