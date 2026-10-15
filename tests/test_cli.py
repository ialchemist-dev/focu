import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from the_few.cli import main


class AgentCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "agent.sqlite3")

    def call(self, *args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--db", self.db, *args])
        return code, json.loads(stdout.getvalue() or stderr.getvalue())

    def test_install_initialize_and_capture(self):
        code, doctor = self.call("doctor")
        self.assertEqual(code, 0)
        self.assertFalse(doctor["automatic_research"])
        code, initialized = self.call("init")
        self.assertEqual(code, 0)
        self.assertEqual(initialized["status"], "initialized")
        code, item = self.call("capture", "Why do tools constrain us?")
        self.assertEqual(code, 0)
        self.assertEqual(item["status"], "queued")
        code, result = self.call("start", item["id"])
        self.assertEqual(result["status"], "researching")
        code, result = self.call("fail", item["id"], "--error", "timeout")
        self.assertEqual(result["status"], "failed")
        code, result = self.call("retry", item["id"])
        self.assertEqual(result["status"], "queued")

    def test_missing_intent_fails_with_json_error(self):
        code, result = self.call("show", "int_" + "0" * 32)
        self.assertEqual(code, 1)
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
