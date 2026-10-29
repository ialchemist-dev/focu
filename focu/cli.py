"""Stable, scriptable command-line entrypoint for external agents."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from focu import __version__
from focu.evidence import EvidenceStore
from focu.intents import IntentStore
from focu.research import ingest_research
from focu.web import fetch_page, FetchError
from focu.snapshots import save_snapshot, verify_snapshot
from focu import tts
from focu import open_notebook
from focu.delivery import DeliveryArchive
from focu.collectors import collect_export, collect_youtube
from focu.podcast_delivery import deliver, wait_and_deliver


def _json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="focu", description="Agent-native research workflow")
    parser.add_argument("--db", default=(os.getenv("FOCU_DB") or os.getenv("THE_FEW_DB") or ("data/the-few.sqlite3" if Path("data/the-few.sqlite3").exists() else "data/focu.sqlite3")))
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
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
    fetch.add_argument("--retries", type=int, default=2)
    fetch.add_argument("--snapshot-dir", help="Save a content-addressed local snapshot")
    verify = sub.add_parser("verify-snapshot", help="Check text against SHA256")
    verify.add_argument("path")
    verify.add_argument("sha256")
    fetch.add_argument("--max-bytes", type=int, default=2_000_000)

    tts_cmd = sub.add_parser("tts", help="Configure and run opt-in TTS")
    tts_cmd.add_argument("tts_args", nargs=argparse.REMAINDER)

    podcast_cmd = sub.add_parser("podcast", help="Open Notebook podcast handoff")
    podcast_cmd.add_argument("podcast_args", nargs=argparse.REMAINDER)

    report = sub.add_parser("report", help="Archive/export a canonical cited Markdown research report")
    report.add_argument("evidence_id")
    report.add_argument("--output", required=True)
    artifacts = sub.add_parser("artifacts", help="List stored delivery formats for an Evidence Pack")
    artifacts.add_argument("evidence_id")
    artifact = sub.add_parser("artifact", help="Export an archived artifact")
    artifact.add_argument("artifact_id")
    artifact.add_argument("--output", required=True)
    sync = sub.add_parser("sync-podcast", help="Archive a completed Open Notebook episode's transcript and outline")
    sync.add_argument("--evidence-id", required=True)
    sync.add_argument("--episode-id", required=True)
    delivery = sub.add_parser("deliver", help="Deliver report, podcast and transcript from a completed episode")
    delivery.add_argument("--evidence-id", required=True)
    choice = delivery.add_mutually_exclusive_group(required=True)
    choice.add_argument("--episode-id")
    choice.add_argument("--job-id")
    delivery.add_argument("--output-dir", required=True)
    delivery.add_argument("--timeout", type=int, default=900)
    collect = sub.add_parser("collect", help="Opt-in source collector PoC")
    collect_sub = collect.add_subparsers(dest="platform", required=True)
    yt = collect_sub.add_parser("youtube", help="Fetch a single video transcript")
    yt.add_argument("url")
    yt.add_argument("--scope", required=True)
    yt.add_argument("--output", required=True)
    yt.add_argument("--language", action="append", default=[])
    li = collect_sub.add_parser("linkedin-export", help="Import an authorized MCP feed JSON export")
    li.add_argument("--input", required=True)
    li.add_argument("--scope", required=True)
    li.add_argument("--output", required=True)
    reader_cmd = sub.add_parser("reader", help="Finite mobile reader and source marketplace")
    reader_cmd.add_argument("reader_args", nargs=argparse.REMAINDER)
    daily_cmd = sub.add_parser("daily", help="Persistent feed-to-podcast stages")
    daily_cmd.add_argument("daily_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.command == "daily":
            from focu.daily.cli import main as daily_main
            return daily_main(args.daily_args)
        if args.command == "reader":
            from focu.reader import main as reader_main
            return reader_main(args.reader_args, db_path=args.db)
        if args.command == "collect":
            if args.platform == "youtube":
                _json(collect_youtube(args.url, args.db, args.scope, args.output,
                                      tuple(args.language or ["en"])))
            else:
                _json(collect_export(args.input, "linkedin", args.db, args.scope, args.output))
            return 0
        if args.command == "deliver":
            if args.episode_id:
                result = deliver(args.evidence_id, args.episode_id, args.output_dir, args.db)
            else:
                result = wait_and_deliver(args.evidence_id, args.job_id, args.output_dir, args.db, timeout=args.timeout)
            _json(result)
            return 0
        if args.command == "podcast":
            return open_notebook.main(args.podcast_args)
        if args.command == "tts":
            return tts.main(args.tts_args)
        if args.command == "report":
            archive = DeliveryArchive(args.db)
            saved = archive.archive_report(args.evidence_id)
            content = archive.get(saved["id"])["content"]
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(content, encoding="utf-8")
            _json({"artifact": saved, "output": str(output)})
            return 0
        if args.command == "artifacts":
            _json(DeliveryArchive(args.db).list(args.evidence_id))
            return 0
        if args.command == "artifact":
            content = DeliveryArchive(args.db).get(args.artifact_id)
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(content["content"], encoding="utf-8")
            _json({"artifact_id": args.artifact_id, "kind": content["kind"], "output": str(output)})
            return 0
        if args.command == "sync-podcast":
            client = open_notebook.OpenNotebookClient()
            episode = client.request("GET", "/api/podcasts/episodes/" +
                open_notebook.urllib.parse.quote(args.episode_id, safe=""))
            if not isinstance(episode, dict) or str(episode.get("id")) != args.episode_id:
                raise ValueError("Episode ID mismatch")
            _json(DeliveryArchive(args.db).sync_podcast(args.evidence_id, episode))
            return 0
        if args.command == "doctor":
            path = Path(args.db)
            _json({"python": sys.version.split()[0], "db_path": str(path),
                   "db_exists": path.is_file(), "db_parent_writable": os.access(path.parent if path.parent.exists() else Path("."), os.W_OK),
                   "agent_handoff": True, "automatic_research": False,
                   "live_web_requires_network": True, "ready_for_init": True})
            return 0
        if args.command == "verify-snapshot":
            valid = verify_snapshot(args.path, args.sha256)
            _json({"valid": valid})
            return 0 if valid else 1
        if args.command == "fetch":
            page = fetch_page(args.url, timeout=args.timeout, max_bytes=args.max_bytes, retries=args.retries)
            snapshot = save_snapshot(args.snapshot_dir, url=page.url, title=page.title, text=page.text) if args.snapshot_dir else None
            _json({"url": page.url, "title": page.title, "text": page.text,
                   "status": page.status, "content_type": page.content_type, "image_url": page.image_url, "snapshot": snapshot})
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
        payload = {"error": str(exc)}
        if isinstance(exc, FetchError):
            payload.update({"category": exc.category, "http_status": exc.status})
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
