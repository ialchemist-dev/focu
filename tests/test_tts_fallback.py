"""Tests for the quota-only TTS fallback (owner decision, 2026-11-17).

The fallback policy: when the primary speech provider fails on exhausted
credits/quota, synthesize_long_with_fallback re-synthesizes the whole
script with the fallback speech_fn and records engine="fallback". Every
other failure propagates; the fallback is never a general retry.
"""
import tempfile
import unittest
from pathlib import Path

from focu.tts import is_quota_failure, synthesize_long_with_fallback

SCRIPT = "Host paragraph one is spoken here.\n\nA second short paragraph follows.\n"


def _write_script(directory: str) -> Path:
    path = Path(directory) / "script.txt"
    path.write_text(SCRIPT, encoding="utf-8")
    return path


class QuotaDetectionTests(unittest.TestCase):
    def test_quota_markers(self):
        for text in (
            "connector speech call failed: insufficient_quota",
            "TTS provider returned HTTP 429: credit_balance_exhausted",
            "Error code: 429 - rate limited",
            '{"status": 429}',
        ):
            self.assertTrue(is_quota_failure(RuntimeError(text)), text)

    def test_non_quota_failures(self):
        for text in (
            "TTS provider returned HTTP 500",
            "TTS provider network request failed",
            "TTS input is empty",
            "connector speech call failed: invalid voice",
        ):
            self.assertFalse(is_quota_failure(RuntimeError(text)), text)


class FallbackBehaviourTests(unittest.TestCase):
    def test_quota_failure_uses_fallback(self):
        calls = {"fallback": 0}

        def primary(chunk: str) -> bytes:
            raise RuntimeError("connector speech call failed: credit_balance_exhausted")

        def fallback(chunk: str) -> bytes:
            calls["fallback"] += 1
            return b"fallback-mp3-bytes"

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.mp3"
            result = synthesize_long_with_fallback(
                _write_script(td), out, speech_fn=primary, fallback_fn=fallback)
            self.assertEqual(result["engine"], "fallback")
            self.assertIn("credit_balance_exhausted", result["fallback_reason"])
            self.assertEqual(out.read_bytes(), b"fallback-mp3-bytes")
            self.assertGreaterEqual(calls["fallback"], 1)

    def test_non_quota_failure_propagates_without_fallback(self):
        calls = {"fallback": 0}

        def primary(chunk: str) -> bytes:
            raise RuntimeError("TTS provider returned HTTP 500")

        def fallback(chunk: str) -> bytes:
            calls["fallback"] += 1
            return b"should-not-be-used"

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.mp3"
            with self.assertRaises(RuntimeError):
                synthesize_long_with_fallback(
                    _write_script(td), out, speech_fn=primary, fallback_fn=fallback)
            self.assertEqual(calls["fallback"], 0)
            self.assertFalse(out.exists())

    def test_primary_success_never_touches_fallback(self):
        calls = {"fallback": 0}

        def primary(chunk: str) -> bytes:
            return b"primary-mp3-bytes"

        def fallback(chunk: str) -> bytes:
            calls["fallback"] += 1
            return b"should-not-be-used"

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.mp3"
            result = synthesize_long_with_fallback(
                _write_script(td), out, speech_fn=primary, fallback_fn=fallback)
            self.assertEqual(result["engine"], "primary")
            self.assertEqual(out.read_bytes(), b"primary-mp3-bytes")
            self.assertEqual(calls["fallback"], 0)

    def test_quota_failure_without_fallback_fn_propagates(self):
        def primary(chunk: str) -> bytes:
            raise RuntimeError("insufficient_quota")

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.mp3"
            with self.assertRaises(RuntimeError):
                synthesize_long_with_fallback(
                    _write_script(td), out, speech_fn=primary, fallback_fn=None)
            self.assertFalse(out.exists())

    def test_fallback_failure_propagates(self):
        def primary(chunk: str) -> bytes:
            raise RuntimeError("insufficient_quota")

        def fallback(chunk: str) -> bytes:
            raise RuntimeError("kokoro model missing")

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.mp3"
            with self.assertRaisesRegex(RuntimeError, "kokoro model missing"):
                synthesize_long_with_fallback(
                    _write_script(td), out, speech_fn=primary, fallback_fn=fallback)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
