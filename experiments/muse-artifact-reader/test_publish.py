import json
from pathlib import Path
import tempfile
import unittest
from publish import build, sha256

class PublisherTests(unittest.TestCase):
    def test_build_and_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            deliveries = root / "deliveries"
            folder = deliveries / "frontier-20261102"
            folder.mkdir(parents=True)
            (folder / "podcast.mp3").write_bytes(b"real-existing-audio-fixture")
            (folder / "research.md").write_text("# A Research Briefing\n")
            template = Path(__file__).with_name("index.html")
            output = root / "artifact-v1"
            self.assertEqual(build(deliveries, output, template, 15), 1)
            data = json.loads((output / "assets/episodes.json").read_text())
            episode = data["episodes"][0]
            self.assertEqual(episode["title"], "A Research Briefing")
            self.assertEqual(sha256(output / episode["audio_url"]), sha256(folder / "podcast.mp3"))
            self.assertIn("A Research Briefing", (output / "index.html").read_text())
            with self.assertRaises(FileExistsError):
                build(deliveries, output, template, 15)

    def test_reject_empty_and_unsafe_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            deliveries = root / "deliveries"
            deliveries.mkdir()
            template = Path(__file__).with_name("index.html")
            with self.assertRaises(ValueError):
                build(deliveries, root / "out", template, 15)
            with self.assertRaises(ValueError):
                build(deliveries, deliveries / "out", template, 15)
            with self.assertRaises(ValueError):
                build(deliveries, root / "out", template, 0)

if __name__ == "__main__":
    unittest.main()
