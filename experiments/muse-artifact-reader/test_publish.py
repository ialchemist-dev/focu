import json
from pathlib import Path
import tempfile
import unittest
from publish import build, sha256, episode_date

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

    def test_dates_and_chronological_limit(self):
        self.assertEqual(episode_date("frontier-20261102"), "2026-11-02")
        self.assertEqual(episode_date("voice-input_20261018"), "2026-10-18")
        self.assertEqual(episode_date("frontier-20261340"), "")
        self.assertEqual(episode_date("voice-input"), "")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            deliveries = root / "deliveries"
            for name in ("voice-input-20261018", "frontier-20261102", "frontier-20261031"):
                folder = deliveries / name
                folder.mkdir(parents=True)
                (folder / "podcast.mp3").write_bytes(name.encode())
            output = root / "bundle"
            build(deliveries, output, Path(__file__).with_name("index.html"), 2)
            episodes = json.loads((output / "assets/episodes.json").read_text())["episodes"]
            self.assertEqual([ep["date"] for ep in episodes], ["2026-11-02", "2026-10-31"])
            self.assertEqual([ep["id"] for ep in episodes], ["frontier-20261102", "frontier-20261031"])

    def test_muse_loader_fallback_structure(self):
        html = Path(__file__).with_name("index.html").read_text()
        self.assertIn("const manifest=params.get('manifest')||'assets/episodes.json'", html)
        self.assertIn("try{const url=safeUrl(manifest);if(!url)throw Error('Invalid manifest URL');const response=", html)
        self.assertIn("}catch(e){data=embedded;note='embedded snapshot (manifest unavailable)'", html)
        self.assertIn("return v}", html)

    def test_unified_item_with_article_and_editorial_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "topic-20261103"
            folder.mkdir(parents=True)
            (folder / "podcast.mp3").write_bytes(b"unchanged-audio")
            (folder / "article.html").write_text("<h1>Readable article</h1>")
            (folder / "content.json").write_text(json.dumps({"title": "A Specific Topic", "summary": "A short explanation."}))
            output = root / "bundle"
            build(root / "deliveries", output, Path(__file__).with_name("index.html"), 15)
            payload = json.loads((output / "assets/episodes.json").read_text())
            item = payload["items"][0]
            self.assertEqual(item["content_id"], "topic-20261103")
            self.assertEqual(item["title"], "A Specific Topic")
            self.assertEqual(item["summary"], "A short explanation.")
            self.assertIn("article", item["formats"])
            self.assertEqual((output / item["formats"]["article"]["path"]).read_text(), "<h1>Readable article</h1>")
            self.assertEqual((output / item["audio_url"]).read_bytes(), b"unchanged-audio")
            self.assertEqual(payload["episodes"][0]["id"], item["content_id"])

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
