"""Instagram adapter prototype (focu/adapters/instagram.py).

Covers the adapter contract from the infra design (B.2 + B.5 Seam 1)
with the LinkedIn emitter as reference: session-file-only access (no
login, no credentials in Focu), feed-post normalization from fixture
posts, the LinkedIn unit shape, per-day URL identity (the 2026-11-15
LinkedIn lesson), the hard daily cap, the owner's-own-post skip, the
pacing hook, and the STOP conditions — checkpoint / challenge /
login-required abort the day with a ``stopped`` report entry and no
partial emit. Everything runs against fake loaders: no Instaloader,
no network, no live account.
"""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from focu.adapters import instagram
from focu.adapters.instagram import (AdapterConfig, emit, gist_for,
                                     normalize_post, stop_reason,
                                     truncate_words, username_from_session_path)
from focu.daily.identity import canonical_url, content_identity

DAY = "2026-11-17"        # a Tuesday; America/Denver is MST (UTC-7)
DAY_BEFORE = "2026-11-16"


def raw_post(shortcode, author="alice", caption="A caption",
             date_utc=datetime(2026, 11, 17, 15, 0), is_video=False,
             mediacount=1):
    """A duck-typed stand-in for an Instaloader Post (naive UTC date,
    exactly as Instaloader's ``date_utc`` arrives)."""
    return SimpleNamespace(shortcode=shortcode, owner_username=author,
                           caption=caption, date_utc=date_utc,
                           is_video=is_video, mediacount=mediacount)


def day_post(n, hour=15):
    return raw_post(f"CODE{n}", author=f"user{n}", caption=f"Post number {n}",
                    date_utc=datetime(2026, 11, 17, hour, 0))


class FakeLoader:
    """Injectable loader: returns fixture posts or raises, and records
    how it was called (session path, username, scan bound)."""

    def __init__(self, posts=(), error=None):
        self.posts = list(posts)
        self.error = error
        self.calls = []

    def __call__(self, session_path, username, *, max_scan):
        self.calls.append({"session": str(session_path), "username": username,
                           "max_scan": max_scan})
        if self.error is not None:
            raise self.error
        return iter(self.posts)


class LoginRequiredException(Exception):
    """Named like Instaloader's own login-required error."""


def make_session(tmp, name="session-testuser"):
    path = Path(tmp) / name
    path.write_text("dummy-session-bytes", encoding="utf-8")
    return str(path)


def no_sleep(seconds):
    return None


class NormalizePostTests(unittest.TestCase):
    def test_normalize_post_fields(self):
        post = normalize_post(raw_post("ABC123", author="alice",
                                       caption="Hello world",
                                       date_utc=datetime(2026, 11, 17, 15, 30)))
        self.assertIsNotNone(post)
        self.assertEqual(post.shortcode, "ABC123")
        self.assertEqual(post.author, "alice")
        self.assertEqual(post.caption, "Hello world")
        self.assertEqual(post.url, "https://www.instagram.com/p/ABC123/")
        self.assertEqual(post.media, "image")
        # Naive Instaloader date_utc is read as UTC, never left zone-less.
        self.assertEqual(post.published,
                         datetime(2026, 11, 17, 15, 30, tzinfo=timezone.utc))

    def test_media_kinds(self):
        self.assertEqual(normalize_post(raw_post("V", is_video=True)).media, "video")
        self.assertEqual(normalize_post(raw_post("C", mediacount=4)).media, "carousel")
        self.assertEqual(normalize_post(raw_post("I", mediacount=1)).media, "image")

    def test_unusable_posts_are_skipped_not_guessed(self):
        self.assertIsNone(normalize_post(raw_post("")))
        self.assertIsNone(normalize_post(SimpleNamespace(
            shortcode="X", owner_username="a", caption="c", date_utc=None)))
        self.assertIsNone(normalize_post(SimpleNamespace(owner_username="a")))


