import contextlib
import io
import json
import os
import re
import shutil
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


class ChunkScriptTests(unittest.TestCase):
    def test_paragraphs_pack_and_preserve_order(self):
        paragraphs = [f"Paragraph {i} " + "x" * 90 for i in range(12)]
        chunks = tts.chunk_script("\n\n".join(paragraphs), limit=350)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(0 < len(c) <= 350 for c in chunks))
        joined = " ".join(chunks)
        positions = [joined.index(f"Paragraph {i} ") for i in range(12)]
        self.assertEqual(positions, sorted(positions))

    def test_sentences_are_never_split_when_a_boundary_fits(self):
        sentence = "The system recorded 948 observations in this run."
        text = " ".join([sentence] * 30)
        chunks = tts.chunk_script(text, limit=400)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 400 for c in chunks))
        for chunk in chunks:
            self.assertTrue(chunk.endswith("run."), chunk[-40:])
        self.assertEqual(" ".join(chunks).split(), text.split())

    def test_oversized_sentence_falls_back_to_word_boundaries(self):
        text = ("word " * 500).strip()
        chunks = tts.chunk_script(text, limit=400)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 400 for c in chunks))
        self.assertEqual(" ".join(chunks).split(), text.split())

    def test_short_text_is_a_single_chunk(self):
        self.assertEqual(tts.chunk_script("Host: Short script."), ["Host: Short script."])
        self.assertEqual(tts.chunk_script("  \n\n  "), [])


def _ffmpeg_tone(path, frequency=440, duration=1.0):
    import subprocess
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                    "-i", f"sine=frequency={frequency}:duration={duration}",
                    "-c:a", "libmp3lame", str(path)], check=True, capture_output=True)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "requires audio tools")
class LongFormSynthesisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tone = self.root / "tone.mp3"
        _ffmpeg_tone(self.tone, duration=0.5)
        self.tone_bytes = self.tone.read_bytes()

    def script_file(self, text):
        path = self.root / "script.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def test_short_input_uses_single_provider_call(self):
        seen = []
        def fake(chunk):
            seen.append(chunk)
            return self.tone_bytes
        out = self.root / "out.mp3"
        result = tts.synthesize_long(self.script_file("Host: Brief update."),
                                     out, speech_fn=fake)
        self.assertEqual(seen, ["Host: Brief update."])
        self.assertEqual(result["chunks"], 1)
        self.assertFalse(result["long_form"])
        self.assertEqual(out.read_bytes(), self.tone_bytes)

    def test_long_input_chunks_in_order_and_concatenates(self):
        from focu.media_integrity import inspect_mp3
        paragraphs = [f"Section {i} opens the report. " + "Detail follows here. " * 105
                      for i in range(3)]  # ~2100 chars each -> one chunk each
        seen = []
        def fake(chunk):
            seen.append(chunk)
            return self.tone_bytes
        out = self.root / "long.mp3"
        result = tts.synthesize_long(self.script_file("\n\n".join(paragraphs)),
                                     out, speech_fn=fake)
        self.assertEqual(seen, tts.chunk_script("\n\n".join(paragraphs)))
        self.assertEqual(len(seen), 3)
        self.assertTrue(result["long_form"])
        audit = inspect_mp3(out)
        # Three 0.5s tones joined by two ~0.7s gaps: ~2.9s, not ~1.5s of
        # overlapped or truncated audio.
        self.assertGreater(audit["decoded_duration_seconds"], 2.2)
        self.assertLess(audit["decoded_duration_seconds"], 4.0)
        import subprocess
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=bit_rate,sample_rate,channels",
            "-of", "json", str(out)
        ], capture_output=True, text=True, check=True)
        track = json.loads(probe.stdout)["streams"][0]
        self.assertEqual(track["sample_rate"], "44100")
        self.assertEqual(track["channels"], 1)
        self.assertLess(abs(int(track["bit_rate"]) - 128000), 5000)

    def test_boundary_silences_are_normalized(self):
        from focu.media_integrity import inspect_mp3
        padded = self.root / "padded.mp3"
        silence = self.root / "silence.mp3"
        import subprocess
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "anullsrc=r=44100:cl=mono", "-t", "1.5",
                        "-c:a", "libmp3lame", str(silence)], check=True, capture_output=True)
        listing = self.root / "pad.txt"
        listing.write_text(f"file '{silence}'\nfile '{self.tone}'\nfile '{silence}'\n")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                        "-i", str(listing), "-codec:a", "libmp3lame", str(padded)],
                       check=True, capture_output=True)
        padded_bytes = padded.read_bytes()  # 1.5s silence + 0.5s tone + 1.5s silence
        paragraphs = ["Report section %d. " % i + "Narration text follows. " * 95
                      for i in range(3)]
        out = self.root / "normalized.mp3"
        tts.synthesize_long(self.script_file("\n\n".join(paragraphs)), out,
                            speech_fn=lambda chunk: padded_bytes)
        duration = inspect_mp3(out)["decoded_duration_seconds"]
        # Unnormalized concatenation would run ~10.5s; normalized output is
        # three trimmed 0.5s tones plus two ~0.7s boundary gaps.
        self.assertLess(duration, 5.0)
        self.assertGreater(duration, 2.0)
        detected = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(out), "-af",
             "silencedetect=noise=-50dB:d=0.4", "-f", "null", "-"],
            capture_output=True, text=True)
        gaps = [float(x) for x in
                re.findall(r"silence_duration: ([0-9.]+)", detected.stderr)]
        self.assertTrue(gaps, "expected measurable boundary gaps")
        self.assertLessEqual(max(gaps), 1.5)

    def test_chunk_failure_aborts_with_no_partial_output(self):
        paragraphs = ["Section %d. " % i + "Content sentence here. " * 130
                      for i in range(4)]
        calls = []
        def flaky(chunk):
            calls.append(chunk)
            if len(calls) == 2:
                raise RuntimeError("provider unavailable")
            return self.tone_bytes
        out = self.root / "aborted.mp3"
        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            tts.synthesize_long(self.script_file("\n\n".join(paragraphs)),
                                out, speech_fn=flaky)
        self.assertEqual(len(calls), 2)
        self.assertFalse(out.exists())
        self.assertEqual(list(self.root.glob(".focu-tts-*")), [])

    def test_unconfigured_long_form_makes_no_provider_request(self):
        env = patch.dict(os.environ, {"FOCU_TTS_CONFIG": str(self.root / "absent.json"),
                                      "OPENAI_API_KEY": ""}, clear=False)
        with env, patch.object(tts.urllib.request, "urlopen") as mock:
            with self.assertRaisesRegex(ValueError, "not configured"):
                tts.synthesize_long(self.script_file("x " * 3000),
                                    self.root / "never.mp3")
            mock.assert_not_called()
        self.assertFalse((self.root / "never.mp3").exists())


if __name__ == "__main__":
    unittest.main()
