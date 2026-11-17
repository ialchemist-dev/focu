"""Source-pack validation, planning, install, uninstall and restore.

Covers the wave-2 implementation of the backend design: schema v1 rules
(cadence basis, HTTPS-only, tracking parameters), loader-identity dedupe,
the load_config-gated install round-trip, ReaderStore-style uninstall
semantics, and byte-level restore. No network: liveness is injected.
"""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from urllib.error import HTTPError

import yaml

from focu.daily.config import load_config
from focu.packs import (PACKS_DIR, install_pack, manifest_path, plan_install,
                        restore_backup, uninstall_pack, validate_pack)
from focu.packs import main as pack_main

TODAY = date(2026, 11, 17)

RSS = (b'<?xml version="1.0" encoding="UTF-8"?>\n'
       b'<rss version="2.0"><channel><title>Example</title>'
       b'<item><title>Post</title><link>https://example.com/post</link>'
       b'<pubDate>Mon, 12 Oct 2026 07:00:00 GMT</pubDate></item>'
       b'</channel></rss>')


def live_fetch(url):
    return url, RSS


def dead_fetch(url):
    raise HTTPError(url, 404, "Not Found", {}, None)


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

FELIX_CONFIG = """version: 1
channels:
  - id: research
    name: Research Digest
sources:
  - name: Felix Rieseberg
    type: rss
    channel: research
    feed_url: https://felixrieseberg.com/rss/
"""

SHARED_CONFIG = """version: 1
channels:
  - id: research
    name: Research Digest
sources:
  - name: Shared Blog
    type: rss
    channel: research
    feed_url: https://shared.example.com/feed
"""


def config_names(path):
    cfg = load_config(path)
    return [s["name"] for s in cfg["sources"]]


class PackTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write_config(self, text=BASE_CONFIG):
        path = self.root / "sources.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    def shipped_pack(self):
        raw = json.loads((PACKS_DIR / "anthropic-personal-blogs.json")
                         .read_text(encoding="utf-8"))
        report = validate_pack(raw, today=TODAY)
        self.assertTrue(report["valid"], report["errors"])
        return raw, report["pack"]


class ShippedPackTests(PackTestCase):
    def test_shipped_anthropic_pack_validates(self):
        raw, pack = self.shipped_pack()
        self.assertEqual(pack["title"], "Anthropic · Personal blogs")
        self.assertEqual(len(pack["sources"]), 10)
        for source in pack["sources"]:
            # writers emit site_url alongside homepage (reader code path)
            self.assertEqual(source["site_url"], source["homepage"])
        self.assertEqual(len(pack["unverified"]), 9)

    def test_schema_file_covers_shipped_pack(self):
        schema = json.loads(
            (Path(__file__).parent.parent / "schemas"
             / "source-pack.schema.json").read_text(encoding="utf-8"))
        raw, _pack = self.shipped_pack()
        for key in schema["required"]:
            self.assertIn(key, raw)
        source_required = schema["$defs"]["source"]["required"]
        for source in raw["sources"]:
            for key in source_required:
                self.assertIn(key, source)


