"""Private cover assets for Muse snapshots: source images first, optional AI, offline art last.

Source image URLs are only fetched on explicit opt-in with the established SSRF
guard. AI generation is opt-in and billed to the user's own provider account.
"""
import base64
import hashlib
from html import escape
import json
import os
from pathlib import Path
import textwrap
import urllib.error
import urllib.request


def typographic_svg(title, summary):
    """Content-specific editorial artwork, deterministic, fully offline."""
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


def generate_ai_cover(title, summary, *, api_key, model="gpt-image-1"):
    if not api_key:
        raise ValueError("AI cover generation requires OPENAI_API_KEY")
    prompt = (
        "Create an editorial magazine illustration for a research article. "
        "No text, logos, captions, brands, or watermarks. Professional, restrained, "
        "highly relevant to this exact subject. Title: " + title[:180] +
        ". Context: " + summary[:360]
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
