"""Explicit, additive v0.1 import; old files are never rewritten."""
import json
import shutil
import uuid
from pathlib import Path

from .collectors import FetchResult
from .config import enabled_sources
from .errors import FewError
from .identity import content_identity, stable_id
from .pipeline import file_hash
from .store import now_utc, revision_fields


def import_legacy(store, cfg, source_dir, register_coverage=False):
    source_dir = Path(source_dir).resolve()
    dest = store.data_dir.resolve()
    if source_dir == dest or source_dir in dest.parents or dest in source_dir.parents:
        raise FewError("legacy source and new data directory must be separate, non-nested directories")
    if not source_dir.is_dir():
        raise FewError("legacy source directory does not exist")
    by_name = {s["name"]: s for s in enabled_sources(cfg)}
    batches = []
    audits = []
    paths = sorted((source_dir / "units").glob("*.json")) + sorted((source_dir / "episodes").glob("*/*-units.json"))
    if not paths:
        raise FewError("no legacy units or episode audit snapshots; state.json alone cannot recover content")
    for path in paths:
        try:
            units = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as ex:
            raise FewError(f"invalid legacy snapshot {path}: {ex}") from ex
        if not isinstance(units, list):
            raise FewError(f"legacy snapshot must be a list: {path}")
        for unit in units:
            if not isinstance(unit, dict) or unit.get("source") not in by_name:
                raise FewError(f"legacy source in {path} does not match an enabled configured source; "
                               "restore its original source name in config before importing")
            content_identity(unit, by_name[unit["source"]]["source_id"])
        batches.extend(units)
        if path.name.endswith("-units.json"):
            channel = path.name.removesuffix("-units.json")
            script = path.with_name(channel + "-script.txt")
            audio = path.with_name(channel + ".mp3")
            if register_coverage:
                if not script.is_file() or not script.stat().st_size:
                    raise FewError(f"cannot trust coverage without a non-empty script: {script}")
                if cfg["output_mode"] == "audio" and (not audio.is_file() or not audio.stat().st_size):
                    raise FewError(f"audio mode requires a non-empty historical MP3: {audio}")
                audits.append((path, units, script, audio))
    # Freeze the input before mutation. Watermarks are backed up, never trusted
    # as evidence that content was persisted or delivered.
    backup = dest / "legacy-backups" / uuid.uuid4().hex
    backup.mkdir(parents=True)
    for name in ("state.json", "units", "digested", "episodes"):
        original = source_dir / name
        if original.is_dir():
            shutil.copytree(original, backup / name)
        elif original.is_file():
            shutil.copy2(original, backup / name)
    store.sync_sources(cfg)
    inserted = 0
    for name, source in by_name.items():
        inserted += store.persist_fetch(source, FetchResult(items=[u for u in batches if u["source"] == name],
                                                           completeness="legacy", status="success"))
    covered = 0
    if register_coverage:
        # These entries are operator-attested, not automatically validated
        # listening history. Keep them outside new daily-run date slots.
        with store.db:
            for path, units, script, audio in audits:
                run_id = stable_id("legacy", f"{path.relative_to(source_dir)}:{file_hash(path)}:{file_hash(script)}:{cfg['output_mode']}")
                episode_id = stable_id("legacy_ep", run_id)
                manifest = {"mode": cfg["output_mode"], "legacy_operator_attested": True,
                            "script": str(backup / script.relative_to(source_dir)),
                            "units": str(backup / path.relative_to(source_dir))}
                if audio.exists():
                    manifest["audio"] = str(backup / audio.relative_to(source_dir))
                store.db.execute("INSERT OR IGNORE INTO runs VALUES (?,?,?,?,?,'completed',?)",
                                 (run_id, run_id, cfg["config_hash"], json.dumps(cfg), cfg["output_mode"], now_utc()))
                store.db.execute("""INSERT OR IGNORE INTO episodes
                    (episode_id,run_id,channel_id,status,script,script_hash,artifact_manifest)
                    VALUES (?,?,?,'finalized',?,?,?)""",
                    (episode_id, run_id, path.name.removesuffix("-units.json"), script.read_text(encoding="utf-8"),
                     file_hash(script), json.dumps(manifest)))
                for pos, unit in enumerate(units):
                    source = by_name[unit["source"]]
                    cid, _, provisional = content_identity(unit, source["source_id"])
                    if provisional:
                        continue
                    revision_id = revision_fields(cid, unit)[0]
                    store.db.execute("INSERT OR IGNORE INTO episode_items VALUES (?,?,?,?,?)",
                                     (episode_id, cid, revision_id, pos, json.dumps(unit)))
                    covered += store.db.execute("INSERT OR IGNORE INTO coverage VALUES (?,?,?)",
                                                (cid, episode_id, now_utc())).rowcount
    return {"status": "imported", "inserted": inserted, "covered": covered, "backup": str(backup),
            "warnings": ["legacy cursors were not restored; use overlap collection with persistent dedup",
                         "coverage is operator-attested; no delivered/played status is inferred"]}
