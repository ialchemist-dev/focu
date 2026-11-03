#!/usr/bin/env python3
"""Build a deterministic, private Muse Artifact staging bundle from Focu deliveries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def build(deliveries, output, template, limit):
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    if not deliveries.is_dir() or not template.is_file():
        raise ValueError("delivery root or HTML template missing")
    output = output.resolve()
    deliveries = deliveries.resolve()
    if output == deliveries or deliveries in output.parents:
        raise ValueError("output must be outside the source deliveries")
    episodes = []
    for audio in deliveries.glob("*/podcast.mp3"):
        if not audio.is_file() or audio.is_symlink() or audio.stat().st_size == 0:
            continue
        folder = audio.parent
        report = folder / "research.md"
        title = folder.name.replace("-", " ")
        if report.is_file():
            for line in report.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("# "):
                    title = line[2:].strip() or title
                    break
        episodes.append((folder.name, title, audio))
    episodes.sort(key=lambda item: item[0], reverse=True)
    episodes = episodes[:limit]
    if not episodes:
        raise ValueError("no nonempty podcast.mp3 files found")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".focu-publish-", dir=output.parent))
    try:
        assets = stage / "assets"
        (assets / "audio").mkdir(parents=True)
        (assets / "covers").mkdir()
        manifest = []
        checksums = {}
        for episode_id, title, audio in episodes:
            safe_id = hashlib.sha256(episode_id.encode()).hexdigest()[:16]
            name = safe_id + ".mp3"
            target = assets / "audio" / name
            shutil.copyfile(audio, target)
            original_hash = sha256(audio)
            if sha256(target) != original_hash:
                raise RuntimeError("audio checksum mismatch: " + episode_id)
            item = {"id": episode_id, "title": title, "date": episode_id[:10] if len(episode_id) >= 10 else "", "source": "Focu", "audio_url": "assets/audio/" + name}
            for ext in ("jpg", "jpeg", "png", "webp"):
                cover = audio.parent / ("cover." + ext)
                if cover.is_file() and not cover.is_symlink() and cover.stat().st_size:
                    cover_name = safe_id + "." + ext
                    shutil.copyfile(cover, assets / "covers" / cover_name)
                    item["cover_url"] = "assets/covers/" + cover_name
                    checksums[item["cover_url"]] = sha256(assets / "covers" / cover_name)
                    break
            manifest.append(item)
            checksums[item["audio_url"]] = original_hash
        payload = {"episodes": manifest}
        (assets / "episodes.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        html = template.read_text(encoding="utf-8")
        marker = '<script id="embedded-episodes" type="application/json">'
        if marker not in html:
            raise ValueError("template missing embedded manifest marker")
        start = html.index(marker) + len(marker)
        end = html.index("</script>", start)
        embedded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
        html = html[:start] + embedded + html[end:]
        (stage / "index.html").write_text(html, encoding="utf-8")
        (stage / "build-report.json").write_text(json.dumps({"episode_count": len(manifest), "sha256": checksums, "mode": "immutable-muse-snapshot"}, indent=2) + "\n")
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
    a = p.parse_args()
    try:
        count = build(a.deliveries, a.output, a.template, a.limit)
        print(f"Built {count} episodes at {a.output}")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Publish failed: {exc}", file=sys.stderr)
        sys.exit(1)
