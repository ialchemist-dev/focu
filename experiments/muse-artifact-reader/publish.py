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
from editorial import editorial, compose_article_with_openai, markdown_from_html
from cover_art import typographic_svg, candidate_source_image, fetch_source_cover, generate_ai_cover
from focu.media_integrity import inspect_mp3, MediaIntegrityError
from focu.audience import load_profile, calibration, mismatch_report, detect_domain

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

def build(deliveries, output, template, limit, *, fetch_source_covers=False, generate_ai_covers=False, generate_editorial=False, requests=None, verify_audio=False):
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if not deliveries.is_dir() or not template.is_file():
        raise ValueError("delivery root or HTML template missing")
    deliveries = deliveries.resolve()
    output = output.resolve()
    if output == deliveries or deliveries in output.parents:
        raise ValueError("output must be outside the source deliveries")
    if (generate_ai_covers or generate_editorial) and not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY required for opt-in editorial or image generation")
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
        audio_audit = {}
        for episode_id, title, audio, folder, published_date in episodes:
            safe_id = hashlib.sha256(episode_id.encode()).hexdigest()[:16]
            item = {"id": episode_id, "title": title, "date": published_date, "source": "Focu"}
            if audio:
                if verify_audio:
                    try:
                        audit = inspect_mp3(audio)
                    except MediaIntegrityError as exc:
                        raise ValueError(f"Audio validation failed for {episode_id}: {exc}") from exc
                    audio_audit[episode_id] = audit
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
            content_origin = metadata.get("origin") or "registered_source"
            if content_origin not in ("registered_source", "user_initiated", "daily_compilation"):
                raise ValueError("Unknown content origin: " + str(content_origin))
            mode = metadata.get("podcast_mode")
            if mode is None:
                mode = "none" if content_origin == "user_initiated" else "daily_compilation"
            if mode not in ("none", "single", "daily_compilation"):
                raise ValueError("Invalid podcast_mode: " + str(mode))
            if content_origin == "user_initiated" and mode == "daily_compilation":
                raise ValueError("User research must not enter daily compilation")
            if content_origin != "user_initiated" and mode == "single":
                raise ValueError("Standalone audio only belongs to user-initiated research")
            if mode == "none" and audio:
                raise ValueError("podcast_mode=none item has a stray MP3: " + episode_id)
            if (content_origin == "registered_source" and audio
                    and metadata.get("podcast_mode") == "daily_compilation"
                    and not metadata.get("covered_content_ids")):
                raise ValueError("Registered-source article cannot receive its own daily podcast")
            if content_origin == "user_initiated":
                item["source"] = "Your research"
            item["origin"] = content_origin
            item["podcast_mode"] = mode
            if metadata.get("podcast_requested_at"):
                item["podcast_requested_at"] = metadata["podcast_requested_at"]
            covered = metadata.get("covered_content_ids", [])
            if not isinstance(covered, list) or not all(isinstance(x, str) and x for x in covered):
                raise ValueError("covered_content_ids must be a list of content IDs")
            if covered and (content_origin != "daily_compilation"
                            or mode != "daily_compilation"):
                raise ValueError("Only a compiled daily briefing may cover individual items")
            # The text report must remain publishable when audio/script QC
            # blocks a bad MP3. No audio format or Listen is invented.
            if covered:
                item["covered_content_ids"] = covered
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
            # Legacy HTML-only content can also be read in the native article
            # reader, without opening an untrusted HTML file in a new tab.
            legacy_html = folder / "article.html"
            if not markdown and legacy_html.is_file() and not legacy_html.is_symlink():
                if legacy_html.stat().st_size > 1_000_000:
                    raise ValueError("Legacy HTML article exceeds 1 MB: " + episode_id)
                markdown = markdown_from_html(legacy_html.read_text(encoding="utf-8", errors="replace"))
            # Curated article.md wins. Otherwise an explicit opt-in may turn
            # research into original article prose, with a keyed local cache.
            if (generate_editorial and markdown and markdown_path.name == "research.md"):
                model = "gpt-4.1-mini"
                profile = load_profile()
                audience = calibration(metadata.get("audience_domain") or detect_domain(markdown), profile)
                digest = hashlib.sha256((model + "\n" + profile["profile_sha256"] +
                                        "\n" + audience["domain"] + "\n" + markdown).encode()).hexdigest()[:20]
                cache = output.parent / ".focu-editorial-cache"
                cache.mkdir(parents=True, exist_ok=True)
                cached = cache / (safe_id + "-" + digest + ".json")
                try:
                    if cached.is_file():
                        generated = json.loads(cached.read_text(encoding="utf-8"))
                    else:
                        generated = compose_article_with_openai(
                            markdown, api_key=os.environ["OPENAI_API_KEY"], model=model,
                            audience_domain=metadata.get("audience_domain") or detect_domain(markdown))
                        pending = cache / ("." + cached.name + ".tmp")
                        pending.write_text(json.dumps(generated, ensure_ascii=False), encoding="utf-8")
                        os.replace(pending, cached)
                    if not isinstance(generated.get("article_markdown"), str):
                        raise ValueError("Invalid editorial cache")
                    markdown = generated["article_markdown"]
                    metadata = {**generated, **metadata}
                except (OSError, ValueError, RuntimeError, KeyError) as exc:
                    warnings.append(episode_id + ": editorial generation unavailable: " + type(exc).__name__)
            info = editorial(markdown, metadata)
            profile = calibration(metadata.get("audience_domain") or detect_domain(markdown))
            item["audience_profile_version"] = profile["profile_version"]
            item["audience_profile_sha256"] = profile["profile_sha256"]
            item["audience_domain"] = profile["domain"]
            item["audience_level"] = profile["level"]
            if markdown:
                item["audience_qc"] = mismatch_report(markdown, metadata.get("audience_domain") or detect_domain(markdown))
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
            if audio and episode_id in audio_audit:
                formats["audio"]["duration_seconds"] = audio_audit[episode_id]["decoded_duration_seconds"]
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
            stable_id = metadata.get("content_id", episode_id)
            if not isinstance(stable_id, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.:-]{0,119}", stable_id):
                raise ValueError("Invalid content_id for " + episode_id)
            item["content_id"] = stable_id
            meta_date = metadata.get("published_at")
            if isinstance(meta_date, str):
                try:
                    date.fromisoformat(meta_date)
                except ValueError:
                    meta_date = None
            else:
                meta_date = None
            item["published_at"] = meta_date or published_date or None
            item["formats"] = formats
            item["cover"] = {"path": item["cover_url"], "origin": origin}
            if origin == "source" and source_url:
                item["cover"]["source_url"] = source_url
            manifest.append(item)
        # Daily compilations link readable registered-source and user-requested
        # articles. Coverage never authorizes per-item MP3 generation.
        compilations = {}
        for item in manifest:
            if item["origin"] != "daily_compilation":
                continue
            if not item.get("covered_content_ids"):
                raise ValueError("Daily compilation must list covered_content_ids")
            if "article" not in item["formats"] and "audio" not in item["formats"]:
                raise ValueError("Daily compilation requires a real article or QC-approved audio")
            day = item.get("published_at") or item.get("date")
            if not day:
                raise ValueError("Daily compilation is missing its publication date")
            if day in compilations:
                raise ValueError("Multiple daily compilations for " + day)
            compilations[day] = item["content_id"]
        seen_ids = set()
        for item in manifest:
            if item["content_id"] in seen_ids:
                raise ValueError("Duplicate canonical content ID: " + item["content_id"])
            seen_ids.add(item["content_id"])
        for item in manifest:
            refs = item.get("covered_content_ids", [])
            if len(refs) != len(set(refs)):
                raise ValueError("Duplicate daily coverage IDs")
            for ref in refs:
                other = next((x for x in manifest if x["content_id"] == ref), None)
                if not other:
                    raise ValueError("Daily compilation references missing content: " + ref)
                allowed_source = (other["origin"] == "registered_source" and
                                  other["podcast_mode"] == "daily_compilation")
                allowed_research = (other["origin"] == "user_initiated" and
                                    other["podcast_mode"] in ("none", "single"))
                if not (allowed_source or allowed_research):
                    raise ValueError("Daily briefing coverage must reference a readable source or on-demand article")
                if "article" not in other["formats"]:
                    raise ValueError("Every covered item must have an individual readable article")
        pending = []
        if requests is not None:
            request_path = Path(requests)
            if not request_path.is_file() or request_path.is_symlink():
                raise ValueError("Research requests export is missing or unsafe")
            data = json.loads(request_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("requests"), list):
                raise ValueError("Expected research request export")
            published_ids = {item["content_id"] for item in manifest}
            seen = set()
            for task in data["requests"][:500]:
                if not isinstance(task, dict):
                    continue
                identifier = task.get("intent_id")
                status = task.get("status")
                if (not isinstance(identifier, str) or not re.fullmatch(r"int_[a-f0-9]{32}", identifier)
                        or status not in {"queued", "researching", "completed", "failed"}
                        or identifier in seen or identifier in published_ids):
                    continue
                seen.add(identifier)
                pending.append({"intent_id": identifier, "status": status,
                                "title": str(task.get("title") or "Untitled research")[:160],
                                "created_at": str(task.get("created_at") or "")[:40],
                                "error": str(task.get("error") or "")[:180] if status == "failed" else None})
                if len(pending) == 100:
                    break
        payload = {"schema_version": 1, "items": manifest,
                   "episodes": [x for x in manifest if x.get("audio_url")],
                   "research_requests": pending}
        (assets / "episodes.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        html = template.read_text(encoding="utf-8")
        marker = '<script id="embedded-episodes" type="application/json">'
        if marker not in html:
            raise ValueError("template missing embedded manifest marker")
        start = html.index(marker) + len(marker)
        end = html.index("</script>", start)
        embedded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
        (stage / "index.html").write_text(html[:start] + embedded + html[end:], encoding="utf-8")
        (stage / "build-report.json").write_text(json.dumps({"item_count": len(manifest), "episode_count": sum(1 for x in manifest if x.get("audio_url")), "sha256": checksums, "audio_audit": audio_audit, "warnings": warnings, "mode": "immutable-muse-snapshot"}, indent=2) + "\n", encoding="utf-8")
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
    p.add_argument("--skip-audio-audit", action="store_true", help="Unsafe: bypass actual MP3 decode/duration check for test fixtures only")
    p.add_argument("--requests", type=Path, help="Optional private focu request-export JSON snapshot")
    p.add_argument("--fetch-source-covers", action="store_true", help="Opt in to downloading public HTTPS source images")
    p.add_argument("--generate-ai-covers", action="store_true", help="Opt in to paid OpenAI image generation, using OPENAI_API_KEY")
    p.add_argument("--generate-editorial", action="store_true", help="Opt in to paid AI blog article writing, using OPENAI_API_KEY")
    a = p.parse_args()
    try:
        count = build(a.deliveries, a.output, a.template, a.limit, fetch_source_covers=a.fetch_source_covers, generate_ai_covers=a.generate_ai_covers, generate_editorial=a.generate_editorial, requests=a.requests, verify_audio=not a.skip_audio_audit)
        print(f"Built {count} content items at {a.output}")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Publish failed: {exc}", file=sys.stderr)
        sys.exit(1)
