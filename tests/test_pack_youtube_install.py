"""Wave 40: youtube-type sources through the pack system, end to end.

The four packs shipped before this wave are all rss/blog. The
followed-people pack carries four youtube sources, so it is the test
case: validate -> plan_install (identity computed by the daily
loader's own rules) -> merged registry passes load_config -> the
installed youtube sources are shaped exactly like the production
硅谷101 registration and route to the daily pipeline's youtube
collector. A registry pre-seeded with production's exact 硅谷101
entry must see the pack's copy as a duplicate, never a second
subscription.

Also pinned here: liveness treats a connection dropped mid-body
(http.client.IncompleteRead — how Ethan Mollick's host answered every
fetch on 2026-11-17) as a recorded "unreachable" outcome, never a
crash. Network results are data in focu.packs; before this wave an
IncompleteRead propagated out of check_liveness and _probe_feed.

No network: installs run with check_feeds=False; the HTTPException
tests inject raising fetches.
"""
import http.client
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from focu.daily import collectors
from focu.daily.config import load_config
from focu.daily.identity import stable_id
from focu.packs import (PACKS_DIR, _probe_feed, check_liveness,
                        install_pack)

PRODUCTION_VALLEY = {
    "name": "硅谷101", "type": "youtube", "channel": "research",
    "channel_id": "UCKV2yWPB3wn0RTZh3cTD8YA", "handle": "@TheValley101",
    "max_items_per_day": 2,
}

BASE_CONFIG = {
    "version": 1, "timezone": "America/Denver",
    "channels": [{"id": "research", "name": "Daily AI Briefing",
                  "language": "en", "max_minutes": 35,
                  "words_per_minute": 150}],
    "sources": [dict(PRODUCTION_VALLEY)],
}


def load_followed_people():
    return json.loads(
        (PACKS_DIR / "followed-people.json").read_text(encoding="utf-8"))


class YoutubePackInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Path(self.tmp.name) / "sources.yaml"
        self.config.write_text(
            yaml.safe_dump(BASE_CONFIG, allow_unicode=True, sort_keys=False),
            encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_youtube_pack_installs_and_dedupes_production_source(self):
        result = install_pack(load_followed_people(), self.config,
                              check_feeds=False)
        plan = result["plan"]
        self.assertTrue(result["applied"], plan)
        self.assertEqual(plan["errors"], [])
        # The pack's 硅谷101 resolves to production's identity: a
        # duplicate, not an add.
        dupes = {d["pack_source_id"]: d for d in plan["duplicates"]}
        self.assertIn("silicon-valley-101", dupes)
        self.assertEqual(dupes["silicon-valley-101"]["existing_name"], "硅谷101")
        valley_identity = stable_id(
            "src", "https://www.youtube.com/channel/"
            "UCKV2yWPB3wn0RTZh3cTD8YA")
        self.assertEqual(dupes["silicon-valley-101"]["source_id"],
                         valley_identity)
        added = {a["pack_source_id"] for a in plan["adds"]}
        self.assertEqual(added, {"simon-willison", "3blue1brown",
                                 "dwarkesh-patel", "lex-fridman",
                                 "wang-lufei"})

    def test_installed_youtube_sources_load_and_route_to_youtube(self):
        install_pack(load_followed_people(), self.config, check_feeds=False)
        cfg = load_config(self.config)
        by_name = {s["name"]: s for s in cfg["sources"]}
        # Production's entry is untouched and still the only 硅谷101.
        self.assertEqual(
            [n for n in by_name if n == "硅谷101"], ["硅谷101"])
        youtube = {n: s for n, s in by_name.items()
                   if s.get("type") == "youtube"}
        self.assertEqual(set(youtube), {"硅谷101", "3Blue1Brown",
                                        "Lex Fridman", "北美王路飞"})
        for name, src in youtube.items():
            # Loader identity is the channel URL, exactly as the
            # production registration computes it.
            self.assertEqual(
                src["canonical_url"],
                "https://www.youtube.com/channel/" + src["channel_id"])
            self.assertEqual(src["source_id"],
                             stable_id("src", src["canonical_url"]))
            # Collectable in principle: the daily collector routes a
            # loaded youtube source to collect_youtube.
            sentinel = object()
            original = collectors.collect_youtube
            collectors.collect_youtube = lambda source: sentinel
            try:
                self.assertIs(collectors.collect(src), sentinel)
            finally:
                collectors.collect_youtube = original


class LivenessHttpExceptionTests(unittest.TestCase):
    def test_check_liveness_records_incomplete_read_as_unreachable(self):
        def dropping_fetch(url):
            raise http.client.IncompleteRead(b"partial", 1234)
        pack = {"sources": [{
            "id": "dropped", "name": "Dropped Host", "enabled": True,
            "feed_url": "https://dropped.example.com/feed",
            "homepage": "https://dropped.example.com/"}]}
        results = check_liveness(pack, fetch=dropping_fetch)
        self.assertEqual(results["dropped"]["feed"]["status"], "unreachable")
        self.assertIn("IncompleteRead", results["dropped"]["feed"]["error"])

    def test_probe_feed_records_incomplete_read_as_unreachable(self):
        def dropping_fetch(url):
            raise http.client.IncompleteRead(b"partial", 1234)
        feed = _probe_feed("https://dropped.example.com/feed", dropping_fetch)
        self.assertEqual(feed["status"], "unreachable")
        self.assertIn("IncompleteRead", feed["error"])


if __name__ == "__main__":
    unittest.main()
