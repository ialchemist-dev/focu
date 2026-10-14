import tempfile
import unittest
from pathlib import Path
from the_few.evidence import EvidenceStore, validate_pack
from the_few.intents import IntentStore


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "test.sqlite3"
        self.intents = IntentStore(self.path)
        self.evidence = EvidenceStore(self.path)
        self.intent = self.intents.capture("Why do tools constrain us?")
        self.pack = {"schema_version": "0.2", "id": "ev_test", "intent_id": self.intent["id"],
                     "summary": "A grounded explanation", "created_at": "2026-10-13T00:00:00Z",
                     "sources": [{"id": "s1", "url": "https://example.org/paper", "title": "Paper"}],
                     "findings": [{"claim": "Path dependence can constrain choices.", "source_ids": ["s1"]}]}

    def test_valid_pack_persists(self):
        self.evidence.save(self.pack)
        self.assertEqual(EvidenceStore(self.path).get("ev_test"), self.pack)

    def test_unknown_citation_fails(self):
        self.pack["findings"][0]["source_ids"] = ["missing"]
        with self.assertRaises(ValueError):
            validate_pack(self.pack)

    def test_duplicate_id_conflict_fails(self):
        self.evidence.save(self.pack)
        self.pack["summary"] = "Different"
        with self.assertRaises(ValueError):
            self.evidence.save(self.pack)

    def test_cannot_complete_without_saved_pack(self):
        self.intents.transition(self.intent["id"], "queued", "researching")
        with self.assertRaises(ValueError):
            self.intents.transition(self.intent["id"], "researching", "completed", evidence_pack_id="ev_missing")
        self.evidence.save(self.pack)
        self.intents.transition(self.intent["id"], "researching", "completed", evidence_pack_id="ev_test")
        self.assertEqual(self.intents.get(self.intent["id"])["status"], "completed")

    def test_cannot_attach_other_intent_evidence(self):
        other = self.intents.capture("Different question")
        self.evidence.save(self.pack)
        self.intents.transition(other["id"], "queued", "researching")
        with self.assertRaises(ValueError):
            self.intents.transition(other["id"], "researching", "completed", evidence_pack_id="ev_test")


if __name__ == "__main__":
    unittest.main()