class GistTests(unittest.TestCase):
    def test_caption_gist_truncates_at_30_words(self):
        caption = " ".join(f"word{i}" for i in range(40))
        post = normalize_post(raw_post("ABC", caption=caption))
        self.assertEqual(gist_for(post), " ".join(f"word{i}" for i in range(30)))
        self.assertEqual(truncate_words(caption), gist_for(post))

    def test_single_token_caption_is_char_capped(self):
        # P2-5 regression: the 30-word rule alone let one whitespace-
        # free token (base64 dump, unspaced CJK run) through unbounded.
        post = normalize_post(raw_post("ABC", caption="a" * 5000))
        self.assertEqual(len(gist_for(post)), 500)
        self.assertEqual(len(truncate_words("a" * 5000)), 500)

    def test_captionless_posts_get_factual_media_labels(self):
        self.assertEqual(gist_for(normalize_post(raw_post("P", caption=""))),
                         "Photo post")
        self.assertEqual(gist_for(normalize_post(
            raw_post("V", caption=None, is_video=True))), "Video post")
        self.assertEqual(gist_for(normalize_post(
            raw_post("C", caption="", mediacount=3))), "Carousel post")


class StopReasonTests(unittest.TestCase):
    def test_class_name_markers(self):
        self.assertEqual(stop_reason(LoginRequiredException("x")), "login_required")

    def test_message_markers(self):
        self.assertEqual(stop_reason(Exception("checkpoint_url returned")),
                         "checkpoint")
        self.assertEqual(stop_reason(Exception("challenge_required")), "challenge")
        self.assertEqual(stop_reason(Exception("Please wait a few minutes "
                                               "before you try again.")),
                         "rate_limited")

    def test_ordinary_errors_are_not_stops(self):
        self.assertIsNone(stop_reason(RuntimeError("boom")))
        self.assertIsNone(stop_reason(ValueError("bad payload")))


class EmitShapeTests(unittest.TestCase):
    def test_emit_shape_matches_linkedin_unit(self):
        posts = [raw_post("LATE", author="bob", caption="Later post",
                          date_utc=datetime(2026, 11, 17, 20, 0)),
                 raw_post("EARLY", author="alice", caption="Earlier post",
                          date_utc=datetime(2026, 11, 17, 15, 0))]
        loader = FakeLoader(posts)
        with tempfile.TemporaryDirectory() as tmp:
            session = make_session(tmp)
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, session, out, load_feed=loader, sleep=no_sleep)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(report["units"], 1)
        self.assertEqual(report["stopped"], [])
        self.assertEqual(report["failures"], [])
        self.assertEqual(report["feed"]["scanned"], 2)
        self.assertEqual(report["feed"]["included"], 2)
        self.assertEqual(len(units), 1)
        unit = units[0]
        # Exactly the Seam-1 keys, all strings.
        self.assertEqual(set(unit), {"source", "title", "url", "published_at", "body"})
        for value in unit.values():
            self.assertIsInstance(value, str)
        self.assertEqual(unit["source"], "Instagram Feed")
        self.assertEqual(unit["title"], "Instagram Feed — Tuesday, November 17, 2026")
        self.assertEqual(unit["url"], f"https://www.instagram.com/?day={DAY}")
        # End of the Denver day, full ISO offset (MST in November).
        self.assertEqual(unit["published_at"], "2026-11-17T23:59:00-07:00")
        lines = unit["body"].split("\n")
        self.assertEqual(len(lines), 2)
        # Newest first, LinkedIn line shape: N. @author — gist (permalink).
        self.assertEqual(lines[0], "1. @bob — Later post "
                                   "(https://www.instagram.com/p/LATE/)")
        self.assertEqual(lines[1], "2. @alice — Earlier post "
                                   "(https://www.instagram.com/p/EARLY/)")
        # The loader saw the session path, the derived username, and
        # the scan bound — and nothing resembling a password exists
        # anywhere in the call.
        self.assertEqual(loader.calls[0]["session"], session)
        self.assertEqual(loader.calls[0]["username"], "testuser")
        self.assertEqual(loader.calls[0]["max_scan"], AdapterConfig().max_scan)

    def test_denver_day_boundary(self):
        # 05:30 UTC on the 18th is 22:30 MST on the 17th; 06:59 UTC on
        # the 17th is 23:59 MST on the 16th.
        posts = [raw_post("D17", date_utc=datetime(2026, 11, 18, 5, 30)),
                 raw_post("D16", date_utc=datetime(2026, 11, 17, 6, 59))]
        with tempfile.TemporaryDirectory() as tmp:
            session = make_session(tmp)
            out17 = str(Path(tmp) / "u17.json")
            emit(DAY, session, out17, load_feed=FakeLoader(posts), sleep=no_sleep)
            units17 = json.loads(Path(out17).read_text(encoding="utf-8"))
            out16 = str(Path(tmp) / "u16.json")
            emit(DAY_BEFORE, session, out16, load_feed=FakeLoader(posts),
                 sleep=no_sleep)
            units16 = json.loads(Path(out16).read_text(encoding="utf-8"))
            out18 = str(Path(tmp) / "u18.json")
            emit("2026-11-18", session, out18, load_feed=FakeLoader(posts),
                 sleep=no_sleep)
            units18 = json.loads(Path(out18).read_text(encoding="utf-8"))
        self.assertEqual(len(units17), 1)
        self.assertIn("/p/D17/", units17[0]["body"])
        self.assertNotIn("/p/D16/", units17[0]["body"])
        self.assertEqual(len(units16), 1)
        self.assertIn("/p/D16/", units16[0]["body"])
        # A day with nothing collected still writes a valid empty list.
        self.assertEqual(units18, [])

    def test_username_from_session_path(self):
        self.assertEqual(username_from_session_path("/x/session-jerry94242"),
                         "jerry94242")
        self.assertIsNone(username_from_session_path("/x/whatever.bin"))
        # P2-5 regression: dotted usernames survive intact — session
        # files are extensionless, so the name is not a stem.
        self.assertEqual(username_from_session_path("/x/session-jerry.94242"),
                         "jerry.94242")
        self.assertEqual(username_from_session_path("session-a-b"), "a-b")
        self.assertIsNone(username_from_session_path("/x/session-"))


