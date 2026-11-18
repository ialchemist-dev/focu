"""YouTube adapter prototype: channel RSS + transcripts -> daily units.

This is the first platform adapter built against the contract in the
infra design (``docs/dev-team/infra-design.md`` B.5, Seam 1), with the
LinkedIn feed as the reference implementation. It validates the adapter
contract on the lowest-risk platform: discovery is YouTube's official
per-channel RSS feed (no API key, no scraping, no login), and bodies are
transcripts fetched through the same ladder production uses.

What it does, per channel and Denver day:

- Reads the channel's official RSS feed
  (``https://www.youtube.com/feeds/videos.xml?channel_id=...``), keeps
  the videos whose publication date in America/Denver is the target day,
  newest first.
- Applies a HARD per-channel daily cap (default 2, the production
  硅谷101 registration in sources.yaml; a channel entry may carry its
  own ``max_items``). The cap counts candidates, mirroring production:
  a video whose transcript cannot be retrieved consumes a slot and is
  reported as pending — it is never emitted title-only or empty.
- Fetches each candidate's transcript through the production ladder:
  (1) ``youtube_transcript_api``; (2) yt-dlp subtitle download with the
  android player client, VTT converted to text with auto-caption line
  dedupe (the ladder learned 2026-09-24, implemented in production by
  ``~/focu-runtime/bin/youtube_transcript.py``). The yt-dlp rung tries
  its subtitle language groups in separate invocations, so a rate
  limit on one group's tracks cannot discard another group's (P2-5
  live finding, 2026-11-18). A body under
  ``MIN_TRANSCRIPT_CHARS`` counts as missing at every rung.
- Emits ONE digest unit per channel-day (zero when nothing survives),
  in the exact shape ``linkedin_to_units.py`` emits and the daily
  pipeline ingests::

      {"source": <registered source name>,
       "title": "<name> — <Weekday, Month D, YYYY>",
       "url": "https://www.youtube.com/channel/<channel_id>?day=<date>",
       "published_at": "<day>T23:59:00<Denver offset>",
       "body": "1. <video title> (<watch URL>)\\n<transcript>\\n\\n2. ...",
       "kind": "video"}

  The ``?day=`` parameter is load-bearing, not decoration: the pipeline
  derives a unit's content identity from its canonical URL, and a bare
  channel URL would collapse every day's digest into one content_id
  (the 2026-11-15 LinkedIn incident). It survives
  ``focu.daily.identity.canonical_url`` — channel paths are not
  rewritten and ``day`` is not a tracking parameter — so each day is a
  distinct content item. ``published_at`` is the end of the collection
  day in America/Denver with a full ISO offset, because recency scoring
  silently ignores date-only or zone-less timestamps. The extra
  ``kind: "video"`` key mirrors production's per-video YouTube units.

Failure handling follows the briefing-integration rule: a channel whose
feed cannot be fetched or parsed is recorded in the report's
``failures`` and skipped; the adapter never raises for one channel, so
an adapter failure can never block the briefing. Collection is serial
(one feed, then one transcript at a time) — human pace by construction,
and YouTube needs no session, so the runbook's login stop conditions do
not arise; there are no credentials in Focu (the collectors contract).

Production wiring (NOT done by this prototype — dev-main only):

1. Register each channel in ``sources.yaml`` as ``type: youtube`` with
   its ``channel_id`` and ``max_items_per_day`` (the config validator
   already knows the type; ingest matches units to the source by name,
   so the registry ``name`` here must equal the sources.yaml ``name``).
2. In the morning briefing job, after the host collector writes
   ``units-<D>.json`` and before ingest, run
   ``focu youtube-adapter emit --day <D-1> --channels <registry.json>
   --out youtube-units-<D-1>.json`` and append the emitted units,
   exactly as ``linkedin_to_units.py`` output is appended today.
3. Transcript fetching in production runs under the durable toolchain
   venv (POT provider + android-client fallback for datacenter IPs);
   the yt-dlp rung here resolves ``~/workspace/.venv/bin/yt-dlp``
   before falling back to ``PATH``, matching that layout.

Usage:
  python -m focu.adapters.youtube emit --day YYYY-MM-DD \
      --channels registry.json --out units-youtube.json
  # --channels also accepts comma-separated channel IDs (the source
  # name then comes from each feed's own channel title).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date as Date, datetime, time
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

DENVER = ZoneInfo("America/Denver")
FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
CHANNEL_URL = "https://www.youtube.com/channel/{channel_id}"
WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
# The production 硅谷101 registration (sources.yaml max_items_per_day).
DEFAULT_MAX_PER_CHANNEL = 2
# Production's threshold: a shorter body counts as "no transcript".
MIN_TRANSCRIPT_CHARS = 200
LANGS = ["en", "zh-Hans", "zh-Hant"]
USER_AGENT = "Focu/0.4 (youtube-adapter)"
NS = {"a": "http://www.w3.org/2005/Atom",
      "yt": "http://www.youtube.com/xml/schemas/2015"}


@dataclass
class AdapterConfig:
    """Adapter-wide knobs; per-channel ``max_items`` overrides the cap."""

    max_per_channel: int = DEFAULT_MAX_PER_CHANNEL
    min_transcript_chars: int = MIN_TRANSCRIPT_CHARS
    timezone: ZoneInfo = DENVER


@dataclass
class VideoEntry:
    video_id: str
    title: str
    published: datetime
    author: str = ""
    link: str = ""


# ---------------------------------------------------------------------------
# Discovery: channel RSS (official feed, no key, no scraping).

def fetch_feed_bytes(channel_id: str) -> bytes:
    request = Request(FEED_URL.format(channel_id=channel_id),
                      headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read()


def parse_feed(payload: bytes) -> tuple[str, list[VideoEntry]]:
    """Parse a channel RSS (Atom) payload into (channel title, entries).

    Entries keep feed order (newest first). Entries without a video id
    or a parseable publication timestamp are skipped, never guessed.
    """
    root = ET.fromstring(payload)
    channel_title = (root.findtext("a:title", namespaces=NS) or "").strip()
    entries: list[VideoEntry] = []
    for entry in root.findall("a:entry", NS):
        video_id = (entry.findtext("yt:videoId", namespaces=NS) or "").strip()
        raw_published = (entry.findtext("a:published", namespaces=NS) or "").strip()
        if not video_id or not raw_published:
            continue
        try:
            published = datetime.fromisoformat(raw_published.replace("Z", "+00:00"))
        except ValueError:
            continue
        if published.tzinfo is None:
            continue
        author = (entry.findtext("a:author/a:name", namespaces=NS) or "").strip()
        entries.append(VideoEntry(
            video_id=video_id,
            title=(entry.findtext("a:title", namespaces=NS) or "").strip(),
            published=published,
            author=author,
            link=WATCH_URL.format(video_id=video_id)))
    return channel_title, entries


# ---------------------------------------------------------------------------
# Transcripts: the production ladder (API first, yt-dlp android fallback).

def transcript_via_api(video_id: str) -> str:
    from youtube_transcript_api import YouTubeTranscriptApi
    fetched = YouTubeTranscriptApi().fetch(video_id, languages=LANGS)
    return " ".join(s.text for s in fetched).strip()


def vtt_to_text(vtt: str) -> str:
    """Convert WebVTT subtitle text to plain text (production algorithm:
    drop headers/timestamps/tags, dedupe consecutive auto-caption lines)."""
    lines: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")) or "-->" in line:
            continue
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line and (not lines or lines[-1] != line):
            lines.append(line)
    return " ".join(lines).strip()


def _ytdlp_binary() -> str | None:
    durable = Path.home() / "workspace" / ".venv" / "bin" / "yt-dlp"
    if durable.exists():
        return str(durable)
    return shutil.which("yt-dlp")


# Subtitle language groups for the yt-dlp rung, in preference order.
# They are attempted in SEPARATE yt-dlp invocations (P2-5 live finding,
# 2026-11-18): yt-dlp downloads one invocation's tracks in order and a
# rate-limit (HTTP 429) on an early track — typically an auto-translated
# track the adapter does not need — aborts the invocation before the
# usable tracks are written, discarding the whole rung. One group
# failing must never poison the next.
SUB_LANG_GROUPS = ("zh-Hans,zh-Hant,zh.*", "en.*")


def transcript_via_ytdlp(video_id: str) -> str:
    binary = _ytdlp_binary()
    if not binary:
        return ""
    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / "sub.%(ext)s")
        for group in SUB_LANG_GROUPS:
            subprocess.run(
                [binary, "--skip-download", "--write-subs", "--write-auto-subs",
                 "--sub-langs", group, "--sub-format", "vtt",
                 "--extractor-args", "youtube:player_client=android",
                 "-o", out, WATCH_URL.format(video_id=video_id)],
                capture_output=True, timeout=120)
            for vtt_path in sorted(Path(tmp).glob("sub.*.vtt")):
                text = vtt_to_text(vtt_path.read_text(
                    encoding="utf-8", errors="replace"))
                if len(text) >= MIN_TRANSCRIPT_CHARS:
                    return text
    return ""


def fetch_transcript(video_id: str, *, via_api=None, via_ytdlp=None,
                     min_chars: int = MIN_TRANSCRIPT_CHARS) -> tuple[str, str]:
    """Run the ladder for one video. Returns (body, via) or ("", "").

    A rung only counts when its body reaches ``min_chars`` — the same
    rule production applies, so a stub or blocked response falls through
    to the next rung instead of passing as a transcript.
    """
    api = transcript_via_api if via_api is None else via_api
    ytdlp = transcript_via_ytdlp if via_ytdlp is None else via_ytdlp
    body = ""
    try:
        body = api(video_id)
    except Exception:
        body = ""
    if len(body) >= min_chars:
        return body, "api"
    try:
        alt = ytdlp(video_id)
    except Exception:
        alt = ""
    if len(alt) >= min_chars:
        return alt, "yt-dlp-android"
    return "", ""


def _ladder_transcript(video_id: str, min_chars: int) -> tuple[str, str]:
    """The module-level ladder, looked up by global name at call time so
    tests (and only tests) can substitute it wholesale."""
    return fetch_transcript(video_id, min_chars=min_chars)


# ---------------------------------------------------------------------------
# Channel specs: registry dicts (production youtube_sources.json shape),
# plain dicts, or bare channel IDs.

def normalize_channel(spec) -> dict:
    if isinstance(spec, str):
        return {"channel_id": spec}
    channel = dict(spec)
    if not channel.get("channel_id"):
        raise ValueError(f"channel spec has no channel_id: {spec!r}")
    return channel


def load_channels(argument: str) -> list[dict]:
    """Resolve a --channels argument: a registry JSON file (production
    shape ``{"sources": [...]}`` or a bare list) or comma-separated IDs."""
    path = Path(argument)
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
        specs = raw.get("sources", []) if isinstance(raw, dict) else raw
        return [normalize_channel(spec) for spec in specs]
    return [normalize_channel(part.strip()) for part in argument.split(",") if part.strip()]


def channel_cap(channel: dict, config: AdapterConfig) -> int:
    for key in ("max_items", "max_items_per_day"):
        if channel.get(key) is not None:
            return int(channel[key])
    return config.max_per_channel


# ---------------------------------------------------------------------------
# The adapter proper.

def build_unit(name: str, channel_id: str, day: str, videos: list[dict]) -> dict:
    date = Date.fromisoformat(day)
    published = datetime.combine(date, time(23, 59), tzinfo=DENVER)
    sections = [
        f"{n}. {video['title']} ({video['url']})\n{video['body']}"
        for n, video in enumerate(videos, start=1)
    ]
    return {
        "source": name,
        "title": f"{name} — {date.strftime('%A, %B ')}{date.day}, {date.year}",
        "url": f"{CHANNEL_URL.format(channel_id=channel_id)}?day={day}",
        "published_at": published.isoformat(timespec="seconds"),
        "body": "\n\n".join(sections),
        "kind": "video",
    }


def collect_channel_day(channel: dict, day: str, *, config: AdapterConfig,
                        fetch_feed, fetch_transcript) -> dict:
    """Collect one channel's digest for one Denver day.

    Returns a per-channel result: the unit (or None), the videos it
    includes, the pending videos (transcript not retrievable), and the
    candidate count. Raises only for feed fetch/parse failures — the
    caller records those as channel failures.
    """
    channel_id = channel["channel_id"]
    payload = fetch_feed(channel_id)
    feed_title, entries = parse_feed(payload)
    name = channel.get("name") or feed_title or channel_id
    target = Date.fromisoformat(day)
    cap = channel_cap(channel, config)
    candidates = [e for e in entries
                  if e.published.astimezone(config.timezone).date() == target][:cap]
    included: list[dict] = []
    pending: list[dict] = []
    for entry in candidates:
        body, via = fetch_transcript(entry.video_id)
        if len(body) < config.min_transcript_chars:
            pending.append({"video_id": entry.video_id, "title": entry.title,
                            "published_at": entry.published.astimezone(
                                config.timezone).date().isoformat()})
            continue
        included.append({
            "video_id": entry.video_id, "title": entry.title, "url": entry.link,
            "published_at": entry.published.astimezone(config.timezone).isoformat(),
            "body": body, "via": via})
    unit = build_unit(name, channel_id, day, included) if included else None
    return {"channel_id": channel_id, "name": name, "candidates": len(candidates),
            "included": included, "pending": pending, "unit": unit}


def emit(day: str, channels: list[dict], out: str, *, config: AdapterConfig | None = None,
         fetch_feed=None, fetch_transcript=None) -> dict:
    """Emit one day's digest units for all channels to ``out`` (JSON list).

    Always writes the file (``[]`` when nothing survives) and returns a
    report: per-channel summaries, every pending transcript, and every
    channel failure. Never raises for a single channel's failure.
    """
    config = config or AdapterConfig()
    feed_fetcher = fetch_feed_bytes if fetch_feed is None else fetch_feed
    if fetch_transcript is None:
        def transcript_fetcher(video_id: str):
            return _ladder_transcript(video_id, config.min_transcript_chars)
    else:
        transcript_fetcher = fetch_transcript
    units: list[dict] = []
    summaries: list[dict] = []
    pending_all: list[dict] = []
    failures: list[dict] = []
    for spec in channels:
        channel = normalize_channel(spec)
        try:
            result = collect_channel_day(channel, day, config=config,
                                         fetch_feed=feed_fetcher,
                                         fetch_transcript=transcript_fetcher)
        except Exception as exc:  # adapter failure never blocks the briefing
            failures.append({"source": channel.get("name") or channel["channel_id"],
                             "channel_id": channel["channel_id"],
                             "error": type(exc).__name__})
            continue
        if result["unit"] is not None:
            units.append(result["unit"])
        pending_all.extend({**p, "source": result["name"]} for p in result["pending"])
        summaries.append({"source": result["name"], "channel_id": result["channel_id"],
                          "candidates": result["candidates"],
                          "included": len(result["included"]),
                          "pending": len(result["pending"]),
                          "transcript_via": [v["via"] for v in result["included"]]})
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(units, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return {"day": day, "units": len(units), "out": out, "channels": summaries,
            "pending_transcripts": pending_all, "failures": failures}


# ---------------------------------------------------------------------------
# CLI: `focu youtube-adapter ...` (thin argparse wrapper, like focu.packs).

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="focu youtube-adapter",
        description="YouTube channel digests for the Focu daily pipeline (prototype)")
    sub = parser.add_subparsers(dest="action", required=True)
    emit_cmd = sub.add_parser(
        "emit", help="Emit one day's per-channel digest units as a JSON list")
    emit_cmd.add_argument("--day", required=True, help="Denver day, YYYY-MM-DD")
    emit_cmd.add_argument("--channels", required=True,
                          help="Registry JSON file or comma-separated channel IDs")
    emit_cmd.add_argument("--out", required=True, help="Where to write the units JSON")
    emit_cmd.add_argument("--max-per-channel", type=int, default=None,
                          help="Default per-channel daily cap (a channel's own "
                               "max_items wins; built-in default is "
                               f"{DEFAULT_MAX_PER_CHANNEL})")
    emit_cmd.add_argument("--pending-out", default=None,
                          help="Also write the pending-transcripts list to this path")
    args = parser.parse_args(argv)

    if args.action == "emit":
        config = AdapterConfig()
        if args.max_per_channel is not None:
            config.max_per_channel = args.max_per_channel
        channels = load_channels(args.channels)
        report = emit(args.day, channels, args.out, config=config)
        if args.pending_out:
            pending_path = Path(args.pending_out)
            pending_path.parent.mkdir(parents=True, exist_ok=True)
            pending_path.write_text(
                json.dumps(report["pending_transcripts"], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
