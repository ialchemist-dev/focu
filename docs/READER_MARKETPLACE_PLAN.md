# Focu: finite reader and source marketplace

## Product contract
A personal mobile reading/listening app backed by the existing Focu research pipeline. A published batch is finite and immutable: browsing never starts collection or generation. Reading completion removes an item from the inbox, not from storage. Saved items and history remain accessible; completion is reversible. One Evidence Pack has one consumption identity across its reading, audio and video presentations. A scroll or lack of interaction is not feedback.

## Experience
- Today: compact editorial cards; title, summary, source labels, estimated reading time; an explicit end state.
- Detail: cited research report plus optional local audio/video; original URLs remain accessible. Only available formats are offered.
- Complete / undo / save; durable SQLite state shared across devices using the same server.
- Discover: searchable, categorized source packs; inspect authors, URLs, collection readiness and affiliation evidence before explicitly subscribing.
- Library: saved and completed content. No popularity ranking or engagement optimization.
- Installable web manifest, standalone mode, mobile safe areas, app-shell service worker. Private API responses and user content are never cached by the worker.

## Data and interfaces
Existing IntentStore -> EvidenceStore -> DeliveryArchive remain the research truth. Add:
- reader_items: immutable presentation snapshot keyed by evidence_id, cited Markdown, summary, media paths.
- reader_batches + batch_members: atomic, immutable, ordered finite selections with caller-controlled IDs and a maximum item budget.
- reader_state: explicit completion/save state, separate from collection and generation dedup.
- versioned source-pack JSON: ID, version, categories, discovery coverage, authors, URLs, identity evidence, verification status/date and collection method.
- subscriptions: pinned pack version and source membership snapshot. Subscribing again is idempotent; updating versions is explicit. Shared sources deduplicate by canonical locator; removing a pack preserves sources required by other packs.
- `focu reader publish`: publish already archived, evidence-linked research; no LLM or TTS call.
- `focu reader serve`: serve app and same-origin JSON APIs on loopback by default.
- `focu reader sources`: export subscribed sources for Muse; existing source schema stays compatible.

## Implementation dependency order
1. Durable item/batch/state and subscription contracts with regression tests.
2. Python API + mobile reader + source-pack browser + manifest/offline app shell.
3. Muse handoff: source export -> research ingest/report/podcast -> finite publish. Publishing does not authorize recurring scheduling or expanded sources.
4. Anthropic employee blog discovery: public LinkedIn discovery where accessible, author sites and official bios for identity cross-check; inspect feeds; retain candidates and failures. Publish only supported memberships. Coverage is explicit, never described as a complete employee census.
5. Production hosting adapter and live mobile acceptance after the local end-to-end flow; preserve the Python/SQLite core. Hosted access requires HTTPS and authentication; do not expose the development server to the internet.
6. Extend collectors, generation orchestration and video renderers behind the same contracts. Existing PRs #1/#4 require migration from the_few; #7/#9 are independently reviewable; #13 does not implement employee discovery.

## Acceptance
- Existing report + local audio can appear as one card; completing it survives server restart and does not reappear under a second format.
- Retrying publication is idempotent; reusing IDs with changed membership fails without partial writes.
- Empty feed is a terminal state. GET routes never generate, collect or publish.
- Source pack details expose membership and readiness; only explicit subscription changes active sources.
- Two overlapping packs export one source; unsubscribe preserves remaining memberships.
- Untrusted report text is displayed safely; media reads cannot escape the configured media directory; cross-origin mutations fail.
- Installable shell and iPhone layout are checked separately from actual iOS installation, remote access and live Muse generation.

## Scope tracking
This document describes the entire target and its dependencies, not a time schedule. Implementation status and verification are recorded in the PR and READER_APP.md. The first runnable implementation can use existing generated material without waiting for broad source discovery or new AI orchestration.
