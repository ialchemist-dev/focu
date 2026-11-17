"""Pack-freshness constant validation: the rot-history harness.

Plan-4 direction 2 (pm-plan-3-closeout.md section 4.2), run under the
wave-25 rule: a constant stands unless a named fixture built from
real evidence fails against it. The fixtures below are encoded from
the run's RECORDED history — the shipped packs' own coverage and
readiness fields — not invented scenarios:

* The Anthropic rot event. The pack (site v0.1.0 / focu v1.0.0) was
  verified 2026-10-28, pack and sources alike. The 2026-11-17
  re-check — age 20 days — found three feeds rotten, recorded in
  focu/source_packs/anthropic-personal-blogs.json (v1.1.0 coverage):
  Felix Rieseberg's feed malformed (73 '<![CDATA[' opens vs 72
  ']]>' closes, one unclosed CDATA section), Chris Olah's feed
  answering HTTP 404, Joe Carlsmith's feed grown to ~2.87 MB, over
  the 2 MB fetch cap. Every affiliation was re-checked at the same
  pass and held.
* The geothermal pack's recorded states (observed 2026-11-17):
  EGEC's feed URL intermittently answers with an HTML interstitial
  although the feed is healthy; IGA is listed disabled with its
  declared feed's newest item 2025-09-01 while the site lives;
  Baseload Capital's host dropped connections in two full validator
  runs while succeeding in standalone fetches; DEEP's feed is live
  but dormant (newest item 2025-09-25).
* The Silicon Valley pack's PostHog entry: a live feed measured at
  3,296,701 bytes — over the fetch cap — on a source listed
  disabled, so its state is already priced into the pack.

Verdicts this harness records (see ConstantVerdictTests):
REFRESH_DUE_PACK_DAYS = 14 STANDS — the recorded rot was present by
day 20 and the pack rule trips at day 15, before the discovery date;
any value >= 20 would have missed the run's one real rot event.
REFRESH_DUE_SOURCE_DAYS = 30 STANDS, unrefuted and undiscriminated:
in the one aged pack, sources and pack shared a verification date
and the pack rule tripped first; recorded history contains no
mixed-age pack, so this rule is pinned mechanically (boundary
fixtures), not validated by a rot case. AFFILIATION_STALE_DAYS = 90
STANDS — at age 20 every recorded affiliation in fact held, so the
section correctly stayed empty; the run's affiliation changes
(Karpathy's move, Weng's departure-and-return) were all caught by
research acts, never by age, which is why the section is advisory.
STALE_DAYS = 180 STANDS (the wave-29 recorded non-change,
re-validated) — at the day-20 rot event the age signal correctly did
NOT fire: the three feed signals carried the verdict precisely, and
an age threshold <= 20 would only have double-reported them.

No network: every fetch is a fixture. All surfaces stay read-only;
byte-identity is asserted around the runs.
"""
import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError

import focu.packs as packs_module
from focu.packs import (AFFILIATION_STALE_DAYS, PACKS_DIR,
                        REFRESH_DUE_PACK_DAYS, REFRESH_DUE_SOURCE_DAYS,
                        STALE_DAYS, refresh_check, refresh_due)

DISCOVERY = date(2026, 11, 17)   # the day the recorded rot was found


def rss(pubdate):
    return (b'<?xml version="1.0" encoding="UTF-8"?>\n'
            b'<rss version="2.0"><channel><title>Example</title>'
            b'<item><title>Post</title>'
            b'<link>https://example.com/post</link>'
            b'<pubDate>' + pubdate.encode() + b'</pubDate></item>'
            b'</channel></rss>')


# The Felix Rieseberg failure shape, as recorded: an RSS document
# whose CDATA section is never closed, so the parser rejects it.
MALFORMED_CDATA = (b'<?xml version="1.0"?><rss version="2.0"><channel>'
                   b'<item><title><![CDATA[never closed</title></item>')
# The EGEC failure shape: an HTML page where the feed should be.
HTML_INTERSTITIAL = (b"<html><head><title>Interstitial</title></head>"
                     b"<body>Checking your browser</body></html>")
# A real feed document's opening, for over-cap responses (the
# Carlsmith / PostHog shape: valid feed, too many bytes).
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


