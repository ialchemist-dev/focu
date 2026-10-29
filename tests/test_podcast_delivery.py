import tempfile
import unittest
from pathlib import Path
from focu.delivery import DeliveryArchive
from focu.evidence import EvidenceStore
from focu.intents import IntentStore
from focu.podcast_delivery import deliver, wait_and_deliver

class FakeClient:
    def __init__(self, state="completed"):
        self.state = state
        self.downloads = 0
    def request(self, method, path):
        return {"id":"episode:123","job_status":self.state,"name":"Brief",
                "transcript":{"segments":[{"text":"Spoken"}]},"audio_url":"/api/podcasts/episodes/episode:123/audio"}
    def download(self, episode_id, path):
        self.downloads += 1
        path.write_bytes(b"mp3")
    def job(self, job_id):
        return {"status":self.state,"result":{"episode_id":"episode:123"}}

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "focu.db"
        intent = IntentStore(self.db).capture("Question?")
        EvidenceStore(self.db).save({"schema_version":"0.2","id":"ev_one","intent_id":intent["id"],
            "summary":"Fact","findings":[{"claim":"Fact","source_ids":["s1"]}],
            "sources":[{"id":"s1","title":"Source","url":"https://example.org"}],
            "created_at":"2026-10-17T00:00:00Z"})
        self.output = Path(self.tmp.name) / "delivery"

    def test_delivery_and_idempotence(self):
        client = FakeClient()
        first = deliver("ev_one", "episode:123", self.output, self.db, client)
        self.assertEqual(first["status"], "delivered")
        self.assertIn("https://example.org", Path(first["report"]).read_text())
        self.assertIn("Spoken", Path(first["transcript"]).read_text())
        self.assertEqual(Path(first["audio"]).read_bytes(), b"mp3")
        self.assertEqual(deliver("ev_one", "episode:123", self.output, self.db, client)["artifacts"], first["artifacts"])
        self.assertEqual(len(DeliveryArchive(self.db).list("ev_one")), 3)

    def test_unfinished_never_archives_episode(self):
        with self.assertRaisesRegex(ValueError, "not completed"):
            deliver("ev_one", "episode:123", self.output, self.db, FakeClient("queued"))
        self.assertEqual(len(DeliveryArchive(self.db).list("ev_one")), 1)

    def test_wait_handoff(self):
        result = wait_and_deliver("ev_one", "job:1", self.output, self.db, FakeClient())
        self.assertEqual(result["episode_id"], "episode:123")

    def test_failed_job(self):
        with self.assertRaises(RuntimeError):
            wait_and_deliver("ev_one", "job:1", self.output, self.db, FakeClient("failed"))
