"""Pack refresh-check: re-verification reports, never writes.

Covers the wave-14 freshness check: feed status taxonomy (live,
not_a_feed, http_error, unreachable, oversized, no_feed), newest-item
vs recorded last_post_at, verified_at aging, the per-pack verdict, and
the report-only guarantee (byte-identical files after a run). No
network: every fetch is a fixture.
"""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError

import focu.packs as packs_module
from focu.packs import (PACKS_DIR, format_refresh, refresh_check,
                        refresh_check_bundled)
from focu.packs import main as pack_main

TODAY = date(2026, 11, 17)


def rss(pubdate):
    return (b'<?xml version="1.0" encoding="UTF-8"?>\n'
            b'<rss version="2.0"><channel><title>Example</title>'
            b'<item><title>Post</title>'
            b'<link>https://example.com/post</link>'
            b'<pubDate>' + pubdate.encode() + b'</pubDate></item>'
            b'</channel></rss>')


RSS_OCT = rss("Mon, 12 Oct 2026 07:00:00 GMT")   # newest 2026-10-12
RSS_NOV = rss("Mon, 16 Nov 2026 07:00:00 GMT")   # newest 2026-11-16
HTML = b"<html><head><title>Interstitial</title></head></html>"
MALFORMED = (b'<?xml version="1.0"?><rss version="2.0"><channel>'
             b'<item><title><![CDATA[never closed</title></item>')
FEED_PREFIX = (b'<?xml version="1.0" encoding="UTF-8"?>\n'
               b'<rss version="2.0"><channel><title>Big Feed</title>'
               b'<item><title>Post</title>')


def make_source(**overrides):
    source = {"id": "alice", "name": "Alice Example", "type": "rss",
              "channel": "research", "platform": "Ghost",
              "homepage": "https://alice.example.com/",
              "feed_url": "https://alice.example.com/feed",
              "cadence": {"posts_per_month": 1.0,
                          "basis": "feed items dated 2026-09-01 and "
                                   "2026-10-01",
                          "as_of": "2026-11-17"},
              "verified_at": "2026-11-17", "enabled": True,
              "last_post_at": "2026-10-12"}
    source.update(overrides)
    return source


def make_pack(sources=None, **overrides):
    pack = {"schema_version": 1, "id": "test-pack", "title": "Test Pack",
            "version": "1.0.0", "curator": {"name": "Test Curator"},
            "description": "A pack used by tests.", "tags": ["test"],
            "coverage": "Only test fixtures.", "verified_at": "2026-11-17",
            "sources": sources if sources is not None else [make_source()]}
    pack.update(overrides)
    return pack


def returning(result):
    def fetch(url):
        return result
    return fetch


def raising(exc):
    def fetch(url):
        raise exc
    return fetch


def routed(routes):
    def fetch(url):
        outcome = routes[url]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    return fetch


def check(pack, fetch, **kwargs):
    return refresh_check(pack, fetch=fetch, today=TODAY, **kwargs)


