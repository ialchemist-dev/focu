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

def build(deliveries, output, template, limit):
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if not deliveries.is_dir() or not template.is_file():
        raise ValueError("delivery root or HTML template missing")
    deliveries = deliveries.resolve()
    output = output.resolve()
    if output == deliveries or deliveries in output.parents:
        raise ValueError("output must be outside the source deliveries")
    episodes = []
    for audio in deliveries.glob("*/podcast.mp3"):
        if not audio.is_file() or audio.is_symlink() or audio.stat().st_size == 0:
            continue
        folder = audio.parent
        title = folder.name.replace("-", " ")
        report = folder / "research.md"
        if report.is_file():
            for line in report.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("# "):
                    title = line[2:].strip() or title
                    break
        episodes.append((folder.name, title, audio, episode_date(folder.name)))
    episodes.sort(key=lambda ep: (bool(ep[3]), ep[3], ep[0]), reverse=True)
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
        for episode_id, title, audio, published_date in episodes:
            safe_id = hashlib.sha256(episode_id.encode()).hexdigest()[:16]
            target = assets / "audio" / (safe_id + ".mp3")
            shutil.copyfile(audio, target)
            original_hash = sha256(audio)
            if sha256(target) != original_hash:
                raise RuntimeError("audio checksum mismatch: " + episode_id)
            item = {"id": episode_id, "title": title, "date": published_date, "source": "Focu", "audio_url": "assets/audio/" + target.name}
            checksums[item["audio_url"]] = original_hash
            for ext in ("jpg", "jpeg", "png", "webp"):
                cover = audio.parent / ("cover." + ext)
                if cover.is_file() and not cover.is_symlink() and cover.stat().st_size:
                    cover_target = assets / "covers" / (safe_id + "." + ext)
                    shutil.copyfile(cover, cover_target)
                    item["cover_url"] = "assets/covers/" + cover_target.name
                    checksums[item["cover_url"]] = sha256(cover_target)
                    break
            manifest.append(item)
        payload = {"episodes": manifest}
        (assets / "episodes.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        html = template.read_text(encoding="utf-8")
        marker = '<script id="embedded-episodes" type="application/json">'
        if marker not in html:
            raise ValueError("template missing embedded manifest marker")
        start = html.index(marker) + len(marker)
        end = html.index("</script>", start)
        embedded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
        (stage / "index.html").write_text(html[:start] + embedded + html[end:], encoding="utf-8")
        (stage / "build-report.json").write_text(json.dumps({"episode_count": len(manifest), "sha256": checksums, "mode": "immutable-muse-snapshot"}, indent=2) + "\n", encoding="utf-8")
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
