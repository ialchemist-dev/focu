import tempfile
import unittest
from pathlib import Path
from the_few.provenance import normalized_text
from the_few.evidence import validate_pack
from the_few.research import render_markdown
from the_few.snapshots import save_snapshot, verify_snapshot


class AuditabilityTests(unittest.TestCase):
    def test_normalized_whitespace(self):
        self.assertEqual(normalized_text("alpha\t  beta\n gamma"), "alpha beta gamma")

    def test_quote_with_whitespace_variation(self):
        pack = {"schema_version": "0.2", "id": "ev_x", "intent_id": "int_" + "a"*32,
                "summary": "Summary", "created_at": "2026-10-16T00:00:00Z",
                "sources": [{"id": "s1", "url": "https://example.com", "title": "Example",
                             "extracted_text": "alpha\t  beta\n gamma"}],
                "findings": [{"claim": "Claim", "source_ids": ["s1"],
                              "evidence_quote": "alpha beta gamma"}]}
        validate_pack(pack)
        rendered = render_markdown(pack, "Question")
        self.assertIn("> alpha beta gamma", rendered)

    def test_snapshot_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            metadata = save_snapshot(tmp, url="https://example.com", text="Research text")
            self.assertTrue(verify_snapshot(metadata["path"], metadata["sha256"]))
            Path(metadata["path"]).write_text("tampered", encoding="utf-8")
            self.assertFalse(verify_snapshot(metadata["path"], metadata["sha256"]))


if __name__ == "__main__":
    unittest.main()
