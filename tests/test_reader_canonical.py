"""Reader canonical_url unification (backend-design §5 follow-up, Q6).

The reader used to carry its own canonicalizer: it stripped trailing
slashes but kept tracking parameters, while the daily registry's
``focu.daily.identity.canonical_url`` does the opposite on both counts.
The same publication could therefore dedupe in one registry and not the
other. These tests pin the reader to the registry's identity semantics.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from focu.daily.identity import canonical_url as identity_canonical_url
from focu.reader import ReaderStore, canonical_url
from focu.source_collection import parse_feed


class ReaderCanonicalUrlTests(unittest.TestCase):
    def test_reader_matches_identity_on_a_url_battery(self):
        urls = [
            "https://example.org/blog",
            "https://example.org/blog/",
            "https://EXAMPLE.org/Blog/Post?id=12&utm_source=x#part",
            "https://example.org/feed?fbclid=abc&x=1",
            "https://twitter.com/person/status/1",
            "https://www.youtube.com/watch?v=abc123&utm_medium=email",
            "https://youtu.be/abc123",
            "https://example.org:443/a",
            "http://example.org:80/a",
            "https://example.org/a?b=&c=2",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(canonical_url(url), identity_canonical_url(url))

    def test_tracking_param_variants_dedupe(self):
        self.assertEqual(
            canonical_url("https://example.org/blog?utm_source=news"),
            canonical_url("https://example.org/blog"),
        )

    def test_trailing_slash_variants_stay_distinct(self):
        # The registry deliberately preserves trailing slashes: the
        # equivalence is not guaranteed for arbitrary publishers, and a
        # reader-side merge would hide a source the pipeline counts
        # separately (daily raises on duplicate identity instead).
        self.assertNotEqual(
            canonical_url("https://example.org/blog"),
            canonical_url("https://example.org/blog/"),
        )

    def test_platform_forms_normalize_like_the_registry(self):
        self.assertEqual(
            canonical_url("https://twitter.com/person/status/1"),
            canonical_url("https://x.com/person/status/1"),
        )
        self.assertEqual(
            canonical_url("https://youtu.be/abc123"),
            canonical_url("https://www.youtube.com/watch?v=abc123"),
        )

    def test_unknown_query_and_path_case_stay_significant(self):
        self.assertNotEqual(
            canonical_url("https://example.org/?id=12"),
            canonical_url("https://example.org/?id=13"),
        )
        self.assertNotEqual(
            canonical_url("https://example.org/A"),
            canonical_url("https://example.org/a"),
        )

    def test_rejects_credentials_non_http_and_non_strings(self):
        for bad in (
            "https://user:secret@example.org/a",
            "ftp://example.org/a",
            "example.org/no-scheme",
            None,
            42,
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    canonical_url(bad)


class ReaderSourcesDedupeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = ReaderStore(self.root / "focu.sqlite3")

    def _packs(self, spec):
        packs = self.root / "packs"
        packs.mkdir(exist_ok=True)
        for pid, urls in spec.items():
            (packs / (pid + ".json")).write_text(json.dumps({
                "id": pid, "version": "1",
                "sources": [
                    {"name": "Author", "site_url": url, "feed_url": url,
                     "channel": "research", "type": "rss"}
                    for url in urls
                ],
            }))
        return packs

    def test_tracking_variant_of_same_feed_dedupes_across_packs(self):
        packs = self._packs({
            "a": ["https://example.org/feed"],
            "b": ["https://example.org/feed?utm_source=pack"],
        })
        with patch("focu.reader.PACKS", packs):
            self.store.subscribe("a", True, "1")
            self.store.subscribe("b", True, "1")
            sources = self.store.sources()
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["groups"], ["a", "b"])

    def test_trailing_slash_variant_is_a_distinct_source(self):
        packs = self._packs({
            "a": ["https://example.org/feed"],
            "b": ["https://example.org/feed/"],
        })
        with patch("focu.reader.PACKS", packs):
            self.store.subscribe("a", True, "1")
            self.store.subscribe("b", True, "1")
            self.assertEqual(len(self.store.sources()), 2)


class ParseFeedCanonicalTests(unittest.TestCase):
    def test_feed_item_urls_are_identity_canonical(self):
        rss = (
            b'<rss><channel>'
            b'<item><title>A</title>'
            b"<link>https://example.org/a?utm_source=rss</link>"
            b"<description>Fact</description></item>"
            b'<item><title>B</title>'
            b"<link>https://youtu.be/abc123</link>"
            b"<description>Video</description></item>"
            b"</channel></rss>"
        )
        records = parse_feed(rss, "https://example.org/feed")
        self.assertEqual(records[0]["url"], "https://example.org/a")
        self.assertEqual(
            records[1]["url"], "https://www.youtube.com/watch?v=abc123"
        )


if __name__ == "__main__":
    unittest.main()