def routed(routes):
    def fetch(url):
        outcome = routes[url]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    return fetch


# ---------------------------------------------------------------------------
# The Anthropic rot event, encoded as recorded. Pack and sources carry
# their v1.0.0 verification date (2026-10-28, per the site pack file);
# probe outcomes are the ones the 2026-11-17 re-check recorded. Only
# the three rotten sources are encoded: the healthy sources'
# v1.0.0-era last_post_at values are not in the recorded history, and
# the assertions below concern exactly the recorded rot.

def anthropic_v1_pack():
    return make_pack(
        id="anthropic-personal-blogs",
        title="Anthropic · Personal blogs", version="1.0.0",
        verified_at="2026-10-28",
        sources=[
            make_source(
                id="felix", name="Felix Rieseberg",
                homepage="https://felixrieseberg.com/",
                feed_url="https://felixrieseberg.com/rss/",
                verified_at="2026-10-28", last_post_at=None),
            make_source(
                id="colah", name="Chris Olah",
                homepage="https://colah.github.io/",
                feed_url="https://colah.github.io/rss.xml",
                verified_at="2026-10-28", last_post_at="2019-05-30"),
            make_source(
                id="carlsmith", name="Joe Carlsmith",
                homepage="https://joecarlsmith.com/",
                feed_url="https://joecarlsmith.substack.com/feed",
                verified_at="2026-10-28", last_post_at="2026-04-09"),
        ])


def anthropic_rot_fetch():
    return routed({
        "https://felixrieseberg.com/rss/":
            ("https://felixrieseberg.com/rss/", MALFORMED_CDATA),
        "https://colah.github.io/rss.xml":
            HTTPError("https://colah.github.io/rss.xml", 404,
                      "Not Found", {}, None),
        "https://joecarlsmith.substack.com/feed":
            ("https://joecarlsmith.substack.com/feed", FEED_PREFIX, True),
    })


class AnthropicRotHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        path = self.dir / "anthropic-personal-blogs.json"
        path.write_text(json.dumps(anthropic_v1_pack()), encoding="utf-8")

    def due_report(self, today):
        with mock.patch.object(packs_module, "PACKS_DIR", self.dir):
            return refresh_due(today=today)

    def test_due_at_the_recorded_discovery_age(self):
        # Age 20 on 2026-11-17, with three rotten feeds in fact: the
        # pack is due, via the pack rule alone (source ages are also
        # 20, under the 30-day source rule), and the reason names the
        # constant that tripped.
        report = self.due_report(DISCOVERY)
        entry = report["packs"][0]
        self.assertTrue(entry["due"])
        self.assertEqual(entry["age_days"], 20)
        self.assertEqual([r["constant"] for r in entry["reasons"]],
                         ["REFRESH_DUE_PACK_DAYS"])
        self.assertEqual(entry["reasons"][0]["age_days"], 20)

    def test_due_first_trips_before_the_discovery_date(self):
        # Boundary pin on the recorded dates: age 14 (2026-11-11) is
        # not due; age 15 (2026-11-12) is — five days before the rot
        # was found. A pack constant of 20 or more would have missed
        # the run's one real rot event entirely.
        self.assertFalse(
            self.due_report(date(2026, 11, 11))["packs"][0]["due"])
        self.assertTrue(
            self.due_report(date(2026, 11, 12))["packs"][0]["due"])

    def test_refresh_check_reproduces_the_recorded_rot(self):
        report = refresh_check(anthropic_v1_pack(),
                               fetch=anthropic_rot_fetch(),
                               today=DISCOVERY)
        by_id = {s["id"]: s for s in report["sources"]}
        self.assertEqual(by_id["felix"]["feed"]["status"], "not_a_feed")
        self.assertEqual([s["kind"] for s in by_id["felix"]["signals"]],
                         ["feed_not_a_feed"])
        self.assertEqual(by_id["colah"]["feed"]["status"], "http_error")
        self.assertEqual(by_id["colah"]["feed"]["error"], "HTTP 404")
        self.assertEqual([s["kind"] for s in by_id["colah"]["signals"]],
                         ["feed_http_error"])
        self.assertEqual(by_id["carlsmith"]["feed"]["status"],
                         "oversized")
        self.assertEqual(
            [s["kind"] for s in by_id["carlsmith"]["signals"]],
            ["feed_oversized"])
        self.assertEqual(report["stale_signals"], 3)
        self.assertEqual(report["verdict"], "3 stale signals")
        # STALE_DAYS re-validated on recorded evidence: at age 20 the
        # verification-age signal does NOT fire, at pack or source
        # level — the feed signals carry the verdict precisely.
        self.assertEqual(report["signals"], [])
        for src in report["sources"]:
            self.assertEqual(src["verified_age_days"], 20)
            self.assertNotIn("verification_stale",
                             [s["kind"] for s in src["signals"]])
        # AFFILIATION_STALE_DAYS on recorded evidence: every
        # affiliation in this pack was re-checked on 2026-11-17 and
        # held, and the advisory section correctly stays empty at
        # age 20.
        self.assertEqual(report["affiliation"], [])

    def test_rot_history_runs_write_nothing(self):
        config = self.dir / "sources.yaml"
        config.write_text("version: 1\n", encoding="utf-8")
        before = {p.name: p.read_bytes()
                  for p in sorted(self.dir.iterdir())}
        refresh_check(anthropic_v1_pack(), config,
                      fetch=anthropic_rot_fetch(), today=DISCOVERY)
        self.due_report(DISCOVERY)
        after = {p.name: p.read_bytes()
                 for p in sorted(self.dir.iterdir())}
        self.assertEqual(after, before)


