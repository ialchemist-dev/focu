#!/usr/bin/env python3
"""Stage immutable Muse podcast artifacts from existing Focu deliveries."""
import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from editorial import editorial
from cover_art import typographic_svg, candidate_source_image, fetch_source_cover, generate_ai_cover

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def episode_date(folder_name):
    match = re.search(r"(?:^|[-_])([0-9]{8})$", folder_name)
    if not match:
        return ""
    raw = match.group(1)
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8])).isoformat()
    except ValueError:
        return ""

def build(deliveries, output, template, limit, *, fetch_source_covers=False, generate_ai_covers=False):
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if not deliveries.is_dir() or not template.is_file():
        raise ValueError("delivery root or HTML template missing")
    deliveries = deliveries.resolve()
    output = output.resolve()
    if output == deliveries or deliveries in output.parents:
        raise ValueError("output must be outside the source deliveries")
    if generate_ai_covers and not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is required with --generate-ai-covers")
    episodes = []
    for folder in deliveries.iterdir():
        if not folder.is_dir() or folder.is_symlink():
            continue
        audio_path = folder / "podcast.mp3"
        audio = audio_path if audio_path.is_file() and not audio_path.is_symlink() and audio_path.stat().st_size else None
        article_paths = [folder / name for name in ("article.md", "research.md", "article.html")]
        has_article = any(p.is_file() and not p.is_symlink() and p.stat().st_size for p in article_paths)
        if not audio and not has_article:
            continue
        title = folder.name.replace("-", " ")
        report = folder / "research.md"
        if report.is_file():
            for line in report.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("# "):
                    title = line[2:].strip() or title
                    break
        episodes.append((folder.name, title, audio, folder, episode_date(folder.name)))
    episodes.sort(key=lambda ep: (bool(ep[4]), ep[4], ep[0]), reverse=True)
    episodes = episodes[:limit]
    if not episodes:
        raise ValueError("no nonempty podcast or article deliveries found")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".focu-publish-", dir=output.parent))
    try:
        assets = stage / "assets"
        (assets / "audio").mkdir(parents=True)
        (assets / "covers").mkdir()
        (assets / "articles").mkdir()
        manifest = []
        checksums = {}
        warnings = []
        for episode_id, title, audio, folder, published_date in episodes:
            safe_id = hashlib.sha256(episode_id.encode()).hexdigest()[:16]
            item = {"id": episode_id, "title": title, "date": published_date, "source": "Focu"}
            if audio:
                target = assets / "audio" / (safe_id + ".mp3")
                shutil.copyfile(audio, target)
                original_hash = sha256(audio)
                if sha256(target) != original_hash:
                    raise RuntimeError("audio checksum mismatch: " + episode_id)
                item["audio_url"] = "assets/audio/" + target.name
                checksums[item["audio_url"]] = original_hash
            for ext in ("jpg", "jpeg", "png", "webp"):
                cover = folder / ("cover." + ext)
                if cover.is_file() and not cover.is_symlink() and cover.stat().st_size:
                    cover_target = assets / "covers" / (safe_id + "." + ext)
                    shutil.copyfile(cover, cover_target)
                    item["cover_url"] = "assets/covers/" + cover_target.name
                    checksums[item["cover_url"]] = sha256(cover_target)
                    break
            meta_path = folder / "content.json"
            metadata = {}
            if meta_path.is_file():
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                if not isinstance(metadata, dict):
                    raise ValueError("content.json must be an object")
            # Markdown is the canonical reading format; never evaluate untrusted HTML
            # inside the reader WebView. Existing article.html remains a legacy asset.
            markdown_path = folder / "article.md"
            if not markdown_path.is_file() or markdown_path.is_symlink():
                markdown_path = folder / "research.md"
            markdown = ""
            if markdown_path.is_file() and not markdown_path.is_symlink():
                if markdown_path.stat().st_size > 1_000_000:
                    raise ValueError("Article source exceeds 1 MB: " + episode_id)
                markdown = markdown_path.read_text(encoding="utf-8", errors="replace")
            info = editorial(markdown, metadata)
            if markdown:
                item["title"] = info["title"]
                item["summary"] = info["summary"]
                item["article_blocks"] = info["article_blocks"]
                item["reading_minutes"] = info["reading_minutes"]
            else:
                if isinstance(metadata.get("title"), str) and metadata["title"].strip():
                    item["title"] = metadata["title"].strip()
                if isinstance(metadata.get("summary"), str):
                    item["summary"] = metadata["summary"].strip()
            formats = {"audio": {"path": item["audio_url"], "mime_type": "audio/mpeg"}} if audio else {}
            legacy_article = folder / "article.html"
            if legacy_article.is_file() and not legacy_article.is_symlink():
                article_target = assets / "articles" / (safe_id + ".html")
                shutil.copyfile(legacy_article, article_target)
                article_path = "assets/articles/" + article_target.name
                formats["article"] = {"path": article_path, "mime_type": "text/html"}
                checksums[article_path] = sha256(article_target)
            elif markdown:
                article_target = assets / "articles" / (safe_id + ".md")
                article_target.write_text(markdown, encoding="utf-8")
                article_path = "assets/articles/" + article_target.name
                formats["article"] = {"path": article_path, "mime_type": "text/markdown"}
                checksums[article_path] = sha256(article_target)
            # A real supplied image wins. Fetch public source URLs only with opt-in.
            origin = "source" if item.get("cover_url") else None
            source_url = candidate_source_image(metadata)
            if not item.get("cover_url") and fetch_source_covers and source_url:
                try:
                    with tempfile.TemporaryDirectory(prefix=".source-cover-", dir=stage) as source_stage:
                        downloaded = fetch_source_cover(source_url, source_stage)
                        suffix = downloaded.suffix.lower()
                        dest = assets / "covers" / (safe_id + suffix)
                        shutil.copyfile(downloaded, dest)
                    item["cover_url"] = "assets/covers/" + dest.name
                    checksums[item["cover_url"]] = sha256(dest)
                    origin = "source"
                except (OSError, ValueError, RuntimeError) as exc:
                    warnings.append(episode_id + ": source image unavailable: " + str(exc))
            if not item.get("cover_url") and generate_ai_covers:
                try:
                    cache = output.parent / ".focu-generated-covers"
                    cache.mkdir(parents=True, exist_ok=True)
                    cached = cache / (safe_id + ".png")
                    if cached.is_file():
                        png = cached.read_bytes()
                    else:
                        png = generate_ai_cover(item["title"], item.get("summary", ""),
                                                api_key=os.environ["OPENAI_API_KEY"])
                        cached.write_bytes(png)
                    dest = assets / "covers" / (safe_id + ".png")
                    dest.write_bytes(png)
                    item["cover_url"] = "assets/covers/" + dest.name
                    checksums[item["cover_url"]] = sha256(dest)
                    origin = "ai_generated"
                except (OSError, ValueError, RuntimeError) as exc:
                    warnings.append(episode_id + ": AI cover generation unavailable: " + str(exc))
            if not item.get("cover_url"):
                dest = assets / "covers" / (safe_id + ".svg")
                dest.write_bytes(typographic_svg(item["title"], item.get("summary", "")))
                item["cover_url"] = "assets/covers/" + dest.name
                checksums[item["cover_url"]] = sha256(dest)
                origin = "offline_art"
            item["content_id"] = episode_id
            item["published_at"] = published_date or None
            item["formats"] = formats
            item["cover"] = {"path": item["cover_url"], "origin": origin}
            if origin == "source" and source_url:
                item["cover"]["source_url"] = source_url
            manifest.append(item)
        payload = {"schema_version": 1, "items": manifest, "episodes": [x for x in manifest if x.get("audio_url")]}
        (assets / "episodes.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        html = template.read_text(encoding="utf-8")
        marker = '<script id="embedded-episodes" type="application/json">'
        if marker not in html:
            raise ValueError("template missing embedded manifest marker")
        start = html.index(marker) + len(marker)
        end = html.index("</script>", start)
        embedded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
        (stage / "index.html").write_text(html[:start] + embedded + html[end:], encoding="utf-8")
        (stage / "build-report.json").write_text(json.dumps({"item_count": len(manifest), "episode_count": sum(1 for x in manifest if x.get("audio_url")), "sha256": checksums, "warnings": warnings, "mode": "immutable-muse-snapshot"}, indent=2) + "\n", encoding="utf-8")
        if output.exists():
            raise FileExistsError("output exists; choose a new versioned directory: " + str(output))
        os.replace(stage, output)
        return len(manifest)
    finally:
        if stage.exists():
            shutil.rmtree(stage)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--deliveries", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--template", type=Path, default=Path(__file__).with_name("index.html"))
    p.add_argument("--limit", type=int, default=15)
    p.add_argument("--fetch-source-covers", action="store_true", help="Opt in to downloading public HTTPS source images")
    p.add_argument("--generate-ai-covers", action="store_true", help="Opt in to paid OpenAI image generation, using OPENAI_API_KEY")
    a = p.parse_args()
    try:
        count = build(a.deliveries, a.output, a.template, a.limit, fetch_source_covers=a.fetch_source_covers, generate_ai_covers=a.generate_ai_covers)
        print(f"Built {count} content items at {a.output}")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Publish failed: {exc}", file=sys.stderr)
        sys.exit(1)
