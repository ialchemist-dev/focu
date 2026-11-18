"""Marketplace catalog, recommended default, and static page (P2-2).

The catalog is generated from the bundled packs, so these tests pin
the generation contract: every shipped pack appears exactly once with
numbers derived from its own file, the default is exactly the
followed-people pack, the on-disk marketplace/ files match a fresh
build, and the page is self-contained (no scripts, no external assets)
with one card and one install command per pack.
"""
import json
import unittest
from pathlib import Path

from focu.marketplace import (RECOMMENDED_PACK_ID, SLOGAN, build_catalog,
                              build_default, render_marketplace_html)
from focu.packs import PACKS_DIR, validate_pack

ROOT = Path(__file__).parent.parent
MARKETPLACE_DIR = ROOT / "marketplace"


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = build_catalog()
        self.by_id = {p["id"]: p for p in self.catalog["packs"]}

    def test_catalog_covers_every_bundled_pack(self):
        files = sorted(p.name for p in PACKS_DIR.glob("*.json"))
        self.assertEqual(len(self.catalog["packs"]), len(files))
        for name in files:
            raw = json.loads((PACKS_DIR / name).read_text("utf-8"))
            self.assertIn(raw["id"], self.by_id)

    def test_entry_fields_match_pack_file(self):
        for entry in self.catalog["packs"]:
            raw = json.loads(
                (ROOT / entry["pack_file"]).read_text("utf-8"))
            pack = validate_pack(raw)["pack"]
            self.assertEqual(entry["name"], pack["title"])
            self.assertEqual(entry["description"], pack["description"])
            self.assertEqual(entry["source_count"], len(pack["sources"]))
            expected_ppm = round(sum(
                s["cadence"]["posts_per_month"]
                for s in pack["sources"]
                if s.get("enabled") is True
                and isinstance(s.get("cadence"), dict)), 4)
            self.assertAlmostEqual(entry["posts_per_month"], expected_ppm)
            self.assertIn(entry["pack_file"], entry["install_command"])
            self.assertIn("pack install", entry["install_command"])
            self.assertIn("pack preview", entry["preview_command"])
            self.assertIn(entry["id"], entry["uninstall_command"])

    def test_exactly_one_recommended_pack(self):
        rec = [p for p in self.catalog["packs"] if p["recommended"]]
        self.assertEqual([p["id"] for p in rec], [RECOMMENDED_PACK_ID])
        self.assertEqual(self.catalog["recommended_pack_id"],
                         RECOMMENDED_PACK_ID)
        self.assertEqual(self.catalog["slogan"], SLOGAN)


class DefaultTests(unittest.TestCase):
    def test_default_is_followed_people_with_swap_steps(self):
        default = build_default()
        self.assertEqual(default["recommended_pack_id"], "followed-people")
        self.assertEqual(default["source_count"], 6)
        self.assertAlmostEqual(default["posts_per_month"], 58.4)
        self.assertTrue(any("uninstall" in step for step in default["swap"]))
        self.assertIn("followed-people", default["uninstall_command"])


class OnDiskTests(unittest.TestCase):
    def test_on_disk_catalog_and_default_match_fresh_build(self):
        catalog = json.loads(
            (MARKETPLACE_DIR / "catalog.json").read_text("utf-8"))
        self.assertEqual(catalog, build_catalog())
        default = json.loads(
            (MARKETPLACE_DIR / "default.json").read_text("utf-8"))
        self.assertEqual(default, build_default())

    def test_on_disk_page_matches_fresh_render(self):
        page = (MARKETPLACE_DIR / "index.html").read_text("utf-8")
        self.assertEqual(page, render_marketplace_html())


class PageTests(unittest.TestCase):
    def setUp(self):
        self.catalog = build_catalog()
        self.page = render_marketplace_html(self.catalog)

    def test_page_has_slogan_card_and_command_per_pack(self):
        self.assertIn(SLOGAN, self.page)
        for entry in self.catalog["packs"]:
            self.assertIn(entry["title"], self.page)
            self.assertIn(entry["install_command"], self.page)
        self.assertIn("https://github.com/ialchemist-dev/focu", self.page)

    def test_page_is_self_contained_and_script_free(self):
        self.assertNotIn("<script", self.page)
        self.assertNotIn("<link", self.page)
        self.assertNotIn("src=", self.page)


if __name__ == "__main__":
    unittest.main()
