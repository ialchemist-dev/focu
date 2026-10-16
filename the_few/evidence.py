"""Validate and persist evidence packs with source-reference integrity."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from urllib.parse import urlparse
from the_few.provenance import validate_provenance


def validate_pack(pack: dict) -> None:
    required = {"schema_version", "id", "intent_id", "summary", "findings", "sources", "created_at"}
    if not isinstance(pack, dict) or not required.issubset(pack):
        raise ValueError("Missing evidence pack fields")
    if pack["schema_version"] != "0.2" or not all(isinstance(pack[k], str) and pack[k].strip() for k in ("id", "intent_id", "summary", "created_at")):
        raise ValueError("Invalid evidence pack metadata")
    if not isinstance(pack["sources"], list) or not pack["sources"]:
        raise ValueError("Evidence requires sources")
    source_ids = set()
    for source in pack["sources"]:
        if not isinstance(source, dict) or not all(isinstance(source.get(k), str) and source[k].strip() for k in ("id", "url", "title")):
            raise ValueError("Invalid evidence source")
        parsed = urlparse(source["url"])
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Source URL must be HTTP(S)")
        if source["id"] in source_ids:
            raise ValueError("Duplicate source ID")
        source_ids.add(source["id"])
    if not isinstance(pack["findings"], list) or not pack["findings"]:
        raise ValueError("Evidence requires findings")
    for finding in pack["findings"]:
        if not isinstance(finding, dict) or not isinstance(finding.get("claim"), str) or not finding["claim"].strip():
            raise ValueError("Invalid finding")
        refs = finding.get("source_ids")
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or ref not in source_ids for ref in refs) or len(set(refs)) != len(refs):
            raise ValueError("Finding cites unknown or duplicate source IDs")

    validate_provenance(pack)


class EvidenceStore:
    def __init__(self, db_path: str | Path = "data/the-few.sqlite3") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS evidence_packs (
                id TEXT PRIMARY KEY, intent_id TEXT NOT NULL,
                payload TEXT NOT NULL, created_at TEXT NOT NULL
            )""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def save(self, pack: dict) -> dict:
        validate_pack(pack)
        payload = json.dumps(pack, ensure_ascii=False, sort_keys=True)
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO evidence_packs (id, intent_id, payload, created_at) VALUES (?, ?, ?, ?)",
                       (pack["id"], pack["intent_id"], payload, pack["created_at"]))
            row = db.execute("SELECT payload FROM evidence_packs WHERE id=?", (pack["id"],)).fetchone()
            if row["payload"] != payload:
                raise ValueError("Evidence pack ID already exists with different content")
        return pack

    def get(self, pack_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM evidence_packs WHERE id=?", (pack_id,)).fetchone()
        return json.loads(row["payload"]) if row else None
