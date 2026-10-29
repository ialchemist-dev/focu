import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from focu.open_notebook import OpenNotebookClient, main


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def read(self): return self.payload


class OpenNotebookTests(unittest.TestCase):
    def setUp(self):
        self.client = OpenNotebookClient(base_url="http://127.0.0.1:5055", password="test-secret")

    def test_doctor_and_profile_names(self):
        payloads = [b'{"status":"healthy"}', b'[{"name":"Deep Dive"}]', b'[{"name":"Two Hosts"}]']
        with patch("urllib.request.urlopen", side_effect=[FakeResponse(p) for p in payloads]) as mock:
            result = self.client.doctor()
        self.assertTrue(result["ready_for_generation"])
        self.assertEqual(result["episode_profiles"], ["Deep Dive"])
        self.assertEqual(mock.call_count, 3)

    def test_generate_uses_exact_api_payload_and_secret_header(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse(b'{"job_id":"job:123","status":"submitted"}')) as mock:
            result = self.client.generate(episode_name="Test", episode_profile="Deep Dive",
                                          speaker_profile="Two Hosts", content="Evidence only")
        req = mock.call_args.args[0]
        self.assertEqual(req.full_url, "http://127.0.0.1:5055/api/podcasts/generate")
        self.assertEqual(req.get_header("Authorization"), "Bearer test-secret")
        self.assertEqual(json.loads(req.data)["content"], "Evidence only")
        self.assertEqual(result["job_id"], "job:123")

    def test_job_url_encodes_record_id(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse(b'{"status":"completed"}')) as mock:
            self.client.job("job:123")
        self.assertIn("/api/podcasts/jobs/job%3A123", mock.call_args.args[0].full_url)

    def test_download_and_empty_audio(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "audio.mp3"
            with patch("urllib.request.urlopen", return_value=FakeResponse(b"mp3bytes")):
                self.assertEqual(self.client.download("episode:1", target)["bytes"], 8)
            self.assertEqual(target.read_bytes(), b"mp3bytes")
            with patch("urllib.request.urlopen", return_value=FakeResponse(b"")):
                with self.assertRaisesRegex(RuntimeError, "Empty audio"):
                    self.client.download("episode:2", target)

    def test_provider_error_redacts_secret(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
                "http://127.0.0.1:5055", 401, "secret=should-not-leak", {}, None)):
            with self.assertRaisesRegex(RuntimeError, "HTTP 401") as ctx:
                self.client.episodes()
            self.assertNotIn("should-not-leak", str(ctx.exception))

    def test_rejects_invalid_or_oversize_content(self):
        with self.assertRaises(ValueError):
            self.client.generate(episode_name="x", episode_profile="x",
                                 speaker_profile="x", content=" ")
        with self.assertRaises(ValueError):
            self.client.generate(episode_name="x", episode_profile="x",
                                 speaker_profile="x", content="x" * 2_000_001)
        with self.assertRaises(ValueError):
            OpenNotebookClient(base_url="file:///tmp/db")

    def test_cli_offline_with_mock(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "evidence.md"
            src.write_text("Verified source: https://example.org", encoding="utf-8")
            with patch.dict(os.environ, {"OPEN_NOTEBOOK_URL": "http://127.0.0.1:5055"}), patch(
                "urllib.request.urlopen", return_value=FakeResponse(b'{"job_id":"job:1"}')):
                self.assertEqual(main(["generate", "--content-file", str(src), "--episode-name", "Research",
                    "--episode-profile", "Deep Dive", "--speaker-profile", "Two Hosts"]), 0)


if __name__ == "__main__":
    unittest.main()
