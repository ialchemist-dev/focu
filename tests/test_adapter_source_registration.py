"""Wave-17 (PM sweep F2): the Instagram, RedNote and Facebook adapter
types are registrable daily sources, so their Seam-1 units can actually
enter a briefing instead of emitting into a void.

Before this wave ``KNOWN_TYPES`` in focu/daily/config.py held only
{rss, blog, youtube, x, linkedin}: load_config rejected the three
adapter types outright, and ingest refuses any unit whose source
matches no enabled configured source. The identity fall-through in
focu/daily/identity.py already served any type carrying a
``profile_url`` (the LinkedIn pattern); these tests pin that the
whitelist extension is all it took:

- load_config accepts each adapter type with a profile_url and derives
  the registry source_id from the canonical profile URL;
- load_config rejects each adapter type with no locator at all (the
  fall-through's KeyError surfaces as a FewError, as for LinkedIn);
- a real adapter unit (built by the adapter's own build_unit) ingests
  and persists under the registry source_id;
- two different days' units for one adapter source get distinct
  content identities (the ?day= parameter survives canonicalization —
  the 2026-11-15 LinkedIn content_id lesson), while re-ingesting the
  same day's unit does not duplicate it;
- the anti-spoof guard still fires: a unit naming an unconfigured
  source, or carrying a source_id that disagrees with the registry,
  is refused and persists nothing.
"""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from focu.adapters import facebook, instagram, rednote
from focu.daily.config import load_config
from focu.daily.errors import FewError
from focu.daily.identity import canonical_url, content_identity, stable_id
from focu.daily.pipeline import ingest
from focu.daily.store import Store

DAY1 = "2026-11-16"
DAY2 = "2026-11-17"
STAMP = datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)


def _instagram_unit(day):
    post = instagram.FeedPost(
        shortcode="Cabc123", author="someone", caption="Agents all the way down",
        published=STAMP, url="https://www.instagram.com/p/Cabc123/", media="image")
    return instagram.build_unit(day, [post])


def _rednote_unit(day):
    note = rednote.Note(
        author="作者甲", url="https://www.xiaohongshu.com/explore/abc123",
        title="智能体笔记", text="一篇关于智能体的笔记正文",
        published=STAMP, collected=STAMP)
    return rednote.build_unit(day, [note])


def _facebook_unit(day):
    post = facebook.Post(
        author="Someone", url="https://www.facebook.com/someone/posts/123",
        text="A post about geothermal energy and agents",
        published=STAMP, collected=STAMP)
    return facebook.build_unit(day, [post])


SPECS = [
    {"name": "Instagram Feed", "type": "instagram",
     "profile_url": "https://www.instagram.com/", "build": _instagram_unit},
    {"name": "RedNote Feed", "type": "rednote",
     "profile_url": "https://www.xiaohongshu.com/explore", "build": _rednote_unit},
    {"name": "Facebook Feed", "type": "facebook",
     "profile_url": "https://www.facebook.com/", "build": _facebook_unit},
]


