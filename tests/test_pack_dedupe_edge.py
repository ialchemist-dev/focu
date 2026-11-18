"""Cross-locator dedupe pressure (PM self-iteration Q6).

Identity in the daily registry is type-dependent
(``focu/daily/identity.py: source_url``): an ``rss`` source is identified
by its feed URL, a ``blog`` source by its site URL. The same publication
can therefore enter the registry twice under two identities — once as a
feed, once as a site — when two packs (or a pack and a manual entry)
describe it with different locators. These tests pin what the install
planner does in each case:

- same identity after canonicalization -> duplicate, skipped (good);
- different identity, same publication -> the plan must *warn* in the
  preview, because the preview is the judgment surface and silently
  subscribing twice taxes attention every day;
- unrelated sources -> no warning (warnings that cry wolf are their own
  attention tax).
"""
import tempfile
import unittest
from pathlib import Path

from focu.packs import plan_install, validate_pack

TODAY = "2026-11-17"

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


def make_pack(sources, **overrides):
    pack = {"schema_version": 1, "id": "edge-pack", "title": "Edge Pack",
            "version": "1.0.0", "curator": {"name": "Test Curator"},
            "description": "Cross-locator dedupe fixtures.", "tags": ["test"],
            "coverage": "Only test fixtures.", "verified_at": "2026-11-17",
            "sources": sources}
    pack.update(overrides)
    return pack


def plan_for(config_text, raw_pack):
    report = validate_pack(raw_pack)
    assert report["valid"], report["errors"]
    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "sources.yaml"
        config.write_text(config_text, encoding="utf-8")
        return plan_install(report["pack"], config)


class CrossLocatorDedupeTests(unittest.TestCase):
    def test_tracking_params_in_registry_still_dedupe(self):
        # canonical_url strips utm_* from the identity, so a manual
        # registry entry carrying tracking parameters is the same
        # source as the pack's clean feed URL.
        config = BASE_CONFIG.replace(
            "https://existing.example.com/feed",
            "https://alice.example.com/feed?utm_source=newsletter")
        config = config.replace("Existing Blog", "Alice Manual")
        plan = plan_for(config, make_pack([make_source()]))
        self.assertEqual(plan["adds"], [])
        self.assertEqual(len(plan["duplicates"]), 1)
        self.assertEqual(plan["duplicates"][0]["existing_name"], "Alice Manual")

    def test_cross_type_same_publication_warns(self):
        # Registry holds Alice's feed (rss identity = feed URL). The
        # pack lists Alice as a blog (identity = site root). Different
        # identities, same publication: the plan adds her a second time
        # and must say so in the preview.
        config = BASE_CONFIG.replace(
            "https://existing.example.com/feed",
            "https://alice.example.com/feed").replace(
            "Existing Blog", "Alice Feed")
        blog = make_source(type="blog", feed_url=None)
        blog.pop("feed_url")
        plan = plan_for(config, make_pack([blog]))
        self.assertEqual(len(plan["adds"]), 1)
        joined = " ".join(plan["warnings"])
        self.assertIn("Alice Feed", joined)
        self.assertIn("different identity", joined)

    def test_trailing_slash_feed_variant_warns(self):
        # identity.canonical_url deliberately preserves trailing
        # slashes, so .../feed and .../feed/ are different identities;
        # the planner must flag the near-certain duplicate.
        config = BASE_CONFIG.replace(
            "https://existing.example.com/feed",
            "https://alice.example.com/feed/").replace(
            "Existing Blog", "Alice Feed")
        plan = plan_for(config, make_pack([make_source()]))
        self.assertEqual(len(plan["adds"]), 1)
        joined = " ".join(plan["warnings"])
        self.assertIn("Alice Feed", joined)
        self.assertIn("different identity", joined)

    def test_unrelated_source_no_warning(self):
        plan = plan_for(BASE_CONFIG, make_pack([make_source()]))
        self.assertEqual(len(plan["adds"]), 1)
        self.assertEqual(plan["warnings"], [])


if __name__ == "__main__":
    unittest.main()