class IdentityTests(unittest.TestCase):
    def test_per_day_url_identity_differs(self):
        units_by_day = {}
        with tempfile.TemporaryDirectory() as tmp:
            session = make_session(tmp)
            for day, post in ((DAY_BEFORE, raw_post(
                    "P16", date_utc=datetime(2026, 11, 16, 18, 0))),
                              (DAY, raw_post(
                    "P17", date_utc=datetime(2026, 11, 17, 18, 0)))):
                out = str(Path(tmp) / f"units-{day}.json")
                emit(day, session, out, load_feed=FakeLoader([post]),
                     sleep=no_sleep)
                units_by_day[day] = json.loads(Path(out).read_text(encoding="utf-8"))[0]
        url16, url17 = units_by_day[DAY_BEFORE]["url"], units_by_day[DAY]["url"]
        self.assertNotEqual(url16, url17)
        self.assertTrue(url16.endswith(f"?day={DAY_BEFORE}"))
        self.assertTrue(url17.endswith(f"?day={DAY}"))
        # The pipeline's own identity function must keep the days apart:
        # canonicalization preserves ?day=, so the stable content
        # identities differ (the 2026-11-15 LinkedIn lesson).
        self.assertNotEqual(canonical_url(url16), canonical_url(url17))
        id16, _, _ = content_identity(units_by_day[DAY_BEFORE], "src_test")
        id17, _, _ = content_identity(units_by_day[DAY], "src_test")
        self.assertNotEqual(id16, id17)


class CapTests(unittest.TestCase):
    def test_default_cap_is_20_and_consumption_stops_there(self):
        pulled = []

        def counting_loader(session_path, username, *, max_scan):
            for i in range(25):
                pulled.append(i)
                yield day_post(i)

        with tempfile.TemporaryDirectory() as tmp:
            session = make_session(tmp)
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, session, out, load_feed=counting_loader,
                          sleep=no_sleep)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(len(units), 1)
        self.assertEqual(len(units[0]["body"].split("\n")), 20)
        self.assertEqual(report["feed"]["included"], 20)
        self.assertEqual(report["feed"]["cap"], 20)
        # The cap is hard: the loader was never consumed past it.
        self.assertEqual(len(pulled), 20)

    def test_config_cap_override(self):
        loader = FakeLoader([day_post(i) for i in range(6)])
        with tempfile.TemporaryDirectory() as tmp:
            session = make_session(tmp)
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, session, out, config=AdapterConfig(max_per_day=3),
                          load_feed=loader, sleep=no_sleep)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(report["feed"]["included"], 3)
        self.assertEqual(len(units[0]["body"].split("\n")), 3)


class OwnPostTests(unittest.TestCase):
    def test_owners_own_posts_are_skipped(self):
        posts = [raw_post("MINE", author="TestUser", caption="My own post"),
                 raw_post("THEIRS", author="alice", caption="Someone else")]
        with tempfile.TemporaryDirectory() as tmp:
            session = make_session(tmp)  # session-testuser -> "testuser"
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, session, out, load_feed=FakeLoader(posts),
                          sleep=no_sleep)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        # Case-insensitive match against the session's username.
        self.assertEqual(report["feed"]["skipped_own"], 1)
        self.assertEqual(len(units), 1)
        self.assertNotIn("/p/MINE/", units[0]["body"])
        self.assertIn("/p/THEIRS/", units[0]["body"])