class AdapterRegistrationTests(unittest.TestCase):
    def make_env(self, sources):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        config = {"version": 2, "timezone": "UTC", "output_mode": "text_only",
                  "channels": [{"id": "research", "language": "en", "max_minutes": 12}],
                  "sources": sources}
        config_path = root / "sources.yaml"
        config_path.write_text(json.dumps(config))
        cfg = load_config(config_path)
        store = Store(root / "data")
        self.addCleanup(store.close)
        return root, cfg, store

    def source_entry(self, spec, **changes):
        entry = {"name": spec["name"], "type": spec["type"], "channel": "research",
                 "profile_url": spec["profile_url"], "max_items_per_day": 1}
        entry.update(changes)
        return entry

    def units_file(self, root, items):
        path = root / "units.json"
        path.write_text(json.dumps(items))
        return path

    def count(self, store, table):
        return store.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def test_config_accepts_adapter_type_and_derives_registry_identity(self):
        for spec in SPECS:
            with self.subTest(type=spec["type"]):
                _root, cfg, _store = self.make_env([self.source_entry(spec)])
                src = cfg["sources"][0]
                self.assertEqual(src["canonical_url"], canonical_url(spec["profile_url"]))
                self.assertEqual(src["source_id"],
                                 stable_id("src", canonical_url(spec["profile_url"])))

    def test_config_rejects_adapter_type_without_profile_url(self):
        for spec in SPECS:
            with self.subTest(type=spec["type"]):
                entry = self.source_entry(spec)
                del entry["profile_url"]
                temp = tempfile.TemporaryDirectory()
                self.addCleanup(temp.cleanup)
                config_path = Path(temp.name) / "sources.yaml"
                config = {"version": 2, "timezone": "UTC", "output_mode": "text_only",
                          "channels": [{"id": "research", "language": "en",
                                        "max_minutes": 12}],
                          "sources": [entry]}
                config_path.write_text(json.dumps(config))
                with self.assertRaisesRegex(FewError, "missing/invalid locator"):
                    load_config(config_path)

    def test_ingest_persists_adapter_unit_under_registry_source_id(self):
        for spec in SPECS:
            with self.subTest(type=spec["type"]):
                root, cfg, store = self.make_env([self.source_entry(spec)])
                unit = spec["build"](DAY1)
                report = ingest(store, cfg, DAY1, self.units_file(root, [unit]))
                self.assertEqual(report["inserted"], 1)
                source_id = cfg["sources"][0]["source_id"]
                expected_content_id = content_identity(unit, source_id)[0]
                rows = store.db.execute(
                    "SELECT source_id, content_id FROM observations").fetchall()
                self.assertEqual([(r[0], r[1]) for r in rows],
                                 [(source_id, expected_content_id)])
                self.assertEqual(self.count(store, "contents"), 1)

    def test_two_days_get_distinct_content_identities(self):
        for spec in SPECS:
            with self.subTest(type=spec["type"]):
                root, cfg, store = self.make_env([self.source_entry(spec)])
                source_id = cfg["sources"][0]["source_id"]
                unit1, unit2 = spec["build"](DAY1), spec["build"](DAY2)
                self.assertNotEqual(content_identity(unit1, source_id)[0],
                                    content_identity(unit2, source_id)[0])
                ingest(store, cfg, DAY1, self.units_file(root, [unit1]))
                ingest(store, cfg, DAY2, self.units_file(root, [unit2]))
                self.assertEqual(self.count(store, "contents"), 2)
                # Re-ingesting the same day's unit must not duplicate it:
                # the per-day identity is stable, not provisional.
                ingest(store, cfg, DAY1, self.units_file(root, [unit1]))
                self.assertEqual(self.count(store, "contents"), 2)

    def test_ingest_refuses_unit_for_unconfigured_adapter_source(self):
        # The anti-spoof guard: an "Instagram Feed" unit against a config
        # that never registered it is refused and persists nothing.
        root, cfg, store = self.make_env([
            {"name": "Test", "type": "rss", "channel": "research",
             "feed_url": "https://example.org/feed", "max_items_per_day": 2}])
        unit = _instagram_unit(DAY1)
        with self.assertRaisesRegex(FewError,
                                    "unit source must match an enabled configured source"):
            ingest(store, cfg, DAY1, self.units_file(root, [unit]))
        self.assertEqual(self.count(store, "contents"), 0)

    def test_ingest_refuses_unit_with_disagreeing_source_id(self):
        spec = SPECS[0]
        root, cfg, store = self.make_env([self.source_entry(spec)])
        unit = _instagram_unit(DAY1)
        unit["source_id"] = stable_id("src", "https://www.instagram.com/@attacker")
        with self.assertRaisesRegex(FewError, "unit source_id disagrees"):
            ingest(store, cfg, DAY1, self.units_file(root, [unit]))
        self.assertEqual(self.count(store, "contents"), 0)


if __name__ == "__main__":
    unittest.main()
