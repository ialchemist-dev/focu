import unittest
from focu.evidence import validate_pack


def pack():
    return {
        "schema_version": "0.2", "id": "ev_1", "intent_id": "int_" + "a" * 32,
        "summary": "Test", "created_at": "2026-10-15T00:00:00Z",
        "sources": [{"id": "s1", "url": "https://example.org", "title": "Example",
                     "source_type": "secondary_reporting", "access_status": "partial",
                     "verification": "checked_extracted_text", "original_source_accessed": False,
                     "extracted_text": "The reported figure is 12 percent."}],
        "findings": [{"claim": "The report says 12 percent.", "source_ids": ["s1"],
                      "evidence_quote": "12 percent"}],
        "research_completeness": {"status": "partial", "answered": ["reported figure"],
                                  "unverified": ["original PDF"], "limitations": ["secondary source only"]}
    }


class ProvenanceTests(unittest.TestCase):
    def test_partial_secondary_source_is_allowed(self):
        validate_pack(pack())

    def test_search_snippet_cannot_support_claim(self):
        item = pack()
        item["sources"][0]["source_type"] = "search_snippet"
        item["sources"][0]["verification"] = "unverified"
        with self.assertRaises(ValueError):
            validate_pack(item)

    def test_unavailable_source_cannot_be_verified(self):
        item = pack()
        item["sources"][0]["access_status"] = "unavailable"
        with self.assertRaises(ValueError):
            validate_pack(item)

    def test_quote_must_be_present_in_extracted_text(self):
        item = pack()
        item["findings"][0]["evidence_quote"] = "a different figure"
        with self.assertRaises(ValueError):
            validate_pack(item)

    def test_complete_research_cannot_hide_unverified_items(self):
        item = pack()
        item["research_completeness"]["status"] = "complete"
        with self.assertRaises(ValueError):
            validate_pack(item)

    def test_legacy_pack_remains_valid(self):
        item = pack()
        item.pop("research_completeness")
        for key in ["source_type", "access_status", "verification", "original_source_accessed", "extracted_text"]:
            item["sources"][0].pop(key)
        item["findings"][0].pop("evidence_quote")
        validate_pack(item)


if __name__ == "__main__":
    unittest.main()
