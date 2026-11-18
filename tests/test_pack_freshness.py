"""Pack freshness ownership (wave 29): refresh-due, affiliation-as-of,
and the attention-totals pin.

Covers the cadence owner for pack freshness: `refresh_due` (pure date
arithmetic over the bundled packs — due under REFRESH_DUE_PACK_DAYS /
REFRESH_DUE_SOURCE_DAYS, reasons naming the tripped constant),
refresh-check's affiliation section (sources whose affiliation
evidence is older than AFFILIATION_STALE_DAYS, computed from pack data
with zero additional fetches, advisory only — never a stale signal),
`focu pack show`'s per-source affiliation-as-of date, and one test
pinning that the three attention accumulators (catalog/show's
_attention_total, the install plan, the update plan) agree exactly
for every shipped pack. STALE_DAYS staying 180 is pinned as the
recorded non-change. No network: every fetch is a fixture.
"""
import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import focu.packs as packs_module
from focu.packs import (AFFILIATION_STALE_DAYS, PACKS_DIR,
                        REFRESH_DUE_PACK_DAYS, REFRESH_DUE_SOURCE_DAYS,
                        STALE_DAYS, _affiliation_as_of, _attention_total,
                        format_refresh, format_refresh_due, format_show,
                        install_pack, pack_catalog, refresh_check,
                        refresh_due, show_pack, update_pack, validate_pack)
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


def bob_source(**overrides):
    source = make_source(id="bob", name="Bob Example",
                         homepage="https://bob.example.com/",
                         feed_url="https://bob.example.com/feed")
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


class FixedDate(date):
    """date.today() pinned to TODAY, for CLI runs of refresh-due."""

    @classmethod
    def today(cls):
        return TODAY


class RefreshDueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def write_pack(self, pack, filename):
        path = self.dir / filename
        path.write_text(json.dumps(pack), encoding="utf-8")
        return path

    def due_report(self, packs):
        for filename, pack in packs.items():
            self.write_pack(pack, filename)
        with mock.patch.object(packs_module, "PACKS_DIR", self.dir):
            return refresh_due(today=TODAY)

    def test_shipped_packs_none_due_on_verification_day(self):
        # Acceptance 1: the five shipped packs were all verified
        # 2026-11-17, so on that day nothing is due and the not-due
        # count is the whole shelf.
        report = refresh_due(today=TODAY)
        self.assertEqual(report["checked_at"], "2026-11-17")
        self.assertEqual(report["due_count"], 0)
        self.assertEqual(report["not_due_count"], 5)
        self.assertEqual(len(report["packs"]), 5)
        for entry in report["packs"]:
            self.assertNotIn("error", entry)
            self.assertFalse(entry["due"])
            self.assertEqual(entry["age_days"], 0)
            self.assertEqual(entry["reasons"], [])
        text = format_refresh_due(report)
        self.assertIn("0 due; 5 not due", text)
        self.assertNotIn("DUE", text)

    def test_pack_age_trips_pack_constant(self):
        # verified_at 2026-10-28 is 20 days before TODAY: past the
        # 14-day pack threshold, sources fresh, so only the pack
        # constant trips and the reason names it.
        old = make_pack(id="old-pack", title="Old Pack",
                        verified_at="2026-10-28")
        fresh = make_pack(id="fresh-pack", title="Fresh Pack")
        report = self.due_report({"old.json": old, "fresh.json": fresh})
        self.assertEqual(report["due_count"], 1)
        self.assertEqual(report["not_due_count"], 1)
        by_id = {e["id"]: e for e in report["packs"]}
        entry = by_id["old-pack"]
        self.assertTrue(entry["due"])
        self.assertEqual(entry["age_days"], 20)
        self.assertEqual(len(entry["reasons"]), 1)
        reason = entry["reasons"][0]
        self.assertEqual(reason["kind"], "pack_stale")
        self.assertEqual(reason["constant"], "REFRESH_DUE_PACK_DAYS")
        self.assertEqual(reason["age_days"], 20)
        self.assertFalse(by_id["fresh-pack"]["due"])
        text = format_refresh_due(report)
        self.assertIn("old-pack", text)
        self.assertIn("20 days old", text)
        self.assertIn("1 due; 1 not due", text)
        self.assertNotIn("fresh-pack", text)

    def test_stalest_source_trips_source_constant_and_is_named(self):
        # Pack itself verified today; two sources are past the 30-day
        # source threshold (40 and 51 days) — the reason names the
        # stalest one.
        pack = make_pack(
            id="people-pack", title="People Pack",
            sources=[make_source(verified_at="2026-10-08"),
                     bob_source(verified_at="2026-09-27")])
        report = self.due_report({"people.json": pack})
        entry = report["packs"][0]
        self.assertTrue(entry["due"])
        self.assertEqual(entry["age_days"], 0)
        self.assertEqual(len(entry["reasons"]), 1)
        reason = entry["reasons"][0]
        self.assertEqual(reason["kind"], "source_stale")
        self.assertEqual(reason["constant"], "REFRESH_DUE_SOURCE_DAYS")
        self.assertEqual(reason["source_id"], "bob")
        self.assertEqual(reason["source"], "Bob Example")
        self.assertEqual(reason["age_days"], 51)
        self.assertIn("Bob Example", format_refresh_due(report))

    def test_exactly_at_threshold_is_not_due(self):
        # The rule is strictly older-than: a pack exactly
        # REFRESH_DUE_PACK_DAYS old with a source exactly
        # REFRESH_DUE_SOURCE_DAYS old is not due.
        pack = make_pack(verified_at="2026-11-03",
                         sources=[make_source(verified_at="2026-10-18")])
        report = self.due_report({"edge.json": pack})
        entry = report["packs"][0]
        self.assertEqual(entry["age_days"], REFRESH_DUE_PACK_DAYS)
        self.assertEqual(entry["stalest_source"]["age_days"],
                         REFRESH_DUE_SOURCE_DAYS)
        self.assertFalse(entry["due"])
        self.assertEqual(report["not_due_count"], 1)

    def test_cli_lists_due_pack_and_counts(self):
        old = make_pack(id="old-pack", title="Old Pack",
                        verified_at="2026-10-28")
        fresh = make_pack(id="fresh-pack", title="Fresh Pack")
        self.write_pack(old, "old.json")
        self.write_pack(fresh, "fresh.json")
        with mock.patch.object(packs_module, "PACKS_DIR", self.dir), \
                mock.patch.object(packs_module, "date", FixedDate):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = pack_main(["refresh-due"])
        self.assertEqual(rc, 0)
        text = out.getvalue()
        self.assertIn("old-pack", text)
        self.assertIn("DUE", text)
        self.assertIn("1 due; 1 not due", text)
        with mock.patch.object(packs_module, "PACKS_DIR", self.dir), \
                mock.patch.object(packs_module, "date", FixedDate):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = pack_main(["refresh-due", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["due_count"], 1)
        self.assertEqual(payload["not_due_count"], 1)
        by_id = {p["id"]: p for p in payload["packs"]}
        reason = by_id["old-pack"]["reasons"][0]
        self.assertEqual(reason["constant"], "REFRESH_DUE_PACK_DAYS")


class AffiliationSectionTests(unittest.TestCase):
    def counting_fetch(self, result):
        calls = []

        def fetch(url):
            calls.append(url)
            return result
        return fetch, calls

    def test_old_affiliation_listed_with_date_and_no_extra_fetches(self):
        # Alice's affiliation evidence is 100 days old (> 90); Bob's
        # is fresh. Both feeds answer live and match their records, so
        # nothing else can signal — and the fetch count is exactly one
        # probe per feed, proving the section added zero network calls.
        pack = make_pack([make_source(verified_at="2026-08-09"),
                          bob_source()])
        fetch, calls = self.counting_fetch(("https://a/", RSS_OCT, False))
        report = refresh_check(pack, fetch=fetch, today=TODAY)
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            report["affiliation"],
            [{"id": "alice", "name": "Alice Example",
              "verified_at": "2026-08-09", "age_days": 100,
              "inherited": False}])
        # Advisory only: the affiliation section is not a stale signal
        # and does not move the verdict.
        self.assertEqual(report["stale_signals"], 0)
        self.assertEqual(report["verdict"], "current")
        text = format_refresh(report)
        self.assertIn("affiliation — evidence older than "
                      f"{AFFILIATION_STALE_DAYS} days", text)
        self.assertIn("Alice Example: verified 2026-08-09 "
                      "(100 days ago)", text)
        self.assertIn("not an automated one", text)

    def test_exactly_at_threshold_is_not_listed(self):
        pack = make_pack([make_source(verified_at="2026-08-19")])
        fetch, _calls = self.counting_fetch(("https://a/", RSS_OCT, False))
        report = refresh_check(pack, fetch=fetch, today=TODAY)
        self.assertEqual(report["sources"][0]["verified_age_days"],
                         AFFILIATION_STALE_DAYS)
        self.assertEqual(report["affiliation"], [])
        self.assertNotIn("affiliation —", format_refresh(report))

    def test_fresh_pack_has_empty_affiliation_section(self):
        fetch, calls = self.counting_fetch(("https://a/", RSS_OCT, False))
        report = refresh_check(make_pack(), fetch=fetch, today=TODAY)
        self.assertEqual(report["affiliation"], [])
        self.assertEqual(len(calls), 1)


