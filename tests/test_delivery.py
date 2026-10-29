import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from focu.delivery import DeliveryArchive
from focu.evidence import EvidenceStore
from focu.intents import IntentStore

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "focu.sqlite3"
        self.intent = IntentStore(self.db).capture("What happened?")
        self.pack = {"schema_version":"0.2","id":"ev_test","intent_id":self.intent["id"],
            "summary":"Two sourced facts.","findings":[
                {"claim":"Fact A","source_ids":["s1"]},
                {"claim":"Fact B","source_ids":["s2"],"uncertainty":"Date unclear"}],
            "sources":[{"id":"s1","url":"https://example.org/a","title":"A"},
                       {"id":"s2","url":"https://example.org/b","title":"B"}],
            "created_at":"2026-10-17T00:00:00Z"}
        EvidenceStore(self.db).save(self.pack)
        self.archive = DeliveryArchive(self.db)

    def test_report_preserves_all_findings_and_urls(self):
        result = self.archive.archive_report("ev_test")
        report = self.archive.get(result["id"])["content"]
        for term in ("Fact A", "Fact B", "https://example.org/a", "https://example.org/b", "Date unclear"):
            self.assertIn(term, report)
        self.assertEqual(self.archive.archive_report("ev_test")["id"], result["id"])

    def test_saved_report_survives_renderer_upgrade(self):
        result = self.archive.archive_report("ev_test")
        original = self.archive.get(result["id"])["content"]
        with patch("focu.delivery.render_markdown", return_value="New renderer output"):
            self.assertEqual(self.archive.archive_report("ev_test"), result)
        self.assertEqual(self.archive.get(result["id"])["content"], original)

    def test_episode_archive_keeps_transcript_distinct(self):
        self.archive.archive_report("ev_test")
        episode = {"id":"episode:abc","name":"Brief","job_status":"completed",
            "transcript":{"segments":[{"speaker":"solo","text":"Spoken summary."}]},
            "outline":{"sections":["Intro"]},"audio_url":"/api/podcasts/episodes/episode:abc/audio"}
        artifacts = self.archive.sync_podcast("ev_test", episode)
        self.assertEqual(len(artifacts), 3)
        self.assertEqual(len(self.archive.list("ev_test")), 4)
        self.assertIn("Spoken summary", self.archive.get("podcast_transcript:episode:abc")["content"])
        self.assertNotIn("Spoken summary", self.archive.get("research:ev_test")["content"])
        self.assertEqual(self.archive.sync_podcast("ev_test", episode), artifacts)

    def test_rejects_unfinished_or_unlinked(self):
        with self.assertRaises(ValueError):
            self.archive.sync_podcast("ev_test", {"id":"episode:abc","job_status":"queued"})
        with self.assertRaises(ValueError):
            self.archive.sync_podcast("ev_unknown", {"id":"episode:abc","job_status":"completed"})
        with self.assertRaises(ValueError):
            self.archive.archive_report("ev_unknown")

    def test_immutable_artifact(self):
        self.archive.save("x", "ev_test", "podcast_transcript", "original")
        with self.assertRaises(ValueError):
            self.archive.save("x", "ev_test", "podcast_transcript", "changed")

if __name__ == "__main__":
    unittest.main()