class FeedStatusTests(unittest.TestCase):
    def test_live_feed_matching_record_is_current(self):
        report = check(make_pack(), returning(("https://a/", RSS_OCT, False)))
        src = report["sources"][0]
        self.assertEqual(src["feed"]["status"], "live")
        self.assertEqual(src["feed"]["items"], 1)
        self.assertEqual(src["feed"]["newest"], "2026-10-12")
        self.assertEqual(src["signals"], [])
        self.assertEqual(report["stale_signals"], 0)
        self.assertEqual(report["verdict"], "current")

    def test_two_tuple_fetch_accepted(self):
        # check_liveness-style fixtures return (final_url, bytes).
        report = check(make_pack(), returning(("https://a/", RSS_OCT)))
        self.assertEqual(report["sources"][0]["feed"]["status"], "live")

    def test_html_interstitial_is_not_a_feed(self):
        report = check(make_pack(), returning(("https://a/", HTML)))
        src = report["sources"][0]
        self.assertEqual(src["feed"]["status"], "not_a_feed")
        self.assertEqual([s["kind"] for s in src["signals"]],
                         ["feed_not_a_feed"])
        self.assertEqual(report["verdict"], "1 stale signal")

    def test_malformed_xml_is_not_a_feed(self):
        # The Felix Rieseberg failure shape: unclosed CDATA section.
        report = check(make_pack(), returning(("https://a/", MALFORMED)))
        self.assertEqual(report["sources"][0]["feed"]["status"],
                         "not_a_feed")

    def test_http_error(self):
        fetch = raising(HTTPError("https://a/", 404, "Not Found", {}, None))
        report = check(make_pack(), fetch)
        src = report["sources"][0]
        self.assertEqual(src["feed"]["status"], "http_error")
        self.assertEqual(src["feed"]["error"], "HTTP 404")
        self.assertEqual([s["kind"] for s in src["signals"]],
                         ["feed_http_error"])
        self.assertEqual(report["verdict"], "1 stale signal")

    def test_unreachable_only_source_is_unverifiable(self):
        # Nothing answered at all: unreachability describes our vantage
        # point, so it is a status, not a stale signal.
        fetch = raising(URLError("Name or service not known"))
        report = check(make_pack(), fetch)
        src = report["sources"][0]
        self.assertEqual(src["feed"]["status"], "unreachable")
        self.assertEqual(src["signals"], [])
        self.assertEqual(report["verdict"], "unverifiable from here")

    def test_unreachable_signals_when_another_probe_answers(self):
        bob = make_source(id="bob", name="Bob Example",
                          feed_url="https://bob.example.com/feed",
                          homepage="https://bob.example.com/")
        fetch = routed({
            "https://alice.example.com/feed":
                URLError("Connection reset by peer"),
            "https://bob.example.com/feed": ("https://b/", RSS_OCT, False)})
        report = check(make_pack([make_source(), bob]), fetch)
        alice = report["sources"][0]
        self.assertEqual(alice["feed"]["status"], "unreachable")
        self.assertEqual([s["kind"] for s in alice["signals"]],
                         ["feed_unreachable"])
        self.assertEqual(report["verdict"], "1 stale signal")

    def test_oversized_valid_feed(self):
        # The Carlsmith failure shape: a real feed over the 2 MB cap.
        fetch = returning(("https://a/", FEED_PREFIX, True))
        report = check(make_pack(), fetch)
        src = report["sources"][0]
        self.assertEqual(src["feed"]["status"], "oversized")
        self.assertEqual([s["kind"] for s in src["signals"]],
                         ["feed_oversized"])
        self.assertEqual(report["verdict"], "1 stale signal")

    def test_oversized_non_feed_is_not_a_feed(self):
        fetch = returning(("https://a/", HTML, True))
        report = check(make_pack(), fetch)
        self.assertEqual(report["sources"][0]["feed"]["status"],
                         "not_a_feed")

    def test_oversized_by_body_length_two_tuple(self):
        big = FEED_PREFIX + b"x" * 2_100_000
        report = check(make_pack(), returning(("https://a/", big)))
        self.assertEqual(report["sources"][0]["feed"]["status"],
                         "oversized")

    def test_oversized_via_bounded_fetch_contract(self):
        # An injected fetch with _bounded_fetch's raising contract.
        fetch = raising(ValueError("response exceeds 2 MB"))
        report = check(make_pack(), fetch)
        self.assertEqual(report["sources"][0]["feed"]["status"],
                         "oversized")

    def test_no_feed_source_is_unverifiable(self):
        src = make_source(type="blog", feed_url=None)
        report = check(make_pack([src]), returning(("https://a/", RSS_OCT)))
        self.assertEqual(report["sources"][0]["feed"]["status"], "no_feed")
        self.assertEqual(report["verdict"], "unverifiable from here")


class FreshnessSignalTests(unittest.TestCase):
    def test_newer_items_flagged(self):
        report = check(make_pack(), returning(("https://a/", RSS_NOV, False)))
        src = report["sources"][0]
        self.assertEqual([s["kind"] for s in src["signals"]],
                         ["newer_items"])
        self.assertIn("2026-11-16", src["signals"][0]["detail"])
        self.assertEqual(report["verdict"], "1 stale signal")

    def test_newer_items_when_no_recorded_date(self):
        src = make_source(last_post_at=None)
        report = check(make_pack([src]),
                       returning(("https://a/", RSS_OCT, False)))
        self.assertEqual([s["kind"] for s in report["sources"][0]["signals"]],
                         ["newer_items"])

    def test_recorded_newer_than_feed_is_mismatch(self):
        src = make_source(last_post_at="2026-11-16")
        report = check(make_pack([src]),
                       returning(("https://a/", RSS_OCT, False)))
        self.assertEqual([s["kind"] for s in report["sources"][0]["signals"]],
                         ["newest_mismatch"])

    def test_verified_at_aging_pack_and_source(self):
        pack = make_pack([make_source(verified_at="2026-01-01")],
                         verified_at="2026-01-01")
        report = check(pack, returning(("https://a/", RSS_OCT, False)))
        self.assertEqual(report["pack"]["verified_age_days"], 320)
        self.assertEqual([s["kind"] for s in report["signals"]],
                         ["verification_stale"])
        src = report["sources"][0]
        self.assertEqual(src["verified_age_days"], 320)
        self.assertEqual([s["kind"] for s in src["signals"]],
                         ["verification_stale"])
        self.assertEqual(report["stale_signals"], 2)
        self.assertEqual(report["verdict"], "2 stale signals")

    def test_fresh_verified_at_reports_age_without_signal(self):
        report = check(make_pack(), returning(("https://a/", RSS_OCT, False)))
        self.assertEqual(report["pack"]["verified_age_days"], 0)
        self.assertEqual(report["signals"], [])

    def test_disabled_source_dead_feed_is_not_a_signal(self):
        # Disabled already prices in the feed's state; only the status
        # is reported.
        src = make_source(enabled=False)
        fetch = raising(HTTPError("https://a/", 404, "Not Found", {}, None))
        report = check(make_pack([src]), fetch)
        self.assertEqual(report["sources"][0]["feed"]["status"],
                         "http_error")
        self.assertEqual(report["sources"][0]["signals"], [])
        self.assertEqual(report["verdict"], "current")

    def test_disabled_source_resumed_activity_signals(self):
        src = make_source(enabled=False)
        report = check(make_pack([src]),
                       returning(("https://a/", RSS_NOV, False)))
        self.assertEqual([s["kind"] for s in report["sources"][0]["signals"]],
                         ["newer_items"])


