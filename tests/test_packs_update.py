"""Source-pack catalog, show and update (wave 9).

Covers the rest of the design's command surface: the read-only catalog
(bundled packs + manifest install state), show (full membership with
install state), and the pinned update flow — source-level diff against
the manifest snapshot, ReaderStore removal semantics for dropped
sources, the already-current no-op, and refusal when not installed.
No network: liveness is disabled or injected.
"""
import contextlib
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from focu.daily.config import load_config
from focu.packs import (PACKS_DIR, install_pack, list_backups, manifest_path,
                        pack_catalog, show_pack, uninstall_pack, update_pack)
from focu.packs import main as pack_main

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


def make_pack(sources=None, **overrides):
    pack = {"schema_version": 1, "id": "test-pack", "title": "Test Pack",
            "version": "1.0.0", "curator": {"name": "Test Curator"},
            "description": "A pack used by tests.", "tags": ["test"],
            "coverage": "Only test fixtures.", "verified_at": "2026-11-17",
            "sources": sources if sources is not None else [make_source()]}
    pack.update(overrides)
    return pack


def bob_source():
    return make_source(id="bob", name="Bob Example",
                       homepage="https://bob.example.com/",
                       feed_url="https://bob.example.com/feed")


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

def config_names(path):
    return [s["name"] for s in load_config(path)["sources"]]


def manifest_records(path, pack_id=None):
    manifest = json.loads(manifest_path(path).read_text("utf-8"))
    records = manifest["packs"]
    if pack_id is not None:
        records = [r for r in records if r["pack_id"] == pack_id]
    return records


class UpdateTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write_config(self, text=BASE_CONFIG):
        path = self.root / "sources.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    def install(self, pack, config, **kwargs):
        kwargs.setdefault("check_feeds", False)
        kwargs.setdefault("today", TODAY)
        return install_pack(pack, config, **kwargs)

    def update(self, pack, config, **kwargs):
        kwargs.setdefault("check_feeds", False)
        kwargs.setdefault("today", TODAY)
        return update_pack(pack, config, **kwargs)


