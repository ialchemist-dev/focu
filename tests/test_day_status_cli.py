"""Wave 26: the owner-visible day-status surface (`focu daily day-status`).

Wave 23's honest record was assembled and persisted as a `day_status`
stage row, but nothing outside pipeline.py read it. This CLI surface is
strictly read-only: it prints the stored record (human lines, or the
record exactly as recorded with --json), or one explicit line when no
record exists for the date — it never assembles a substitute record
from other data. Fixtures are built through the real pipeline, the
same helpers as tests/test_day_status.py.
"""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from focu.daily.cli import main as daily_main
from focu.daily.collectors import FetchResult
from focu.daily.config import load_config
from focu.daily.pipeline import run_pipeline
from focu.daily.store import Store


class DayStatusCliTests(unittest.TestCase):
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
        self.data_dir = self.root / "data"
        self.store = Store(self.data_dir)
        self.store.sync_sources(self.cfg)
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

    def stored_raw(self, run_id):
        row = self.store.db.execute(
            "SELECT report_json FROM stage_runs WHERE run_id=? AND stage='day_status'",
            (run_id,)).fetchone()
        return row[0] if row else None

    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = daily_main(list(argv))
        return code, out.getvalue()

    def day_status(self, *extra):
        return self.run_cli("day-status", "--data-dir", str(self.data_dir), *extra)

    def clean_day(self):
        return run_pipeline(self.store, self.cfg, self.today, "text_only",
                            self.units_file([self.item()]))

    # -- rendering ------------------------------------------------------

    def test_clean_day_renders_fully(self):
        result = self.clean_day()
        stored = json.loads(self.stored_raw(result["run_id"]))
        code, out = self.day_status()
        self.assertEqual(code, 0)
        self.assertIn(f"Day status for {self.today} — success", out)
        # The record's own summary, verbatim.
        self.assertIn(stored["summary"], out)
        # Per-source line: name and the record's counts.
        self.assertIn("- Test: collected 1, considered 1, selected 1", out)
        # Audio roll-up line.
        self.assertIn("Audio: 0 synthesized, 0 text-only, 1 not attempted", out)

    def test_thin_day_renders_its_summary_verbatim(self):
        with patch("focu.daily.pipeline.collect",
                   return_value=FetchResult(items=[], status="empty")):
            result = run_pipeline(self.store, self.cfg, self.today, "text_only")
        stored = json.loads(self.stored_raw(result["run_id"]))
        self.assertTrue(stored["summary"].startswith("Nothing new"))
        code, out = self.day_status("--date", self.today)
        self.assertEqual(code, 0)
        self.assertIn(stored["summary"], out)
        self.assertIn("- Test: collected 0, considered 0, selected 0", out)

    def test_partial_failure_names_the_failing_source(self):
        self.config["sources"].append(
            {"name": "Other", "type": "blog", "channel": "research",
             "site_url": "https://example.org/other"})
        self.reload_config()
        self.store.sync_sources(self.cfg)

        def collector(source, state):
            if source["name"] == "Other":
                raise TimeoutError("unavailable")
            return FetchResult(items=[self.item()])

        with patch("focu.daily.pipeline.collect", side_effect=collector):
            result = run_pipeline(self.store, self.cfg, self.today, "text_only")
        stored = json.loads(self.stored_raw(result["run_id"]))
        self.assertEqual(stored["outcome"], "partial_failure")
        code, out = self.day_status()
        self.assertEqual(code, 0)
        self.assertIn(f"Day status for {self.today} — partial_failure", out)
        self.assertIn(stored["summary"], out)
        # The failing source is named on its own line, as the record names it.
        self.assertIn("- Other: collected 0, considered 0, selected 0; "
                      "fetch error (fetch_failed): ", out)
        self.assertIn("unavailable", out)
        self.assertIn("- Test: collected 1, considered 1, selected 1", out)

    def test_withholding_is_named_on_the_source_line(self):
        result = run_pipeline(self.store, self.cfg, self.today, "text_only",
                              self.units_file([self.item(i) for i in range(3)]))
        stored = json.loads(self.stored_raw(result["run_id"]))
        self.assertEqual(stored["outcome"], "success_with_withholdings")
        code, out = self.day_status()
        self.assertEqual(code, 0)
        self.assertIn(stored["summary"], out)
        self.assertIn("- Test: collected 3, considered 3, selected 2; "
                      "withheld: 1 over_cap", out)

    # -- --json -----------------------------------------------------------

    def test_json_prints_the_stored_record_byte_for_byte(self):
        result = self.clean_day()
        raw = self.stored_raw(result["run_id"])
        code, out = self.day_status("--json")
        self.assertEqual(code, 0)
        # Byte-for-byte as recorded (print adds only the trailing newline).
        self.assertEqual(out, raw + "\n")
        self.assertEqual(json.loads(out), json.loads(raw))

    # -- missing records ----------------------------------------------------

    def test_missing_record_for_a_date_with_no_run(self):
        self.clean_day()
        code, out = self.day_status("--date", "1999-01-01")
        self.assertEqual(code, 0)
        self.assertEqual(out, "No day-status record for 1999-01-01. "
                              "No run exists for that date.\n")

    def test_missing_record_for_an_unfinished_run(self):
        # F3: the missing-record line names the run's actual state.
        # This fixture (ensure_run only) is a run that never finished —
        # status "pending" — not a completed pre-Q5 run; the old line
        # called every record-less run "predates day-status assembly",
        # which misdiagnosed the rehearsal's failed day.
        self.store.ensure_run(self.today, self.cfg, "text_only")
        code, out = self.day_status("--date", self.today)
        self.assertEqual(code, 0)
        self.assertEqual(out, f"No day-status record for {self.today}. "
                              "The run has not finished; no day-status "
                              "record has been assembled yet.\n")

    def test_missing_record_for_a_completed_run_predates_day_status(self):
        # The genuine pre-Q5 shape: a completed run with no record.
        run = self.store.ensure_run(self.today, self.cfg, "text_only")
        with self.store.db:
            self.store.db.execute(
                "UPDATE runs SET status='completed' WHERE run_id=?",
                (run["run_id"],))
        code, out = self.day_status("--date", self.today)
        self.assertEqual(code, 0)
        self.assertEqual(out, f"No day-status record for {self.today}. "
                              "The run predates day-status assembly.\n")

    def test_missing_record_for_a_failed_run_says_so(self):
        # A failed run with no record (pre-D2b, or recording failed):
        # the line says the run failed, not that it predates assembly.
        run = self.store.ensure_run(self.today, self.cfg, "text_only")
        with self.store.db:
            self.store.db.execute(
                "UPDATE runs SET status='failed' WHERE run_id=?",
                (run["run_id"],))
        code, out = self.day_status("--date", self.today)
        self.assertEqual(code, 0)
        self.assertEqual(out, f"No day-status record for {self.today}. "
                              "The run failed and no day-status record "
                              "was assembled for it.\n")

    def test_failed_run_renders_its_failure_record(self):
        # D2b end to end: a compose failure leaves a record, and the
        # surface renders it — outcome failed, the failure named — with
        # no missing-record line anywhere.
        from focu.daily.errors import FewError
        qc_error = FewError("briefing script omitted source items or "
                            "figures", "briefing_qc_failed", 4)
        with patch("focu.daily.pipeline.compose", side_effect=qc_error):
            with self.assertRaises(FewError):
                run_pipeline(self.store, self.cfg, self.today, "text_only",
                             self.units_file([self.item()]))
        code, out = self.day_status()
        self.assertEqual(code, 0)
        self.assertIn(f"Day status for {self.today} — failed", out)
        self.assertIn("- compose: briefing script omitted source items "
                      "or figures", out)
        self.assertNotIn("No day-status record", out)

    def test_missing_store_prints_one_line_and_creates_nothing(self):
        missing = self.root / "no-such-data"
        code, out = self.run_cli("day-status", "--data-dir", str(missing),
                                 "--date", "2026-01-01")
        self.assertEqual(code, 0)
        self.assertEqual(out, "No day-status record for 2026-01-01. "
                              "No run exists for that date.\n")
        # Read-only: the surface must not initialize a store to say so.
        self.assertFalse(missing.exists())

    # -- default date -------------------------------------------------------

    def test_default_date_picks_the_latest_run(self):
        yesterday = (datetime.now(timezone.utc).date()
                     - timedelta(days=1)).isoformat()
        run_pipeline(self.store, self.cfg, yesterday, "text_only",
                     self.units_file([self.item()]))
        with patch("focu.daily.pipeline.collect",
                   return_value=FetchResult(items=[], status="empty")):
            result = run_pipeline(self.store, self.cfg, self.today, "text_only")
        stored = json.loads(self.stored_raw(result["run_id"]))
        code, out = self.day_status()
        self.assertEqual(code, 0)
        self.assertIn(f"Day status for {self.today} — ", out)
        self.assertIn(stored["summary"], out)
        self.assertNotIn(f"Day status for {yesterday} — ", out)

    # -- wiring -------------------------------------------------------------

    def test_top_level_cli_dispatches_day_status(self):
        from focu.cli import main as focu_main
        result = self.clean_day()
        stored = json.loads(self.stored_raw(result["run_id"]))
        out = io.StringIO()
        with redirect_stdout(out):
            code = focu_main(["daily", "day-status", "--data-dir",
                              str(self.data_dir), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue()), stored)


if __name__ == "__main__":
    unittest.main()
