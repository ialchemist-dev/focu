"""Deterministic, local observation history for host-managed repeated research.

This module compares exact normalized content, not semantic significance.
No notifications, subscriptions, or external requests are performed.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def canonical_url(url: str) -> str:
    if not isinstance(url, str):
        raise ValueError("URL must be a string")
    value = url.strip()
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("Observation URL must be HTTP(S)")
    host = parts.hostname.lower()
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("Invalid URL port") from exc
    if ":" in host:
        host = f"[{host}]"
    if port and port != (443 if parts.scheme.lower() == "https" else 80):
        host += f":{port}"
    return urlunsplit((parts.scheme.lower(), host, parts.path or "/", parts.query, ""))


def content_hash(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("Observation content must be text")
    normalized = " ".join(text.split())
    if not normalized:
        raise ValueError("Observation content cannot be empty")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class ObservationStore:
    def __init__(self, db_path: str | Path = "data/focu.sqlite3") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_id TEXT NOT NULL,
                source_url TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                UNIQUE(scope_id, source_url, content_sha256)
            )""")
            db.execute("""CREATE INDEX IF NOT EXISTS idx_observations_source
                ON observations(scope_id, source_url, id DESC)""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def observe(self, scope_id: str, url: str, content: str) -> dict:
        """Return new, changed, or unchanged; retries do not add duplicates.

        'changed' means content differs from the latest *recorded* version,
        not that a host agent judged the change meaningful.
        """
        if not isinstance(scope_id, str) or not scope_id.strip():
            raise ValueError("scope_id is required")
        scope_id = scope_id.strip()
        source_url = canonical_url(url)
        digest = content_hash(content)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            latest = db.execute("""SELECT id, content_sha256 FROM observations
                WHERE scope_id=? AND source_url=? ORDER BY id DESC LIMIT 1""",
                (scope_id, source_url)).fetchone()
            if latest and latest["content_sha256"] == digest:
                status = "unchanged"
                observation_id = latest["id"]
            else:
                status = "changed" if latest else "new"
                cur = db.execute("""INSERT OR IGNORE INTO observations
                    (scope_id, source_url, content_sha256, observed_at)
                    VALUES (?, ?, ?, ?)""", (scope_id, source_url, digest, now))
                if cur.rowcount:
                    observation_id = cur.lastrowid
                else:
                    existing = db.execute("""SELECT id FROM observations WHERE
                        scope_id=? AND source_url=? AND content_sha256=?""",
                        (scope_id, source_url, digest)).fetchone()
                    observation_id = existing["id"]
                    status = "unchanged"
        return {"status": status, "observation_id": observation_id,
                "scope_id": scope_id, "source_url": source_url,
                "content_sha256": digest, "requires_semantic_review": status != "unchanged"}