# ---------------------------------------------------------------------------
# The geothermal pack's recorded states, observed 2026-11-17 (pack age
# 0). Fixture URLs are stand-ins; the recorded content is each source's
# state, dates, and probe outcome.

def geothermal_pack():
    def src(**kw):
        base = {"channel": "research", "verified_at": "2026-11-17"}
        base.update(kw)
        return make_source(**base)
    return make_pack(
        id="geothermal-industry", title="Geothermal Industry",
        verified_at="2026-11-17",
        sources=[
            src(id="thinkgeoenergy", name="ThinkGeoEnergy",
                feed_url="https://thinkgeoenergy.example/feed",
                homepage="https://thinkgeoenergy.example/",
                last_post_at="2026-11-16"),
            src(id="egec", name="EGEC",
                feed_url="https://egec.example/feed",
                homepage="https://egec.example/",
                last_post_at="2026-10-29"),
            src(id="baseload", name="Baseload Capital",
                feed_url="https://baseload.example/feed",
                homepage="https://baseload.example/",
                last_post_at="2026-08-19"),
            src(id="deep", name="DEEP Earth Energy",
                feed_url="https://deep.example/feed",
                homepage="https://deep.example/",
                last_post_at="2025-09-25"),
            src(id="iga", name="IGA", enabled=False,
                feed_url="https://iga.example/feed",
                homepage="https://iga.example/",
                last_post_at="2025-09-01"),
        ])


def geothermal_fetch(egec_outcome):
    return routed({
        "https://thinkgeoenergy.example/feed":
            ("https://t/", rss("Mon, 16 Nov 2026 07:00:00 GMT")),
        "https://egec.example/feed": egec_outcome,
        "https://baseload.example/feed":
            URLError("Connection reset by peer"),
        "https://deep.example/feed":
            ("https://d/", rss("Thu, 25 Sep 2025 07:00:00 GMT")),
        "https://iga.example/feed":
            ("https://i/", rss("Mon, 01 Sep 2025 07:00:00 GMT")),
    })


