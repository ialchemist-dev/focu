"""Marketplace catalog + recommended default for bundled source packs.

P2-2 deliverable: a machine-readable catalog generated from the repo's
packs (``focu/source_packs/*.json``) and a single self-contained static
page that can be dropped into aipraxislab.com as a subpage.

Design rules (attention sovereignty):
- The catalog is generated, never hand-edited: every number in it is
  derived from a validated pack file, so the page cannot drift from
  what ``focu pack install`` would actually install.
- Exactly one recommended default: People I Follow. A default serves
  the user's objective only when the user asked their agent to choose
  (docs/dev-team/q11-cold-start-design.md); it is never silent, never
  a bundle, and swapping it is preview -> uninstall -> install.
- The page is calm by construction: no scripts, no external assets,
  no tracking, no ranking by popularity. Packs are listed with the
  recommended one first, the rest alphabetically.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from focu.packs import PACKS_DIR, validate_pack

SLOGAN = "Focu: the way to digest information in the agentic age."
REPO_URL = "https://github.com/ialchemist-dev/focu"
SITE_URL = "https://aipraxislab.com/focu"
RECOMMENDED_PACK_ID = "followed-people"
SCHEMA_VERSION = 1


def _attention_total(pack):
    total = 0.0
    for src in pack.get("sources", []):
        if src.get("enabled") is True:
            cadence = src.get("cadence") or {}
            ppm = cadence.get("posts_per_month")
            if isinstance(ppm, (int, float)) and not isinstance(ppm, bool):
                total += ppm
    return round(total, 4)


def pack_entry(pack, filename):
    """One catalog entry for a validated, normalized pack."""
    pack_file = f"focu/source_packs/{filename}"
    return {
        "id": pack["id"],
        "name": pack["title"],
        "title": pack["title"],
        "description": pack["description"],
        "version": pack["version"],
        "verified_at": pack["verified_at"],
        "tags": list(pack.get("tags") or []),
        "curator": pack.get("curator"),
        "source_count": len(pack["sources"]),
        "enabled_source_count": sum(
            1 for s in pack["sources"] if s.get("enabled") is True),
        "posts_per_month": _attention_total(pack),
        "attention_estimate": pack.get("attention_estimate"),
        "pack_file": pack_file,
        "recommended": pack["id"] == RECOMMENDED_PACK_ID,
        "preview_command": (
            f".venv/bin/focu pack preview {pack_file} --config sources.yaml"),
        "install_command": (
            f".venv/bin/focu pack install {pack_file} "
            "--config sources.yaml --yes"),
        "uninstall_command": (
            f".venv/bin/focu pack uninstall {pack['id']} "
            "--config sources.yaml"),
    }


def build_catalog(packs_dir=None):
    """Build the marketplace catalog dict from the bundled packs.

    Raises ValueError if any bundled pack fails validation — a catalog
    that lists a broken pack is worse than no catalog.
    """
    packs_dir = Path(packs_dir) if packs_dir is not None else PACKS_DIR
    entries = []
    for path in sorted(packs_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        report = validate_pack(raw)
        if not report["valid"] or report["pack"] is None:
            raise ValueError(
                f"bundled pack {path.name} fails validation: "
                + "; ".join(report["errors"]))
        entries.append(pack_entry(report["pack"], path.name))
    entries.sort(key=lambda e: e["id"])
    return {
        "schema_version": SCHEMA_VERSION,
        "slogan": SLOGAN,
        "repo_url": REPO_URL,
        "site_url": SITE_URL,
        "recommended_pack_id": RECOMMENDED_PACK_ID,
        "packs": entries,
    }


def build_default(catalog=None):
    """The machine-readable recommended default (exactly one pack)."""
    catalog = catalog if catalog is not None else build_catalog()
    rec = next(p for p in catalog["packs"]
               if p["id"] == RECOMMENDED_PACK_ID)
    return {
        "schema_version": SCHEMA_VERSION,
        "slogan": SLOGAN,
        "recommended_pack_id": RECOMMENDED_PACK_ID,
        "pack_file": rec["pack_file"],
        "name": rec["name"],
        "description": rec["description"],
        "source_count": rec["source_count"],
        "posts_per_month": rec["posts_per_month"],
        "preview_command": rec["preview_command"],
        "install_command": rec["install_command"],
        "uninstall_command": rec["uninstall_command"],
        "rationale": (
            "People I Follow is the recommended starter because it is "
            "people, not platforms: six verified sources the curator "
            "demonstrably follows, on their own sites and channels. "
            "It is a recommendation only when the user asked their "
            "agent to choose; it is never installed silently."),
        "swap": [
            "Preview the replacement first: " + rec["preview_command"].replace(
                rec["pack_file"], "<replacement pack_file>"),
            f"Remove the default: {rec['uninstall_command']}",
            "Install the replacement with its own install_command "
            "from marketplace/catalog.json.",
            "Exactly one starter pack at a time; installing a pack "
            "enables nothing else.",
        ],
    }


def _fmt_ppm(value):
    return f"{value:g}"


def render_marketplace_html(catalog=None):
    """Render the static marketplace page (self-contained, no scripts)."""
    catalog = catalog if catalog is not None else build_catalog()
    packs = sorted(
        catalog["packs"],
        key=lambda e: (not e["recommended"], e["id"]))
    cards = []
    for p in packs:
        badge = ('<span class="badge">Recommended starter</span>'
                 if p["recommended"] else "")
        tags = "".join(
            f'<span class="tag">{html.escape(t)}</span>' for t in p["tags"])
        cards.append(f"""    <article class="card">
      <h2>{html.escape(p['title'])} {badge}</h2>
      <p class="meta">{p['source_count']} sources &middot; &asymp;{_fmt_ppm(p['posts_per_month'])} posts/month &middot; verified {html.escape(p['verified_at'])} &middot; v{html.escape(p['version'])}</p>
      <p>{html.escape(p['description'])}</p>
      <p class="tags">{tags}</p>
      <p class="label">Preview, then install</p>
      <pre><code>{html.escape(p['preview_command'])}
{html.escape(p['install_command'])}</code></pre>
      <p class="label">Remove</p>
      <pre><code>{html.escape(p['uninstall_command'])}</code></pre>
    </article>""")
    cards_html = "\n".join(cards)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Focu — Source Library</title>
<style>
:root {{
  --paper: #fbf6ef; --card: #fffdf9; --ink: #2b211c; --muted: #6b5d54;
  --terra: #b85c38; --terra-soft: #f3ddd0; --border: #e8dccf;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--paper); color: var(--ink);
  font-family: Georgia, 'Times New Roman', serif; line-height: 1.55; }}
main {{ max-width: 760px; margin: 0 auto; padding: 32px 20px 64px; }}
h1 {{ font-size: 1.9rem; line-height: 1.2; margin: 0 0 8px; }}
.slogan {{ color: var(--terra); font-style: italic; margin: 0 0 16px; }}
.lede {{ color: var(--muted); }}
.card {{ background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px; margin: 20px 0; }}
.card h2 {{ font-size: 1.25rem; margin: 0 0 6px; }}
.badge {{ background: var(--terra-soft); color: var(--terra);
  border-radius: 999px; padding: 2px 10px; font-size: 0.75rem;
  vertical-align: middle; white-space: nowrap; }}
.meta {{ color: var(--muted); font-size: 0.9rem; margin: 0 0 10px; }}
.tags {{ margin: 8px 0; }}
.tag {{ background: var(--terra-soft); border-radius: 999px;
  padding: 1px 8px; margin-right: 6px; font-size: 0.8rem; }}
.label {{ color: var(--muted); font-size: 0.85rem; margin: 14px 0 4px; }}
pre {{ background: var(--paper); border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 12px; overflow-x: auto; margin: 0; }}
code {{ font-family: ui-monospace, Menlo, monospace; font-size: 0.82rem; }}
a {{ color: var(--terra); }}
footer {{ color: var(--muted); font-size: 0.9rem; margin-top: 32px; }}
</style>
</head>
<body>
<main>
  <h1>Focu — Source Library</h1>
  <p class="slogan">{html.escape(SLOGAN)}</p>
  <p class="lede">Curated source packs for Focu. You choose the people
  and publications; Focu digests what they publish into one short daily
  briefing. Every pack states its attention cost up front, in
  posts/month, and installs only after a preview. No ranking, no
  engagement metrics, nothing installed silently.</p>
  <p class="lede">The machine-readable catalog is
  <a href="catalog.json">catalog.json</a>; the recommended default is
  <a href="default.json">default.json</a>.</p>
{cards_html}
  <footer>
    <p><a href="{REPO_URL}">Focu on GitHub</a> &middot;
    <a href="https://aipraxislab.com/">AI Praxis Lab</a></p>
    <p>Attention returned, never attention captured.</p>
  </footer>
</main>
</body>
</html>
"""


def write_marketplace(out_dir, packs_dir=None):
    """Write catalog.json, default.json and index.html into out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    catalog = build_catalog(packs_dir)
    default = build_default(catalog)
    (out_dir / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    (out_dir / "default.json").write_text(
        json.dumps(default, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    (out_dir / "index.html").write_text(
        render_marketplace_html(catalog), encoding="utf-8")
    return catalog
