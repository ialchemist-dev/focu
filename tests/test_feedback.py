import tempfile
import unittest
from pathlib import Path

from focu.feedback import FeedbackStore


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "focu.sqlite3"
        self.store = FeedbackStore(self.db)

    def test_explicit_feedback_persists(self):
        item = self.store.record(target_type="episode", target_id="2026-10-17/research",
                                 kind="too_long", note="Please be more concise")
        self.assertEqual(item["kind"], "too_long")
        self.assertEqual(FeedbackStore(self.db).list(target_id="2026-10-17/research")[0]["id"], item["id"])

    def test_idempotency_and_conflict(self):
        args = dict(target_type="evidence_pack", target_id="ev1", kind="useful", event_id="fb_test")
        self.assertEqual(self.store.record(**args)["id"], self.store.record(**args)["id"])
        with self.assertRaises(ValueError):
            self.store.record(**{**args, "kind": "incorrect"})

    def test_isolation(self):
        self.store.record(target_type="episode", target_id="same", kind="useful")
        self.store.record(target_type="observation", target_id="same", kind="not_useful")
        self.assertEqual(len(self.store.list(target_type="episode")), 1)
        self.assertEqual(len(self.store.list(target_id="same")), 2)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            self.store.record(target_type="unknown", target_id="x", kind="useful")
        with self.assertRaises(ValueError):
            self.store.record(target_type="episode", target_id="x", kind="unknown")
        with self.assertRaises(ValueError):
            self.store.record(target_type="episode", target_id="", kind="useful")


if __name__ == "__main__":
    unittest.main()
