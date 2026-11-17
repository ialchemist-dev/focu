"""Instagram adapter prototype: own feed via saved session -> daily unit.

This is the second platform adapter built against the contract in the
infra design (``docs/dev-team/infra-design.md`` B.2 and B.5, Seam 1),
with the LinkedIn feed as the reference implementation and
``focu/adapters/youtube.py`` as the code template. Instagram is the
opposite end of the risk spectrum from YouTube: there is no official
home-feed surface at all (the Graph API offers none), so the route is
the conservative one the design recommends — Instaloader reusing a
saved session file to read the owner's OWN feed, at low volume, under
the LinkedIn behavioral contract.

The session boundary (the load-bearing rule of this module):

- Focu NEVER sees a password. The adapter accepts only the PATH to an
  Instaloader session file, created outside Focu by the owner's own
  tooling (see "Production wiring"). It never performs a login, never
  prompts for credentials, never stores or copies the session file,
  and never retries a failed session load.
- The Instaloader call sits behind one injectable loader function
  (``load_feed``). Instaloader is deliberately NOT a dependency of this
  package — it is not installed in the dev environment, and the default
  loader below is therefore NOT exercised here or by the tests; every
  test runs against fakes. Production wiring installs a pinned
  Instaloader in the runtime toolchain and smoke-tests the default
  loader there (see below).

What it does, per Denver day:

- Loads the owner's feed posts through the session and keeps the posts
  whose publication date in America/Denver is the target day. The home
  feed is algorithmic, not chronological, so the adapter scans up to
  ``max_scan`` posts (default 100) and filters by date — it cannot
  stop at the first older post the way a channel RSS reader can.
- Skips the owner's own posts (when the username is known) — the
  Seam-1 rule LinkedIn follows. Promoted/sponsored items cannot be
  distinguished from organic posts on Instaloader's Post surface, so
  no ad filtering is claimed.
- Applies a HARD daily cap (default 20 posts — deliberately below the
  LinkedIn digest's 50: Meta enforcement is the strictest of the four
  platforms and lands on the owner's personal account). Collection is
  strictly serial, with a pacing hook between consumed posts (a
  randomized 2–5s pause by default; production wiring owns the real
  schedule inside the owner's plausible active hours).
- Emits ONE digest unit per day (zero when nothing survives), in the
  exact shape ``linkedin_to_units.py`` emits and the daily pipeline
  ingests::

      {"source": "Instagram Feed",
       "title": "Instagram Feed — <Weekday, Month D, YYYY>",
       "url": "https://www.instagram.com/?day=<date>",
       "published_at": "<day>T23:59:00<Denver offset>",
       "body": "1. @<author> — <gist> (<permalink>)\\n2. ..."}

  The ``?day=`` parameter is load-bearing, not decoration: the pipeline
  derives a unit's content identity from its canonical URL, and a bare
  feed URL would collapse every day's digest into one content_id (the
  2026-11-15 LinkedIn incident). ``day`` is an unknown parameter, so it
  survives ``focu.daily.identity.canonical_url`` and each day is a
  distinct content item. ``published_at`` is the end of the collection
  day in America/Denver with a full ISO offset, because recency scoring
  silently ignores date-only or zone-less timestamps. Body lines are
  newest first; a gist is the post's caption truncated to 30 words
  (the LinkedIn rule), or — for a captionless post — a factual media
  label ("Photo post" / "Video post" / "Carousel post"), never
  invented text.

STOP conditions (the scraping research + LinkedIn runbook rule): a
checkpoint, challenge, login-required, two-factor, or rate-limit
response from the platform ends the day immediately. The adapter
raises ``AdapterStopped`` internally, writes NO unit (never a partial
digest), records the stop in the report's ``stopped`` list with the
reason, and never retries around it. Resolving the stop is an
owner-only step (see "Production wiring"). Any other loader failure is
recorded in the report's ``failures`` and also emits nothing, so an
adapter failure can never block the briefing. A missing session file
is a clean ``failures`` entry (``SessionFileNotFound``), never a
traceback.

Production wiring (NOT done by this prototype — dev-main only):

1. Install a PINNED Instaloader in the runtime toolchain environment
   (not as a focu dependency). The default loader targets
   Instaloader's session-file API — ``load_session_from_file`` plus
   the context's feed-post iteration — with
   ``max_connection_attempts=1`` so the library itself never retries
   around a checkpoint; smoke-test it there against the pinned
   version before scheduling anything. It has not been run live.
2. Session creation is the OWNER's step, outside Focu: the owner runs
   Instaloader's own login once, interactively (e.g.
   ``instaloader --login <username>``), which saves a
   ``session-<username>`` file. The file lives outside the repo with
   owner-only permissions; only its path is handed to this adapter.
   When a session expires the adapter stops with ``login_required``
   and the owner re-creates the file the same way — the adapter
   never logs in on anyone's behalf.
3. Register the source in ``sources.yaml`` as ``type: instagram``
   (the config validator must learn the type — a production-wiring
   change, not made here) with ``name`` exactly "Instagram Feed" and
   ``max_items_per_day: 1`` (it counts digest units, not posts).
4. Schedule a collector step inside the owner's plausible active
   hours: in the morning briefing job, run
   ``focu instagram-adapter emit --day <D-1> --session <path>
   --out instagram-units-<D-1>.json`` and append the emitted unit to
   ``units-<D>.json`` before ingest, exactly as the LinkedIn unit is
   appended today. A non-empty ``stopped`` list in the report must be
   surfaced to the owner — it names the owner-only step the platform
   is demanding.

Usage:
  python -m focu.adapters.instagram emit --day YYYY-MM-DD \
      --session /path/to/session-<username> --out units-instagram.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass
from datetime import date as Date, datetime, time as Time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DENVER = ZoneInfo("America/Denver")
SOURCE_NAME = "Instagram Feed"
FEED_URL = "https://www.instagram.com/"
POST_URL = "https://www.instagram.com/p/{shortcode}/"
# Conservative by design: below the LinkedIn digest's 50/day, on the
# platform with the strictest enforcement, against a personal account.
DEFAULT_MAX_PER_DAY = 20
# The home feed is algorithmic; scanning is bounded so a stale or
# unexpectedly deep feed cannot page forever.
DEFAULT_MAX_SCAN = 100
# The LinkedIn gist rule: at most 30 words per digest line.
MAX_GIST_WORDS = 30
DEFAULT_PACE_MIN_SECONDS = 2.0
DEFAULT_PACE_MAX_SECONDS = 5.0


@dataclass
class AdapterConfig:
    """Adapter-wide knobs; ``max_per_day`` is the hard daily cap."""

    max_per_day: int = DEFAULT_MAX_PER_DAY
    max_scan: int = DEFAULT_MAX_SCAN
    pace_min_seconds: float = DEFAULT_PACE_MIN_SECONDS
    pace_max_seconds: float = DEFAULT_PACE_MAX_SECONDS
    timezone: ZoneInfo = DENVER


@dataclass
class FeedPost:
    """One feed post, normalized from an Instaloader Post (duck-typed).

    ``published`` is always timezone-aware; Instaloader's naive
    ``date_utc`` is read as UTC. ``media`` is "image", "video", or
    "carousel" and only feeds the captionless-post gist label.
    """

    shortcode: str
    author: str
    caption: str
    published: datetime
    url: str
    media: str = "image"


class AdapterStopped(Exception):
    """The platform demanded an owner-only step; the day is aborted.

    Carries a stable ``reason`` token (checkpoint / challenge /
    login_required / two_factor / rate_limited / stopped) and the
    original exception's class name for the report. Nothing partial
    is ever emitted for a stopped day.
    """

    def __init__(self, reason: str, original: BaseException | None = None):
        super().__init__(reason)
        self.reason = reason
        self.error = type(original).__name__ if original is not None else ""


# ---------------------------------------------------------------------------
# Stop classification. Instaloader is not imported here, so stop-class
# errors are recognized by exception class name and message markers —
# which also keeps the classifier testable with fakes.

_STOP_CLASS_MARKERS = (
    ("two_factor", ("twofactor", "two_factor")),
    ("checkpoint", ("checkpoint",)),
    ("challenge", ("challenge",)),
    ("login_required", ("loginrequired", "login_required", "badcredentials")),
)
_STOP_MESSAGE_MARKERS = (
    ("two_factor", ("two-factor", "two factor")),
    ("checkpoint", ("checkpoint",)),
    ("challenge", ("challenge",)),
    ("login_required", ("login required", "login_required")),
    ("rate_limited", ("please wait a few minutes", "please wait before")),
)


def stop_reason(exc: BaseException) -> str | None:
    """Classify an exception as a platform stop condition, or None.

    A checkpoint/challenge/login-required/two-factor/rate-limit
    response is a stop: the day ends, nothing is emitted, and the
    adapter never retries around it.
    """
    class_name = type(exc).__name__.lower()
    for reason, markers in _STOP_CLASS_MARKERS:
        if any(marker in class_name for marker in markers):
            return reason
    message = str(exc).lower()
    for reason, markers in _STOP_MESSAGE_MARKERS:
        if any(marker in message for marker in markers):
            return reason
    return None


# ---------------------------------------------------------------------------
# The Instaloader boundary: ONE injectable loader function.
# Signature: loader(session_path, username, *, max_scan) -> iterable of
# raw (duck-typed) Post objects. Tests inject fakes; production uses
# the default below.

def instaloader_feed_posts(session_path, username, *, max_scan: int):
    """Default loader: Instaloader session-file reuse -> raw feed posts.

    Imports instaloader lazily: the library is a production-wiring
    dependency (pinned in the runtime toolchain), deliberately not
    required to import or test this module, and this function is not
    exercised in the dev environment. It ONLY loads the saved session
    — it never logs in and never sees a password — and sets
    ``max_connection_attempts=1`` so the library never retries around
    a checkpoint or a rate-limit response.
    """
    import instaloader  # production-only dependency, pinned at wiring time
    loader = instaloader.Instaloader(
        download_pictures=False, download_videos=False,
        download_video_thumbnails=False, download_geotags=False,
        download_comments=False, save_metadata=False, compress_json=False,
        max_connection_attempts=1)
    loader.load_session_from_file(username, str(session_path))
    count = 0
    for post in loader.context.get_feed_posts():
        yield post
        count += 1
        if count >= max_scan:
            return


def normalize_post(raw) -> FeedPost | None:
    """Normalize one duck-typed Instaloader Post into a FeedPost.

    Returns None for a post without a shortcode or a usable timestamp
    — such a post has no permalink and no day, so it is skipped,
    never guessed.
    """
    shortcode = getattr(raw, "shortcode", None)
    if not shortcode:
        return None
    raw_date = getattr(raw, "date_utc", None) or getattr(raw, "date", None)
    if not isinstance(raw_date, datetime):
        return None
    published = (raw_date if raw_date.tzinfo is not None
                 else raw_date.replace(tzinfo=timezone.utc))
    if getattr(raw, "is_video", False):
        media = "video"
    elif int(getattr(raw, "mediacount", 1) or 1) > 1:
        media = "carousel"
    else:
        media = "image"
    return FeedPost(
        shortcode=str(shortcode),
        author=str(getattr(raw, "owner_username", "") or ""),
        caption=str(getattr(raw, "caption", "") or ""),
        published=published,
        url=POST_URL.format(shortcode=shortcode),
        media=media)


def username_from_session_path(session_path) -> str | None:
    """Derive the username from Instaloader's ``session-<username>``
    file convention, when the session file follows it."""
    stem = Path(session_path).stem
    if stem.startswith("session-") and len(stem) > len("session-"):
        return stem[len("session-"):]
    return None


# ---------------------------------------------------------------------------
# Gist + unit construction (mirrors linkedin_to_units.py).

def truncate_words(text: str, limit: int = MAX_GIST_WORDS) -> str:
    words = str(text or "").split()
    return " ".join(words[:limit])


def gist_for(post: FeedPost) -> str:
    """The digest gist: the caption (<=30 words), or a factual media
    label for a captionless post. Never invented text."""
    caption = " ".join(post.caption.split())
    if caption:
        return truncate_words(caption)
    return {"video": "Video post", "carousel": "Carousel post"}.get(
        post.media, "Photo post")


def build_unit(day: str, posts: list[FeedPost]) -> dict:
    date = Date.fromisoformat(day)
    published = datetime.combine(date, Time(23, 59), tzinfo=DENVER)
    lines = [
        f"{n}. @{post.author} — {gist_for(post)} ({post.url})"
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
# The adapter proper.

def _pace(config: AdapterConfig, sleep) -> None:
    """The pacing hook: one randomized pause between consumed posts.

    Collection is strictly serial — the loader is consumed one post at
    a time and this hook fires between consumptions, which is where
    the human pace lives. ``sleep`` is injectable for tests.
    """
    if config.pace_max_seconds <= 0:
        return
    sleep(random.uniform(config.pace_min_seconds, config.pace_max_seconds))


def collect_feed_day(day: str, *, config: AdapterConfig, session_path,
                     username: str | None, load_feed, sleep) -> dict:
    """Collect one day's feed digest through the saved session.

    Returns the day's posts (newest first), the scan count, and the
    own-post skip count. Raises AdapterStopped the moment the platform
    demands an owner-only step — posts already collected are discarded
    by the caller, so a stopped day never emits a partial digest. Any
    other loader exception propagates to the caller as a failure.
    """
    target = Date.fromisoformat(day)
    included: list[FeedPost] = []
    scanned = 0
    skipped_own = 0
    try:
        posts = load_feed(session_path, username, max_scan=config.max_scan)
        first = True
        for raw in posts:
            if not first:
                _pace(config, sleep)
            first = False
            scanned += 1
            post = normalize_post(raw)
            if post is None:
                continue
            if post.published.astimezone(config.timezone).date() != target:
                continue
            if username and post.author.lower() == username.lower():
                skipped_own += 1
                continue
            included.append(post)
            if len(included) >= config.max_per_day:
                break
    except AdapterStopped:
        raise
    except Exception as exc:
        reason = stop_reason(exc)
        if reason is not None:
            raise AdapterStopped(reason, exc) from exc
        raise
    included.sort(key=lambda post: post.published, reverse=True)
    return {"posts": included, "scanned": scanned, "skipped_own": skipped_own}


def emit(day: str, session: str, out: str, *, config: AdapterConfig | None = None,
         username: str | None = None, load_feed=None, sleep=None) -> dict:
    """Emit one day's Instagram feed digest unit to ``out`` (JSON list).

    Always writes the file (``[]`` when nothing is emitted) and returns
    a report: the feed summary, any ``stopped`` entry (the platform
    demanded an owner-only step; nothing was emitted), and any
    ``failures``. Never raises for a platform or session problem, so
    an adapter failure can never block the briefing.
    """
    config = config or AdapterConfig()
    loader = instaloader_feed_posts if load_feed is None else load_feed
    sleeper = time.sleep if sleep is None else sleep
    resolved_username = username or username_from_session_path(session)
    units: list[dict] = []
    stopped: list[dict] = []
    failures: list[dict] = []
    summary = {"scanned": 0, "included": 0, "skipped_own": 0,
               "cap": config.max_per_day}
    if not Path(session).is_file():
        failures.append({"source": SOURCE_NAME, "error": "SessionFileNotFound",
                         "session": str(session)})
    else:
        try:
            result = collect_feed_day(day, config=config, session_path=session,
                                      username=resolved_username,
                                      load_feed=loader, sleep=sleeper)
        except AdapterStopped as stop:
            stopped.append({"source": SOURCE_NAME, "reason": stop.reason,
                            "error": stop.error})
        except Exception as exc:  # adapter failure never blocks the briefing
            error = ("SessionFileNotFound" if isinstance(exc, FileNotFoundError)
                     else type(exc).__name__)
            failures.append({"source": SOURCE_NAME, "error": error})
        else:
            summary.update({"scanned": result["scanned"],
                            "included": len(result["posts"]),
                            "skipped_own": result["skipped_own"]})
            if result["posts"]:
                units.append(build_unit(day, result["posts"]))
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(units, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return {"day": day, "units": len(units), "out": out, "feed": summary,
            "stopped": stopped, "failures": failures}


# ---------------------------------------------------------------------------
# CLI: `focu instagram-adapter ...` (thin argparse wrapper, like focu.packs).

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="focu instagram-adapter",
        description="Instagram own-feed digest for the Focu daily pipeline (prototype)")
    sub = parser.add_subparsers(dest="action", required=True)
    emit_cmd = sub.add_parser(
        "emit", help="Emit one day's feed digest unit as a JSON list")
    emit_cmd.add_argument("--day", required=True, help="Denver day, YYYY-MM-DD")
    emit_cmd.add_argument("--session", required=True,
                          help="Path to an Instaloader session file created "
                               "outside Focu by the owner (never a password)")
    emit_cmd.add_argument("--out", required=True, help="Where to write the units JSON")
    emit_cmd.add_argument("--username", default=None,
                          help="Feed owner's username (default: derived from a "
                               "session-<username> file name)")
    emit_cmd.add_argument("--max-per-day", type=int, default=None,
                          help="Hard daily cap on posts in the digest "
                               f"(built-in default is {DEFAULT_MAX_PER_DAY})")
    args = parser.parse_args(argv)

    if args.action == "emit":
        config = AdapterConfig()
        if args.max_per_day is not None:
            config.max_per_day = args.max_per_day
        report = emit(args.day, args.session, args.out, config=config,
                      username=args.username)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
