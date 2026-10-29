"""Opt-in source collector PoC. No credentials are stored in Focu."""
from __future__ import annotations
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from focu.observations import ObservationStore

@dataclass(frozen=True)
class SourceRecord:
    platform: str
    source_url: str
    author: str | None
    published_at: str | None
    text: str
    collected_at: str
    method: str
    segments: list[dict] | None = None

def youtube_video_id(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Expected a YouTube video URL")
    host = parsed.hostname.lower()
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/shorts/", "/live/")):
            video_id = parsed.path.split("/")[2]
        else:
            raise ValueError("Unsupported YouTube URL path")
    elif host in ("youtu.be", "www.youtu.be"):
        video_id = parsed.path.strip("/").split("/")[0]
    else:
        raise ValueError("Not a YouTube URL")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("Invalid YouTube video ID")
    return video_id

def youtube_transcript(url: str, languages: tuple[str, ...] = ("en",)) -> SourceRecord:
    video_id = youtube_video_id(url)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError("Install the optional youtube-transcript-api dependency") from exc
    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id, languages=list(languages))
    segments = [{"text": s.text, "start": s.start, "duration": s.duration} for s in transcript]
    if not segments:
        raise RuntimeError("No transcript segments returned")
    return SourceRecord(
        platform="youtube", source_url=f"https://www.youtube.com/watch?v={video_id}",
        author=None, published_at=None, text=" ".join(s["text"] for s in segments),
        collected_at=datetime.now(timezone.utc).isoformat(),
        method="youtube-transcript-api", segments=segments)

def linkedin_feed_from_export(payload: object) -> list[SourceRecord]:
    """Normalize an authorized MCP feed export; never launch or automate a login."""
    if isinstance(payload, dict):
        items = payload.get("posts")
        if items is None:
            items = payload.get("items")
    else:
        items = payload
    if not isinstance(items, list):
        raise ValueError("Expected a list of LinkedIn posts (or posts/items array)")
    records = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each post must be an object")
        url = item.get("post_url") or item.get("url") or item.get("postUrl")
        text = item.get("text") or item.get("content")
        if not isinstance(url, str) or not isinstance(text, str) or not text.strip():
            raise ValueError("Post must include a permanent URL and nonempty text")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in ("linkedin.com", "www.linkedin.com"):
            raise ValueError("Post URL must be on linkedin.com")
        if not (parsed.path.startswith("/feed/update/") or parsed.path.startswith("/posts/")):
            raise ValueError("Post URL must identify a LinkedIn post")
        author = item.get("author")
        if isinstance(author, dict):
            author = author.get("name")
        records.append(SourceRecord(
            platform="linkedin", source_url=url, author=author if isinstance(author, str) else None,
            published_at=item.get("published_at") or item.get("publishedAt"),
            text=text.strip(), collected_at=datetime.now(timezone.utc).isoformat(),
            method="authorized-mcp-export"))
    return records

def collect_export(input_path: str | Path, platform: str, db_path: str | Path,
                   scope_id: str, output_path: str | Path) -> dict:
    if platform != "linkedin":
        raise ValueError("Only LinkedIn MCP exports are supported")
    records = linkedin_feed_from_export(json.loads(Path(input_path).read_text(encoding="utf-8")))
    store = ObservationStore(db_path)
    result = []
    for record in records:
        observation = store.observe(scope_id, record.source_url, record.text)
        result.append({**asdict(record), "observation": observation})
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"platform": platform, "total": len(result),
            "new_or_changed": sum(r["observation"]["status"] != "unchanged" for r in result),
            "output": str(output)}

def collect_youtube(url: str, db_path: str | Path, scope_id: str, output_path: str | Path,
                    languages: tuple[str, ...] = ("en",)) -> dict:
    record = youtube_transcript(url, languages)
    observation = ObservationStore(db_path).observe(scope_id, record.source_url, record.text)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({**asdict(record), "observation": observation},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    return {"platform": "youtube", "status": observation["status"], "output": str(output),
            "segments": len(record.segments or [])}
