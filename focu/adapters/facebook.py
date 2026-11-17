"""Facebook adapter prototype: owner browser-session export -> daily unit.

This is the fourth platform adapter built against the contract in the
infra design (``docs/dev-team/infra-design.md`` B.3 and B.5, Seam 1),
and it is shaped exactly like the RedNote adapter
(``focu/adapters/rednote.py``): an export-file adapter containing
zero platform code. That shape is forced by the survey's honest
conclusion for Facebook — there is NO mature, maintained open-source
tool that reads the owner's personal news feed:

- ``kevinzg/facebook-scraper`` (3,329 stars, MIT) was last pushed
  2024-06-22 — ~17 months stale at survey time, with 447 open
  issues — and was never strong on the logged-in personal feed.
- RSSHub's facebook routes cover Pages, groups, photos and reels —
  public/Page surfaces, not the personal feed.
- The official Meta Graph API offers no personal news-feed endpoint
  to third-party apps at all.

So the collection route is the one Focu already operates for
LinkedIn, replicated with zero new dependencies: scheduled agent
browser sessions on the owner's OWN logged-in Chrome read the home
feed and write an export file; this adapter only ever sees that
file. Session and cookie handling NEVER enter Focu — there is no
login, no session code, and no platform request anywhere in this
module, and Focu stores no Facebook credential of any kind. If
Facebook presents a checkpoint, a login demand, or any other
challenge inside the browser session, that is a STOP condition
under the LinkedIn runbook rule: the session ends, the stop is
reported, and resolving it is an owner-only step — the exporter
never solves a checkpoint, and neither does this adapter (it only
consumes whatever export the owner-side tooling produced). If the
exporter disappears tomorrow, this adapter is untouched — only the
export producer changes.

The export shape (the contract the owner's browser tooling must
produce — the LinkedIn store's ``author / gist / permalink`` payload,
carried in the RedNote adapter's record shape)::

    [
      {
        "post_id": "<opaque id>",                          // optional, informational
        "author": "<display name>",                        // required
        "author_id": "<stable profile id>",                // optional; own-post matching
        "text": "<post text>",                             // optional
        "url": "https://www.facebook.com/<user>/posts/<id>",  // required
        "published_at": "2026-11-17T08:30:00-07:00",       // post's own time
        "collected_at": "2026-11-17T09:12:44-07:00"        // when the session read it
      },
      ...
    ]

Field rules, enforced by ``normalize_record``:

- ``author`` and ``url`` are required; a record missing either, or
  with no usable timestamp, is malformed — counted in the report and
  skipped, never crashed on and never guessed at. Non-object entries
  in the list are malformed the same way.
- Tolerated aliases from common exporter output: ``permalink`` for
  ``url``, and ``time`` for ``published_at``.
- Timestamps are ISO 8601 strings, or epoch numbers (values >= 1e12
  are read as milliseconds). A timestamp SHOULD carry an offset; a
  naive value is read as UTC, never silently localized.
- Day membership: a post belongs to the Denver date of its
  ``collected_at`` — the day the owner's feed actually showed it,
  which is the LinkedIn semantic (items read on day D form day D's
  digest, whatever their original publication date). When
  ``collected_at`` is absent, the Denver date of ``published_at`` is
  used instead.

What it does, per Denver day:

- Keeps the target day's posts, newest first (by ``published_at``,
  falling back to ``collected_at``), deduplicated by URL.
- Skips the owner's own posts when an owner handle is configured
  (matched case-insensitively against ``author`` and ``author_id``) —
  the Seam-1 rule every own-feed adapter here follows.
- Applies a HARD daily cap (default 15 posts) — deliberately the
  LOWEST of the four platforms, below even Instagram's 20. The infra
  design's instruction for Facebook is explicit: keep it at the
  lowest volume of the four. Meta's enforcement is the strictest of
  the platforms here and lands on the owner's personal account;
  Facebook challenges unusual-session activity aggressively; and the
  browser-session route is the most brittle of the four to UI
  changes, so every session is a checkpoint risk. Fifteen posts is a
  short, human-shaped read of the feed's top — the digest never asks
  the exporter for more than the cap. (The pacing itself happens in
  the exporter, outside Focu; this cap bounds what Focu will ever
  put in a day's digest.)
- Emits ONE digest unit per day (zero when nothing survives), in the
  exact shape ``linkedin_to_units.py`` emits and the daily pipeline
  ingests::

      {"source": "Facebook Feed",
       "title": "Facebook Feed — <Weekday, Month D, YYYY>",
       "url": "https://www.facebook.com/?day=<date>",
       "published_at": "<day>T23:59:00<Denver offset>",
       "body": "1. <author> — <gist> (<url>)\\n2. ..."}

  The ``?day=`` parameter is load-bearing, not decoration: the pipeline
  derives a unit's content identity from its canonical URL, and a bare
  feed URL would collapse every day's digest into one content_id
  (the 2026-11-15 LinkedIn incident). ``day`` is an unknown parameter,
  so it survives ``focu.daily.identity.canonical_url`` and each day is
  a distinct content item. ``published_at`` is the end of the
  collection day in America/Denver with a full ISO offset, because
  recency scoring silently ignores date-only or zone-less timestamps.
  A gist is the post's text truncated to 30 words (the LinkedIn
  rule); a post with no text (a bare photo or link share) gets the
  factual label "Post (no text)" — never invented text.

Failure shape: a missing export file, an unparseable file, or a file
whose top level is not a list is a clean ``failures`` entry in the
report (``ExportFileNotFound`` / ``ExportParseError`` /
``ExportShapeError``), an empty unit list is still written, and
``emit`` never raises for an export problem — an adapter failure can
never block the briefing.

Production wiring (NOT done by this prototype — dev-main only):

1. The OWNER-side browser tooling runs outside Focu: agent browser
   sessions on the owner's own logged-in Chrome, inside the owner's
   plausible active hours, at human pace, producing the export above
   into a platform store (the LinkedIn plan contract: seeded daily
   plan, small sessions, daily cap). A checkpoint or login demand
   ends the session and is surfaced to the owner — an owner-only
   step, never solved by the tooling. Focu only ever sees the export
   file; no part of the collector is imported, bundled, or invoked
   from here.
2. Register the source in ``sources.yaml`` as ``type: facebook``
   (the config validator must learn the type — a production-wiring
   change, not made here) with ``name`` exactly "Facebook Feed" and
   ``max_items_per_day: 1`` (it counts digest units, not posts),
   following the LinkedIn Feed registration.
3. Schedule the emit step with the morning briefing job, exactly as
   the LinkedIn unit is handled today: run
   ``focu facebook-adapter emit --day <D-1> --export <export path>
   --out facebook-units-<D-1>.json`` and append the emitted unit to
   ``units-<D>.json`` before ingest. Day D's export enters the D+1
   briefing.

Usage:
  python -m focu.adapters.facebook emit --day YYYY-MM-DD \
      --export /path/to/facebook-export.json --out units-facebook.json
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
SOURCE_NAME = "Facebook Feed"
FEED_URL = "https://www.facebook.com/"
# The lowest cap of the four platforms (LinkedIn 50, RedNote 30,
# Instagram 20): Meta enforcement is the strictest, the account is the
# owner's personal one, and the browser-session route is the most
# brittle — see the module docstring and infra design B.3.
DEFAULT_MAX_PER_DAY = 15
# The LinkedIn gist rule: at most 30 words per digest line.
MAX_GIST_WORDS = 30


@dataclass
class AdapterConfig:
    """Adapter-wide knobs; ``max_per_day`` is the hard daily cap and
    ``owner`` (when set) is the feed owner's handle, whose own posts
    are skipped."""

    max_per_day: int = DEFAULT_MAX_PER_DAY
    owner: str | None = None
    timezone: ZoneInfo = DENVER


@dataclass
class Post:
    """One export record, normalized. ``published`` / ``collected``
    are timezone-aware when present; at least one of them is always
    set (a record with neither is malformed and never becomes a
    Post)."""

    author: str
    url: str
    text: str = ""
    author_id: str = ""
    post_id: str = ""
    published: datetime | None = None
    collected: datetime | None = None

    def day_stamp(self) -> datetime:
        """The timestamp that decides day membership: collection time
        first (the day the feed showed the post), publication as the
        fallback."""
        return self.collected or self.published

    def sort_stamp(self) -> datetime:
        """Newest-first ordering: publication time first, collection
        as the fallback."""
        return self.published or self.collected


# ---------------------------------------------------------------------------
# Export parsing. Everything here is tolerant by contract: a bad record
# is counted, never raised on. These small helpers mirror
# focu/adapters/rednote.py's deliberately — each adapter in this
# package is self-contained (instagram.py and rednote.py likewise carry
# their own copies) rather than importing a sibling's record-shaped
# internals; the two export adapters stay structurally identical so
# they are easy to keep in step.

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


def normalize_record(raw) -> Post | None:
    """Normalize one export record into a Post, or None if malformed.

    A record is malformed when it is not an object, has no author, has
    no usable HTTP(S) URL, or carries no parseable timestamp at all.
    Malformed records are counted by the caller and skipped — never
    guessed at, never raised on.
    """
    if not isinstance(raw, dict):
        return None
    author = _text_field(raw, "author")
    url = _text_field(raw, "url", "permalink")
    if not author or not url.startswith(("http://", "https://")):
        return None
    published = parse_timestamp(raw.get("published_at", raw.get("time")))
    collected = parse_timestamp(raw.get("collected_at"))
    if published is None and collected is None:
        return None
    return Post(
        author=author,
        url=url,
        text=_text_field(raw, "text"),
        author_id=_text_field(raw, "author_id"),
        post_id=_text_field(raw, "post_id"),
        published=published,
        collected=collected,
    )


def parse_export(data) -> tuple[list[Post], int]:
    """Split a decoded export payload into (posts, malformed count)."""
    posts: list[Post] = []
    malformed = 0
    for raw in data:
        post = normalize_record(raw)
        if post is None:
            malformed += 1
        else:
            posts.append(post)
    return posts, malformed


# ---------------------------------------------------------------------------
# Gist + unit construction (mirrors linkedin_to_units.py).

def truncate_words(text: str, limit: int = MAX_GIST_WORDS) -> str:
    words = str(text or "").split()
    return " ".join(words[:limit])


def gist_for(post: Post) -> str:
    """The digest gist: the post's text (<=30 words). A post with no
    text (a bare photo or link share) gets a factual label, never
    invented text."""
    source = " ".join(post.text.split())
    if source:
        return truncate_words(source)
    return "Post (no text)"


def build_unit(day: str, posts: list[Post]) -> dict:
    date = Date.fromisoformat(day)
    published = datetime.combine(date, Time(23, 59), tzinfo=DENVER)
    lines = [
        f"{n}. {post.author} — {gist_for(post)} ({post.url})"
        for n, post in enumerate(posts, start=1)
    ]
    return {
        "source": SOURCE_NAME,
        "title": f"{SOURCE_NAME} — {date.strftime('%A, %B ')}{date.day}, {date.year}",
        "url": f"{FEED_URL}?day={day}",
        "published_at": published.isoformat(timespec="seconds"),
        "body": "\n".join(lines),
    }


# ---------------------------------------------------------------------------
# Day selection.

def select_posts(posts: list[Post], day: str, *,
                 config: AdapterConfig) -> dict:
    """Filter one day's posts out of a parsed export.

    Order: day membership (collection-day semantics, Denver), then
    the owner's own posts are skipped, then URL duplicates collapse,
    then newest first, then the hard cap. Returns the included posts
    plus the skip counts the report carries.
    """
    target = Date.fromisoformat(day)
    included: list[Post] = []
    off_day = 0
    skipped_own = 0
    owner = (config.owner or "").lower()
    for post in posts:
        if post.day_stamp().astimezone(config.timezone).date() != target:
            off_day += 1
            continue
        if owner and owner in (post.author.lower(), post.author_id.lower()):
            skipped_own += 1
            continue
        included.append(post)
    seen: set[str] = set()
    unique: list[Post] = []
    duplicates = 0
    for post in included:
        if post.url in seen:
            duplicates += 1
            continue
        seen.add(post.url)
        unique.append(post)
    unique.sort(key=lambda post: post.sort_stamp(), reverse=True)
    return {"posts": unique[:config.max_per_day],
            "off_day": off_day, "skipped_own": skipped_own,
            "duplicates": duplicates,
            "over_cap": max(0, len(unique) - config.max_per_day)}


# ---------------------------------------------------------------------------
# The adapter proper.

def emit(day: str, export: str, out: str, *,
         config: AdapterConfig | None = None) -> dict:
    """Emit one day's Facebook digest unit from an export file.

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
            posts, malformed = parse_export(data)
            result = select_posts(posts, day, config=config)
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
# CLI: `focu facebook-adapter ...` (thin argparse wrapper, like focu.packs).

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="focu facebook-adapter",
        description="Facebook own-feed digest for the Focu daily pipeline "
                    "(prototype; consumes an owner-produced export file, "
                    "never touches the platform)")
    sub = parser.add_subparsers(dest="action", required=True)
    emit_cmd = sub.add_parser(
        "emit", help="Emit one day's digest unit from an export file")
    emit_cmd.add_argument("--day", required=True, help="Denver day, YYYY-MM-DD")
    emit_cmd.add_argument("--export", required=True,
                          help="Path to the JSON export produced outside Focu "
                               "by the owner's own browser tooling")
    emit_cmd.add_argument("--out", required=True, help="Where to write the units JSON")
    emit_cmd.add_argument("--owner", default=None,
                          help="Feed owner's name or profile id; their own "
                               "posts are skipped (default: skip none)")
    emit_cmd.add_argument("--max-per-day", type=int, default=None,
                          help="Hard daily cap on posts in the digest "
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
