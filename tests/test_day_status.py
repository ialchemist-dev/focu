"""Q5: the honest day-status assembly (PM sweep Wave F).

The day status is assembled from the stage reports the run actually
produced — the ingest report, the selection_accounting row selection
writes about itself, and the finalize outcomes — and it reconciles:
collected/considered/selected/withheld must add up per source, or the
record flags a discrepancy and downgrades the outcome instead of
silently passing. Fixtures: a clean day, withheld items (over cap,
title-only awaiting enrichment, expired, paused by the owner), a
failing source, a text-only audio day, a synthesized audio day, an
empty day, and a tampered stage report.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from focu.daily.collectors import FetchResult
from focu.daily.config import load_config
from focu.daily.pipeline import (assemble_day_status, compose,
                                 finalize_episodes, ingest, run_pipeline)
from focu.daily.store import Store


def record_text(entries_block):
    return f"""# Focu learned preferences

**Version:** 2026-11-17.1
**Owner:** one person (Focu's owner)
**Change discipline:** written only by owner acts.

```yaml
version: "2026-11-17.1"
entries:
{entries_block}
```

## Changelog

- **2026-11-17 — v2026-11-17.1:** Record created.
"""


def pause_block(target, created="2026-11-17"):
    return f"""  - id: lp-001
    kind: source_pause
    target: {target}
    value: true
    statement: "Pause this source."
    provenance: owner-accepted
    evidence: "test fixture"
    created_at: {created}
    review_after: 2027-02-15
    status: active
"""


class DayStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config_path = self.root / "sources.yaml"
        self.config = {"version": 2, "timezone": "UTC", "output_mode": "text_only",
                       "channels": [{"id": "research", "language": "en", "max_minutes": 12}],
                       "sources": [{"name": "Test", "type": "rss", "channel": "research",
                                    "feed_url": "https://example.org/feed",
                                    "max_items_per_day": 2}]}
        self.reload_config()
        self.store = Store(self.root / "data")
        self.store.sync_sources(self.cfg)
        self.src = self.cfg["sources"][0]
        self.today = datetime.now(timezone.utc).date().isoformat()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def reload_config(self):
        self.config_path.write_text(json.dumps(self.config))
        self.cfg = load_config(self.config_path)

    def item(self, i=1, **changes):
        return {"native_item_id": str(i), "source": "Test",
                "url": f"https://example.org/article/{i}",
                "title": "Daily update",
                "body": "The source published a short update.", **changes}

    def units_file(self, items):
        path = self.root / "units.json"
        path.write_text(json.dumps(items))
        return path

    def stage_report(self, run_id, stage):
        row = self.store.db.execute(
            "SELECT report_json FROM stage_runs WHERE run_id=? AND stage=?",
            (run_id, stage)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def source_row(self, status, name="Test"):
        return next(s for s in status["sources"] if s["source"] == name)

    # -- clean day -----------------------------------------------------

    def test_clean_day_reconciles_and_reports_success(self):
        result = run_pipeline(self.store, self.cfg, self.today, "text_only",
                              self.units_file([self.item()]))
        # Every pre-existing run-result field is intact; day_status is additive.
        for key in ("status", "run_id", "fetch", "gate", "selection",
                    "compose", "episodes", "warnings"):
            self.assertIn(key, result)
        status = result["day_status"]
        self.assertEqual(status["outcome"], "success")
        self.assertEqual(status["discrepancies"], [])
        self.assertEqual(status["failures"], [])
        row = self.source_row(status)
        self.assertEqual(row["fetch"]["status"], "success")
        self.assertEqual(row["collected"], 1)
        self.assertEqual(row["considered"], 1)
        self.assertEqual(row["selected"], 1)
        self.assertEqual(row["withheld"], [])
        self.assertEqual(row["not_ready"], [])
        self.assertEqual(status["totals"]["selected"], 1)
        episode_id = self.store.episodes(result["run_id"])[0]["episode_id"]
        self.assertEqual(status["audio"]["not_attempted"], [episode_id])
        self.assertEqual(status["episodes"][0]["audio"]["outcome"], "not_attempted")
        self.assertTrue(status["summary"].startswith("1 item(s) selected"))
        # The select stage report keeps its exact pre-Q5 shape.
        self.assertEqual(self.stage_report(result["run_id"], "select"),
                         {"selected": 1})
        # The day status is persisted as a stage row, and a reused run
        # reports the same account.
        self.assertEqual(self.stage_report(result["run_id"], "day_status"), status)
        again = run_pipeline(self.store, self.cfg, self.today, "text_only")
        self.assertEqual(again["status"], "reused")
        self.assertEqual(again["day_status"], status)

    def test_empty_day_is_honestly_nothing_new(self):
        with patch("focu.daily.pipeline.collect",
                   return_value=FetchResult(items=[], status="empty")):
            result = run_pipeline(self.store, self.cfg, self.today, "text_only")
        status = result["day_status"]
        self.assertEqual(status["outcome"], "success")
        self.assertEqual(status["totals"]["selected"], 0)
        self.assertEqual(status["discrepancies"], [])
        self.assertTrue(status["summary"].startswith("Nothing new"))

    # -- withholdings ---------------------------------------------------

    def test_over_cap_withholding_is_named(self):
        result = run_pipeline(self.store, self.cfg, self.today, "text_only",
                              self.units_file([self.item(i) for i in range(3)]))
        status = result["day_status"]
        self.assertEqual(status["outcome"], "success_with_withholdings")
        self.assertEqual(status["discrepancies"], [])
        row = self.source_row(status)
        self.assertEqual(row["collected"], 3)
        self.assertEqual(row["considered"], 3)
        self.assertEqual(row["selected"], 2)
        self.assertEqual(row["withheld"], [{"count": 1, "reason": "over_cap"}])
        self.assertIn("1 item(s) withheld (1 over_cap)", status["summary"])

    def test_title_only_item_is_named_not_ready(self):
        # The pending-transcript / pending-body shape in this codebase: an
        # item persisted with no body is durable but never selection-ready.
        items = [self.item(1), self.item(2, body="")]
        with patch("focu.daily.pipeline.collect",
                   return_value=FetchResult(items=items)):
            result = run_pipeline(self.store, self.cfg, self.today, "text_only")
        status = result["day_status"]
        self.assertEqual(status["outcome"], "success_with_withholdings")
        self.assertEqual(status["discrepancies"], [])
        row = self.source_row(status)
        self.assertEqual(row["collected"], 2)
        self.assertEqual(row["considered"], 1)
        self.assertEqual(row["selected"], 1)
        self.assertEqual(row["not_ready"],
                         [{"count": 1, "reason": "needs_enrichment"}])

    def test_expired_candidate_is_named_not_ready(self):
        old = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        self.store.persist_fetch(self.src, FetchResult(
            items=[self.item(published_at=old)]))
        run = self.store.ensure_run(self.today, self.cfg, "text_only")
        self.store.select(run, self.cfg)
        status = assemble_day_status(self.store, self.cfg, run, outcomes=[])
        self.assertEqual(status["discrepancies"], [])
        row = self.source_row(status)
        self.assertEqual(row["considered"], 0)
        self.assertEqual(row["selected"], 0)
        self.assertEqual(row["not_ready"], [{"count": 1, "reason": "expired"}])
        self.assertEqual(status["outcome"], "success_with_withholdings")

    def test_paused_by_learning_withholding_is_named(self):
        record = self.root / "learned-preferences.md"
        record.write_text(record_text(pause_block(self.src["source_id"])))
        run = self.store.ensure_run(self.today, self.cfg, "text_only")
        fetch_report = ingest(self.store, self.cfg, self.today,
                              self.units_file([self.item()]))
        self.store.stage(run["run_id"], "ingest", "success", fetch_report)
        self.store.select(run, self.cfg, learned_record_path=record)
        compose(self.store, self.cfg, run)
        outcomes = finalize_episodes(self.store, self.cfg, run)
        status = assemble_day_status(self.store, self.cfg, run,
                                     fetch_report=fetch_report,
                                     outcomes=outcomes)
        self.assertEqual(status["discrepancies"], [])
        row = self.source_row(status)
        self.assertEqual(row["considered"], 1)
        self.assertEqual(row["selected"], 0)
        self.assertEqual(row["withheld"],
                         [{"count": 1, "reason": "paused_by_learning"}])
        self.assertEqual(status["outcome"], "success_with_withholdings")
        self.assertEqual(len(status["learned_paused"]), 1)
        self.assertIn("Paused by you on 2026-11-17", status["learned_paused"][0])
        self.assertIn("Paused by you on", status["summary"])
        self.assertIn("Today is thin", status["summary"])

    # -- failures --------------------------------------------------------

    def test_failing_source_is_partial_failure_and_named(self):
        self.config["sources"].append(
            {"name": "Other", "type": "blog", "channel": "research",
             "site_url": "https://example.org/other"})
        self.reload_config()

        def collector(source, state):
            if source["name"] == "Other":
                raise TimeoutError("unavailable")
            return FetchResult(items=[self.item()])

        with patch("focu.daily.pipeline.collect", side_effect=collector):
            result = run_pipeline(self.store, self.cfg, self.today, "text_only")
        self.assertEqual(result["status"], "degraded")  # prior behavior intact
        status = result["day_status"]
        self.assertEqual(status["outcome"], "partial_failure")
        self.assertEqual(status["discrepancies"], [])
        self.assertEqual(len(status["failures"]), 1)
        failure = status["failures"][0]
        self.assertEqual(failure["stage"], "ingest")
        self.assertEqual(failure["source"], "Other")
        self.assertEqual(failure["error_code"], "fetch_failed")
        self.assertIn("unavailable", failure["message"])
        other = self.source_row(status, "Other")
        self.assertEqual(other["fetch"]["status"], "error")
        self.assertEqual(other["collected"], 0)
        self.assertEqual(self.source_row(status)["selected"], 1)
        self.assertIn("1 collector(s) failed (Other)", status["summary"])

    # -- audio outcomes ---------------------------------------------------

    def test_text_only_audio_day_reports_its_reason(self):
        with patch("focu.tts.status",
                   return_value={"provider": "openai", "configured": False,
                                 "credential_source": "missing"}):
            result = run_pipeline(self.store, self.cfg, self.today, "audio",
                                  self.units_file([self.item()]))
        status = result["day_status"]
        self.assertEqual(status["outcome"], "success")
        episode_id = self.store.episodes(result["run_id"])[0]["episode_id"]
        self.assertEqual(status["episodes"][0]["audio"]["outcome"], "text_only")
        self.assertIn("not configured", status["episodes"][0]["audio"]["reason"])
        self.assertEqual(status["audio"]["text_only"][0]["episode_id"], episode_id)
        self.assertIn("audio text-only", status["summary"])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "requires audio tools")
    def test_synthesized_audio_day_reports_synthesized(self):
        tone = self.root / "tone.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=1", "-c:a", "libmp3lame",
                        str(tone)], check=True, capture_output=True)
        payload = tone.read_bytes()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}), \
                patch("focu.tts._request_speech", return_value=payload):
            result = run_pipeline(self.store, self.cfg, self.today, "audio",
                                  self.units_file([self.item()]))
        status = result["day_status"]
        self.assertEqual(status["outcome"], "success")
        episode_id = self.store.episodes(result["run_id"])[0]["episode_id"]
        self.assertEqual(status["audio"]["synthesized"], [episode_id])
        self.assertEqual(status["episodes"][0]["audio"]["outcome"], "synthesized")
        self.assertGreater(
            status["episodes"][0]["audio"]["duration_seconds"], 0.5)

    # -- reconciliation ----------------------------------------------------

    def test_compose_failure_still_leaves_a_failed_day_status(self):
        # D2b (promotion rehearsal): a run that dies at compose — the
        # rehearsal's case was briefing QC failing on an Import AI item
        # — used to leave no day-status record at all: the run stayed
        # "pending" and the CLI misreported the day as predating
        # day-status assembly. The record must exist exactly when the
        # day went wrong. (compose is patched to raise the exact error
        # it raises on a QC failure; what is under test is
        # run_pipeline's failure wiring, not compose itself.)
        from focu.daily.errors import FewError
        qc_error = FewError(
            "briefing script omitted source items or figures: "
            "[{\"issue\": \"missing_key_figures\"}]", "briefing_qc_failed", 4)
        with patch("focu.daily.pipeline.compose", side_effect=qc_error):
            with self.assertRaises(FewError):
                run_pipeline(self.store, self.cfg, self.today, "text_only",
                             self.units_file([self.item()]))
        run = self.store.ensure_run(self.today, self.cfg, "text_only")
        self.assertEqual(run["status"], "failed")
        record = self.stage_report(run["run_id"], "day_status")
        self.assertIsNotNone(record)
        self.assertEqual(record["outcome"], "failed")
        run_failures = [f for f in record["failures"]
                        if f.get("stage") == "compose"]
        self.assertEqual(len(run_failures), 1)
        self.assertIn("briefing", run_failures[0]["error"])
        self.assertIn("run failed at compose", record["summary"])
        # The accounting the completed stages wrote is present: the
        # item was collected and selected before compose failed.
        row = self.source_row(record)
        self.assertEqual(row["collected"], 1)
        self.assertEqual(row["selected"], 1)
        self.assertEqual(record["totals"]["selected"], 1)
        # The day-status stage row itself is staged as failed.
        stage_row = self.store.db.execute(
            "SELECT status FROM stage_runs WHERE run_id=? AND stage='day_status'",
            (run["run_id"],)).fetchone()
        self.assertEqual(stage_row[0], "failed")

    def test_tampered_accounting_is_flagged_never_passed(self):
        result = run_pipeline(self.store, self.cfg, self.today, "text_only",
                              self.units_file([self.item()]))
        run = self.store.ensure_run(self.today, self.cfg, "text_only")
        accounting = self.stage_report(result["run_id"], "selection_accounting")
        accounting["sources"][0]["considered"] = 5  # the lie: 5 considered, 1 accounted
        with self.store.db:
            self.store.db.execute(
                "UPDATE stage_runs SET report_json=? WHERE run_id=? AND stage='selection_accounting'",
                (json.dumps(accounting), result["run_id"]))
        status = assemble_day_status(self.store, self.cfg, run)
        self.assertEqual(status["outcome"], "partial_failure")
        self.assertEqual(len(status["discrepancies"]), 1)
        self.assertIn("Test", status["discrepancies"][0])
        self.assertIn("considered 5", status["discrepancies"][0])


if __name__ == "__main__":
    unittest.main()
