"""Evidence-preserving editorial extraction for the static Focu reader.

No model calls and no invented research: titles and summaries are extracted from
existing research or explicit content.json. Structured article blocks are safe
to render with textContent in an untrusted-source WebView.
"""
import re

GENERIC_TITLE = re.compile(
    r"^(what is new|what.s new|latest updates?|daily|weekly|frontier briefing|"
    r"research briefing|what happened|focu.s registered research sources)",
    re.IGNORECASE,
)
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
REFERENCE = re.compile(r"\s*\((?:\[[^\]]+\]\(https?://[^)]+\)(?:,\s*)?)+\)\s*$")


def clean(text):
    text = REFERENCE.sub("", text or "")
    text = LINK.sub(r"\1", text)
    text = re.sub(r"[*_\x60#]+", "", text)
    return re.sub(r"\s+", " ", text).strip(" \t-–:.")


def shorten(text, limit):
    text = clean(text)
    if len(text) <= limit:
        return text
    prefix = text[:limit + 1].rsplit(" ", 1)[0]
    if len(prefix) < limit // 2:
        prefix = text[:limit]
    return prefix.rstrip(" ,;:.") + "…"


def blocks_from_markdown(markdown):
    """Convert Markdown to bounded, structured text blocks, not arbitrary HTML."""
    blocks = []
    lines = (markdown or "").splitlines()
    paragraph = []
    kind = "paragraph"
    fenced = False

    def flush():
        nonlocal paragraph
        if paragraph:
            text = "\n".join(paragraph).strip()
            if text:
                blocks.append({"type": kind, "text": text})
        paragraph = []

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith(chr(96) * 3):
            flush()
            fenced = not fenced
            kind = "code" if fenced else "paragraph"
            continue
        if fenced:
            if kind != "code":
                flush()
                kind = "code"
            paragraph.append(line)
            continue
        if not stripped:
            flush()
            kind = "paragraph"
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            flush()
            blocks.append({"type": "heading", "level": len(heading.group(1)),
                           "text": heading.group(2)})
            kind = "paragraph"
            continue
        bullet = re.match(r"^(?:[-*]|\d+\.)\s+(.+)$", stripped)
        if bullet:
            flush()
            blocks.append({"type": "bullet", "text": bullet.group(1)})
            kind = "paragraph"
            continue
        if stripped.startswith(">"):
            flush()
            blocks.append({"type": "quote", "text": stripped.lstrip("> ").strip()})
            kind = "paragraph"
            continue
        if line.startswith("  ") and blocks and blocks[-1]["type"] == "quote":
            blocks[-1]["text"] += " " + stripped
            continue
        if kind != "paragraph":
            flush()
            kind = "paragraph"
        paragraph.append(stripped)
    flush()
    return blocks[:500]


def editorial(markdown, metadata=None):
    metadata = metadata or {}
    blocks = blocks_from_markdown(markdown)
    heading = next((clean(b["text"]) for b in blocks
                    if b["type"] == "heading" and b["level"] == 1), "")
    findings = False
    claim = ""
    summary = ""
    for block in blocks:
        if block["type"] == "heading":
            findings = clean(block["text"]).lower() == "findings"
        elif findings and block["type"] == "bullet" and not claim:
            claim = clean(block["text"])
        elif not summary and block["type"] == "paragraph":
            summary = clean(block["text"])
    choice = metadata.get("title")
    if not isinstance(choice, str) or not choice.strip():
        choice = claim if (GENERIC_TITLE.search(heading) and claim) else heading or claim or summary
    synopsis = metadata.get("summary")
    if not isinstance(synopsis, str) or not synopsis.strip():
        synopsis = summary or claim
    title = shorten(choice, 82) or "Untitled research"
    summary = shorten(synopsis, 270)
    word_count = len(re.findall(r"\b[\w'-]+\b", markdown or ""))
    return {"title": title, "summary": summary, "article_blocks": blocks,
            "reading_minutes": max(1, round(word_count / 220))}
