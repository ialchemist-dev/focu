"""Durable, idempotent research-intent queue; no external service required."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

STATUSES = {"queued", "researching", "completed", "failed"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class IntentStore:
    def __init__(self, db_path: str | Path = "data/the-few.sqlite3") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS intents (
                id TEXT PRIMARY KEY, question TEXT NOT NULL,
                kind TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                deliver_after TEXT, evidence_pack_id TEXT, error TEXT
            )""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def capture(self, question: str, *, kind: str = "one_time_research",
                deliver_after: str | None = None, intent_id: str | None = None) -> dict:
        question = question.strip()
        if not question:
            raise ValueError("Question must not be empty")
        if kind not in {"one_time_research", "recurring"}:
            raise ValueError("Unsupported intent kind")
        intent_id = intent_id or "int_" + uuid.uuid4().hex
        if not intent_id.startswith("int_") or len(intent_id) != 36:
            raise ValueError("Invalid intent id")
        now = utcnow()
        with self._connect() as db:
            db.execute("""INSERT OR IGNORE INTO intents
                (id, question, kind, status, created_at, updated_at, deliver_after)
                VALUES (?, ?, ?, 'queued', ?, ?, ?)""",
                (intent_id, question, kind, now, now, deliver_after))
        return self.get(intent_id)

    def get(self, intent_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM intents WHERE id=?", (intent_id,)).fetchone()
        return {"schema_version": "0.2", **dict(row)} if row else None

    def list(self, status: str | None = None) -> list[dict]:
        if status is not None and status not in STATUSES:
            raise ValueError("Invalid status")
        with self._connect() as db:
            if status:
                rows = db.execute("SELECT * FROM intents WHERE status=? ORDER BY created_at, id", (status,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM intents ORDER BY created_at, id").fetchall()
        return [{"schema_version": "0.2", **dict(row)} for row in rows]

    def transition(self, intent_id: str, expected_status: str, new_status: str,
                   *, evidence_pack_id: str | None = None, error: str | None = None) -> dict:
        allowed = {"queued": {"researching"}, "researching": {"completed", "failed"},
                   "failed": {"queued"}, "completed": set()}
        if new_status not in allowed.get(expected_status, set()):
            raise ValueError("Invalid status transition")
        if new_status == "completed" and not evidence_pack_id:
            raise ValueError("Completed research requires an evidence pack ID")
        with self._connect() as db:
            cur = db.execute("""UPDATE intents SET status=?, updated_at=?,
                evidence_pack_id=?, error=? WHERE id=? AND status=?""",
                (new_status, utcnow(), evidence_pack_id, error, intent_id, expected_status))
            if cur.rowcount != 1:
                raise ValueError("Intent missing or changed concurrently")
        return self.get(intent_id)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Capture and inspect research intents")
    parser.add_argument("--db", default="data/the-few.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("question")
    capture.add_argument("--id", dest="intent_id")
    listing = sub.add_parser("list")
    listing.add_argument("--status", choices=sorted(STATUSES))
    args = parser.parse_args()
    store = IntentStore(args.db)
    result = (store.capture(args.question, intent_id=args.intent_id)
              if args.command == "capture" else store.list(args.status))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
