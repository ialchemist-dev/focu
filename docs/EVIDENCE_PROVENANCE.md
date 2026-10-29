# Evidence provenance (v0.2 optional extension)

The Muse live test revealed partial HBR access and secondary reporting of Reuters numbers. A citation URL alone does not prove a claim. Evidence Packs now accept **optional** source provenance and research completeness fields, while old v0.2 packs remain compatible.

Source fields:
- `source_type`: `primary`, `secondary_reporting`, `search_snippet`, `unknown`
- `access_status`: `full`, `partial`, `paywalled`, `unavailable`, `not_attempted`
- `verification`: `checked_extracted_text`, `checked_original_document`, `unverified`
- `original_source_accessed`: boolean
- `extracted_text`: captured source text for checking exact quotes
- `accessed_at`: optional timestamp

Findings may carry `evidence_quote`; if captured text exists, the exact quote must occur in it. This **does not prove** that the claim logically follows from the quote, and does not guarantee the text was genuinely fetched. The agent must still review it.

A `search_snippet` or inaccessible source cannot support a finding. A source marked `checked_extracted_text` must include nonempty captured text; `checked_original_document` requires `original_source_accessed=true`. The system rejects internally inconsistent declarations, not dishonest declarations.

Optional `research_completeness`:

```json
{
  "status": "partial",
  "answered": ["Muse launch details available in accessible text"],
  "unverified": ["Original Reuters PDF", "Shopify/Walmart details"],
  "limitations": ["HBR article partially accessible", "GIJN is secondary reporting"]
}
```

A pack cannot mark research `complete` while listing unresolved or limited items. The Markdown renderer shows these caveats so users can see what was not established.

Run `python -m unittest discover -s tests -v` to exercise compatibility and negative tests. Real internet and primary-document validation are separate future work; no PDF/JS support is claimed.
