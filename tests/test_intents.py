import tempfile
import unittest
from pathlib import Path
from focu.intents import IntentStore
from focu.evidence import EvidenceStore


class IntentStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "intents.sqlite3"
        self.store = IntentStore(self.path)

    def test_capture_persists_after_reopen(self):
        item = self.store.capture("广告的本质是什么？")
        self.assertEqual(IntentStore(self.path).get(item["id"])["question"], "广告的本质是什么？")
        self.assertEqual(item["status"], "queued")

    def test_capture_is_idempotent_by_id(self):
        item = self.store.capture("Question")
        again = self.store.capture("Different", intent_id=item["id"])
        self.assertEqual(again["question"], "Question")
        self.assertEqual(len(self.store.list()), 1)

    def test_transition_and_retry(self):
        item = self.store.capture("Question")
        self.store.transition(item["id"], "queued", "researching")
        self.store.transition(item["id"], "researching", "failed", error="timeout")
        self.store.transition(item["id"], "failed", "queued")
        self.store.transition(item["id"], "queued", "researching")
        EvidenceStore(self.path).save({"schema_version":"0.2","id":"ev_1","intent_id":item["id"],
            "summary":"Summary","created_at":"2026-10-13T00:00:00Z",
            "sources":[{"id":"s1","url":"https://example.com/source","title":"Source"}],
            "findings":[{"claim":"Supported claim","source_ids":["s1"]}]})
        self.store.transition(item["id"], "researching", "completed", evidence_pack_id="ev_1")
        self.assertEqual(self.store.get(item["id"])["evidence_pack_id"], "ev_1")

    def test_cannot_complete_without_evidence(self):
        item = self.store.capture("Question")
        self.store.transition(item["id"], "queued", "researching")
        with self.assertRaises(ValueError):
            self.store.transition(item["id"], "researching", "completed")
        self.assertEqual(self.store.get(item["id"])["status"], "researching")

    def test_reject_blank_question(self):
        with self.assertRaises(ValueError):
            self.store.capture("  ")


if __name__ == "__main__":
    unittest.main()
