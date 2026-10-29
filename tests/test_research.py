import json
import tempfile
import unittest
from pathlib import Path
from focu.intents import IntentStore
from focu.research import ingest_research


class ResearchHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.db = root / "db.sqlite3"
        self.evidence_path = root / "evidence.json"
        self.output = root / "digest.md"
        self.intents = IntentStore(self.db)
        self.intent = self.intents.capture("What is advertising?")
        self.pack = {"schema_version": "0.2", "id": "ev_demo", "intent_id": self.intent["id"],
                     "summary": "A researched explanation.", "created_at": "2026-10-15T00:00:00Z",
                     "sources": [{"id": "s1", "url": "https://example.org/article", "title": "Article"}],
                     "findings": [{"claim": "Advertising finances some media.", "source_ids": ["s1"],
                                   "uncertainty": "This does not describe every media business."}]}
        self.evidence_path.write_text(json.dumps(self.pack), encoding="utf-8")

    def test_agent_evidence_to_cited_markdown(self):
        self.intents.transition(self.intent["id"], "queued", "researching")
        ingest_research(self.db, self.evidence_path, self.output)
        text = self.output.read_text(encoding="utf-8")
        self.assertIn("What is advertising?", text)
        self.assertIn("[s1](https://example.org/article)", text)
        self.assertIn("Uncertainty", text)
        self.assertEqual(self.intents.get(self.intent["id"])["status"], "completed")

    def test_invalid_evidence_does_not_complete(self):
        self.intents.transition(self.intent["id"], "queued", "researching")
        self.pack["findings"][0]["source_ids"] = ["nonexistent"]
        self.evidence_path.write_text(json.dumps(self.pack), encoding="utf-8")
        with self.assertRaises(ValueError):
            ingest_research(self.db, self.evidence_path, self.output)
        self.assertEqual(self.intents.get(self.intent["id"])["status"], "researching")


if __name__ == "__main__":
    unittest.main()
