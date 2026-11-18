# Focu cover style

Every Focu article automatically gets a cover image. This file is the
standing style instruction for those covers — for the built-in procedural
generator today, and for any model-based generator adopted later.

## The one rule above all others

The image is **only for gentle visual pleasure**. It is never bait:
never designed to make people look longer, scroll more, or click. If a
cover choice would work as clickbait, it is wrong here, however pretty.
This follows Focu's design philosophy — attention sovereignty: visuals
serve calm digestion, never engagement capture.

## Source

These rules adopt the owner's own blog-cover rules (the "Agent Adoption
Experiment Cover Image Rules" in the AI Praxis Lab site materials),
applied to Focu articles:

- **Style**: cute but sophisticated editorial illustration; soft 3D
  clay-paper look, tactile objects, rounded forms, gentle depth. Calm,
  personal, intentional — not childish, not corporate.
- **Composition**: 4:3 card-cover composition; one clear central still
  life over cluttered symbolic collages; readable at small card size;
  enough margin for responsive cropping.
- **Palette**: soft teal, warm cream paper, muted amber, graphite, and
  restrained coral / terracotta accents.
- **Lighting**: warm and cozy — morning light or soft dinner light.
- **Forbidden**: readable text of any kind; logos, brand marks, app or
  social-media icons; watermarks; people, hands, faces; robots or
  humanoid AI; neon sci-fi; dominant purple / purple-blue gradients;
  harsh contrast; generic stock-photo darkness. Represent agents
  abstractly: subtle light traces, workflow nodes, voice waveforms, or
  quiet tool arrangements.

## Prompt template (for a model-based generator)

```text
Use case: illustration-story
Asset type: small card cover image, 4:3 aspect ratio
Primary request: Cute but sophisticated cover image for an article about <article theme>.
Scene/backdrop: <one calm still-life scene tied to the article>.
Subject: <the article's meaning, in one quiet image>.
Style/medium: Warm editorial illustration, soft 3D clay-paper look, tasteful and minimal, not childish.
Composition/framing: 4:3 card cover, clear central still life, enough margin for cropping, no text.
Lighting/mood: <morning/evening> light, calm, focused, introspective.
Color palette: soft teal, warm cream, muted amber, graphite accents, optional restrained coral/terracotta.
Text (verbatim): none.
Constraints: no readable text, no logos, no app icons, no brand marks, no people, no hands, no faces, no robots, no social media icons.
Avoid: neon sci-fi, purple gradients, clutter, stock photo style, watermarks, anything that looks like clickbait.
```

`generate_ai_cover` in `experiments/muse-artifact-reader/cover_art.py`
embeds this spec in its prompt; keep the two in sync when either changes.

## The procedural generator (what ships today)

`procedural_cover_png(title, summary)` in
`experiments/muse-artifact-reader/cover_art.py` is the publisher's
fallback cover (`publish.py`, origin `procedural_art`):

- deterministic — seeded by the article's title + summary (SHA-256), so
  the same article always renders the same cover and republishing never
  changes it;
- pure Python standard library (no imaging dependency), 1200×900 PNG;
- approximates the style above with flat clay-paper shapes on a warm
  cream gradient: teal hills, an amber/terracotta sun disc with a soft
  halo, and one seeded motif (arch, graphite ring, or a low stack of
  rounded stones) plus three small accent dots, finished with subtle
  seeded grain;
- contains **no text and no faces by construction** — it cannot render
  either — and uses only the approved palette above.

Priority in the publisher stays: a real source image first, an opt-in
AI cover second (with the prompt above), the procedural cover last —
so every article ends up with exactly one cover.

## Reader behaviour

The Muse reader shows `procedural_art` covers in the feed card and at
the top of the article, like source and AI covers. The retired
`offline_art` typographic SVG placeholders (which rendered the article
title as text inside the image) are no longer generated, and bundles
that already contain them keep their previous behaviour — the reader
still hides that origin — so existing items keep working unchanged.
