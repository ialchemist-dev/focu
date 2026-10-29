import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from focu import tts


class TTSOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"FOCU_TTS_CONFIG": str(self.root / "tts.json")}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_status_does_not_leak_key(self):
        self.assertFalse(tts.status()["configured"])
        (self.root / "tts.json").write_text(json.dumps({"api_key": "private-secret"}))
        output = json.dumps(tts.status())
        self.assertTrue(tts.status()["configured"])
        self.assertNotIn("private-secret", output)

    def test_setup_requires_interactive_terminal(self):
        with patch.object(tts.sys.stdin, "isatty", return_value=False):
            with self.assertRaisesRegex(ValueError, "Interactive terminal"):
                tts.setup()

    def test_setup_decline_creates_no_file(self):
        with patch.object(tts.sys.stdin, "isatty", return_value=True), patch("builtins.input", return_value="n"):
            self.assertEqual(tts.setup()["status"], "cancelled")
        self.assertFalse((self.root / "tts.json").exists())

    def test_missing_key_does_not_make_request(self):
        src = self.root / "script.txt"
        src.write_text("Hello", encoding="utf-8")
        with patch.object(tts.urllib.request, "urlopen") as mock:
            with self.assertRaisesRegex(ValueError, "not configured"):
                tts.synthesize(src, self.root / "out.mp3")
            mock.assert_not_called()

    def test_synthesis_uses_mocked_provider(self):
        src = self.root / "script.txt"
        src.write_text("Host: Hello", encoding="utf-8")
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def read(self): return b"fake-mp3"
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}), patch.object(tts.urllib.request, "urlopen", return_value=Response()) as mocked:
            result = tts.synthesize(src, self.root / "out.mp3")
        self.assertEqual(result["bytes"], 8)
        self.assertEqual((self.root / "out.mp3").read_bytes(), b"fake-mp3")
        self.assertIn("Bearer test-only", mocked.call_args.args[0].get_header("Authorization"))

    def test_long_script_fails_explicitly(self):
        src = self.root / "script.txt"
        src.write_text("x" * 4001)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}):
            with self.assertRaisesRegex(ValueError, "chunking"):
                tts.synthesize(src, self.root / "out.mp3")


if __name__ == "__main__":
    unittest.main()