class ReportShapeTests(unittest.TestCase):
    def test_installed_state_from_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "sources.yaml"
            config.write_text("version: 1\n", encoding="utf-8")
            (root / "packs-installed.json").write_text(json.dumps(
                {"packs": [{"pack_id": "test-pack", "version": "0.9.0",
                            "installed_at": "2026-11-01T00:00:00Z"}]}),
                encoding="utf-8")
            report = check(make_pack(),
                           returning(("https://a/", RSS_OCT, False)),
                           config_path=config)
        self.assertTrue(report["installed"]["installed"])
        self.assertEqual(report["installed"]["installed_version"], "0.9.0")
        self.assertTrue(report["installed"]["update_available"])

    def test_format_refresh_renders_verdict(self):
        report = check(make_pack(), returning(("https://a/", RSS_NOV, False)))
        text = format_refresh(report)
        self.assertIn("verdict: 1 stale signal", text)
        self.assertIn("newer_items", text)

    def test_bundled_covers_shipped_packs(self):
        report = refresh_check_bundled(
            fetch=returning(("https://a/", RSS_OCT, False)), today=TODAY)
        self.assertEqual(report["checked_at"], "2026-11-17")
        by_id = {p["pack"]["id"]: p for p in report["packs"]
                 if not p.get("error")}
        self.assertIn("anthropic-personal-blogs", by_id)
        for item in by_id.values():
            self.assertTrue(item["sources"])
            if item["stale_signals"] == 0:
                self.assertIn(item["verdict"],
                              ("current", "unverifiable from here"))
            else:
                self.assertTrue(
                    item["verdict"].startswith(
                        f"{item['stale_signals']} stale signal")
                    or item["verdict"] == "unverifiable from here")

    def test_invalid_pack_raises(self):
        with self.assertRaises(ValueError):
            check({"id": "x"}, returning(("https://a/", RSS_OCT)))


class ReportOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in sorted(self.root.rglob("*")) if p.is_file()}

    def test_refresh_check_writes_nothing(self):
        pack_path = self.root / "pack.json"
        pack_path.write_text(json.dumps(make_pack()), encoding="utf-8")
        config = self.root / "sources.yaml"
        config.write_text("version: 1\n", encoding="utf-8")
        (self.root / "packs-installed.json").write_text(
            json.dumps({"packs": []}), encoding="utf-8")
        before = self._snapshot()
        fetch = returning(("https://a/", RSS_NOV, False))
        refresh_check(make_pack(), config, fetch=fetch, today=TODAY)
        with mock.patch.object(packs_module, "_bounded_fetch_prefix",
                               fetch):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = pack_main(["refresh-check", str(pack_path),
                                "--config", str(config), "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(self._snapshot(), before)

    def test_bundled_run_leaves_pack_files_byte_identical(self):
        def digest():
            return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(PACKS_DIR.glob("*.json"))}
        before = digest()
        refresh_check_bundled(fetch=returning(("https://a/", RSS_OCT, False)),
                              today=TODAY)
        self.assertEqual(digest(), before)


class CliTests(unittest.TestCase):
    def test_cli_single_pack_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack_path = Path(tmp) / "pack.json"
            pack_path.write_text(json.dumps(make_pack()), encoding="utf-8")
            config = Path(tmp) / "sources.yaml"
            config.write_text("version: 1\n", encoding="utf-8")
            fetch = returning(("https://a/", RSS_NOV, False))
            with mock.patch.object(packs_module, "_bounded_fetch_prefix",
                                   fetch):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    rc = pack_main(["refresh-check", str(pack_path),
                                    "--config", str(config), "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["pack"]["id"], "test-pack")
        self.assertEqual(payload["verdict"], "1 stale signal")

    def test_cli_single_pack_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack_path = Path(tmp) / "pack.json"
            pack_path.write_text(json.dumps(make_pack()), encoding="utf-8")
            config = Path(tmp) / "sources.yaml"
            config.write_text("version: 1\n", encoding="utf-8")
            fetch = returning(("https://a/", RSS_OCT, False))
            with mock.patch.object(packs_module, "_bounded_fetch_prefix",
                                   fetch):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    rc = pack_main(["refresh-check", str(pack_path),
                                    "--config", str(config)])
        self.assertEqual(rc, 0)
        self.assertIn("verdict: current", out.getvalue())

    def test_cli_bundled_json(self):
        fetch = returning(("https://a/", RSS_OCT, False))
        with mock.patch.object(packs_module, "_bounded_fetch_prefix", fetch):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = pack_main(["refresh-check", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        ids = [p.get("pack", {}).get("id") for p in payload["packs"]]
        self.assertIn("anthropic-personal-blogs", ids)


if __name__ == "__main__":
    unittest.main()