class GeothermalRecordedStateTests(unittest.TestCase):
    def by_id(self, report):
        return {s["id"]: s for s in report["sources"]}

    def test_interstitial_outcome_signals_not_a_feed(self):
        # One of EGEC's two recorded outcomes: the feed URL answers
        # with an HTML interstitial. The surface reports it as
        # not_a_feed on an enabled source; Baseload's recorded
        # unreachable outcome signals because other probes answered;
        # the dormant and priced-in sources stay silent.
        fetch = geothermal_fetch(
            ("https://e/", HTML_INTERSTITIAL))
        report = refresh_check(geothermal_pack(), fetch=fetch,
                               today=DISCOVERY)
        by_id = self.by_id(report)
        self.assertEqual(by_id["egec"]["feed"]["status"], "not_a_feed")
        self.assertEqual([s["kind"] for s in by_id["egec"]["signals"]],
                         ["feed_not_a_feed"])
        self.assertEqual(by_id["baseload"]["feed"]["status"],
                         "unreachable")
        self.assertEqual(
            [s["kind"] for s in by_id["baseload"]["signals"]],
            ["feed_unreachable"])
        self.assertEqual(by_id["thinkgeoenergy"]["signals"], [])
        # DEEP: live but dormant — newest equals the recorded date,
        # so dormancy stays priced into the record, not a signal.
        self.assertEqual(by_id["deep"]["feed"]["status"], "live")
        self.assertEqual(by_id["deep"]["signals"], [])
        # IGA: disabled, declared feed's newest item (2025-09-01,
        # 442 days before the observation) equals its record — the
        # feed-content staleness of a disabled source fires nothing,
        # and no verification-age signal fires at age 0 either.
        self.assertEqual(by_id["iga"]["feed"]["status"], "live")
        self.assertEqual(by_id["iga"]["signals"], [])
        self.assertEqual(report["verdict"], "2 stale signals")

    def test_clean_outcome_clears_egec(self):
        # EGEC's other recorded outcome: the same URL parses cleanly.
        # The surface distinguishes the two recorded outcomes of one
        # URL — the interstitial is a probe outcome, not a pack fact.
        fetch = geothermal_fetch(
            ("https://e/", rss("Thu, 29 Oct 2026 07:00:00 GMT")))
        report = refresh_check(geothermal_pack(), fetch=fetch,
                               today=DISCOVERY)
        by_id = self.by_id(report)
        self.assertEqual(by_id["egec"]["feed"]["status"], "live")
        self.assertEqual(by_id["egec"]["signals"], [])
        self.assertEqual(report["verdict"], "1 stale signal")

    def test_all_unreachable_is_unverifiable(self):
        # Baseload's recorded flakiness, generalized to the vantage
        # rule: when nothing answers, unreachability describes our
        # vantage point, not the pack — no source signals.
        def fetch(url):
            raise URLError("Connection reset by peer")
        report = refresh_check(geothermal_pack(), fetch=fetch,
                               today=DISCOVERY)
        self.assertEqual(report["verdict"], "unverifiable from here")
        for src in report["sources"]:
            self.assertEqual(src["signals"], [])


class SiliconValleyRecordedStateTests(unittest.TestCase):
    def test_posthog_oversized_but_disabled_is_priced_in(self):
        # Recorded: PostHog's feed measured 3,296,701 bytes (265
        # items) on 2026-11-17, over the fetch cap, on a source
        # listed disabled. The probe reports the oversized status;
        # the disabled state prices it in — no signal, clean verdict.
        # Contrast the Anthropic fixture: Carlsmith's oversized feed
        # is on an ENABLED source and does signal.
        posthog = make_source(
            id="posthog", name="PostHog", enabled=False,
            homepage="https://posthog.example.com/",
            feed_url="https://posthog.example.com/feed",
            verified_at="2026-11-17", last_post_at="2026-11-12")
        pack = make_pack(id="silicon-valley-startups",
                         title="Silicon Valley Startups",
                         sources=[posthog], verified_at="2026-11-17")
        fetch = routed({"https://posthog.example.com/feed":
                        ("https://p/", FEED_PREFIX, True)})
        report = refresh_check(pack, fetch=fetch, today=DISCOVERY)
        src = report["sources"][0]
        self.assertEqual(src["feed"]["status"], "oversized")
        self.assertEqual(src["signals"], [])
        self.assertEqual(report["verdict"], "current")


