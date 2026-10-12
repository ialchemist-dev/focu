import argparse
import json
import sys
from datetime import date as Date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import load_config
from .errors import FewError
from .pipeline import compose, digest, finalize_episodes, ingest, run_lock, run_pipeline, tts_argv
from .store import Store


def parser():
    ap = argparse.ArgumentParser(description="The Few persistent pipeline (M1)")
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("run", "ingest", "digest", "compose", "synthesize", "status", "export-state"):
        p = sub.add_parser(name)
        p.add_argument("--config", default="sources.yaml")
        p.add_argument("--data-dir", default="data")
        p.add_argument("--json", action="store_true", help="stable JSON stdout; logs go to stderr")
        if name in {"run", "ingest", "digest", "compose", "synthesize"}:
            p.add_argument("--date", help="YYYY-MM-DD, default today in config timezone")
            p.add_argument("--text-only", action="store_true", help="explicitly finalize text instead of audio")
        if name in {"run", "ingest"}:
            p.add_argument("--input-units", help="JSON units from configured sources; bypasses network fetch")
        if name == "run":
            p.add_argument("--dry-run", action="store_true", help="validate configuration without creating state")
        if name in {"compose", "synthesize"}:
            p.add_argument("--channel")
    legacy = sub.add_parser("import-legacy", help="copy and import v0.1 snapshots into a separate data directory")
    legacy.add_argument("--config", default="sources.yaml")
    legacy.add_argument("--data-dir", required=True)
    legacy.add_argument("--from-dir", required=True)
    legacy.add_argument("--register-coverage", action="store_true",
                        help="explicitly attest existing episode snapshots as covered (does not imply listening)")
    legacy.add_argument("--json", action="store_true")
    return ap


def execute(args):
    path = Path(args.data_dir).resolve()
    if args.command in {"status", "export-state"}:
        if not (path / "few.sqlite3").exists():
            return {"schema_version": 1, "status": "not_initialized", "counts": {}}
        with run_lock(path):
            store = Store(path)
            try:
                report = store.status() if args.command == "status" else store.export()
                # Run configs may contain private notes; status needs only the
                # hashes/status, while export-state is intentionally complete.
                if args.command == "status":
                    for run in report["runs"]:
                        run.pop("config_json", None)
                return {"schema_version": 1, "status": "ok", **report}
            finally:
                store.close()
    cfg = load_config(args.config)
    if args.command == "import-legacy":
        from .legacy import import_legacy
        source = Path(args.from_dir).resolve()
        if source == path or source in path.parents or path in source.parents:
            raise FewError("legacy source and destination must be separate, non-nested directories")
        with run_lock(path):
            store = Store(path)
            try:
                return {"schema_version": 1, **import_legacy(store, cfg, source, args.register_coverage)}
            finally:
                store.close()
    mode = "text_only" if args.text_only else cfg["output_mode"]
    try:
        date = args.date or datetime.now(ZoneInfo(cfg["timezone"])).date().isoformat()
        if Date.fromisoformat(date).isoformat() != date:
            raise ValueError("date must be YYYY-MM-DD")
    except ValueError as ex:
        raise FewError("date must be YYYY-MM-DD") from ex
    if getattr(args, "channel", None) and args.channel not in {ch["id"] for ch in cfg["channels"]}:
        raise FewError("unknown channel")
    if args.command == "run" and args.dry_run:
        if mode == "audio":
            tts_argv(cfg)
        return {"schema_version": 1, "status": "validated", "date": date, "mode": mode,
                "config_hash": cfg["config_hash"], "composer": "deterministic_skeleton"}
    if not (path / "few.sqlite3").exists() and ((path / "state.json").exists() or
                                               (path / "episodes").exists() or (path / "units").exists()):
        raise FewError("legacy v0.1 data detected; use import-legacy into a separate --data-dir first. "
                       "Old files are never overwritten.", "legacy_data")
    with run_lock(path):
        store = Store(path)
        try:
            if args.command == "ingest":
                report = {"status": "collected", "fetch": ingest(store, cfg, date, args.input_units)}
            elif args.command == "run":
                report = run_pipeline(store, cfg, date, mode, args.input_units)
            else:
                run = store.ensure_run(date, cfg, mode)
                if args.command == "digest":
                    store.sync_sources(cfg)
                    report = {"status": "selected", "run_id": run["run_id"], **digest(store, cfg, run)}
                elif args.command == "compose":
                    if not store.db.execute("SELECT 1 FROM stage_runs WHERE run_id=? AND stage='select' AND status='success'",
                                            (run["run_id"],)).fetchone():
                        raise FewError("run digest first")
                    report = {"status": "composed", "run_id": run["run_id"], **compose(store, cfg, run, args.channel)}
                else:
                    if not store.episodes(run["run_id"]):
                        raise FewError("no selected episodes; run digest and compose first")
                    outcomes = finalize_episodes(store, cfg, run, args.channel)
                    report = {"status": "failed" if any(o["status"] == "failed" for o in outcomes) else "finalized",
                              "run_id": run["run_id"], "episodes": outcomes}
            return {"schema_version": 1, **report}
        finally:
            store.close()


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        report = execute(args)
        exit_code = 4 if report["status"] == "failed" else 0
    except FewError as ex:
        report = {"schema_version": 1, "status": "error", "errors": [{"code": ex.code, "message": str(ex),
                   "retryable": ex.exit_code in {3, 4, 5}}]}
        exit_code = ex.exit_code
    except Exception as ex:
        report = {"schema_version": 1, "status": "error", "errors": [{"code": "runtime_error", "message": str(ex), "retryable": True}]}
        exit_code = 3
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