class ValidationTests(unittest.TestCase):
    def errors(self, pack):
        report = validate_pack(pack, today=TODAY)
        return report["valid"], report["errors"]

    def test_cadence_without_basis_is_an_error(self):
        source = make_source(cadence={"posts_per_month": 1.0,
                                      "as_of": "2026-11-17"})
        valid, errors = self.errors(make_pack([source]))
        self.assertFalse(valid)
        self.assertTrue(any("basis" in e for e in errors), errors)

    def test_cadence_missing_on_curated_pack_is_an_error(self):
        source = make_source()
        del source["cadence"]
        valid, errors = self.errors(make_pack([source]))
        self.assertFalse(valid)
        self.assertTrue(any("cadence is required" in e for e in errors), errors)

    def test_http_url_rejected(self):
        source = make_source(feed_url="http://alice.example.com/feed")
        valid, errors = self.errors(make_pack([source]))
        self.assertFalse(valid)
        self.assertTrue(any("HTTPS" in e for e in errors), errors)

    def test_tracking_parameter_rejected_and_named(self):
        source = make_source(
            feed_url="https://alice.example.com/feed?utm_source=newsletter")
        valid, errors = self.errors(make_pack([source]))
        self.assertFalse(valid)
        self.assertTrue(any("utm_source" in e for e in errors), errors)

    def test_credentials_in_url_rejected(self):
        source = make_source(
            feed_url="https://user:secret@alice.example.com/feed")
        valid, errors = self.errors(make_pack([source]))
        self.assertFalse(valid)
        self.assertTrue(any("credentials" in e for e in errors), errors)

    def test_alias_conflict_rejected(self):
        pack = make_pack()
        pack["name"] = "A Different Title"
        valid, errors = self.errors(pack)
        self.assertFalse(valid)
        self.assertTrue(any("disagree" in e for e in errors), errors)

    def test_homepage_site_url_disagreement_rejected(self):
        source = make_source(site_url="https://other.example.com/")
        valid, errors = self.errors(make_pack([source]))
        self.assertFalse(valid)
        self.assertTrue(any("disagree" in e for e in errors), errors)

    def test_legacy_aliases_normalize(self):
        pack = make_pack()
        pack["name"] = pack.pop("title")
        pack["categories"] = pack.pop("tags")
        report = validate_pack(pack, today=TODAY)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["pack"]["title"], "Test Pack")
        self.assertEqual(report["pack"]["tags"], ["test"])

    def test_within_pack_duplicate_identity_rejected(self):
        twin = make_source(id="alice-twin", name="Alice Twin")
        valid, errors = self.errors(make_pack([make_source(), twin]))
        self.assertFalse(valid)
        self.assertTrue(any("same identity" in e for e in errors), errors)

    def test_unverified_candidate_requires_reason(self):
        pack = make_pack()
        pack["unverified"] = [{"name": "Mallory", "checked_at": "2026-11-17"}]
        valid, errors = self.errors(pack)
        self.assertFalse(valid)
        self.assertTrue(any("reason is required" in e for e in errors), errors)

    def test_enabled_rss_requires_feed_url(self):
        source = make_source()
        del source["feed_url"]
        valid, errors = self.errors(make_pack([source]))
        self.assertFalse(valid)
        self.assertTrue(any("requires feed_url" in e for e in errors), errors)


class PlanTests(PackTestCase):
    def test_preview_dedupes_against_existing_sources(self):
        config = self.write_config(FELIX_CONFIG)
        before = config.read_bytes()
        _raw, pack = self.shipped_pack()
        plan = plan_install(pack, config)
        self.assertEqual(plan["errors"], [])
        duplicates = {d["pack_source_id"]: d for d in plan["duplicates"]}
        self.assertIn("felix", duplicates)
        self.assertEqual(duplicates["felix"]["existing_name"],
                         "Felix Rieseberg")
        self.assertEqual(duplicates["felix"]["provided_by"], ["manual"])
        self.assertNotIn("felix", {a["pack_source_id"] for a in plan["adds"]})
        # Planning is pure: no writes, no manifest.
        self.assertEqual(config.read_bytes(), before)
        self.assertFalse(manifest_path(config).exists())

    def test_plan_attention_total_for_shipped_pack(self):
        config = self.write_config()
        _raw, pack = self.shipped_pack()
        plan = plan_install(pack, config)
        self.assertEqual(plan["errors"], [])
        self.assertAlmostEqual(plan["attention_posts_per_month"], 5.5)

    def test_unknown_channel_is_a_plan_error(self):
        config = self.write_config()
        pack = validate_pack(make_pack(), today=TODAY)["pack"]
        plan = plan_install(pack, config, channel_override="nope")
        self.assertTrue(plan["errors"])
        with self.assertRaises(ValueError):
            install_pack(make_pack(), config, channel_override="nope",
                         check_feeds=False)

    def test_name_collision_is_a_plan_error(self):
        config = self.write_config(
            "version: 1\nchannels:\n  - id: research\nsources:\n"
            "  - name: Alice Example\n    type: rss\n    channel: research\n"
            "    feed_url: https://someone-else.example.com/feed\n")
        before = config.read_bytes()
        with self.assertRaises(ValueError):
            install_pack(make_pack(), config, check_feeds=False)
        self.assertEqual(config.read_bytes(), before)


