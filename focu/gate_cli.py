"""Entry point for opt-in Information Gate trials and reproducible comparisons."""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from focu.decision_gate import (
    GateError, GateLedger, PROVIDERS, comparison_report, evaluate_pending,
)
from focu.daily.store import Store


def parser():
    p = argparse.ArgumentParser(prog="focu-gate",
                                description="Opt-in shadow/active information triage and A/B records")
    subs = p.add_subparsers(dest="command", required=True)
    evaluate = subs.add_parser("evaluate", help="evaluate pending daily candidates, no collection")
    evaluate.add_argument("--data-dir", required=True)
    evaluate.add_argument("--date", required=True, help="YYYY-MM-DD")
    evaluate.add_argument("--mode", choices=("off", "shadow", "active"), default="shadow")
    evaluate.add_argument("--provider", choices=PROVIDERS, default="off")
    evaluate.add_argument("--compare", default="", help="comma-separated other providers")
    evaluate.add_argument("--wiki-dir", help="checkout of llm-wiki, optional")
    evaluate.add_argument("--goals-file", help="explicit editable interests and open questions")
    evaluate.add_argument("--limit", type=int, default=20,
                          help="MAX pending candidates to evaluate (not a token budget)")
    evaluate.add_argument("--refresh", action="store_true", help="bypass cached API judgments")
    report = subs.add_parser("report")
    report.add_argument("--data-dir", required=True)
    report.add_argument("--date", required=True)
    feedback = subs.add_parser("feedback", help="store explicit evaluation correction")
    feedback.add_argument("--data-dir", required=True)
    feedback.add_argument("--date", required=True)
    feedback.add_argument("--content-id", required=True)
    feedback.add_argument("--verdict", required=True, choices=(
        "useful", "not_useful", "missed", "incorrect", "too_basic", "other"))
    feedback.add_argument("--note", default="")
    return p


def execute(args):
    date.fromisoformat(args.date)
    base = Path(args.data_dir)
    if args.command == "evaluate":
        if not (base / "few.sqlite3").is_file():
            raise GateError("ingest daily candidates first; missing few.sqlite3")
        compare = tuple(p.strip() for p in args.compare.split(",") if p.strip())
        store = Store(base)
        try:
            return evaluate_pending(store, args.date, mode=args.mode,
                                    provider=args.provider, compare=compare,
                                    wiki_dir=args.wiki_dir, goals_file=args.goals_file,
                                    limit=args.limit, refresh=args.refresh)
        finally:
            store.close()
    if args.command == "report":
        return comparison_report(base, args.date)
    ledger = GateLedger(base)
    try:
        ledger.feedback(args.date, args.content_id, args.verdict, args.note)
        return {"status": "recorded", "date": args.date, "content_id": args.content_id,
                "verdict": args.verdict}
    finally:
        ledger.close()


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (GateError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