class FreshShelfTests(unittest.TestCase):
    """The closeout's negative case, on the shipped packs' recorded
    verification dates (all 2026-11-17): freshly verified packs trip
    nothing, and the shelf turns due only when the pack rule's age
    passes — by arithmetic on recorded dates, not new scenarios."""

    def test_age_13_nothing_due(self):
        report = refresh_due(today=date(2026, 11, 30))
        self.assertEqual(report["due_count"], 0)
        self.assertEqual(report["not_due_count"], 5)

    def test_age_15_whole_shelf_due_via_pack_rule(self):
        report = refresh_due(today=date(2026, 12, 2))
        self.assertEqual(report["due_count"], 5)
        for entry in report["packs"]:
            self.assertEqual([r["constant"] for r in entry["reasons"]],
                             ["REFRESH_DUE_PACK_DAYS"])

    def test_due_report_leaves_shipped_packs_byte_identical(self):
        def digest():
            return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(PACKS_DIR.glob("*.json"))}
        before = digest()
        refresh_due(today=DISCOVERY)
        refresh_due(today=date(2026, 12, 2))
        self.assertEqual(digest(), before)


# ---------------------------------------------------------------------------
# Mechanical boundary pins. Recorded history does not discriminate
# these three constants (see the module docstring), so their exact
# trip points are pinned the way wave 29 pinned its boundaries —
# labelled mechanical, not evidence.

class ConstantBoundaryPinTests(unittest.TestCase):
    def due_report(self, pack):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        (directory / "pack.json").write_text(
            json.dumps(pack), encoding="utf-8")
        with mock.patch.object(packs_module, "PACKS_DIR", directory):
            return refresh_due(today=DISCOVERY)

    def test_source_rule_boundary_30_31(self):
        # A pack re-verified today whose stalest source kept an older
        # verification (the partial-refresh shape): age 30 is not
        # due, age 31 is, and the reason names the source and the
        # constant.
        fresh_pack = {"verified_at": "2026-11-17"}
        at_30 = make_pack(sources=[make_source(verified_at="2026-10-18")],
                          **fresh_pack)
        entry = self.due_report(at_30)["packs"][0]
        self.assertFalse(entry["due"])
        at_31 = make_pack(sources=[make_source(verified_at="2026-10-17")],
                          **fresh_pack)
        entry = self.due_report(at_31)["packs"][0]
        self.assertTrue(entry["due"])
        self.assertEqual([r["constant"] for r in entry["reasons"]],
                         ["REFRESH_DUE_SOURCE_DAYS"])
        self.assertEqual(entry["reasons"][0]["source_id"], "alice")
        self.assertEqual(entry["reasons"][0]["age_days"], 31)

    def test_affiliation_boundary_90_91(self):
        def affiliation_for(verified_at):
            pack = make_pack(
                sources=[make_source(verified_at=verified_at)])
            fetch = routed({"https://alice.example.com/feed":
                            ("https://a/", rss(
                                "Mon, 12 Oct 2026 07:00:00 GMT"))})
            return refresh_check(pack, fetch=fetch,
                                 today=DISCOVERY)["affiliation"]
        self.assertEqual(affiliation_for("2026-08-19"), [])   # age 90
        entries = affiliation_for("2026-08-18")               # age 91
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["age_days"], 91)

    def test_stale_days_boundary_180_181(self):
        def signals_for(verified_at):
            pack = make_pack(
                sources=[make_source(verified_at=verified_at)],
                verified_at=verified_at)
            fetch = routed({"https://alice.example.com/feed":
                            ("https://a/", rss(
                                "Mon, 12 Oct 2026 07:00:00 GMT"))})
            report = refresh_check(pack, fetch=fetch, today=DISCOVERY)
            kinds = [s["kind"] for s in report["signals"]]
            kinds += [s["kind"] for s in report["sources"][0]["signals"]]
            return kinds
        self.assertNotIn("verification_stale",
                         signals_for("2026-05-21"))   # age 180
        self.assertEqual(signals_for("2026-05-20"),   # age 181
                         ["verification_stale", "verification_stale"])


class ConstantVerdictTests(unittest.TestCase):
    """The constants stand at their wave-29 values: no fixture in
    this harness — recorded or boundary — fails against them, so
    none moves. These pins make a future silent retune a deliberate,
    test-breaking act that must cite new evidence."""

    def test_constants_stand(self):
        self.assertEqual(REFRESH_DUE_PACK_DAYS, 14)
        self.assertEqual(REFRESH_DUE_SOURCE_DAYS, 30)
        self.assertEqual(AFFILIATION_STALE_DAYS, 90)
        self.assertEqual(STALE_DAYS, 180)


if __name__ == "__main__":
    unittest.main()