class InstallTests(PackTestCase):
    def test_install_round_trip_through_load_config(self):
        config = self.write_config()
        original = config.read_bytes()
        bob = make_source(id="bob", name="Bob Example", type="blog",
                          platform="Self-hosted",
                          homepage="https://bob.example.com/",
                          enabled=False)
        del bob["feed_url"]
        result = install_pack(make_pack([make_source(), bob]), config,
                              check_feeds=False, pack_sha256="deadbeef")
        self.assertTrue(result["applied"])
        cfg = load_config(config)
        names = [s["name"] for s in cfg["sources"]]
        self.assertIn("Alice Example", names)
        self.assertIn("Bob Example", names)
        alice = next(s for s in cfg["sources"] if s["name"] == "Alice Example")
        manifest = json.loads(manifest_path(config).read_text("utf-8"))
        self.assertEqual(len(manifest["packs"]), 1)
        record = manifest["packs"][0]
        self.assertEqual(record["pack_id"], "test-pack")
        self.assertEqual(record["sha256"], "deadbeef")
        entries = {e["name"]: e for e in record["entries"]}
        self.assertTrue(entries["Alice Example"]["added"])
        self.assertEqual(entries["Alice Example"]["source_id"],
                         alice["source_id"])
        # The backup is a byte copy of the pre-install registry.
        backup = Path(result["backup"])
        self.assertEqual(backup.read_bytes(), original)
        # Provenance stays out of sources.yaml.
        doc = yaml.safe_load(config.read_text("utf-8"))
        for entry in doc["sources"]:
            self.assertNotIn("cadence", entry)
            self.assertNotIn("pack_id", entry)

    def test_install_with_dead_feed_installs_disabled(self):
        config = self.write_config()
        result = install_pack(make_pack(), config, fetch=dead_fetch)
        self.assertTrue(result["applied"])
        add = result["plan"]["adds"][0]
        self.assertFalse(add["enabled"])
        self.assertIn("liveness", add["entry"]["notes"])
        cfg = load_config(config)
        alice = next(s for s in cfg["sources"] if s["name"] == "Alice Example")
        self.assertFalse(alice["enabled"])

    def test_install_with_live_feed_stays_enabled(self):
        config = self.write_config()
        result = install_pack(make_pack(), config, fetch=live_fetch)
        add = result["plan"]["adds"][0]
        self.assertTrue(add["enabled"])
        self.assertEqual(add["liveness"]["status"], "live")
        self.assertEqual(add["liveness"]["newest"], "2026-10-12")

    def test_unverified_candidates_are_never_installed(self):
        config = self.write_config()
        pack = make_pack()
        pack["unverified"] = [
            {"name": "Mallory", "homepage": "https://mallory.example.com/",
             "reason": "affiliation not established",
             "checked_at": "2026-11-17"}]
        result = install_pack(pack, config, check_feeds=False)
        self.assertEqual(result["plan"]["unverified"][0]["name"], "Mallory")
        self.assertNotIn("Mallory", config_names(config))

    def test_reinstall_is_all_duplicates(self):
        config = self.write_config()
        install_pack(make_pack(), config, check_feeds=False)
        count = len(load_config(config)["sources"])
        result = install_pack(make_pack(), config, check_feeds=False)
        self.assertEqual(result["plan"]["adds"], [])
        self.assertEqual(len(result["plan"]["duplicates"]), 1)
        self.assertEqual(len(load_config(config)["sources"]), count)


