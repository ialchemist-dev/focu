"""Durable, one-shot user-initiated research capture.

Capture only. A host agent performs research and publication; this module
does not claim to start a background worker or fetch user-supplied URLs.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4

from focu.intents import IntentStore


def validate_seed_url(value: str | None) -> str | None:
    if not value:
        return None
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("Source URL exceeds limit")
    p = urlsplit(value.strip())
    if p.scheme not in {"https", "http"} or not p.hostname or p.username or p.password:
        raise ValueError("Only HTTP(S) source URLs without credentials are accepted")
    try:
        port = p.port
    except ValueError as exc:
        raise ValueError("Invalid URL port") from exc
    if port not in (None, 80, 443):
        raise ValueError("Nonstandard source URL ports are not accepted")
    host = p.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Private hostnames are not accepted as source URLs")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not ip.is_global:
            raise ValueError("Private or non-global IP addresses are not accepted")
    return value.strip()


def make_title(question: str, url: str | None) -> str:
    label = question.strip() or ("Investigate " + (url or ""))
    label = re.sub(r"\s+", " ", label)
    return (label[:117].rstrip() + "...") if len(label) > 120 else label


def capture_request(db_path: str | Path, question: str = "", *,
                    url: str | None = None, note: str = "",
                    force_new: bool = False, podcast: bool = False) -> dict:
    """Create a durable one-time request; duplicate submissions are idempotent.

    Stable fingerprint is scoped to this local Focu DB, not to a global URL
    corpus. A later explicit force_new always starts a new research task.
    """
    if not isinstance(question, str) or len(question) > 10000:
        raise ValueError("Research question exceeds 10,000 characters")
    if not isinstance(note, str) or len(note) > 5000:
        raise ValueError("Research note exceeds 5,000 characters")
    question, note = question.strip(), note.strip()
    url = validate_seed_url(url)
    if not question and not url:
        raise ValueError("Provide an idea, question, or source URL")
    task_question = question or ("Research this source, assess its main claims and context: " + url)
    source = json.dumps({"question": question, "url": url, "note": note},
                        sort_keys=True, ensure_ascii=False)
    digest = uuid4().hex if force_new else hashlib.sha256(source.encode("utf-8")).hexdigest()[:32]
    intent_id = "int_" + digest

    store = IntentStore(db_path)
    intent = store.capture(task_question, kind="one_time_research", intent_id=intent_id, podcast=podcast)

    with sqlite3.connect(str(db_path), timeout=30) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS research_requests (
            intent_id TEXT PRIMARY KEY,
            submitted_text TEXT NOT NULL,
            seed_url TEXT,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(intent_id) REFERENCES intents(id)
        )""")
        db.execute("""INSERT OR IGNORE INTO research_requests
                      (intent_id, submitted_text, seed_url, note, created_at)
                      VALUES (?, ?, ?, ?, ?)""",
                   (intent_id, question, url, note, intent["created_at"]))
    return {"intent_id": intent_id, "status": intent["status"],
            "title": make_title(question, url), "source_url": url,
            "note": note, "origin": "user_initiated",
            "created_at": intent["created_at"], "podcast_mode": intent["podcast_mode"],
            "podcast_requested_at": intent["podcast_requested_at"],
            "automatic_research_started": False}


def list_requests(db_path: str | Path) -> dict:
    store = IntentStore(db_path)
    # Initialize metadata table so fresh installations can export safely.
    with sqlite3.connect(str(db_path), timeout=30) as db:
        db.row_factory = sqlite3.Row
        db.execute("""CREATE TABLE IF NOT EXISTS research_requests (
            intent_id TEXT PRIMARY KEY,
            submitted_text TEXT NOT NULL,
            seed_url TEXT,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(intent_id) REFERENCES intents(id)
        )""")
        rows = db.execute("""SELECT r.intent_id, r.submitted_text, r.seed_url,
                                   r.note, r.created_at, i.status, i.updated_at,
                                   i.error, i.evidence_pack_id, i.podcast_mode, i.podcast_requested_at
                              FROM research_requests AS r
                              JOIN intents AS i ON r.intent_id=i.id
                             ORDER BY r.created_at DESC, r.intent_id DESC""").fetchall()
    items = []
    for row in rows:
        items.append({
            "intent_id": row["intent_id"], "content_id": row["intent_id"],
            "title": make_title(row["submitted_text"], row["seed_url"]),
            "source_url": row["seed_url"], "status": row["status"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "evidence_pack_id": row["evidence_pack_id"],
            "error": row["error"], "origin": "user_initiated",
            "podcast_mode": row["podcast_mode"],
            "podcast_requested_at": row["podcast_requested_at"],
        })
    return {"schema_version": 1, "requests": items}


def export_requests(db_path: str | Path, output: str | Path) -> dict:
    """Export a snapshot for the private static Muse Artifact.

    For privacy, personal notes and the full original prompt are not exposed
    in the static UI. The local database remains the authoritative record.
    """
    data = list_requests(db_path)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(output)
    finally:
        tmp.unlink(missing_ok=True)
    return {"output": str(output), "count": len(data["requests"])}


def main(argv: list[str] | None = None):
    import argparse
    parser = argparse.ArgumentParser(description="Capture personal one-time research requests")
    parser.add_argument("--db", default="data/focu.sqlite3")
    sub = parser.add_subparsers(dest="action", required=True)
    add = sub.add_parser("add", help="Capture a link or idea; no background work is implied")
    add.add_argument("question", nargs="?", default="")
    add.add_argument("--url")
    add.add_argument("--note", default="")
    add.add_argument("--force-new", action="store_true")
    add.add_argument("--podcast", action="store_true")
    sub.add_parser("list", help="List one-off research requests")
    exp = sub.add_parser("export", help="Export private Muse snapshot of queue states")
    exp.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.action == "add":
        result = capture_request(args.db, args.question, url=args.url, note=args.note,
                                 force_new=args.force_new, podcast=args.podcast)
    elif args.action == "list":
        result = list_requests(args.db)
    else:
        result = export_requests(args.db, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
