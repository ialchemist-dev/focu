import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from focu.media_integrity import inspect_mp3, MediaIntegrityError


class MediaIntegrityTests(unittest.TestCase):
    def test_rejects_unplayable_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "audio.mp3"
            path.write_bytes(b"not an mp3" * 100)
            with self.assertRaises(MediaIntegrityError):
                inspect_mp3(path)

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
