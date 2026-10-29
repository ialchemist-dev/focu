"""Explicit feedback ledger: learning signals without autonomous policy changes."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

KINDS = {"useful", "not_useful", "incorrect", "too_long", "missed_important", "other"}
TARGETS = {"episode", "evidence_pack", "observation", "research_intent"}


class FeedbackStore:
    def __init__(self, db_path: str | Path = "data/focu.sqlite3") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS feedback_events (
                id TEXT PRIMARY KEY,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""")
            db.execute("""CREATE INDEX IF NOT EXISTS idx_feedback_target
                ON feedback_events(target_type, target_id, created_at)""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def record(self, *, target_type: str, target_id: str, kind: str,
               note: str = "", event_id: str | None = None) -> dict:
        if target_type not in TARGETS:
            raise ValueError("Unsupported feedback target type")
        if kind not in KINDS:
            raise ValueError("Unsupported feedback kind")
        if not isinstance(target_id, str) or not target_id.strip():
            raise ValueError("Feedback target ID required")
        if not isinstance(note, str) or len(note) > 4000:
            raise ValueError("Feedback note must be text up to 4000 characters")
        event_id = event_id or "fb_" + uuid.uuid4().hex
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("Feedback event ID required")
        event = {"id": event_id, "target_type": target_type, "target_id": target_id.strip(),
                 "kind": kind, "note": note,
                 "created_at": datetime.now(timezone.utc).isoformat()}
        with self._connect() as db:
            db.execute("""INSERT OR IGNORE INTO feedback_events
                (id, target_type, target_id, kind, note, created_at)
                VALUES (:id, :target_type, :target_id, :kind, :note, :created_at)""", event)
            row = db.execute("SELECT * FROM feedback_events WHERE id=?", (event_id,)).fetchone()
            if any(row[k] != event[k] for k in ("target_type", "target_id", "kind", "note")):
                raise ValueError("Feedback event ID reused with different content")
        return dict(row)

    def list(self, *, target_type: str | None = None, target_id: str | None = None) -> list[dict]:
        if target_type is not None and target_type not in TARGETS:
            raise ValueError("Unsupported feedback target type")
        with self._connect() as db:
            rows = db.execute("""SELECT * FROM feedback_events
                WHERE (? IS NULL OR target_type=?) AND (? IS NULL OR target_id=?)
                ORDER BY created_at, id""", (target_type, target_type, target_id, target_id)).fetchall()
        return [dict(row) for row in rows]


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Explicit feedback for future offline evaluation")
    parser.add_argument("--db", default="data/focu.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("record")
    add.add_argument("--target-type", required=True, choices=sorted(TARGETS))
    add.add_argument("--target-id", required=True)
    add.add_argument("--kind", required=True, choices=sorted(KINDS))
    add.add_argument("--note", default="")
    add.add_argument("--event-id")
    listing = sub.add_parser("list")
    listing.add_argument("--target-type", choices=sorted(TARGETS))
    listing.add_argument("--target-id")
    args = parser.parse_args(argv)
    try:
        store = FeedbackStore(args.db)
        result = (store.record(target_type=args.target_type, target_id=args.target_id,
                               kind=args.kind, note=args.note, event_id=args.event_id)
                  if args.command == "record" else
                  store.list(target_type=args.target_type, target_id=args.target_id))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        import sys
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
