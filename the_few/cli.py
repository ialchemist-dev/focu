"""Stable, scriptable command-line entrypoint for external agents."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from the_few.evidence import EvidenceStore
from the_few.intents import IntentStore
from the_few.research import ingest_research
from the_few.web import fetch_page


def _json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="the-few", description="Agent-native research workflow")
    parser.add_argument("--db", default=os.getenv("THE_FEW_DB", "data/the-few.sqlite3"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Create local SQLite stores")
    sub.add_parser("doctor", help="Inspect local installation without external API calls")
    capture = sub.add_parser("capture", help="Capture a one-time research question")
    capture.add_argument("question")
    capture.add_argument("--id", dest="intent_id")
    listing = sub.add_parser("list", help="List research intents")
    listing.add_argument("--status", choices=["queued", "researching", "completed", "failed"])
    show = sub.add_parser("show", help="Show an intent")
    show.add_argument("intent_id")
    start = sub.add_parser("start", help="Claim a queued intent for research")
    start.add_argument("intent_id")
    fail = sub.add_parser("fail", help="Mark a researching intent failed")
    fail.add_argument("intent_id")
    fail.add_argument("--error", required=True)
    retry = sub.add_parser("retry", help="Return a failed intent to queue")
    retry.add_argument("intent_id")
    ingest = sub.add_parser("ingest-evidence", help="Validate agent research and write cited Markdown")
    ingest.add_argument("--evidence", required=True)
    ingest.add_argument("--output", required=True)
    evidence = sub.add_parser("show-evidence", help="Read saved evidence")
    evidence.add_argument("evidence_id")
    fetch = sub.add_parser("fetch", help="Retrieve public HTML/text for research")
    fetch.add_argument("url")
    fetch.add_argument("--timeout", type=float, default=12)
    fetch.add_argument("--max-bytes", type=int, default=2_000_000)

    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            path = Path(args.db)
            _json({"python": sys.version.split()[0], "db_path": str(path),
                   "db_exists": path.is_file(), "db_parent_writable": os.access(path.parent if path.parent.exists() else Path("."), os.W_OK),
                   "agent_handoff": True, "automatic_research": False,
                   "live_web_requires_network": True, "ready_for_init": True})
            return 0
        if args.command == "fetch":
            page = fetch_page(args.url, timeout=args.timeout, max_bytes=args.max_bytes)
            _json({"url": page.url, "title": page.title, "text": page.text,
                   "status": page.status, "content_type": page.content_type})
            return 0
        if args.command == "ingest-evidence":
            output = ingest_research(args.db, args.evidence, args.output)
            _json({"output": str(output), "status": "completed"})
            return 0
        if args.command == "show-evidence":
            result = EvidenceStore(args.db).get(args.evidence_id)
            if result is None:
                raise ValueError("Evidence pack not found")
            _json(result)
            return 0
        store = IntentStore(args.db)
        if args.command == "init":
            EvidenceStore(args.db)
            _json({"status": "initialized", "db_path": args.db})
        elif args.command == "capture":
            _json(store.capture(args.question, intent_id=args.intent_id))
        elif args.command == "list":
            _json(store.list(args.status))
        elif args.command == "show":
            result = store.get(args.intent_id)
            if result is None:
                raise ValueError("Intent not found")
            _json(result)
        elif args.command in {"start", "fail", "retry"}:
            expected, new = {"start": ("queued", "researching"),
                             "fail": ("researching", "failed"),
                             "retry": ("failed", "queued")}[args.command]
            _json(store.transition(args.intent_id, expected, new,
                                   error=args.error if args.command == "fail" else None))
        return 0
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
