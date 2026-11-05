import json
from pathlib import Path
import tempfile
import os
import shutil
import subprocess
from unittest.mock import patch
import unittest
from publish import build, sha256, episode_date
from editorial import editorial, blocks_from_markdown, compose_article_with_openai
from cover_art import typographic_svg

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

    def test_article_first_generation_from_real_research_shape(self):
        research = (
            "# What is new from Focu's registered research sources between two dates?\n\n"
            "One source announced a new result in distributed inference.\n\n"
            "## Findings\n\n"
            "- Pando releases a memory architecture for long-running agents "
            "([s1](https://example.org/story)).\n"
            "  > Authors demonstrated persistent agent execution.\n\n"
            "## Sources\n\n- [s1](https://example.org/story)\n"
        )
        info = editorial(research)
        self.assertTrue(info["title"].startswith("Pando releases a memory architecture"))
        self.assertNotIn("What is new", info["title"])
        self.assertIn("distributed inference", info["summary"])
        self.assertTrue(any(block["type"] == "heading" for block in info["article_blocks"]))
        self.assertTrue(any(block["type"] == "bullet" for block in info["article_blocks"]))
        self.assertIn("https://example.org/story", str(info["article_blocks"]))
        self.assertGreaterEqual(info["reading_minutes"], 1)

    def test_offline_covers_are_deterministic_and_distinct(self):
        first = typographic_svg("Pando memory architecture", "AI research")
        self.assertEqual(first, typographic_svg("Pando memory architecture", "AI research"))
        self.assertNotEqual(first, typographic_svg("Geothermal rock physics", "Energy"))
        self.assertTrue(first.startswith(b"<svg"))
        self.assertIn(b"Pando memory", first)
        self.assertIn(b"architecture", first)

    def test_build_stages_markdown_and_cover_without_network(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "frontier-20261103"
            folder.mkdir(parents=True)
            (folder / "podcast.mp3").write_bytes(b"original-bytes")
            (folder / "research.md").write_text(
                "# What is new from Focu's registered research sources?\n\n"
                "Research on energy use in AI infrastructure.\n\n"
                "## Findings\n- A new cooling design reduces data-center water use "
                "([src](https://example.org)).\n"
            )
            (folder / "content.json").write_text(json.dumps({"source_image_url": "https://example.org/cover.jpg"}))
            output = root / "bundle"
            build(root / "deliveries", output, Path(__file__).with_name("index.html"), 15)
            item = json.loads((output / "assets/episodes.json").read_text())["items"][0]
            self.assertIn("cooling design", item["title"])
            self.assertEqual(item["cover"]["origin"], "offline_art")
            self.assertTrue((output / item["cover"]["path"]).is_file())
            self.assertGreater(len(item["article_blocks"]), 1)
            self.assertEqual((output / item["audio_url"]).read_bytes(), b"original-bytes")
            embedded = (output / "index.html").read_text()
            self.assertIn("cooling design", embedded)
            self.assertIn("article_blocks", embedded)
            self.assertEqual(item["formats"]["article"]["mime_type"], "text/markdown")

    def test_original_cover_takes_priority(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "topic-20261103"
            folder.mkdir(parents=True)
            (folder / "podcast.mp3").write_bytes(b"audio")
            (folder / "cover.jpg").write_bytes(b"source-owned-cover-fixture")
            (folder / "research.md").write_text("# A specific research finding\n\nA summary.")
            output = root / "bundle"
            build(root / "deliveries", output, Path(__file__).with_name("index.html"), 15)
            item = json.loads((output / "assets/episodes.json").read_text())["items"][0]
            self.assertEqual(item["cover"]["origin"], "source")
            self.assertEqual((output / item["cover"]["path"]).read_bytes(), b"source-owned-cover-fixture")

    def test_reader_automatic_completion_contract(self):
        html = Path(__file__).with_name("index.html").read_text()
        self.assertIn("focu:content-consumption:v1", html)
        self.assertIn("markDone(playingId,'audio')", html)
        self.assertIn("markDone(currentId,'article')", html)
        self.assertIn("bottomSeen&&readMs>=minMs", html)
        self.assertIn("reader.hidden=false", html)
        self.assertNotIn("Done reading", html)
        self.assertNotIn("Mark done", html)

    def test_article_only_and_audio_only_share_optional_format_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            deliveries = root / "deliveries"
            article = deliveries / "article-20261103"
            article.mkdir(parents=True)
            (article / "article.md").write_text("# A standalone research story\n\nAn evidence-backed article.")
            audio = deliveries / "podcast-20261102"
            audio.mkdir(parents=True)
            (audio / "podcast.mp3").write_bytes(b"audio-only")
            output = root / "bundle"
            self.assertEqual(build(deliveries, output, Path(__file__).with_name("index.html"), 15), 2)
            payload = json.loads((output / "assets/episodes.json").read_text())
            self.assertEqual(len(payload["items"]), 2)
            self.assertEqual(len(payload["episodes"]), 1)
            items = {x["content_id"]: x for x in payload["items"]}
            self.assertIn("article", items["article-20261103"]["formats"])
            self.assertNotIn("audio", items["article-20261103"]["formats"])
            self.assertGreater(len(items["article-20261103"]["article_blocks"]), 1)
            self.assertIn("audio", items["podcast-20261102"]["formats"])
            self.assertNotIn("article", items["podcast-20261102"]["formats"])
            self.assertEqual((output / items["podcast-20261102"]["audio_url"]).read_bytes(), b"audio-only")
            self.assertEqual(json.loads((output / "build-report.json").read_text())["item_count"], 2)

    def test_opt_in_editorial_writes_cached_article_without_touching_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "research-20261103"
            folder.mkdir(parents=True)
            (folder / "research.md").write_text(
                "# What is new?\n\nInitial evidence summary.\n\n"
                "## Findings\n- A factual observation ([s1](https://example.org/a)).\n"
            )
            article = ("# A precise article headline\n\n"
                       "A careful explanation with enough context to keep this test "
                       "faithful to the editorial output. " * 6 +
                       "\n\n## Sources\n- [s1](https://example.org/a)\n")
            response = {"title": "A precise article headline",
                        "summary": "A research-based explanation of the original observation.",
                        "article_markdown": article}
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}):
                with patch("publish.compose_article_with_openai", return_value=response) as mock:
                    for name in ("bundle-a", "bundle-b"):
                        build(root / "deliveries", root / name,
                              Path(__file__).with_name("index.html"), 15,
                              generate_editorial=True)
                    self.assertEqual(mock.call_count, 1)
            item = json.loads((root / "bundle-b/assets/episodes.json").read_text())["items"][0]
            self.assertEqual(item["title"], response["title"])
            self.assertEqual(item["summary"], response["summary"])
            self.assertTrue(item["article_blocks"])
            self.assertEqual((folder / "research.md").read_text().splitlines()[0], "# What is new?")

    def test_editorial_provider_rejects_fabricated_citations(self):
        import io
        original = "# Research\n\nEvidence ([s1](https://example.org/a))."
        long_article = "# Valid headline\n\n" + "Technical details remain grounded. " * 12
        long_article += "\n\n## Sources\n- [fake](https://unverified.example/nope)"
        response = {"choices": [{"message": {"content": json.dumps({
            "title": "A valid research headline",
            "summary": "This summary only reflects the provided evidence.",
            "article_markdown": long_article,
        })}}]}
        with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
            with self.assertRaisesRegex(ValueError, "introduced citations"):
                compose_article_with_openai(original, api_key="test-only")

    def test_on_demand_research_queue_and_stable_content_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "idea-012345-20261103"
            folder.mkdir(parents=True)
            intent = "int_" + "a" * 32
            queued = "int_" + "b" * 32
            (folder / "research.md").write_text("# A technical article\n\nA factual summary.")
            (folder / "content.json").write_text(json.dumps({
                "content_id": intent, "title": "A technical article",
                "origin": "user_initiated", "summary": "Evidence-backed notes."
            }))
            requests = root / "requests.json"
            requests.write_text(json.dumps({"schema_version": 1, "requests": [
                {"intent_id": intent, "title": "A technical article",
                 "status": "completed", "created_at": "2026-11-03"},
                {"intent_id": queued, "title": "Could this work?",
                 "status": "queued", "created_at": "2026-11-03"}
            ]}))
            output = root / "bundle"
            build(root / "deliveries", output, Path(__file__).with_name("index.html"),
                  15, requests=requests)
            data = json.loads((output / "assets/episodes.json").read_text())
            self.assertEqual(data["items"][0]["content_id"], intent)
            self.assertEqual(data["items"][0]["source"], "Your research")
            self.assertEqual(len(data["research_requests"]), 1)
            self.assertEqual(data["research_requests"][0]["intent_id"], queued)
            self.assertIn(queued, (output / "index.html").read_text())
            self.assertNotIn('"intent_id": "' + intent + '"', json.dumps(data["research_requests"]))
            self.assertEqual(len(data["episodes"]), 0)

    def test_untrusted_research_status_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "article-20261103"
            folder.mkdir(parents=True)
            (folder / "article.md").write_text("# Topic\n\nSome content.")
            requests = root / "bad.json"
            requests.write_text(json.dumps({"requests": [
                {"intent_id": "bad", "status": "researching", "title": "untrusted"},
                {"intent_id": "int_" + "b"*32, "status": "hacked", "title": "untrusted"}
            ]}))
            output = root / "bundle"
            build(root / "deliveries", output, Path(__file__).with_name("index.html"),
                  15, requests=requests)
            data = json.loads((output / "assets/episodes.json").read_text())
            self.assertEqual(data["research_requests"], [])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires local audio tools")
    def test_strict_media_audit_rejects_truncated_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "article-20261103"
            folder.mkdir(parents=True)
            (folder / "article.md").write_text("# Important research result\\n\\nFull article.")
            audio = folder / "podcast.mp3"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                            "-y", "-f", "lavfi", "-i", "sine=frequency=400:duration=6",
                            "-codec:a", "libmp3lame", "-b:a", "64k", str(audio)],
                           check=True, timeout=30, capture_output=True)
            target = root / "good-bundle"
            build(root / "deliveries", target, Path(__file__).with_name("index.html"),
                  15, verify_audio=True)
            data = json.loads((target / "assets/episodes.json").read_text())
            self.assertGreater(data["items"][0]["formats"]["audio"]["duration_seconds"], 5)
            report = json.loads((target / "build-report.json").read_text())
            self.assertTrue(report["audio_audit"]["article-20261103"]["verified"])
            original = audio.read_bytes()
            audio.write_bytes(original[:len(original)//3])
            with self.assertRaisesRegex(ValueError, "Audio validation failed"):
                build(root / "deliveries", root / "rejected-bundle",
                      Path(__file__).with_name("index.html"), 15, verify_audio=True)
            self.assertFalse((root / "rejected-bundle").exists())

    def test_zero_cost_article_narration_and_consumption_contract(self):
        html = Path(__file__).with_name("index.html").read_text()
        self.assertIn("speechSynthesis.speak(utterance)", html)
        self.assertIn("markDone(completedId,'device_voice')", html)
        self.assertIn("stopNarration()", html)
        self.assertIn("bottomSeen&&readMs>=minMs", html)
        self.assertIn("Reading history cannot be saved", html)

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
