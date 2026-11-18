"""Private cover assets for Muse snapshots: source images first, optional AI,
procedural art last.

Source image URLs are only fetched on explicit opt-in with the established SSRF
guard. AI generation is opt-in and billed to the user's own provider account.
The last-resort cover is `procedural_cover_png`: a deterministic, fully
offline PNG in the house style recorded in docs/cover-style.md — soft
abstract shapes on warm cream, subtle grain, NO text, NO faces, nothing
designed to bait attention. It replaces the old typographic SVG, whose
rendered title text violated that style.
"""
import base64
import hashlib
from html import escape
import json
import math
import os
from pathlib import Path
import random
import struct
import textwrap
import urllib.error
import urllib.request
import zlib


def typographic_svg(title, summary):
    """DEPRECATED legacy fallback: renders the title as text inside the art,
    which docs/cover-style.md forbids. Kept only so old bundles/tests that
    import it do not break; publish.py no longer uses it (procedural PNG
    is the fallback since P2-4)."""
    digest = hashlib.sha256((title + "\n" + summary).encode("utf-8")).digest()
    palettes = [
        ("#1b3834", "#79a59e", "#dae6da"),
        ("#302b4e", "#aaa1d3", "#ece8f3"),
        ("#513a32", "#cb987c", "#efe0d0"),
        ("#1e3c58", "#84acc7", "#e1edf2"),
        ("#4b3548", "#bb8fae", "#efdee8"),
    ]
    dark, middle, light = palettes[digest[0] % len(palettes)]
    lines = textwrap.wrap(title, width=24, max_lines=4, placeholder="…")
    headline = "".join(
        '<text x="75" y="' + str(338 + idx * 62) +
        '" fill="' + light + '" font-family="Arial, sans-serif"'
        ' font-size="47" font-weight="700">' + escape(line) + "</text>"
        for idx, line in enumerate(lines)
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="650" viewBox="0 0 900 650">'
        '<rect width="900" height="650" fill="' + dark + '"/>'
        '<circle cx="' + str(635 + digest[1] % 120) + '" cy="100" r="250" fill="' + middle + '" opacity=".35"/>'
        '<circle cx="790" cy="440" r="330" fill="none" stroke="' + middle + '" stroke-width="2" opacity=".8"/>'
        '<circle cx="790" cy="440" r="270" fill="none" stroke="' + middle + '" stroke-width="2" opacity=".45"/>'
        '<path d="M0 230 Q260 120 520 230 T940 120" stroke="' + middle + '" opacity=".6" fill="none" stroke-width="3"/>'
        '<text x="75" y="86" fill="' + light + '" font-family="Arial, sans-serif"'
        ' font-size="20" letter-spacing="5">FOCU / RESEARCH</text>'
        '<rect x="75" y="258" width="74" height="4" fill="' + middle + '"/>'
        + headline +
        '<text x="75" y="603" fill="' + light + '" font-family="Arial, sans-serif" font-size="18" opacity=".75">Read · Listen · Reflect</text>'
        '</svg>'
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# Procedural covers (P2-4). Style contract: docs/cover-style.md.
# Palette is restricted to the owner's blog-cover family: warm cream paper,
# soft teal, muted amber, terracotta, restrained coral, graphite. No purple,
# no neon. Shapes are flat clay-paper abstractions (disc, hills, arch, ring,
# small accent dots) painted as per-row intervals, so rendering is fast in
# pure stdlib Python; grain is a seeded speckle pass. The seed is the
# article's title + summary, so the same article always gets the same cover
# and different articles get visibly different ones.
# ---------------------------------------------------------------------------

COVER_WIDTH = 1200
COVER_HEIGHT = 900  # 4:3 card composition, per the style spec

_CREAM_TOP = (246, 238, 222)
_CREAM_BOTTOM = (238, 224, 199)
_TEAL = (95, 141, 132)
_TEAL_DEEP = (65, 112, 106)
_AMBER = (217, 164, 65)
_TERRACOTTA = (196, 113, 75)
_CORAL = (211, 128, 106)
_GRAPHITE = (67, 72, 77)


def _blend(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _png_bytes(width, height, rgb):
    """Encode raw RGB bytes as a PNG (filter 0 rows, zlib)."""
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    stride = width * 3
    raw = b"".join(b"\x00" + bytes(rgb[y * stride:(y + 1) * stride])
                   for y in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def procedural_cover_png(title, summary=""):
    """Deterministic 1200x900 PNG cover seeded by the article. No text."""
    digest = hashlib.sha256((title + "\n" + (summary or "")).encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[16:24], "big"))
    w, h = COVER_WIDTH, COVER_HEIGHT
    layout = digest[0] % 4
    # Seeded placement jitter, kept well inside calm margins.
    sun_cx = w * (0.66 + (digest[1] % 17 - 8) / 100.0)
    sun_cy = h * (0.30 + (digest[2] % 13 - 6) / 100.0)
    sun_r = h * (0.16 + (digest[3] % 5) / 100.0)
    sun = _AMBER if digest[4] % 2 else _TERRACOTTA
    arch_cx = w * (0.30 + (digest[5] % 15 - 7) / 100.0)
    accent = _CORAL if digest[6] % 2 else _AMBER

    def circle(row, cx, cy, r):
        dy = row - cy
        if abs(dy) > r:
            return None
        dx = math.sqrt(max(r * r - dy * dy, 0.0))
        return (cx - dx, cx + dx)

    def ellipse(row, cx, cy, rx, ry):
        dy = (row - cy) / ry
        if abs(dy) > 1:
            return None
        dx = rx * math.sqrt(max(1 - dy * dy, 0.0))
        return (cx - dx, cx + dx)

    # Shape painters, back to front. Each returns (x0, x1, rgb) intervals
    # for one row; flat colours keep the clay-paper feel and the speed.
    def shapes(row):
        out = []
        # Distant hill: a broad ellipse rising from the bottom edge.
        iv = ellipse(row, w * 0.22, h * 1.28, w * 0.78, h * 0.62)
        if iv:
            out.append((iv[0], iv[1], _TEAL))
        # Near hill from the opposite corner.
        iv = ellipse(row, w * 0.88, h * 1.38, w * 0.72, h * 0.58)
        if iv:
            out.append((iv[0], iv[1], _TEAL_DEEP))
        # Sun disc with one soft halo ring (pre-blended against cream).
        iv = circle(row, sun_cx, sun_cy, sun_r * 1.22)
        if iv:
            out.append((iv[0], iv[1], _blend(_CREAM_TOP, sun, 0.35)))
        iv = circle(row, sun_cx, sun_cy, sun_r)
        if iv:
            out.append((iv[0], iv[1], sun))
        if layout in (0, 2):
            # Arch: semicircle top over a quiet column — a doorway still
            # life, the house motif for an agent that waits calmly.
            top_r = w * 0.085
            base_y = h * 0.86
            if row <= base_y:
                if row < base_y - top_r * 2.4:
                    iv = None
                elif row < base_y - top_r * 1.4:
                    iv = circle(row, arch_cx, base_y - top_r * 1.4, top_r)
                else:
                    iv = (arch_cx - top_r, arch_cx + top_r)
                if iv:
                    out.append((iv[0], iv[1], _TERRACOTTA if layout == 0 else _TEAL_DEEP))
        if layout in (1, 2):
            # Graphite ring, thin and restrained, upper left.
            ring_cx, ring_cy, ring_r = w * 0.20, h * 0.26, h * 0.105
            outer = circle(row, ring_cx, ring_cy, ring_r)
            if outer:
                inner = circle(row, ring_cx, ring_cy, ring_r * 0.82)
                if inner:
                    out.append((outer[0], inner[0], _GRAPHITE))
                    out.append((inner[1], outer[1], _GRAPHITE))
                else:
                    out.append((outer[0], outer[1], _GRAPHITE))
        if layout in (1, 3):
            # A low stack of two rounded stones (overlapping ellipses).
            iv = ellipse(row, w * 0.60, h * 0.80, w * 0.13, h * 0.075)
            if iv:
                out.append((iv[0], iv[1], _TERRACOTTA))
            iv = ellipse(row, w * 0.615, h * 0.715, w * 0.095, h * 0.06)
            if iv:
                out.append((iv[0], iv[1], _AMBER if layout == 3 else _CORAL))
        # Three small accent dots, like quiet workflow nodes.
        for k in range(3):
            dx = w * (0.44 + 0.055 * k) + (digest[7 + k] % 13 - 6)
            iv = circle(row, dx, h * (0.60 + 0.028 * (k % 2)), 11 + 3 * k)
            if iv:
                out.append((iv[0], iv[1], accent))
        return out

    image = bytearray(w * h * 3)
    stride = w * 3
    for row in range(h):
        base = _blend(_CREAM_TOP, _CREAM_BOTTOM, row / max(h - 1, 1))
        line = bytearray(base * w)
        for x0, x1, rgb in shapes(row):
            lo = max(int(x0), 0)
            hi = min(int(x1), w - 1)
            if hi >= lo:
                line[lo * 3:(hi + 1) * 3] = bytes(rgb) * (hi - lo + 1)
        image[row * stride:(row + 1) * stride] = line
    # Subtle grain: seeded speckles nudging pixels a few steps darker or
    # lighter — paper texture, never noise for its own sake.
    for _ in range(14000):
        x = rng.randrange(w)
        y = rng.randrange(h)
        idx = (y * w + x) * 3
        delta = rng.choice((-14, -9, 9, 14))
        for c in range(3):
            image[idx + c] = min(255, max(0, image[idx + c] + delta))
    return _png_bytes(w, h, image)


def generate_ai_cover(title, summary, *, api_key, model="gpt-image-1"):
    if not api_key:
        raise ValueError("AI cover generation requires OPENAI_API_KEY")
    # Style spec: docs/cover-style.md (the owner's blog-cover rules).
    prompt = (
        "Use case: illustration-story. Asset type: small card cover image, "
        "4:3 aspect ratio. Create one calm cover image for this article. "
        "Style/medium: warm editorial illustration, soft 3D clay-paper look, "
        "tactile rounded forms, tasteful and minimal, not childish. "
        "Composition: one clear central still life, enough margin for "
        "cropping, readable at small card size. Lighting/mood: warm morning "
        "or soft dinner light, calm, focused, introspective. Color palette: "
        "soft teal, warm cream paper, muted amber, graphite accents, "
        "restrained coral/terracotta. The image is only for gentle visual "
        "pleasure — never clickbait, never designed to hold attention. "
        "Text (verbatim): none. Constraints: no readable text, no logos, no "
        "captions, no brands, no watermarks, no people, no hands, no faces, "
        "no robots, no app or social-media icons. Avoid: neon sci-fi, purple "
        "gradients, clutter, generic stock-photo style. "
        "Subject context (do not render any words from it): " + title[:180] +
        ". " + summary[:360]
    )
    payload = json.dumps({
        "model": model, "size": "1024x1024", "quality": "low",
        "n": 1, "prompt": prompt,
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=payload,
        headers={"Authorization": "Bearer " + api_key,
                 "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.load(response)
    raw = result.get("data", [{}])[0].get("b64_json")
    if not isinstance(raw, str):
        raise ValueError("Image provider did not return image bytes")
    image = base64.b64decode(raw, validate=True)
    if not image.startswith(b"\x89PNG\r\n\x1a\n") or len(image) > 10_000_000:
        raise ValueError("Image provider returned invalid or oversized PNG")
    return image


def fetch_source_cover(url, stage):
    """Use existing Focu public-HTTPS, non-private-network fetch restrictions."""
    try:
        from focu.cover_archive import mirror
    except ImportError as exc:
        raise RuntimeError("Install the focu package to fetch source covers") from exc
    return mirror(url, stage)


def candidate_source_image(metadata):
    candidate = metadata.get("source_image_url")
    if isinstance(candidate, str) and candidate:
        return candidate
    for source in metadata.get("sources", []) if isinstance(metadata.get("sources"), list) else []:
        if isinstance(source, dict) and isinstance(source.get("image_url"), str):
            return source["image_url"]
    return None