class CatalogTests(UpdateTestCase):
    def test_catalog_lists_bundled_packs_with_cost_and_state(self):
        config = self.write_config()
        shipped = json.loads((PACKS_DIR / "anthropic-personal-blogs.json")
                             .read_text(encoding="utf-8"))
        self.install(shipped, config)
        catalog = pack_catalog(config)
        by_id = {p["id"]: p for p in catalog["packs"] if not p.get("error")}
        anthropic = by_id["anthropic-personal-blogs"]
        self.assertEqual(anthropic["version"], "1.0.0")
        self.assertEqual(anthropic["verified_at"], "2026-11-17")
        self.assertEqual(anthropic["sources"], 10)
        self.assertAlmostEqual(anthropic["attention_posts_per_month"], 5.5)
        self.assertTrue(anthropic["installed"])
        self.assertEqual(anthropic["installed_version"], "1.0.0")
        self.assertFalse(anthropic["update_available"])
        geothermal = by_id["geothermal-industry"]
        self.assertFalse(geothermal["installed"])
        self.assertIsNone(geothermal["installed_version"])
        # A pack installed from a file is not bundled, so it is not a
        # catalog entry; the catalog is the bundled shelf.
        self.assertNotIn("test-pack", by_id)

    def test_catalog_without_config_reports_nothing_installed(self):
        catalog = pack_catalog()
        self.assertTrue(catalog["packs"])
        for item in catalog["packs"]:
            if not item.get("error"):
                self.assertFalse(item["installed"])

    def test_catalog_cli_json(self):
        config = self.write_config()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = pack_main(["catalog", "--config", str(config), "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        ids = {p.get("id") for p in payload["packs"]}
        self.assertIn("anthropic-personal-blogs", ids)


class ShowTests(UpdateTestCase):
    def test_show_reports_membership_unverified_and_install_state(self):
        config = self.write_config()
        pack = make_pack()
        pack["unverified"] = [
            {"name": "Mallory", "homepage": "https://mallory.example.com/",
             "reason": "affiliation not established",
             "checked_at": "2026-11-17"}]
        before = show_pack(pack, config, check_feeds=False, today=TODAY)
        self.assertFalse(before["installed"]["installed"])
        self.assertEqual(len(before["sources"]), 1)
        source = before["sources"][0]
        self.assertEqual(source["name"], "Alice Example")
        self.assertEqual(source["feed_status"], "unchecked")
        self.assertEqual(source["cadence_posts_per_month"], 1.0)
        self.assertIn("2026-09-01", source["cadence_basis"])
        self.assertEqual(before["unverified"][0]["name"], "Mallory")
        self.assertEqual(before["unverified"][0]["reason"],
                         "affiliation not established")
        self.assertAlmostEqual(before["attention_posts_per_month"], 1.0)

        self.install(pack, config)
        after = show_pack(pack, config, check_feeds=False, today=TODAY)
        self.assertTrue(after["installed"]["installed"])
        self.assertEqual(after["installed"]["installed_version"], "1.0.0")
        self.assertEqual(after["installed"]["available_version"], "1.0.0")
        self.assertFalse(after["installed"]["update_available"])

    def test_show_shipped_pack_unverified_and_cli(self):
        raw = json.loads((PACKS_DIR / "anthropic-personal-blogs.json")
                         .read_text(encoding="utf-8"))
        report = show_pack(raw, check_feeds=False, today=TODAY)
        self.assertEqual(len(report["sources"]), 10)
        self.assertEqual(len(report["unverified"]), 9)
        self.assertTrue(all(s["feed_status"] in {"unchecked", "no_feed"}
                            for s in report["sources"]))
        config = self.write_config()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = pack_main(["show", "anthropic-personal-blogs",
                            "--config", str(config), "--no-liveness",
                            "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["pack"]["id"], "anthropic-personal-blogs")


class UpdateTests(UpdateTestCase):
    def test_update_adds_a_source(self):
        config = self.write_config()
        self.install(make_pack(), config)
        result = self.update(
            make_pack([make_source(), bob_source()], version="1.1.0"),
            config)
        self.assertTrue(result["applied"])
        self.assertFalse(result["already_current"])
        plan = result["plan"]
        self.assertEqual(plan["installed_version"], "1.0.0")
        self.assertEqual([a["name"] for a in plan["adds"]], ["Bob Example"])
        self.assertEqual([u["name"] for u in plan["unchanged"]],
                         ["Alice Example"])
        self.assertEqual(plan["removes"], [])
        names = config_names(config)
        self.assertIn("Alice Example", names)
        self.assertIn("Bob Example", names)
        records = manifest_records(config, "test-pack")
        self.assertEqual([r["version"] for r in records], ["1.0.0", "1.1.0"])
        # The pre-update backup holds the one-source registry.
        backup = Path(result["backup"])
        self.assertNotIn("Bob Example",
                         [s["name"] for s in
                          load_config(backup)["sources"]])

    def test_update_removes_unshared_source(self):
        config = self.write_config()
        self.install(make_pack([make_source(), bob_source()]), config)
        result = self.update(make_pack(version="1.1.0"), config)
        self.assertTrue(result["applied"])
        self.assertEqual([r["name"] for r in result["plan"]["removes"]],
                         ["Bob Example"])
        self.assertNotIn("Bob Example", config_names(config))
        self.assertIn("Alice Example", config_names(config))

    def test_update_removed_source_shared_with_another_pack_survives(self):
        # Shared Blog is added by pack-one and then listed by pack-two,
        # so pack-one's update must not detach it (BASE_CONFIG keeps it
        # out of the pre-existing registry, unlike SHARED_CONFIG).
        config = self.write_config()
        shared = make_source(id="shared", name="Shared Blog",
                             homepage="https://shared.example.com/",
                             feed_url="https://shared.example.com/feed")
        only = make_source(id="only", name="Only One",
                           homepage="https://only.example.com/",
                           feed_url="https://only.example.com/feed")
        self.install(make_pack([shared, only], id="pack-one"), config)
        self.install(make_pack([shared], id="pack-two"), config)
        result = self.update(
            make_pack([only], id="pack-one", version="1.1.0"), config)
        self.assertTrue(result["applied"])
        plan = result["plan"]
        self.assertEqual(plan["removes"], [])
        keeps = {k["name"]: k["reason"] for k in plan["keeps"]}
        self.assertIn("Shared Blog", keeps)
        self.assertIn("pack-two", keeps["Shared Blog"])
        names = config_names(config)
        self.assertIn("Shared Blog", names)
        self.assertIn("Only One", names)

    def test_update_locator_change_replaces_entry(self):
        config = self.write_config()
        self.install(make_pack(), config)
        moved = make_source(feed_url="https://alice.example.com/rss")
        result = self.update(make_pack([moved], version="1.1.0"), config)
        self.assertTrue(result["applied"])
        changed = result["plan"]["changed"]
        self.assertEqual(len(changed), 1)
        self.assertTrue(changed[0]["identity_changed"])
        cfg = load_config(config)
        alice = next(s for s in cfg["sources"]
                     if s["name"] == "Alice Example")
        self.assertEqual(alice["feed_url"], "https://alice.example.com/rss")
        record = manifest_records(config, "test-pack")[-1]
        entry = next(e for e in record["entries"]
                     if e["name"] == "Alice Example")
        self.assertTrue(entry["added"])
        self.assertEqual(entry["source_id"], alice["source_id"])

    def test_update_already_current_writes_nothing(self):
        config = self.write_config()
        self.install(make_pack(), config)
        config_bytes = config.read_bytes()
        manifest_bytes = manifest_path(config).read_bytes()
        backups_before = list_backups(config)
        result = self.update(make_pack(), config)
        self.assertTrue(result["already_current"])
        self.assertFalse(result["applied"])
        self.assertEqual(config.read_bytes(), config_bytes)
        self.assertEqual(manifest_path(config).read_bytes(), manifest_bytes)
        self.assertEqual(list_backups(config), backups_before)

    def test_update_refused_when_not_installed(self):
        config = self.write_config()
        with self.assertRaises(ValueError) as caught:
            self.update(make_pack(), config)
        self.assertIn("not installed", str(caught.exception))
        pack_file = self.root / "pack.json"
        pack_file.write_text(json.dumps(make_pack()), encoding="utf-8")
        with self.assertRaises(ValueError):
            pack_main(["update", str(pack_file), "--config", str(config),
                       "--yes", "--no-liveness"])

    def test_update_dry_run_writes_nothing(self):
        config = self.write_config()
        self.install(make_pack(), config)
        config_bytes = config.read_bytes()
        manifest_bytes = manifest_path(config).read_bytes()
        result = self.update(
            make_pack([make_source(), bob_source()], version="1.1.0"),
            config, dry_run=True)
        self.assertFalse(result["applied"])
        self.assertEqual([a["name"] for a in result["plan"]["adds"]],
                         ["Bob Example"])
        self.assertEqual(config.read_bytes(), config_bytes)
        self.assertEqual(manifest_path(config).read_bytes(), manifest_bytes)

    def test_update_then_uninstall_removes_current_membership(self):
        config = self.write_config()
        self.install(make_pack(), config)
        self.update(make_pack([make_source(), bob_source()],
                              version="1.1.0"), config)
        result = uninstall_pack("test-pack", config)
        self.assertTrue(result["applied"])
        removed = {r["name"] for r in result["removes"]}
        self.assertEqual(removed, {"Alice Example", "Bob Example"})
        self.assertEqual(config_names(config), ["Existing Blog"])

    def test_update_cli_end_to_end(self):
        config = self.write_config()
        v1 = self.root / "pack-v1.json"
        v1.write_text(json.dumps(make_pack()), encoding="utf-8")
        self.assertEqual(
            pack_main(["install", str(v1), "--config", str(config),
                       "--yes", "--no-liveness"]), 0)
        v2 = self.root / "pack-v2.json"
        v2.write_text(json.dumps(
            make_pack([make_source(), bob_source()], version="1.1.0")),
            encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = pack_main(["update", str(v2), "--config", str(config),
                            "--yes", "--no-liveness", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["applied"])
        self.assertIn("Bob Example", config_names(config))
        # Second run at the same version reports already current.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = pack_main(["update", str(v2), "--config", str(config),
                            "--yes", "--no-liveness"])
        self.assertEqual(rc, 0)
        self.assertIn("already current", out.getvalue())


if __name__ == "__main__":
    unittest.main()
