"""Offline contract tests for spoken/one-off research capture and UI snapshots."""
import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from focu.cli import main as focu_cli
from focu.intents import IntentStore
from focu.research_requests import capture_request, export_requests, list_requests


class ResearchRequestTests(unittest.TestCase):
    def test_one_shot_idea_is_durable_and_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "focu.sqlite3"
            first = capture_request(db, "Why do agents need memory?", note="A thought on my walk")
            repeated = capture_request(db, "Why do agents need memory?", note="A thought on my walk")
            self.assertEqual(first["intent_id"], repeated["intent_id"])
            self.assertFalse(first["automatic_research_started"])
            self.assertEqual(first["status"], "queued")
            rows = list_requests(db)["requests"]
            self.assertEqual(len(rows), 1)
            self.assertNotIn("A thought on my walk", json.dumps(rows))
            self.assertEqual(IntentStore(db).get(first["intent_id"])["kind"], "one_time_research")
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM intents").fetchone()[0], 1)

    def test_url_only_preserves_url_and_never_fetches(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "focu.sqlite3"
            r = capture_request(db, url="https://example.org/technical-blog")
            self.assertEqual(r["source_url"], "https://example.org/technical-blog")
            self.assertIn("Research this source", IntentStore(db).get(r["intent_id"])["question"])
            self.assertEqual(len(list_requests(db)["requests"]), 1)

    def test_rejects_bad_requests_and_allows_explicit_reresearch(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "focu.sqlite3"
            for kwargs in ({"url": "file:///etc/passwd"},
                           {"url": "https://admin:pass@example.com/"},
                           {"question": " "},
                           {"question": "X" * 10001},
                           {"question": "ok", "note": "N" * 5001}):
                with self.assertRaises(ValueError):
                    capture_request(db, **kwargs)
            original = capture_request(db, "Analyze the tradeoff")
            repeated = capture_request(db, "Analyze the tradeoff", force_new=True)
            self.assertNotEqual(original["intent_id"], repeated["intent_id"])

    def test_queue_export_tracks_real_status_without_leaking_notes(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "focu.sqlite3"
            row = capture_request(db, "Investigate this claim", note="private note")
            IntentStore(db).transition(row["intent_id"], "queued", "researching")
            path = Path(root) / "private-requests.json"
            result = export_requests(db, path)
            self.assertEqual(result["count"], 1)
            obj = json.loads(path.read_text())
            self.assertEqual(obj["requests"][0]["status"], "researching")
            self.assertNotIn("private note", path.read_text())
            self.assertEqual(obj["requests"][0]["content_id"], row["intent_id"])

    def test_cli_request_and_export(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "focu.sqlite3"
            capture_out = io.StringIO()
            with contextlib.redirect_stdout(capture_out):
                self.assertEqual(focu_cli(["--db", str(db), "request",
                                           "Evaluate this method", "--url",
                                           "https://example.org/method"]), 0)
            payload = json.loads(capture_out.getvalue())
            self.assertTrue(payload["intent_id"].startswith("int_"))
            export_path = Path(root) / "export.json"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(focu_cli(["--db", str(db), "request-export",
                                           "--output", str(export_path)]), 0)
            self.assertEqual(len(json.loads(export_path.read_text())["requests"]), 1)


if __name__ == "__main__":
    unittest.main()
