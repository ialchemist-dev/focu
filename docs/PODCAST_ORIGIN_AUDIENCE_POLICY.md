# Focu — Origin-aware podcast policy and audience calibration

Date: 2026-11-05. Draft PR #23: feat/podcast-origin-audience-policy.
Built independently from main. Do not merge or rebase onto Draft PR #22.

## Owner-approved behavior

- Registered-source content: individually readable articles, compiled once
  each day into one secretary briefing MP3. Each source item carries
  podcast_mode=daily_compilation and NO personal MP3.
- User-initiated research: article by default, podcast_mode=none. The owner
  can explicitly opt into a standalone audio recording per item.
- User content cannot be included in a registered-source daily compilation.
  Violation is an error, not a silent skip.
- Podcast is another format on the same content_id, never a duplicate card.
- One shared Inbox/Archive consumption state remains unchanged.

## Audience source of truth

Edit only references/audience-profile.md based on explicit owner feedback,
append a dated change record and commit. It encodes only owner-stated PhD,
software/ML engineer roles, CS/programming/ML expertise, and sociology as a
novice-domain example. Unknown domains default to working knowledge.

The same focu.audience module guides optional OpenAI article writing and
standalone Open Notebook audio. Host Muse research agents writing article.md
must call:

    focu audience-prompt --domain machine_learning

and apply the output to the actual article-writing instructions. Domain
selection is explicit, from article metadata, or conservative article-keyword
classification; it never changes the owner's expertise profile.

Expert: peer-level, exact mechanisms, numbers, negative controls,
replication, limitations and criticism, no beginners' metaphors.
Novice: define basics, explain unfamiliar terminology and scaffold learning.
Working-knowledge: light orientation without a basics lecture.

Audience QC reports searched patterns, matching excerpts, version/hash and
domain for every transcript. It is NONBLOCKING unless the owner later approves
a hard gate. Technical factual review remains required.

## Record an explicit podcast request

Default request (capture only; no background worker implied):

    focu request "Research this technical question" \
      --url https://example.org/post

Initial request that explicitly includes audio:

    focu request "Research this post and make a podcast" \
      --url https://example.org/post --podcast

The older capture command also accepts --podcast.

For a completed article, use an idempotent state transition:

    focu request-podcast int_<32_hex_characters> \
      --deliveries /private/data/deliveries

This records podcast_mode=single plus podcast_requested_at in SQLite and
updates the matching content.json when present. No hand-edited DB required.
Legacy intents migrate in place with preserved rows, defaulting to none.

The delivery must have the same canonical content_id, origin=user_initiated,
and finished article.md. It should also retain provenance and citations.

## Generate single-item audio

    focu podcast-for int_<32_hex_characters> \
      --deliveries /private/data/deliveries \
      --domain machine_learning

The command refuses unknown or non-single intents and uses the article,
not the raw research dump. Open Notebook is the existing configured provider:
episode profile solo_expert, speaker profile solo_expert. No new service,
credential or paid provider is enabled by this PR.

The generated transcript must preserve all Markdown article section headings
in order and every numeric token/figure in its own section. A section name
mentioned casually in body text is NOT proof of coverage. The script is
also checked for mismatch against the owner's expertise. Audience findings
are diagnostic only.

On fidelity failure: record podcast-qc.json and retry at most once. If both
attempts fail, do NOT attach audio. The original article remains readable.
On pass: validate and stage the actual MP3, attach podcast.mp3 and transcript,
update the same content.json, then rebuild the private static Artifact.

A literal-heading/number gate cannot independently prove that mechanism,
causation, or negative controls were explained accurately. Muse must also
perform a substantive factual review before calling the real episode ready.

## Daily item linkage

A source delivery has:
- origin: registered_source
- podcast_mode: daily_compilation
- its own article.md
- no per-item podcast.mp3

The day's compiled episode is a separate delivery with:
- origin: daily_compilation
- podcast_mode: daily_compilation
- date/published_at
- a single podcast.mp3
- covered_content_ids listing all corresponding source content IDs

The publisher verifies unique content IDs, at most one compilation per day,
complete source article coverage, no on-demand linkage and no stray MP3 for
any item with podcast_mode=none. The reader presents a small link from the
source article to its day's briefing. No new reader view is introduced.

Legacy records lacking podcast_mode get a display-only manifest default and
are not rewritten. New bundle validation still fails for a user-initiated
none item with an unauthorized MP3.

## PR #22 integration contract

PR #22 supplies the owner-editable secretary briefing *form* and multi-item
coverage QC; this PR supplies content-origin policy, audience *level/stance*,
and standalone audio. Neither should overwrite the other's source of truth.
When #22 is eventually merged, the combined daily generation prompt must
apply both files: briefing-style.md governs form and ordering;
audience-profile.md governs depth and critical stance. Preserve two separate
coverage gates. Check and resolve any overlap in CLI and daily pipeline when
integrating; this PR does not merge, modify or depend on #22.

## Private-only E2E acceptance

Run from an isolated clean worktree and test SQLite DB using a NEW generic
on-demand request. Do not use the existing Weight-Space Programming item.

Capture it without podcast; produce and verify the research article; ask for
and record an explicit podcast request; generate through the currently
authorized Open Notebook, check all transcript headings and figures, decode
the MP3 and publish one new immutable snapshot to a private focu-v04-test
Artifact. Check the newly available Listen button on iPhone. Test an item
without audio as article-only; never claim the static Artifact hot-updates.

Production checkout, production DB, sources.yaml, daily schedule, provider
credentials and production podcast library must remain untouched.