class PacingTests(unittest.TestCase):
    def test_pacing_hook_fires_between_consumed_posts(self):
        delays = []
        loader = FakeLoader([day_post(i) for i in range(4)])
        with tempfile.TemporaryDirectory() as tmp:
            session = make_session(tmp)
            out = str(Path(tmp) / "units.json")
            emit(DAY, session, out,
                 config=AdapterConfig(pace_min_seconds=0.25,
                                      pace_max_seconds=0.25),
                 load_feed=loader, sleep=delays.append)
        # Strictly serial: one pause between consecutive posts, none
        # before the first; every delay inside the configured band.
        self.assertEqual(delays, [0.25, 0.25, 0.25])


class StopTests(unittest.TestCase):
    def test_login_required_stops_the_day(self):
        loader = FakeLoader(error=LoginRequiredException("session expired"))
        with tempfile.TemporaryDirectory() as tmp:
            session = make_session(tmp)
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, session, out, load_feed=loader, sleep=no_sleep)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(units, [])
        self.assertEqual(report["units"], 0)
        self.assertEqual(report["failures"], [])
        self.assertEqual(len(report["stopped"]), 1)
        self.assertEqual(report["stopped"][0]["reason"], "login_required")
        self.assertEqual(report["stopped"][0]["error"], "LoginRequiredException")

    def test_checkpoint_mid_iteration_emits_nothing_partial(self):
        def checkpointing_loader(session_path, username, *, max_scan):
            yield day_post(1)
            yield day_post(2)
            raise Exception("checkpoint_url: verify your identity")

        with tempfile.TemporaryDirectory() as tmp:
            session = make_session(tmp)
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, session, out, load_feed=checkpointing_loader,
                          sleep=no_sleep)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        # Two posts were collected before the stop; the day still
        # emits nothing — a partial digest is never shipped.
        self.assertEqual(units, [])
        self.assertEqual(report["units"], 0)
        self.assertEqual(len(report["stopped"]), 1)
        self.assertEqual(report["stopped"][0]["reason"], "checkpoint")


class FailureTests(unittest.TestCase):
    def test_missing_session_is_a_clean_report_not_a_traceback(self):
        loader = FakeLoader([day_post(1)])
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "session-ghost")
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, missing, out, load_feed=loader, sleep=no_sleep)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(units, [])
        self.assertEqual(report["units"], 0)
        self.assertEqual(report["stopped"], [])
        self.assertEqual(len(report["failures"]), 1)
        self.assertEqual(report["failures"][0]["error"], "SessionFileNotFound")
        # The loader was never invoked without a session file.
        self.assertEqual(loader.calls, [])

    def test_ordinary_loader_failure_is_recorded_not_raised(self):
        loader = FakeLoader(error=RuntimeError("boom"))
        with tempfile.TemporaryDirectory() as tmp:
            session = make_session(tmp)
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, session, out, load_feed=loader, sleep=no_sleep)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(units, [])
        self.assertEqual(report["stopped"], [])
        self.assertEqual(len(report["failures"]), 1)
        self.assertEqual(report["failures"][0]["error"], "RuntimeError")


class CliTests(unittest.TestCase):
    def test_module_cli_emit(self):
        loader = FakeLoader([day_post(1)])
        with tempfile.TemporaryDirectory() as tmp:
            session = make_session(tmp)
            out = str(Path(tmp) / "units.json")
            with mock.patch.object(instagram, "instaloader_feed_posts", loader):
                code = instagram.main(["emit", "--day", DAY, "--session", session,
                                       "--out", out])
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["source"], "Instagram Feed")

    def test_focu_cli_dispatch(self):
        from focu.cli import main as focu_main
        loader = FakeLoader([day_post(1)])
        with tempfile.TemporaryDirectory() as tmp:
            session = make_session(tmp)
            out = str(Path(tmp) / "units.json")
            with mock.patch.object(instagram, "instaloader_feed_posts", loader):
                code = focu_main(["instagram-adapter", "emit", "--day", DAY,
                                  "--session", session, "--out", out])
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(len(units), 1)


if __name__ == "__main__":
    unittest.main()
