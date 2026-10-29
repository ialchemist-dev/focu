import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from focu.collectors import youtube_video_id, linkedin_feed_from_export, collect_export, collect_youtube, SourceRecord

class CollectorTests(unittest.TestCase):
    def test_youtube_url_variants(self):
        vid = "dQw4w9WgXcQ"
        for url in [f"https://youtu.be/{vid}", f"https://www.youtube.com/watch?v={vid}&t=10",
                    f"https://youtube.com/shorts/{vid}", f"https://m.youtube.com/live/{vid}"]:
            self.assertEqual(youtube_video_id(url), vid)
        for bad in ["https://evil.example/watch?v=dQw4w9WgXcQ", "https://youtube.com/watch?v=bad",
                    "file:///tmp/x"]:
            with self.assertRaises(ValueError):
                youtube_video_id(bad)

    def test_linkedin_normalize(self):
        posts = [{"post_url":"https://www.linkedin.com/feed/update/urn:li:activity:123/",
                  "text":"Hello", "author":{"name":"A"}}]
        result = linkedin_feed_from_export({"posts":posts})
        self.assertEqual(result[0].author, "A")
        with self.assertRaises(ValueError):
            linkedin_feed_from_export([{"url":"https://evil.example/posts/1", "text":"bad"}])

    def test_export_dedup_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            src = path / "feed.json"
            src.write_text(json.dumps({"posts":[{"url":"https://linkedin.com/feed/update/urn:li:activity:123/",
                                                 "text":"Hello"}]}))
            args = (src, "linkedin", path / "db.sqlite3", "feed", path / "result.json")
            self.assertEqual(collect_export(*args)["new_or_changed"], 1)
            self.assertEqual(collect_export(*args)["new_or_changed"], 0)

    def test_youtube_offline_mock(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            record = SourceRecord("youtube","https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                None,None,"Hello","2026-10-18T00:00:00Z","youtube-transcript-api",
                [{"text":"Hello","start":0.0,"duration":1.0}])
            args = ("https://youtu.be/dQw4w9WgXcQ", path / "db.sqlite3", "youtube", path / "video.json")
            with patch("focu.collectors.youtube_transcript", return_value=record):
                self.assertEqual(collect_youtube(*args)["status"], "new")
                self.assertEqual(collect_youtube(*args)["status"], "unchanged")