class ShowAffiliationTests(unittest.TestCase):
    def test_show_reports_each_sources_own_date(self):
        report = show_pack(make_pack(), check_feeds=False, today=TODAY)
        src = report["sources"][0]
        self.assertEqual(src["affiliation_as_of"], "2026-11-17")
        self.assertFalse(src["affiliation_inherited"])
        self.assertIn("affiliation as of 2026-11-17]",
                      format_show(report))

    def test_show_shipped_people_pack_dates(self):
        raw = json.loads((PACKS_DIR / "anthropic-personal-blogs.json")
                         .read_text(encoding="utf-8"))
        report = show_pack(raw, check_feeds=False, today=TODAY)
        self.assertEqual(len(report["sources"]), 11)
        for src in report["sources"]:
            self.assertEqual(src["affiliation_as_of"],
                             src["verified_at"])
            self.assertFalse(src["affiliation_inherited"])
        text = format_show(report)
        for src in report["sources"]:
            self.assertIn(f"- {src['name']} ", text)
        self.assertIn("affiliation as of 2026-11-17]", text)

    def test_inherited_date_is_labelled_pack_level(self):
        report = show_pack(make_pack(), check_feeds=False, today=TODAY)
        report["sources"][0]["affiliation_as_of"] = "2026-10-01"
        report["sources"][0]["affiliation_inherited"] = True
        self.assertIn("affiliation as of 2026-10-01 (pack-level)]",
                      format_show(report))

    def test_affiliation_as_of_helper(self):
        self.assertEqual(
            _affiliation_as_of({"verified_at": "2026-10-01"},
                               "2026-11-17"),
            ("2026-10-01", False))
        self.assertEqual(_affiliation_as_of({}, "2026-11-17"),
                         ("2026-11-17", True))
        self.assertEqual(
            _affiliation_as_of({"verified_at": "not-a-date"},
                               "2026-11-17"),
            ("2026-11-17", True))


