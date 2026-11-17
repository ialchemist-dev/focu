"""Pin the ReaderStore side of the source-pack contract (PM sweep #3, S3-F2).

Two pack consumers read focu/source_packs/: focu/packs.py (validate /
normalize / catalog) and the legacy ReaderStore. The reader's contract used
to be held only by writer discipline — v1 writers dual-emit the legacy
site_url alias alongside the canonical homepage. These tests pin what the
reader actually guarantees: every shipped pack round-trips through it, a
canonically written (homepage-only) pack works, and a malformed file
degrades to an error entry the way focu pack catalog degrades it.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from focu.reader import PACKS as SHIPPED_PACKS_DIR
from focu.reader import ReaderStore, canonical_url


def expected_locators(pack):
    return {
        canonical_url(s.get('feed_url') or s.get('site_url') or s.get('homepage'))
        for s in pack['sources']
    }


class ShippedPackRoundTripTests(unittest.TestCase):
    """Every pack shipped in focu/source_packs/ loads through ReaderStore."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / 'focu.sqlite3'
        self.shipped = {}
        for path in sorted(SHIPPED_PACKS_DIR.glob('*.json')):
            pack = json.loads(path.read_text(encoding='utf-8'))
            self.shipped[pack['id']] = pack
        # The pin is meaningless if the shelf silently empties.
        self.assertGreaterEqual(len(self.shipped), 4)

    def test_packs_lists_every_shipped_pack_unsubscribed(self):
        store = ReaderStore(self.db_path)
        listed = {p['id']: p for p in store.packs() if 'id' in p}
        self.assertEqual(set(listed), set(self.shipped))
        for pack_id, pack in self.shipped.items():
            self.assertEqual(listed[pack_id]['version'], pack['version'])
            self.assertIsNone(listed[pack_id]['subscribed_version'])

    def test_subscribe_at_pinned_version_and_sources_round_trip(self):
        for pack_id, pack in self.shipped.items():
            with self.subTest(pack=pack_id):
                store = ReaderStore(Path(self.tmp.name) / (pack_id + '.sqlite3'))
                with self.assertRaises(ValueError):
                    store.subscribe(pack_id, True, '0.0.0-unpinned')
                result = store.subscribe(pack_id, True, pack['version'])
                self.assertEqual(result, {'id': pack_id, 'subscribed': True,
                                          'version': pack['version']})
                listed = {p['id']: p for p in store.packs() if 'id' in p}
                self.assertEqual(listed[pack_id]['subscribed_version'],
                                 pack['version'])
                sources = store.sources()
                self.assertEqual(
                    {canonical_url(s.get('feed_url') or s['site_url'])
                     for s in sources},
                    expected_locators(pack))
                for source in sources:
                    self.assertEqual(source['groups'], [pack_id])
                store.subscribe(pack_id, False)
                self.assertEqual(store.sources(), [])

    def test_all_shipped_packs_subscribed_together(self):
        store = ReaderStore(self.db_path)
        for pack_id, pack in self.shipped.items():
            store.subscribe(pack_id, True, pack['version'])
        sources = store.sources()
        expected = set()
        for pack in self.shipped.values():
            expected |= expected_locators(pack)
        self.assertEqual(
            {canonical_url(s.get('feed_url') or s['site_url']) for s in sources},
            expected)
        grouped = set()
        for source in sources:
            grouped |= set(source['groups'])
        self.assertEqual(grouped, set(self.shipped))


class HomepageFallbackTests(unittest.TestCase):
    """sources() honors the packs.py alias rule: homepage is canonical."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.packs_dir = self.root / 'packs'
        self.packs_dir.mkdir()
        self.store = ReaderStore(self.root / 'focu.sqlite3')

    def write_pack(self, pack):
        (self.packs_dir / (pack['id'] + '.json')).write_text(json.dumps(pack))

    def test_homepage_only_source_resolves(self):
        # The canonical v1 shape: homepage, no legacy site_url alias.
        self.write_pack({'id': 'canon', 'version': '1', 'sources': [
            {'name': 'Canonical', 'homepage': 'https://canon.example.org'}]})
        with patch('focu.reader.PACKS', self.packs_dir):
            self.store.subscribe('canon', True, '1')
            sources = self.store.sources()
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]['homepage'], 'https://canon.example.org')

    def test_site_url_only_source_still_resolves(self):
        self.write_pack({'id': 'legacy', 'version': '1', 'sources': [
            {'name': 'Legacy', 'site_url': 'https://legacy.example.org'}]})
        with patch('focu.reader.PACKS', self.packs_dir):
            self.store.subscribe('legacy', True, '1')
            sources = self.store.sources()
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]['site_url'], 'https://legacy.example.org')

    def test_feed_url_still_wins_over_homepage(self):
        self.write_pack({'id': 'feeded', 'version': '1', 'sources': [
            {'name': 'Feeded', 'homepage': 'https://feeded.example.org',
             'feed_url': 'https://feeded.example.org/rss.xml'}]})
        with patch('focu.reader.PACKS', self.packs_dir):
            self.store.subscribe('feeded', True, '1')
            sources = self.store.sources()
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]['feed_url'],
                         'https://feeded.example.org/rss.xml')


class MalformedPackDegradationTests(unittest.TestCase):
    """packs() degrades a bad file to an error entry, like focu pack catalog."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.packs_dir = self.root / 'packs'
        self.packs_dir.mkdir()
        self.store = ReaderStore(self.root / 'focu.sqlite3')
        (self.packs_dir / 'good.json').write_text(json.dumps(
            {'id': 'good', 'version': '1', 'sources': [
                {'name': 'Good', 'site_url': 'https://good.example.org'}]}))
        (self.packs_dir / 'broken.json').write_text('{"id": "broken", ')
        (self.packs_dir / 'list.json').write_text('["not", "a", "pack"]')

    def test_packs_degrades_instead_of_raising(self):
        with patch('focu.reader.PACKS', self.packs_dir):
            packs = self.store.packs()
        by_file = {p.get('file'): p for p in packs if 'error' in p}
        self.assertEqual(by_file['broken.json']['error'], 'unreadable')
        self.assertEqual(by_file['list.json']['error'],
                         'pack must be a JSON object')
        good = next(p for p in packs if p.get('id') == 'good')
        self.assertIsNone(good['subscribed_version'])

    def test_subscribe_survives_error_entries(self):
        with patch('focu.reader.PACKS', self.packs_dir):
            result = self.store.subscribe('good', True, '1')
            self.assertTrue(result['subscribed'])
            self.assertEqual(len(self.store.sources()), 1)
            with self.assertRaises(ValueError):
                self.store.subscribe('missing', True, '1')


if __name__ == '__main__':
    unittest.main()