class UninstallTests(PackTestCase):
    def test_uninstall_removes_added_and_keeps_preexisting(self):
        config = self.write_config(SHARED_CONFIG)
        shared = make_source(id="shared", name="Shared Blog",
                             homepage="https://shared.example.com/",
                             feed_url="https://shared.example.com/feed")
        only = make_source(id="only", name="Only One",
                           homepage="https://only.example.com/",
                           feed_url="https://only.example.com/feed")
        install_pack(make_pack([shared, only]), config, check_feeds=False)
        self.assertIn("Only One", config_names(config))
        result = uninstall_pack("test-pack", config)
        self.assertTrue(result["applied"])
        self.assertEqual([r["name"] for r in result["removes"]], ["Only One"])
        self.assertEqual([k["name"] for k in result["keeps"]], ["Shared Blog"])
        self.assertEqual(config_names(config), ["Shared Blog"])
        manifest = json.loads(manifest_path(config).read_text("utf-8"))
        self.assertEqual(manifest["packs"], [])

    def test_uninstall_preserves_sources_another_pack_provides(self):
        config = self.write_config(SHARED_CONFIG)
        only = make_source(id="only", name="Only One",
                           homepage="https://only.example.com/",
                           feed_url="https://only.example.com/feed")
        two = make_source(id="two", name="Only Two",
                          homepage="https://two.example.com/",
                          feed_url="https://two.example.com/feed")
        install_pack(make_pack([only], id="pack-one"), config,
                     check_feeds=False)
        install_pack(make_pack([only, two], id="pack-two"), config,
                     check_feeds=False)
        first = uninstall_pack("pack-one", config)
        self.assertEqual(first["removes"], [])
        self.assertEqual([k["name"] for k in first["keeps"]], ["Only One"])
        self.assertIn("Only One", config_names(config))
        second = uninstall_pack("pack-two", config)
        self.assertEqual([r["name"] for r in second["removes"]], ["Only Two"])
        # Pack two never added Only One (it was a duplicate for it too), so
        # it survives as a detached manual entry rather than being deleted
        # by a pack that did not install it.
        self.assertIn("Only One", config_names(config))

    def test_uninstall_unknown_pack_raises(self):
        config = self.write_config()
        with self.assertRaises(ValueError):
            uninstall_pack("nope", config)


class RestoreTests(PackTestCase):
    def test_restore_returns_sources_yaml_byte_identical(self):
        config = self.write_config()
        original = config.read_bytes()
        install_pack(make_pack(), config, check_feeds=False)
        self.assertNotEqual(config.read_bytes(), original)
        result = restore_backup(config)
        self.assertTrue(result["applied"])
        self.assertEqual(config.read_bytes(), original)

    def test_restore_preview_reports_discarded_names(self):
        config = self.write_config()
        install_pack(make_pack(), config, check_feeds=False)
        before = config.read_bytes()
        result = restore_backup(config, dry_run=True)
        self.assertFalse(result["applied"])
        self.assertEqual(result["removed_names"], ["Alice Example"])
        self.assertEqual(config.read_bytes(), before)


class CliTests(PackTestCase):
    def test_cli_validate_install_and_top_level_wiring(self):
        config = self.write_config()
        pack_file = self.root / "pack.json"
        pack_file.write_text(json.dumps(make_pack()), encoding="utf-8")
        self.assertEqual(
            pack_main(["validate", str(pack_file), "--no-liveness"]), 0)
        self.assertEqual(
            pack_main(["install", str(pack_file), "--config", str(config),
                       "--yes", "--no-liveness"]), 0)
        self.assertIn("Alice Example", config_names(config))
        from focu.cli import main as cli_main
        self.assertEqual(
            cli_main(["pack", "list", "--config", str(config)]), 0)
        self.assertEqual(
            cli_main(["pack", "preview", "anthropic-personal-blogs",
                      "--config", str(config), "--no-liveness"]), 0)


if __name__ == "__main__":
    unittest.main()
