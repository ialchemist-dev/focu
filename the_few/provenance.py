"""Optional evidence provenance contract, backwards compatible with v0.2 packs."""
from __future__ import annotations

import re


def normalized_text(value: str) -> str:
    return re.sub(r"\\s+", " ", value).strip()


SOURCE_TYPES = {"primary", "secondary_reporting", "search_snippet", "unknown"}
ACCESS_STATUSES = {"full", "partial", "paywalled", "unavailable", "not_attempted"}
VERIFICATION_LEVELS = {"checked_extracted_text", "checked_original_document", "unverified"}
COMPLETENESS = {"complete", "partial", "blocked"}


def validate_provenance(pack: dict) -> None:
    for source in pack["sources"]:
        for field, allowed in (
            ("source_type", SOURCE_TYPES),
            ("access_status", ACCESS_STATUSES),
            ("verification", VERIFICATION_LEVELS),
        ):
            if field in source and source[field] not in allowed:
                raise ValueError(f"Invalid {field} for source {source['id']}")
        if "original_source_accessed" in source and not isinstance(source["original_source_accessed"], bool):
            raise ValueError("original_source_accessed must be boolean")
        if "accessed_at" in source and (not isinstance(source["accessed_at"], str) or not source["accessed_at"].strip()):
            raise ValueError("accessed_at must be a nonempty timestamp")
        if "extracted_text" in source and (not isinstance(source["extracted_text"], str) or not source["extracted_text"].strip()):
            raise ValueError("extracted_text must be nonempty")
        if source.get("verification") in {"checked_extracted_text", "checked_original_document"}:
            if source.get("access_status") in {"unavailable", "not_attempted"}:
                raise ValueError("Cannot verify an unavailable or unattempted source")
            if source.get("verification") == "checked_extracted_text" and not source.get("extracted_text"):
                raise ValueError("checked_extracted_text requires captured extracted_text")
            if source.get("verification") == "checked_original_document" and source.get("original_source_accessed") is not True:
                raise ValueError("checked_original_document requires original_source_accessed=true")
        if source.get("source_type") == "search_snippet" and source.get("verification") not in {None, "unverified"}:
            raise ValueError("Search snippets cannot be marked as verified")
    if "research_completeness" in pack:
        rc = pack["research_completeness"]
        if not isinstance(rc, dict) or rc.get("status") not in COMPLETENESS:
            raise ValueError("Invalid research completeness")
        for key in ("answered", "unverified", "limitations"):
            if key in rc and (not isinstance(rc[key], list) or any(not isinstance(x, str) or not x.strip() for x in rc[key])):
                raise ValueError(f"Invalid research completeness {key}")
        if rc["status"] == "complete" and (rc.get("unverified") or rc.get("limitations")):
            raise ValueError("Complete research cannot list unresolved items or limitations")
    sources = {source["id"]: source for source in pack["sources"]}
    for finding in pack["findings"]:
        if "evidence_quote" in finding and (not isinstance(finding["evidence_quote"], str) or not finding["evidence_quote"].strip()):
            raise ValueError("evidence_quote must be nonempty")
        for source_id in finding["source_ids"]:
            source = sources[source_id]
            if source.get("source_type") == "search_snippet":
                raise ValueError("Search snippets cannot support findings")
            if source.get("access_status") in {"unavailable", "not_attempted"}:
                raise ValueError("Inaccessible sources cannot support findings")
            if finding.get("evidence_quote") and source.get("extracted_text"):
                if normalized_text(finding["evidence_quote"]) not in normalized_text(source["extracted_text"]):
                    raise ValueError("Evidence quote not present in cited extracted text")
