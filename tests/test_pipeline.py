import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from focu.daily.collectors import FetchResult, rss_from_bytes
from focu.daily.config import load_config
from focu.daily.errors import FewError
from focu.daily.identity import canonical_url, content_identity, source_url, stable_id
from focu.daily.pipeline import compose, digest, finalize_episodes, ingest, run_lock, run_pipeline
from focu.daily.store import Store


class IdentityTests(unittest.TestCase):
    def test_video_identity_keeps_video_id(self):
        urls = ["https://youtu.be/A?t=20", "https://youtube.com/watch?v=A&utm_source=x",
                "https://www.youtube.com/shorts/A", "https://m.youtube.com/embed/A"]
        self.assertEqual(len({canonical_url(u) for u in urls}), 1)
        self.assertNotEqual(canonical_url(urls[0]), canonical_url("https://youtube.com/watch?v=B"))

    def test_unknown_query_and_path_are_not_destroyed(self):
        self.assertEqual(canonical_url("https://EXAMPLE.org/Article?id=12&utm_source=x#part"),
                         "https://example.org/Article?id=12")
        self.assertNotEqual(canonical_url("https://example.org/?id=12"), canonical_url("https://example.org/?id=13"))
        self.assertNotEqual(canonical_url("https://example.org/A"), canonical_url("https://example.org/a"))

    def test_twitter_alias_and_title_only(self):
        self.assertEqual(canonical_url("https://twitter.com/person/status/1"), canonical_url("https://x.com/person/status/1"))
        self.assertNotEqual(content_identity({"title": "Daily"}, "src_x")[0],
                            content_identity({"title": "Daily"}, "src_x")[0])

    def test_source_identity_ignores_label_and_transport(self):
        a = {"type": "rss", "feed_url": "https://example.org/feed", "name": "Before", "channel": "a"}
        b = {**a, "name": "After", "channel": "b"}
        self.assertEqual(source_url(a), source_url(b))
        self.assertEqual(source_url(a), source_url({"type": "blog", "site_url": "https://example.org/feed"}))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config_path = self.root / "sources.yaml"
        self.config = {"version": 2, "timezone": "UTC", "output_mode": "text_only",
                       "channels": [{"id": "research", "language": "en", "max_minutes": 12}],
                       "sources": [{"name": "Test", "type": "rss", "channel": "research",
                                    "feed_url": "https://example.org/feed", "max_items_per_day": 2}]}
        self.reload_config()
        self.store = Store(self.root / "data")
        self.store.sync_sources(self.cfg)
        self.src = self.cfg["sources"][0]
        self.today = datetime.now(timezone.utc).date().isoformat()
        self.tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def reload_config(self):
        self.config_path.write_text(json.dumps(self.config))
        self.cfg = load_config(self.config_path)

    def item(self, i=1, **changes):
        return {"native_item_id": str(i), "source": "Test", "url": f"https://example.org/article/{i}",
                "title": "Daily update", "body": "The source published a short update.", **changes}

    def units_file(self, items):
        path = self.root / "units.json"
        path.write_text(json.dumps(items))
        return path

    def count(self, table):
        return self.store.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    @unittest.skipUnless(importlib.util.find_spec("feedparser"), "requires base feedparser dependency")
    def test_rss_native_cursor_and_reordered_repeat_feed(self):
        def feed(ids):
            return ('<rss version="2.0"><channel><title>Demo</title><link>https://example.org</link>'
                    '<description>Demo</description>' + ''.join(
                    f'<item><guid>{i}</guid><link>https://example.org/article/{i}</link><title>Update</title>'
                    '<description>Content</description></item>' for i in ids) + '</channel></rss>').encode()
        first = rss_from_bytes(self.src, feed([3, 2, 1]))
        self.assertEqual(first.cursor, {"native_item_id": "3"})
        self.assertEqual(self.store.persist_fetch(self.src, first), 3)
        second = rss_from_bytes(self.src, feed([2, 3, 1]))
        self.assertEqual(self.store.persist_fetch(self.src, second), 0)
        self.assertEqual(self.count("contents"), 3)

    def test_all_items_persist_but_daily_cap_keeps_backlog(self):
        file = self.units_file([self.item(i) for i in range(8)])
        first = run_pipeline(self.store, self.cfg, self.today, "text_only", file)
        self.assertEqual(first["selection"]["selected"], 2)
        self.assertEqual(self.count("contents"), 8)
        self.assertEqual(self.count("coverage"), 2)
        second = run_pipeline(self.store, self.cfg, self.tomorrow, "text_only", file)
        self.assertEqual(second["selection"]["selected"], 2)
        self.assertEqual(self.count("coverage"), 4)

    def test_cross_transport_dedup_and_same_title_distinct_urls(self):
        self.store.persist_fetch(self.src, FetchResult(items=[self.item(1), self.item(2)]))
        other = {**self.src, "name": "Blog", "type": "blog", "site_url": "https://example.org/blog",
                 "canonical_url": "https://example.org/blog", "source_id": stable_id("src", "https://example.org/blog")}
        cfg = {**self.cfg, "sources": [self.src, other]}
        self.store.sync_sources(cfg)
        self.store.persist_fetch(other, FetchResult(items=[self.item(1, url="https://example.org/article/1?utm_source=blog",
                                                                   body="A much more complete version of the original article text.")]))
        self.assertEqual(self.count("contents"), 2)
        self.assertEqual(self.count("observations"), 3)
        run = self.store.ensure_run(self.today, self.cfg, "text_only")
        self.store.select(run, self.cfg)
        units = self.store.units(self.store.episodes(run["run_id"])[0]["episode_id"])
        self.assertEqual(len(units), 2)
        self.assertTrue(any(u["body"].startswith("A much more") for u in units))

    def test_transaction_failure_rolls_back_items_and_cursor(self):
        first = FetchResult(items=[self.item(1)], cursor={"native_item_id": "1"})
        self.store.persist_fetch(self.src, first)
        bad = FetchResult(items=[self.item(2), self.item(3, url="file:///invalid")], cursor={"native_item_id": "3"})
        with self.assertRaises(ValueError):
            self.store.persist_fetch(self.src, bad)
        self.assertEqual(self.count("contents"), 1)
        self.assertEqual(self.store.fetch_state(self.src["source_id"]), first.cursor)

    def test_partial_fetch_never_advances_cursor(self):
        first = FetchResult(items=[self.item(1)], cursor={"native_item_id": "1"})
        self.store.persist_fetch(self.src, first)
        self.store.persist_fetch(self.src, FetchResult(items=[self.item(2)], cursor={"native_item_id": "2"},
                                                      status="partial", completeness="partial"))
        self.assertEqual(self.count("contents"), 2)
        self.assertEqual(self.store.fetch_state(self.src["source_id"]), first.cursor)

    def test_title_only_waits_for_enrichment(self):
        self.store.persist_fetch(self.src, FetchResult(items=[self.item(body="")]))
        run = self.store.ensure_run(self.today, self.cfg, "text_only")
        self.store.select(run, self.cfg)
        self.assertEqual(self.store.episodes(run["run_id"]), [])
        self.assertEqual(self.count("coverage"), 0)
        self.store.persist_fetch(self.src, FetchResult(items=[self.item()]))
        other = self.store.ensure_run(self.tomorrow, self.cfg, "text_only")
        self.assertEqual(len(self.store.select(other, self.cfg)), 1)

    def test_same_day_retry_is_immutable_and_does_not_refetch(self):
        file = self.units_file([self.item()])
        report = run_pipeline(self.store, self.cfg, self.today, "text_only", file)
        episode = self.store.episodes(report["run_id"])[0]
        manifest = json.loads(episode["artifact_manifest"])
        files = [Path(manifest[k]) for k in ("script", "units")]
        before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in files]
        with patch("focu.daily.pipeline.collect", side_effect=AssertionError("must not fetch")):
            again = run_pipeline(self.store, self.cfg, self.today, "text_only")
        self.assertEqual(again["status"], "reused")
        self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns) for p in files])
        self.assertEqual(self.count("coverage"), 1)

    def test_tts_failure_does_not_cover_or_lose_selected_items(self):
        file = self.units_file([self.item()])
        cfg = {**self.cfg, "tts_argv": [sys.executable, "-c", "import sys;sys.exit(1)", "{input}", "{output}"]}
        first = run_pipeline(self.store, cfg, self.today, "audio", file)
        self.assertEqual(first["status"], "failed")
        self.assertEqual(self.count("coverage"), 0)
        ep = self.store.episodes(first["run_id"])[0]
        self.assertEqual(ep["status"], "script_ready")
        self.assertEqual(len(self.store.units(ep["episode_id"])), 1)
        with patch("focu.daily.pipeline.collect", side_effect=AssertionError("must reuse frozen input")):
            again = run_pipeline(self.store, cfg, self.today, "audio")
        self.assertEqual(again["run_id"], first["run_id"])
        self.assertEqual(self.count("episodes"), 1)
        self.assertEqual(self.count("coverage"), 0)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires audio tools")
    def test_audio_resume_after_failure_and_publish_crash(self):
        marker = self.root / "tts-calls.txt"
        tts = self.root / "tts backend.py"
        tts.write_text('import pathlib,subprocess,sys\n'
                       f'with pathlib.Path({str(marker)!r}).open("a") as f: f.write("call\\n")\n'
                       'subprocess.run(["ffmpeg","-v","error","-y","-f","lavfi","-i",'
                       '"sine=frequency=440:duration=1","-c:a","libmp3lame",sys.argv[2]],check=True)\n')
        file = self.units_file([self.item()])
        cfg = {**self.cfg, "tts_argv": [sys.executable, "-c", "raise SystemExit(1)", "{input}", "{output}"]}
        first = run_pipeline(self.store, cfg, self.today, "audio", file)
        self.assertEqual(first["status"], "failed")
        cfg["tts_argv"] = [sys.executable, str(tts), "{input}", "{output}"]
        with patch.object(self.store, "finalize", side_effect=OSError("simulated crash after audio publication")):
            crashed = run_pipeline(self.store, cfg, self.today, "audio")
        self.assertEqual(crashed["status"], "failed")
        self.assertEqual(self.count("coverage"), 0)
        with patch("focu.daily.pipeline.collect", side_effect=AssertionError("must not re-fetch")):
            complete = run_pipeline(self.store, cfg, self.today, "audio")
        self.assertEqual(complete["status"], "completed")
        self.assertEqual(marker.read_text(), "call\n")
        self.assertEqual(self.count("coverage"), 1)
        self.assertEqual(self.store.episodes(first["run_id"])[0]["status"], "finalized")

    def test_failed_episode_is_not_selected_again_for_another_date(self):
        cfg = {**self.cfg, "tts_argv": [sys.executable, "-c", "raise SystemExit(1)", "{input}", "{output}"]}
        run_pipeline(self.store, cfg, self.today, "audio", self.units_file([self.item()]))
        run = self.store.ensure_run(self.tomorrow, cfg, "audio")
        self.assertEqual(self.store.select(run, cfg), [])
        self.assertEqual(self.count("coverage"), 0)

    def test_empty_fetch_keeps_persisted_backlog(self):
        ingest(self.store, self.cfg, self.today, self.units_file([self.item(1), self.item(2)]))
        ingest(self.store, self.cfg, self.today, self.units_file([]))
        self.assertEqual(self.count("contents"), 2)
        snapshot = json.loads((self.store.data_dir / "units" / f"{self.today}.json").read_text())
        self.assertEqual(len(snapshot), 2)

    def test_failed_source_is_visible_and_others_continue(self):
        self.config["sources"].append({"name": "Other", "type": "blog", "channel": "research",
                                       "site_url": "https://example.org/other"})
        self.reload_config()
        def collector(source, state):
            if source["name"] == "Other":
                raise TimeoutError("unavailable")
            return FetchResult(items=[self.item()])
        with patch("focu.daily.pipeline.collect", side_effect=collector):
            report = run_pipeline(self.store, self.cfg, self.today, "text_only")
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(self.count("coverage"), 1)
        self.assertEqual(report["fetch"]["sources"][1]["error_code"], "fetch_failed")

    def test_outage_can_use_durable_backlog_without_hiding_failure(self):
        self.store.persist_fetch(self.src, FetchResult(items=[self.item()]))
        with patch("focu.daily.pipeline.collect", side_effect=TimeoutError("offline")):
            report = run_pipeline(self.store, self.cfg, self.today, "text_only")
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(report["fetch"]["sources"][0]["status"], "error")
        self.assertEqual(self.count("coverage"), 1)

    def test_config_change_cannot_rewrite_frozen_run(self):
        run_pipeline(self.store, self.cfg, self.today, "text_only", self.units_file([self.item()]))
        self.config["channels"][0]["language"] = "zh"
        self.reload_config()
        with self.assertRaises(FewError) as ex:
            run_pipeline(self.store, self.cfg, self.today, "text_only")
        self.assertEqual(ex.exception.code, "frozen_run")

    def test_expired_content_identity_survives(self):
        old = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        self.store.persist_fetch(self.src, FetchResult(items=[self.item(published_at=old)]))
        run = self.store.ensure_run(self.today, self.cfg, "text_only")
        self.store.select(run, self.cfg)
        self.assertEqual(self.store.episodes(run["run_id"]), [])
        self.assertEqual(self.count("contents"), 1)
        self.assertEqual(self.store.db.execute("SELECT state FROM candidates").fetchone()[0], "expired")

    def test_unknown_publication_time_ages_from_first_discovery(self):
        self.store.persist_fetch(self.src, FetchResult(items=[self.item()]))
        first = self.store.db.execute("SELECT expires_at FROM candidates").fetchone()[0]
        with patch("focu.daily.store.now_utc", return_value=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat()):
            self.store.persist_fetch(self.src, FetchResult(items=[self.item()]))
        self.assertEqual(self.store.db.execute("SELECT expires_at FROM candidates").fetchone()[0], first)

    def test_external_input_cannot_expand_source_boundary(self):
        with self.assertRaises(FewError):
            ingest(self.store, self.cfg, self.today, self.units_file([self.item(source="Unapproved")]))
        self.assertEqual(self.count("contents"), 0)

    def test_lock_rejects_concurrent_process(self):
        code = 'from focu.daily.pipeline import run_lock\nfrom focu.daily.errors import FewError\nimport sys\ntry:\n with run_lock(sys.argv[1]): pass\nexcept FewError as e:\n sys.exit(e.exit_code)\n'
        with run_lock(self.store.data_dir):
            proc = subprocess.run([sys.executable, "-c", code, str(self.store.data_dir)], capture_output=True, timeout=10)
        self.assertEqual(proc.returncode, 5, proc.stderr.decode())

    def test_cli_json_error_and_legacy_guard(self):
        from focu.daily.cli import execute, parser
        old_dir = self.root / "legacy"
        (old_dir / "episodes").mkdir(parents=True)
        old = old_dir / "state.json"
        old.write_text('{"sources":{}}')
        args = parser().parse_args(["run", "--config", str(self.config_path), "--data-dir", str(old_dir)])
        with self.assertRaises(FewError) as ex:
            execute(args)
        self.assertEqual(ex.exception.code, "legacy_data")
        self.assertEqual(old.read_text(), '{"sources":{}}')
        self.assertFalse((old_dir / "few.sqlite3").exists())

    def test_legacy_import_is_additive_and_coverage_is_explicit(self):
        from focu.daily.legacy import import_legacy
        old = self.root / "old"
        audits = old / "episodes" / "2026-10-01"
        audits.mkdir(parents=True)
        snapshot = audits / "research-units.json"
        snapshot.write_text(json.dumps([self.item()]))
        (audits / "research-script.txt").write_text("Host: Prior episode.\n")
        (old / "state.json").write_text('{"sources":{"Test":{"last_item_id":"rss:1"}}}')
        before = snapshot.read_bytes()
        imported = import_legacy(self.store, self.cfg, old)
        self.assertEqual(imported["covered"], 0)
        self.assertEqual(self.count("contents"), 1)
        self.assertIsNone(self.store.fetch_state(self.src["source_id"]))
        trusted = import_legacy(self.store, self.cfg, old, register_coverage=True)
        self.assertEqual(trusted["covered"], 1)
        again = import_legacy(self.store, self.cfg, old, register_coverage=True)
        self.assertEqual(again["covered"], 0)
        self.assertEqual(self.count("episodes"), 1)
        self.assertEqual(snapshot.read_bytes(), before)
        self.assertEqual((Path(imported["backup"]) / "episodes/2026-10-01/research-units.json").read_bytes(), before)

    def test_legacy_audio_attestation_requires_audio(self):
        from focu.daily.legacy import import_legacy
        old = self.root / "old"
        audits = old / "episodes/2026-10-01"
        audits.mkdir(parents=True)
        (audits / "research-units.json").write_text(json.dumps([self.item()]))
        (audits / "research-script.txt").write_text("Host: Test.\n")
        with self.assertRaises(FewError):
            import_legacy(self.store, {**self.cfg, "output_mode": "audio"}, old, register_coverage=True)
        self.assertEqual(self.count("coverage"), 0)
        self.assertEqual(self.count("contents"), 0)

    def test_legacy_unknown_source_is_rejected_before_import(self):
        from focu.daily.legacy import import_legacy
        old = self.root / "old"
        (old / "units").mkdir(parents=True)
        (old / "units/2026-10-01.json").write_text(json.dumps([self.item(source="Other")]))
        with self.assertRaises(FewError):
            import_legacy(self.store, self.cfg, old)
        self.assertEqual(self.count("contents"), 0)


if __name__ == "__main__":
    unittest.main()
