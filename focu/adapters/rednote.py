"""RedNote / 小红书 adapter prototype: owner export file -> daily unit.

This is the third platform adapter built against the contract in the
infra design (``docs/dev-team/infra-design.md`` B.1 and B.5, Seam 1),
and it takes the boundary discipline of
``focu/adapters/instagram.py`` one step further. The right-shaped
collection tool for 小红书 is MediaCrawler in CDP mode on the owner's
own Chrome — but MediaCrawler is licensed under the Non-Commercial
Learning License 1.1 (verified from its LICENSE file), so its code can
NEVER be vendored into Focu. This module therefore contains no
crawling code, no login, no session handling, and no platform requests
at all: it reads ONE local JSON export file produced outside Focu by
the owner's own tooling, normalizes and validates it the way
``focu/collectors.py`` already consumes LinkedIn exports, and emits
the day's digest unit. If the exporter disappears tomorrow, this
adapter is untouched — only the export producer changes.

The export shape (the contract the owner's exporter must produce)::

    [
      {
        "note_id": "68f...",                       // optional, informational
        "author": "<display name>",                // required
        "author_id": "<stable user id>",           // optional; own-note matching
        "title": "<note title>",                   // optional
        "text": "<note body text>",                // optional
        "url": "https://www.xiaohongshu.com/explore/<note_id>",  // required
        "published_at": "2026-11-17T08:30:00+08:00",             // note's own time
        "collected_at": "2026-11-17T09:12:44-07:00"              // when the exporter read it
      },
      ...
    ]

Field rules, enforced by ``normalize_record``:

- ``author`` and ``url`` are required; a record missing either, or
  with no usable timestamp, is malformed — counted in the report and
  skipped, never crashed on and never guessed at. Non-object entries
  in the list are malformed the same way.
- Tolerated aliases from common exporter output: ``nickname`` for
  ``author``, ``desc`` for ``text``, ``note_url`` for ``url``, and
  ``time`` for ``published_at``.
- Timestamps are ISO 8601 strings, or epoch numbers (values >= 1e12
  are read as milliseconds). A timestamp SHOULD carry an offset; a
  naive value is read as UTC, never silently localized.
- Day membership: a note belongs to the Denver date of its
  ``collected_at`` — the day the owner's feed actually showed it,
  which is the LinkedIn semantic (items scraped on day D form day D's
  digest, whatever their original publication date). When
  ``collected_at`` is absent, the Denver date of ``published_at`` is
  used instead.

What it does, per Denver day:

- Keeps the target day's notes, newest first (by ``published_at``,
  falling back to ``collected_at``), deduplicated by URL.
- Skips the owner's own notes when an owner handle is configured
  (matched case-insensitively against ``author`` and ``author_id``) —
  the Seam-1 rule every own-feed adapter here follows.
- Applies a HARD daily cap (default 30 notes). The cap sits between
  Instagram's 20 and LinkedIn's 50, sized from the scraping research's
  measured XHS envelopes: practitioner discipline for agent reading is
  ~20 seconds per note, strictly serial, and hammering trips the
  CAPTCHA / IP block (error 300012) within a few dozen hits, degrading
  the account for hours. Thirty notes is ~10 minutes of paced
  collection for the exporter — and 小红书's risk control （风控） is
  the most aggressive of the platforms here, bound to the owner's
  real-name identity, so the digest never asks the exporter for more
  than the cap. (The pacing itself happens in the exporter, outside
  Focu; this cap bounds what Focu will ever put in a day's digest.)
- Emits ONE digest unit per day (zero when nothing survives), in the
  exact shape ``linkedin_to_units.py`` emits and the daily pipeline
  ingests::

      {"source": "RedNote Feed",
       "title": "RedNote Feed — <Weekday, Month D, YYYY>",
       "url": "https://www.xiaohongshu.com/explore?day=<date>",
       "published_at": "<day>T23:59:00<Denver offset>",
       "body": "1. <author> — <gist> (<url>)\\n2. ..."}

  The ``?day=`` parameter is load-bearing, not decoration: the pipeline
  derives a unit's content identity from its canonical URL, and a bare
  explore URL would collapse every day's digest into one content_id
  (the 2026-11-15 LinkedIn incident). ``day`` is an unknown parameter,
  so it survives ``focu.daily.identity.canonical_url`` and each day is
  a distinct content item. ``published_at`` is the end of the
  collection day in America/Denver with a full ISO offset, because
  recency scoring silently ignores date-only or zone-less timestamps.
  A gist is the note's title, or its text when untitled, truncated to
  30 words (the LinkedIn rule); a note with neither gets the factual
  label "Note (no title or text)" — never invented text.

Failure shape: a missing export file, an unparseable file, or a file
whose top level is not a list is a clean ``failures`` entry in the
report (``ExportFileNotFound`` / ``ExportParseError`` /
``ExportShapeError``), an empty unit list is still written, and
``emit`` never raises for an export problem — an adapter failure can
never block the briefing.

Production wiring (NOT done by this prototype — dev-main only):

1. The OWNER runs the exporter outside Focu, under its own license:
   MediaCrawler (CDP mode) or an equivalent exporter, attached to the
   owner's own logged-in Chrome, inside the owner's plausible active
   hours, at the ~20s/note serial discipline, stopping on the first
   risk-control interstitial. Focu only ever sees the export file the
   exporter writes; no part of the exporter is imported, bundled, or
   invoked from here. (Exporter-side caveat from the research:
   mainland xiaohongshu.com and global rednote.com do not share
   sessions — the exporter must read the domain the owner's account
   actually lives on.)
2. Register the source in ``sources.yaml`` with ``name`` exactly
   "RedNote Feed" and ``max_items_per_day: 1`` (it counts digest
   units, not notes), following the LinkedIn Feed registration.
3. Schedule the emit step with the morning briefing job, exactly as
   the LinkedIn unit is handled today: run
   ``focu rednote-adapter emit --day <D-1> --export <export path>
   --out rednote-units-<D-1>.json`` and append the emitted unit to
   ``units-<D>.json`` before ingest. Day D's export enters the D+1
   briefing.

Usage:
  python -m focu.adapters.rednote emit --day YYYY-MM-DD \
      --export /path/to/rednote-export.json --out units-rednote.json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date as Date, datetime, time as Time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DENVER = ZoneInfo("America/Denver")
SOURCE_NAME = "RedNote Feed"
EXPLORE_URL = "https://www.xiaohongshu.com/explore"
# Between Instagram's 20 (strictest enforcement) and LinkedIn's 50:
# XHS practitioner discipline is ~20s/note serial with a CAPTCHA / IP
# block (300012) within a few dozen hits, so 30 notes is ~10 minutes
# of paced collection — see the module docstring.
DEFAULT_MAX_PER_DAY = 30
# The LinkedIn gist rule: at most 30 words per digest line.
MAX_GIST_WORDS = 30


@dataclass
class AdapterConfig:
    """Adapter-wide knobs; ``max_per_day`` is the hard daily cap and
    ``owner`` (when set) is the feed owner's handle, whose own notes
    are skipped."""

    max_per_day: int = DEFAULT_MAX_PER_DAY
    owner: str | None = None
    timezone: ZoneInfo = DENVER


@dataclass
class Note:
    """One export record, normalized. ``published`` / ``collected``
    are timezone-aware when present; at least one of them is always
    set (a record with neither is malformed and never becomes a
    Note)."""

    author: str
    url: str
    title: str = ""
    text: str = ""
    author_id: str = ""
    note_id: str = ""
    published: datetime | None = None
    collected: datetime | None = None

    def day_stamp(self) -> datetime:
        """The timestamp that decides day membership: collection time
        first (the day the feed showed the note), publication as the
        fallback."""
        return self.collected or self.published

    def sort_stamp(self) -> datetime:
        """Newest-first ordering: publication time first, collection
        as the fallback."""
        return self.published or self.collected


# ---------------------------------------------------------------------------
# Export parsing. Everything here is tolerant by contract: a bad record
# is counted, never raised on.

def parse_timestamp(value) -> datetime | None:
    """Parse one export timestamp into an aware datetime, or None.

    Accepts ISO 8601 strings (a trailing ``Z`` is fine; a naive value
    is read as UTC) and epoch numbers (>= 1e12 read as milliseconds).
    Anything else — including booleans, which are ints in Python — is
    not a timestamp.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000.0 if value >= 1e12 else float(value)
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text[-1] in ("Z", "z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def _text_field(record: dict, *names: str) -> str:
    for name in names:
        value = record.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def normalize_record(raw) -> Note | None:
    """Normalize one export record into a Note, or None if malformed.

    A record is malformed when it is not an object, has no author, has
    no usable HTTP(S) URL, or carries no parseable timestamp at all.
    Malformed records are counted by the caller and skipped — never
    guessed at, never raised on.
    """
    if not isinstance(raw, dict):
        return None
    author = _text_field(raw, "author", "nickname")
    url = _text_field(raw, "url", "note_url")
    if not author or not url.startswith(("http://", "https://")):
        return None
    published = parse_timestamp(raw.get("published_at", raw.get("time")))
    collected = parse_timestamp(raw.get("collected_at"))
    if published is None and collected is None:
        return None
    return Note(
        author=author,
        url=url,
        title=_text_field(raw, "title"),
        text=_text_field(raw, "text", "desc"),
        author_id=_text_field(raw, "author_id"),
        note_id=_text_field(raw, "note_id"),
        published=published,
        collected=collected,
    )


def parse_export(data) -> tuple[list[Note], int]:
    """Split a decoded export payload into (notes, malformed count)."""
    notes: list[Note] = []
    malformed = 0
    for raw in data:
        note = normalize_record(raw)
        if note is None:
            malformed += 1
        else:
            notes.append(note)
    return notes, malformed


# ---------------------------------------------------------------------------
# Gist + unit construction (mirrors linkedin_to_units.py).

def truncate_words(text: str, limit: int = MAX_GIST_WORDS) -> str:
    words = str(text or "").split()
    return " ".join(words[:limit])


def gist_for(note: Note) -> str:
    """The digest gist: the note's title, or its text when untitled
    (<=30 words either way). A note with neither gets a factual label,
    never invented text."""
    source = note.title or note.text
    source = " ".join(source.split())
    if source:
        return truncate_words(source)
    return "Note (no title or text)"


def build_unit(day: str, notes: list[Note]) -> dict:
    date = Date.fromisoformat(day)
    published = datetime.combine(date, Time(23, 59), tzinfo=DENVER)
    lines = [
        f"{n}. {note.author} — {gist_for(note)} ({note.url})"
        for n, note in enumerate(notes, start=1)
    ]
    return {
        "source": SOURCE_NAME,
        "title": f"{SOURCE_NAME} — {date.strftime('%A, %B ')}{date.day}, {date.year}",
        "url": f"{EXPLORE_URL}?day={day}",
        "published_at": published.isoformat(timespec="seconds"),
        "body": "\n".join(lines),
    }


# ---------------------------------------------------------------------------
# Day selection.

def select_notes(notes: list[Note], day: str, *,
                 config: AdapterConfig) -> dict:
    """Filter one day's notes out of a parsed export.

    Order: day membership (collection-day semantics, Denver), then
    the owner's own notes are skipped, then URL duplicates collapse,
    then newest first, then the hard cap. Returns the included notes
    plus the skip counts the report carries.
    """
    target = Date.fromisoformat(day)
    included: list[Note] = []
    off_day = 0
    skipped_own = 0
    owner = (config.owner or "").lower()
    for note in notes:
        if note.day_stamp().astimezone(config.timezone).date() != target:
            off_day += 1
            continue
        if owner and owner in (note.author.lower(), note.author_id.lower()):
            skipped_own += 1
            continue
        included.append(note)
    seen: set[str] = set()
    unique: list[Note] = []
    duplicates = 0
    for note in included:
        if note.url in seen:
            duplicates += 1
            continue
        seen.add(note.url)
        unique.append(note)
    unique.sort(key=lambda note: note.sort_stamp(), reverse=True)
    return {"posts": unique[:config.max_per_day],
            "off_day": off_day, "skipped_own": skipped_own,
            "duplicates": duplicates,
            "over_cap": max(0, len(unique) - config.max_per_day)}


# ---------------------------------------------------------------------------
# The adapter proper.

def emit(day: str, export: str, out: str, *,
         config: AdapterConfig | None = None) -> dict:
    """Emit one day's RedNote digest unit from an export file.

    Always writes ``out`` (``[]`` when nothing is emitted) and returns
    a report: the feed summary (record / malformed / off-day / own /
    duplicate / included counts and the cap) and any ``failures``.
    Never raises for an export problem, so an adapter failure can
    never block the briefing.
    """
    config = config or AdapterConfig()
    units: list[dict] = []
    failures: list[dict] = []
    summary = {"records": 0, "malformed": 0, "off_day": 0,
               "skipped_own": 0, "duplicates": 0, "over_cap": 0,
               "included": 0, "cap": config.max_per_day}
    export_path = Path(export)
    if not export_path.is_file():
        failures.append({"source": SOURCE_NAME, "error": "ExportFileNotFound",
                         "export": str(export)})
    else:
        try:
            data = json.loads(export_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            failures.append({"source": SOURCE_NAME,
                             "error": "ExportParseError",
                             "export": str(export)})
            data = None
        if data is not None and not isinstance(data, list):
            failures.append({"source": SOURCE_NAME,
                             "error": "ExportShapeError",
                             "export": str(export)})
            data = None
        if data is not None:
            notes, malformed = parse_export(data)
            result = select_notes(notes, day, config=config)
            summary.update({
                "records": len(data), "malformed": malformed,
                "off_day": result["off_day"],
                "skipped_own": result["skipped_own"],
                "duplicates": result["duplicates"],
                "over_cap": result["over_cap"],
                "included": len(result["posts"]),
            })
            if result["posts"]:
                units.append(build_unit(day, result["posts"]))
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(units, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return {"day": day, "units": len(units), "out": out, "feed": summary,
            "failures": failures}


# ---------------------------------------------------------------------------
# CLI: `focu rednote-adapter ...` (thin argparse wrapper, like focu.packs).

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="focu rednote-adapter",
        description="RedNote (Xiaohongshu) export digest for the Focu daily "
                    "pipeline (prototype; consumes an owner-produced export "
                    "file, never touches the platform)")
    sub = parser.add_subparsers(dest="action", required=True)
    emit_cmd = sub.add_parser(
        "emit", help="Emit one day's digest unit from an export file")
    emit_cmd.add_argument("--day", required=True, help="Denver day, YYYY-MM-DD")
    emit_cmd.add_argument("--export", required=True,
                          help="Path to the JSON export produced outside Focu "
                               "by the owner's own tooling")
    emit_cmd.add_argument("--out", required=True, help="Where to write the units JSON")
    emit_cmd.add_argument("--owner", default=None,
                          help="Feed owner's handle or display name; their own "
                               "notes are skipped (default: skip none)")
    emit_cmd.add_argument("--max-per-day", type=int, default=None,
                          help="Hard daily cap on notes in the digest "
                               f"(built-in default is {DEFAULT_MAX_PER_DAY})")
    args = parser.parse_args(argv)

    if args.action == "emit":
        config = AdapterConfig(owner=args.owner)
        if args.max_per_day is not None:
            config.max_per_day = args.max_per_day
        report = emit(args.day, args.export, args.out, config=config)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