class AttentionTotalsPinTests(unittest.TestCase):
    """The three accumulators must agree on the same pack state.

    catalog/show read _attention_total over the pack; the install plan
    accumulates over the sources it would add (all of them, against an
    empty registry); the update plan accumulates over the sources the
    update accounts for (all of them, when the new version's sources
    are identical to the installed snapshot's). Same state, same
    enabled-source total — pinned here for every shipped pack so a
    future fourth accumulator cannot drift in silently.
    """

    CONFIG = ("version: 1\nchannels:\n  - id: research\n"
              "    name: Research Digest\nsources: []\n")

    def test_accumulators_agree_for_every_shipped_pack(self):
        paths = sorted(PACKS_DIR.glob("*.json"))
        self.assertEqual(len(paths), 5)
        for path in paths:
            raw = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(pack=path.name):
                self._check_pack(raw)

    def _check_pack(self, raw):
        report = validate_pack(raw, today=TODAY)
        self.assertTrue(report["valid"], report["errors"])
        pack = report["pack"]
        total, unknown = _attention_total(pack)
        catalog = {p["id"]: p for p in pack_catalog()["packs"]
                   if not p.get("error")}
        entry = catalog[pack["id"]]
        self.assertEqual(entry["attention_posts_per_month"], total)
        self.assertEqual(entry["attention_unknown"], unknown)
        shown = show_pack(raw, check_feeds=False, today=TODAY)
        self.assertEqual(shown["attention_posts_per_month"], total)
        self.assertEqual(shown["attention_unknown"], unknown)
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "sources.yaml"
            config.write_text(self.CONFIG, encoding="utf-8")
            installed = install_pack(raw, config, check_feeds=False,
                                     today=TODAY)
            plan = installed["plan"]
            self.assertEqual(plan["errors"], [])
            self.assertEqual(plan["attention_posts_per_month"], total)
            self.assertEqual(plan["attention_unknown"], unknown)
            bumped = copy.deepcopy(raw)
            bumped["version"] = "9.9.9"
            updated = update_pack(bumped, config, dry_run=True,
                                  check_feeds=False, today=TODAY)
            plan = updated["plan"]
            self.assertEqual(plan["errors"], [])
            self.assertEqual(plan["attention_posts_per_month"], total)
            self.assertEqual(sorted(plan["attention_unknown"]),
                             sorted(unknown))


class NonChangeTests(unittest.TestCase):
    def test_stale_days_stays_180(self):
        # Recorded non-change (wave 29 plan): feed-health signals carry
        # the weight in refresh-check; the due report above is the
        # cadence mechanism. Lowering STALE_DAYS would add warning
        # noise without detecting anything the probes don't.
        self.assertEqual(STALE_DAYS, 180)
        self.assertEqual(REFRESH_DUE_PACK_DAYS, 14)
        self.assertEqual(REFRESH_DUE_SOURCE_DAYS, 30)
        self.assertEqual(AFFILIATION_STALE_DAYS, 90)


class ReportOnlyTests(unittest.TestCase):
    def test_refresh_due_and_show_write_nothing(self):
        def digest():
            return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(PACKS_DIR.glob("*.json"))}
        before = digest()
        refresh_due(today=TODAY)
        raw = json.loads((PACKS_DIR / "anthropic-personal-blogs.json")
                         .read_text(encoding="utf-8"))
        show_pack(raw, check_feeds=False, today=TODAY)
        self.assertEqual(digest(), before)

    def test_refresh_due_cli_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack_path = root / "old.json"
            pack_path.write_text(
                json.dumps(make_pack(id="old-pack",
                                     verified_at="2026-10-28")),
                encoding="utf-8")
            before = {str(p): p.read_bytes()
                      for p in sorted(root.rglob("*")) if p.is_file()}
            with mock.patch.object(packs_module, "PACKS_DIR", root), \
                    mock.patch.object(packs_module, "date", FixedDate):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    rc = pack_main(["refresh-due", "--json"])
            self.assertEqual(rc, 0)
            after = {str(p): p.read_bytes()
                     for p in sorted(root.rglob("*")) if p.is_file()}
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
