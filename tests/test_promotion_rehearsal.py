"""Plan-4 direction 1: the promotion rehearsal.

Every wave of the 2026-11-17 run tested its own slice; nothing had ever
run the composed dev-main system as one exercise. This test is that
exercise, on a scratch runtime only (a temp dir; no production path is
read or written, no network is touched — pack liveness checks are off
and the daily run consumes a local units file):

  pack install -> daily pipeline (text-only) -> day-status record ->
  `focu daily day-status` CLI -> reader publisher (registered item +
  daily compilation covering it) -> owner-carried reading-summary
  export marking the COMPILATION -> `focu learn ingest` fan-out ->
  `focu learn` proposals sparsity/stop-rule surface.

The rehearsal's load-bearing assertions are identity assertions: the
source_id minted by pack install is the source_id on the pipeline's
selected unit, is the key of that source's sparsity slot, and the
publisher's compilation coverage resolves to the pipeline's content_id —
one identity across every subsystem, or the composed system leaks
attention at the seams (the Q6/F1 lessons, exercised end to end).

What the rehearsal deliberately does NOT cover is named in
docs/dev-team/promotion-rehearsal.md: audio/TTS, live collectors, and
the production host step that writes publisher delivery folders.
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from focu import learn
from focu.daily.cli import main as daily_main
from focu.daily.config import load_config
from focu.daily.pipeline import run_pipeline
from focu.daily.store import Store
from focu.feedback import FeedbackStore
from focu.packs import install_pack

READER_DIR = (Path(__file__).resolve().parent.parent
              / "experiments" / "muse-artifact-reader")
sys.path.insert(0, str(READER_DIR))
from publish import build as publish_build  # noqa: E402

RECORD_TEXT = """# Focu learned preferences

