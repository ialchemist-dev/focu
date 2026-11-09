import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from focu.media_integrity import inspect_mp3, transcode_ios_cbr, MediaIntegrityError


class MediaIntegrityTests(unittest.TestCase):
    def test_rejects_unplayable_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "audio.mp3"
            path.write_bytes(b"not an mp3" * 100)
            with self.assertRaises(MediaIntegrityError):
                inspect_mp3(path)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "requires local ffmpeg and ffprobe")
    def test_ios_cbr_keeps_original_and_validates_decoded_duration(self):
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp) / "vbr.mp3", Path(temp) / "ios-cbr.mp3"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-v", "error", "-y",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                "-c:a", "libmp3lame", "-q:a", "2", str(source),
            ], check=True, capture_output=True, timeout=60)
            before = source.read_bytes()
            record = transcode_ios_cbr(source, target)
            self.assertEqual(before, source.read_bytes(),
                             "never modify archived source VBR audio")
            self.assertEqual(record["profile"], "mp3_cbr_128k_mono_44100")
            self.assertTrue(record["published_audit"]["verified"])
            self.assertAlmostEqual(
                record["published_audit"]["decoded_duration_seconds"],
                record["source_audit"]["decoded_duration_seconds"], delta=1.5)
            result = subprocess.run([
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=bit_rate,sample_rate,channels",
                "-of", "json", str(target)
            ], check=True, capture_output=True, text=True)
            stream = __import__("json").loads(result.stdout)["streams"][0]
            self.assertEqual(stream["sample_rate"], "44100")
            self.assertEqual(stream["channels"], 1)
            self.assertLess(abs(int(stream["bit_rate"]) - 128000), 5000)
            with self.assertRaises(MediaIntegrityError):
                transcode_ios_cbr(source, source)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "requires local ffmpeg and ffprobe")
    def test_detects_stale_mp3_duration_after_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "audio.mp3"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "sine=frequency=500:duration=6",
                "-codec:a", "libmp3lame", "-b:a", "64k", str(path)
            ], timeout=30, check=True, capture_output=True)
            audit = inspect_mp3(path)
            self.assertGreater(audit["decoded_duration_seconds"], 5.5)
            self.assertTrue(audit["verified"])
            truncated = Path(temp) / "truncated.mp3"
            truncated.write_bytes(path.read_bytes()[:max(2048, path.stat().st_size // 3)])
            with self.assertRaises(MediaIntegrityError):
                inspect_mp3(truncated)


if __name__ == "__main__":
    unittest.main()
