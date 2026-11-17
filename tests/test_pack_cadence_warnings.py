"""Cadence-vs-value flags (self-iteration Q4).

Probe (2026-11-17, shipped packs): the geothermal pack's preview totals
≈92 posts/month without saying that one trade wire (ThinkGeoEnergy,
78/month) is 84% of it, while the Anthropic pack's dominant member is a
weekly newsletter (4.3 of ≈6.1/month) that must NOT be flagged. The fix
is preview warnings only — cadence_warnings never caps, demotes or
excludes; the preview stays the judgment surface (Q6 precedent).

No network: liveness is disabled or omitted everywhere below.
"""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from focu.packs import (PACKS_DIR, cadence_warnings, format_plan,
                        install_pack, plan_install, show_pack, update_pack,
                        validate_pack)

TODAY = date(2026, 11, 17)


def make_source(**overrides):
    source = {"id": "alice", "name": "Alice Example", "type": "rss",
              "channel": "research", "platform": "Ghost",
              "homepage": "https://alice.example.com/",
              "feed_url": "https://alice.example.com/feed",
              "cadence": {"posts_per_month": 1.0,
                          "basis": "feed items dated 2026-09-01 and 2026-10-01",
                          "as_of": "2026-11-17"},
              "verified_at": "2026-11-17", "enabled": True}
    source.update(overrides)
    return source


def with_cadence(source, ppm):
    source["cadence"] = {"posts_per_month": ppm,
                         "basis": f"observed cadence fixture at {ppm}/month",
                         "as_of": "2026-11-17"}
    return source


def make_pack(sources=None, **overrides):
    pack = {"schema_version": 1, "id": "test-pack", "title": "Test Pack",
            "version": "1.0.0", "curator": {"name": "Test Curator"},
            "description": "A pack used by tests.", "tags": ["test"],
            "coverage": "Only test fixtures.", "verified_at": "2026-11-17",
            "sources": sources if sources is not None else [make_source()]}
    pack.update(overrides)
    return pack


BASE_CONFIG = """version: 1
channels:
  - id: research
    name: Research Digest
sources:
  - name: Existing Blog
    type: rss
    channel: research
    feed_url: https://existing.example.com/feed
"""


def cadence_text(warnings):
    return [w for w in warnings
            if "dominates this pack" in w or "is high-volume" in w]


class CadenceWarningHelperTests(unittest.TestCase):
    def test_dominant_wire_fires(self):
        warnings = cadence_warnings(
            [("Wire", 78.0, 5), ("Quiet A", 5.5, None), ("Quiet B", 2.0, None)])
        self.assertEqual(len(warnings), 1)
        self.assertIn("dominates this pack", warnings[0])
        self.assertIn("91%", warnings[0])
        self.assertIn("curator cap: 5/day", warnings[0])
        self.assertIn("choice stays yours", warnings[0])

    def test_high_volume_without_dominance_fires(self):
        warnings = cadence_warnings(
            [("Daily Blog", 31.5, 2), ("Other", 60.0, None),
             ("More", 35.0, None)])
        flagged = [w for w in warnings if "Daily Blog" in w]
        self.assertEqual(len(flagged), 1)
        self.assertIn("is high-volume", flagged[0])
        self.assertIn("curator cap: 2/day", flagged[0])

    def test_weekly_newsletter_dominance_at_low_volume_is_silent(self):
        # The Anthropic pack's shape: dominance without material volume
        # is the pack working as intended, not a tax.
        warnings = cadence_warnings(
            [("Weekly Newsletter", 4.3, 5), ("Rare A", 0.6, None),
             ("Rare B", 0.5, None), ("Rare C", 0.7, None)])
        self.assertEqual(warnings, [])

    def test_quiet_pack_is_silent(self):
        warnings = cadence_warnings(
            [("A", 2.0, None), ("B", 1.0, None), ("C", 0.5, None)])
        self.assertEqual(warnings, [])

    def test_unknown_cadence_is_never_flagged(self):
        warnings = cadence_warnings(
            [("Mystery", None, None), ("Known", 1.0, None)])
        self.assertEqual(warnings, [])

    def test_dominance_needs_material_total(self):
        # 15/month at 60% share of a 25/month pack: dominant clause fires
        # even though the source alone is under the high-volume line.
        warnings = cadence_warnings(
            [("Big Fish", 15.0, None), ("Small Pond", 10.0, None)])
        self.assertEqual(len(warnings), 1)
        self.assertIn("dominates this pack", warnings[0])


class CadencePlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name) / "sources.yaml"
        self.config.write_text(BASE_CONFIG, encoding="utf-8")

    def plan(self, raw):
        report = validate_pack(raw, today=TODAY)
        self.assertTrue(report["valid"], report["errors"])
        return plan_install(report["pack"], self.config)

    def test_install_preview_flags_dominant_wire(self):
        wire = with_cadence(make_source(
            id="wire", name="The Wire",
            homepage="https://wire.example.com/",
            feed_url="https://wire.example.com/feed"), 78.0)
        quiet = with_cadence(make_source(), 5.5)
        plan = self.plan(make_pack([wire, quiet]))
        flagged = cadence_text(plan["warnings"])
        self.assertEqual(len(flagged), 1)
        self.assertIn("The Wire", flagged[0])
        self.assertIn("The Wire", format_plan(plan))

    def test_install_preview_quiet_for_people_pack_shape(self):
        weekly = with_cadence(make_source(), 4.3)
        rare = with_cadence(make_source(
            id="bob", name="Bob Example",
            homepage="https://bob.example.com/",
            feed_url="https://bob.example.com/feed"), 0.6)
        plan = self.plan(make_pack([weekly, rare]))
        self.assertEqual(cadence_text(plan["warnings"]), [])

    def test_disabled_high_volume_source_is_not_flagged(self):
        wire = with_cadence(make_source(enabled=False), 78.0)
        plan = self.plan(make_pack([wire]))
        self.assertEqual(cadence_text(plan["warnings"]), [])

    def test_update_plan_flags_new_dominance(self):
        install_pack(make_pack(), self.config,
                     check_feeds=False, today=TODAY)
        louder = with_cadence(make_source(), 78.0)
        result = update_pack(make_pack([louder], version="1.1.0"),
                             self.config, check_feeds=False, today=TODAY)
        flagged = cadence_text(result["plan"]["warnings"])
        self.assertEqual(len(flagged), 1)
        self.assertIn("Alice Example", flagged[0])


class ShippedPackCadenceTests(unittest.TestCase):
    def shipped(self, name):
        return json.loads((PACKS_DIR / name).read_text(encoding="utf-8"))

    def test_geothermal_show_flags_thinkgeoenergy(self):
        report = show_pack(self.shipped("geothermal-industry.json"),
                           check_feeds=False, today=TODAY)
        flagged = cadence_text(report["warnings"])
        self.assertEqual(len(flagged), 1)
        self.assertIn("ThinkGeoEnergy", flagged[0])
        self.assertIn("dominates this pack", flagged[0])

    def test_anthropic_show_stays_quiet(self):
        report = show_pack(self.shipped("anthropic-personal-blogs.json"),
                           check_feeds=False, today=TODAY)
        self.assertEqual(cadence_text(report["warnings"]), [])


if __name__ == "__main__":
    unittest.main()