**Version:** 2026-11-17.1
**Owner:** one person (Focu's owner)
**Change discipline:** written only by owner acts.

```yaml
version: "2026-11-17.1"
entries: []
```

## Changelog

- **2026-11-17 — v2026-11-17.1:** Record created.
"""

PACK = {
    "schema_version": 1, "id": "rehearsal-pack", "title": "Rehearsal Pack",
    "version": "1.0.0", "curator": {"name": "Rehearsal Curator"},
    "description": "A pack used only by the promotion rehearsal.",
    "tags": ["test"], "coverage": "Only rehearsal fixtures.",
    "verified_at": "2026-11-17",
    "sources": [{
        "id": "alice", "name": "Alice Example", "type": "rss",
        "channel": "research", "platform": "Ghost",
        "homepage": "https://alice.example.com/",
        "feed_url": "https://alice.example.com/feed",
        "cadence": {"posts_per_month": 1.0,
                    "basis": "feed items dated 2026-10-01",
                    "as_of": "2026-11-17"},
        "verified_at": "2026-11-17", "enabled": True}],
}


class PromotionRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime.now(timezone.utc)
        self.today = self.now.date().isoformat()
        # Scratch registry: an empty v2 daily config, nothing else.
        self.config_path = self.root / "sources.yaml"
        self.config_path.write_text(json.dumps({
            "version": 2, "timezone": "UTC", "output_mode": "text_only",
            "channels": [{"id": "research", "language": "en",
                          "max_minutes": 12}],
            "sources": []}))
        installed = install_pack(PACK, self.config_path, check_feeds=False)
        self.assertTrue(installed["applied"])
        self.pack_source_id = installed["plan"]["adds"][0]["source_id"]
        self.cfg = load_config(self.config_path)
        self.data_dir = self.root / "data"
        self.store = Store(self.data_dir)
        self.addCleanup(self.store.close)
        self.store.sync_sources(self.cfg)
        self.record = self.root / "learned-preferences.md"
        self.record.write_text(RECORD_TEXT, encoding="utf-8")
        self.feedback_db = self.root / "focu.sqlite3"

    # -- legs ------------------------------------------------------------

    def run_day(self):
        units_file = self.root / "units.json"
        units_file.write_text(json.dumps([{
            "native_item_id": "1", "source": "Alice Example",
            "url": "https://alice.example.com/post-1",
            "title": "Alice on rehearsal",
            "body": "Alice published a short update about the rehearsal."}]))
        return run_pipeline(self.store, self.cfg, self.today,
                            "text_only", units_file)

    def selected_unit(self, result):
        episodes = self.store.episodes(result["run_id"])
        self.assertEqual(len(episodes), 1)
        units = self.store.units(episodes[0]["episode_id"])
        self.assertEqual(len(units), 1)
        return episodes[0], units[0]

    def publish(self, episode, unit):
        deliveries = self.root / "deliveries"
        item_dir = deliveries / "alice-on-rehearsal"
        item_dir.mkdir(parents=True)
        (item_dir / "article.md").write_text(
            f"# {unit['title']}\n\n{unit['body']}", encoding="utf-8")
        (item_dir / "content.json").write_text(json.dumps({
            "content_id": unit["content_id"],
            "origin": "registered_source",
            "podcast_mode": "daily_compilation",
            "source_name": "Alice Example",
            "source_url": unit["url"]}), encoding="utf-8")
        compilation_id = f"daily-{self.today}"
        comp_dir = deliveries / f"daily-briefing-{self.today.replace('-', '')}"
        comp_dir.mkdir(parents=True)
        (comp_dir / "article.md").write_text(episode["script"],
                                             encoding="utf-8")
        (comp_dir / "content.json").write_text(json.dumps({
            "content_id": compilation_id,
            "origin": "daily_compilation",
            "podcast_mode": "daily_compilation",
            "covered_content_ids": [unit["content_id"]],
            "published_at": self.today}), encoding="utf-8")
        bundle = self.root / "bundle"
        self.assertEqual(
            publish_build(deliveries, bundle, READER_DIR / "index.html", 15),
            2)
        data = json.loads((bundle / "assets" / "episodes.json")
                          .read_text(encoding="utf-8"))
        return compilation_id, data["items"]

    def mark_compilation(self, compilation_id, unit):
        now_iso = self.now.isoformat()
        export = self.root / "focu-reading-summary.json"
        export.write_text(json.dumps({
            "format": "focu-reading-summary", "version": 1,
            "exported_at": now_iso,
            "items": [{
                "content_id": compilation_id, "source": "Focu",
                "status": "not_for_me", "via": None, "archived": True,
                "covered_content_ids": [unit["content_id"]],
                "not_for_me": {"at": now_iso, "source": "Focu"},
                "audio": None, "audio_pos_seconds": None,
                "article_pos_px": None, "updated_at": now_iso}]}),
            encoding="utf-8")
        return learn.ingest_reading_summary(export, self.feedback_db)

    # -- the composed exercise -------------------------------------------

    def test_composed_chain_end_to_end(self):
        # Leg 1+2: the pack-installed source flows through a real daily
        # run; the run's own day-status record reconciles.
        result = self.run_day()
        self.assertEqual(result["status"], "completed")
        status = result["day_status"]
        self.assertEqual(status["outcome"], "success")
        self.assertEqual(status["discrepancies"], [])
        episode, unit = self.selected_unit(result)
        # One identity: pack install -> pipeline unit.
        self.assertEqual(unit["source_id"], self.pack_source_id)
        self.assertEqual(unit["source"], "Alice Example")

        # Leg 3: the owner-visible surface prints the stored record —
        # its summary verbatim, the pack source named with its counts.
        out = io.StringIO()
        with redirect_stdout(out):
            code = daily_main(["day-status", "--data-dir",
                               str(self.data_dir)])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn(status["summary"], text)
        self.assertIn("- Alice Example: collected 1, considered 1, "
                      "selected 1", text)

        # Leg 4: the publisher composes the run into a reader bundle —
        # the compilation covers the pipeline's unit, and the covered
        # item keeps its real source name and its original URL.
        compilation_id, items = self.publish(episode, unit)
        compilation = next(i for i in items
                           if i["content_id"] == compilation_id)
        self.assertEqual(compilation["covered_content_ids"],
                         [unit["content_id"]])
        covered = next(i for i in items
                       if i["content_id"] == unit["content_id"])
        self.assertEqual(covered["source"], "Alice Example")
        self.assertEqual(covered["original_url"], unit["url"])

        # Leg 5: a Not-for-me mark on the COMPILATION (the owner's main
        # surface) fans out through ingest to the covered unit — one
        # attributed event, nothing pooled as unattributed.
        record_before = self.record.read_bytes()
        ingest = self.mark_compilation(compilation_id, unit)
        self.assertEqual(ingest["events_recorded"], 1)
        self.assertEqual(ingest["events_by_kind"], {"not_useful": 1})
        self.assertEqual(ingest["fanned_out_compilations"], 1)
        events = FeedbackStore(self.feedback_db).list()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["target_id"], unit["content_id"])
        self.assertEqual(events[0]["kind"], "not_useful")

        # Leg 6: proposals on the composed store — the honest cold
        # state. One attributed event is below every floor, so the
        # engine drafts nothing and says why, with the pack source's
        # sparsity slot keyed by the same source_id as legs 1-2.
        result = learn.generate_proposals(
            self.feedback_db, self.data_dir, self.record, now=self.now)
        self.assertEqual(result["proposals"], [])
        self.assertEqual(result["attributed_events"], 1)
        self.assertEqual(
            result["signal_reason"],
            "insufficient attributed signal: 1 events in 30 days")
        self.assertIsNone(result["record_error"])
        slot = result["sparsity"]["sources"][self.pack_source_id]
        self.assertEqual(slot["name"], "Alice Example")
        self.assertEqual(slot["delivered"], 1)
        self.assertEqual(slot["negative"], 1)
        # The whole exercise never wrote the preference record.
        self.assertEqual(self.record.read_bytes(), record_before)

    def test_rehearsal_is_repeatable_without_double_counting(self):
        # A rehearsal (and a promotion) must be safe to re-run: the
        # same day's pipeline run is reused with its stored day-status,
        # and re-ingesting the same export records nothing new.
        first = self.run_day()
        episode, unit = self.selected_unit(first)
        compilation_id, _ = self.publish(episode, unit)
        self.assertEqual(
            self.mark_compilation(compilation_id, unit)["events_recorded"],
            1)
        second = run_pipeline(self.store, self.cfg, self.today,
                              "text_only")
        self.assertEqual(second["status"], "reused")
        self.assertEqual(second["day_status"], first["day_status"])
        again = self.mark_compilation(compilation_id, unit)
        self.assertEqual(again["events_recorded"], 0)
        self.assertEqual(again["events_already_recorded"], 1)
        self.assertEqual(len(FeedbackStore(self.feedback_db).list()), 1)


if __name__ == "__main__":
    unittest.main()
