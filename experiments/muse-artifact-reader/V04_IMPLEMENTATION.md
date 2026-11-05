# Focu v0.4 — Article-first Muse reader

Development branch: feat/v04-unified-content-feed (PR #18, Draft).

This is a private, static Muse Artifact build. It never changes the production
focu-podcast-library entry.

## Product contract

One stable content_id identifies one research item even when both an article and
a podcast are available. Inbox shows each item once, with an editorial headline
and summary. Open the item to read the article and optionally tap Listen.
There is no Mark done or Done reading button.

Article completion: the reader must reach the article end, see at least 70% of
the available scroll area, and spend 8/18/30 active seconds (depending on text
length). Fast scrolling alone does not archive.

Audio completion: a native ended event plus at least 80% real played coverage
is needed; seeking to the end alone does not archive.

Either completion archives the whole Content Item. The Archive retains the
article and audio and has a Restore to Inbox option.

The consumption key remains focu:content-consumption:v1 and IDs are unchanged.
Muse WebView persistence across an in-place update and an iPhone force-quit
remains UNVERIFIED; keep PR #18 Draft until the device A/B test passes.

## Delivery folder inputs

    data/deliveries/<stable-content-id>/
        research.md       # evidence-backed report; fallback article
        article.md        # optional blog-style article; preferred
        podcast.mp3       # optional; copied byte-for-byte
        content.json      # optional editorial metadata and image URL
        cover.jpg         # optional local original image

JPG, JPEG, PNG and WebP covers are supported. At least one nonempty article
source or podcast audio is required. Article-only and audio-only items work.

An optional content.json may contain title, summary, source_image_url, and
sources (array of objects with image_url). Existing research Markdown is parsed
into structured text blocks with headings, links, findings and sources; untrusted
HTML is not injected into the WebView. If there is no curated title, the first
substantive finding is used rather than the generic research question.

## Publishing

Run offline tests:

    cd experiments/muse-artifact-reader
    python3 -m unittest discover -p 'test_*.py' -v

Offline, free default (no network or API key required):

    python3 publish.py --deliveries ~/workspace/focu/data/deliveries \
      --output ~/workspace/focu-artifact-builds/v04-new --limit 15

Opt-in public HTTPS original image download (from content.json only):

    python3 publish.py --deliveries /path/to/deliveries \
      --output /path/to/build --fetch-source-covers

Opt-in paid editorial prose and AI image generation:

    # OPENAI_API_KEY must be set in the operator's secret environment.
    python3 publish.py --deliveries /path/to/deliveries \
      --output /path/to/build --generate-editorial --generate-ai-covers

Editorial prose uses gpt-4.1-mini and an evidence-only prompt, validates that
cited URLs were present in the original report, and caches by report content
under .focu-editorial-cache next to staged builds. URL matching is NOT factual
verification. AI covers use gpt-image-1 and cache PNGs under
.focu-generated-covers next to staged builds. Both options incur API costs.
No key or personal cache is packaged in the Artifact.

Cover priority: local original image > optional public-HTTPS source image >
optional AI-generated image > offline typographic SVG. Offline SVG art is
deterministic, source-specific, and not a synthetic photograph. Provider failures
fall back to the safe offline mode and are recorded in build-report.json.
Legacy RSS image metadata is not yet universally carried into delivered
content.json; source download requires that metadata to be present.

The bundle includes index.html, embedded manifest, assets/episodes.json,
assets/audio, assets/articles, assets/covers and build-report.json.
The canonical items list can contain article-only content; the legacy episodes
array contains only audio-capable items.

## Acceptance

GitHub Actions runs publisher tests and Node JavaScript syntax check in addition
to existing Focu tests. This does not validate iOS scroll/reading timers, native
audio coverage, SVG rendering or cross-rebuild localStorage behavior.

Use the separate private focu-v04-test Artifact, not the production library.
Do not merge PR #18 until iPhone playback, reading completion, covers and
in-place persistence have been observed directly. The previous acceptance
report only documents the earlier v0.4 UI, not these changes.
