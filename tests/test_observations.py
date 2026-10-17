import tempfile
import unittest
from pathlib import Path

from focu.observations import ObservationStore, canonical_url, content_hash


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "focu.sqlite3"
        self.store = ObservationStore(self.db)

    def test_first_repeat_and_change(self):
        first = self.store.observe("watch_1", "HTTPS://Example.COM/a#fragment", "A  new   fact")
        self.assertEqual(first["status"], "new")
        repeated = self.store.observe("watch_1", "https://example.com/a", "A new fact")
        self.assertEqual(repeated["status"], "unchanged")
        self.assertEqual(first["observation_id"], repeated["observation_id"])
        changed = self.store.observe("watch_1", "https://example.com/a", "Another fact")
        self.assertEqual(changed["status"], "changed")
        self.assertTrue(changed["requires_semantic_review"])
        self.assertEqual(self.store.observe("watch_1", "https://example.com/a", "Another fact")["status"], "unchanged")

    def test_scope_isolation(self):
        self.store.observe("one", "https://example.com/", "a")
        self.assertEqual(self.store.observe("two", "https://example.com/", "a")["status"], "new")

    def test_reopen_preserves_history(self):
        self.store.observe("watch", "https://example.com", "content")
        reopened = ObservationStore(self.db)
        self.assertEqual(reopened.observe("watch", "https://example.com/", "content")["status"], "unchanged")

    def test_reappearance_does_not_claim_new_change(self):
        self.store.observe("watch", "https://example.com", "a")
        self.store.observe("watch", "https://example.com", "b")
        result = self.store.observe("watch", "https://example.com", "a")
        self.assertEqual(result["status"], "unchanged")

    def test_invalid_inputs(self):
        for url in ["file:///etc/passwd", "not-a-url", "https://"]:
            with self.assertRaises(ValueError):
                self.store.observe("watch", url, "content")
        with self.assertRaises(ValueError):
            self.store.observe("", "https://example.com", "content")
        with self.assertRaises(ValueError):
            self.store.observe("watch", "https://example.com", "   ")
