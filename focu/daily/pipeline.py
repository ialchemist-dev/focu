"""Recoverable stages behind both the CLI and compatibility scripts."""
import contextlib
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from .collectors import FetchResult, collect
from .config import enabled_sources
from .errors import FewError
from .store import now_utc


@contextlib.contextmanager
def run_lock(data_dir):
    # Linux/macOS MVP. The lock is held by the kernel and released on crash;
    # no stale PID files, timeout-based stealing, or overlapping stage writers.
    try:
        import fcntl
    except ImportError as ex:
        raise FewError("M1 runtime supports Linux/macOS; Windows locking is not implemented") from ex
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    with (Path(data_dir) / "run.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as ex:
            raise FewError("another command is writing this data directory", "run_locked", 5) from ex
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".focu-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def ingest(store, cfg, date, input_units=None, collector=None):
    collector = collector or collect
    store.sync_sources(cfg)
    sources = enabled_sources(cfg)
    imported = None
    if input_units:
        try:
            imported = json.loads(Path(input_units).read_text(encoding="utf-8"))
        except (OSError, ValueError) as ex:
            raise FewError(f"cannot read units: {ex}") from ex
        if not isinstance(imported, list) or any(not isinstance(u, dict) for u in imported):
            raise FewError("input-units must be a JSON list of units")
        by_name = {s["name"]: s for s in sources}
        by_id = {s["source_id"]: s for s in sources}
        for item in imported:
            source = by_id.get(item.get("source_id")) or by_name.get(item.get("source"))
            if not source:
                raise FewError("unit source must match an enabled configured source")
            if item.get("source_id") and item["source_id"] != source["source_id"]:
                raise FewError("unit source_id disagrees with configured source")
            item["source_id"] = source["source_id"]
    report = {"sources": [], "inserted": 0, "discovered": 0}
    for source in sources:
        try:
            if imported is not None:
                result = FetchResult(items=[i for i in imported if i["source_id"] == source["source_id"]],
                                     completeness="external", status="success")
            else:
                result = collector(source, store.fetch_state(source["source_id"]))
        except Exception as ex:
            # Network/provider failures are isolated. Storage/configuration
            # errors below must propagate rather than advancing to selection.
            result = FetchResult(status="error", completeness="failed",
                                 error_code="fetch_failed", message=str(ex))
        inserted = store.persist_fetch(source, result)
        report["inserted"] += inserted
        report["discovered"] += len(result.items)
        report["sources"].append({"source_id": source["source_id"], "source": source["name"],
                                  "status": result.status, "completeness": result.completeness,
                                  "items": len(result.items), "error_code": result.error_code,
                                  "message": result.message})
    # A re-run cannot replace today's earlier export with an empty batch.
    rows = store.db.execute("""SELECT c.content_id,c.canonical_url AS url,r.*
        FROM contents c JOIN content_revisions r ON r.revision_id=c.latest_revision_id
        ORDER BY c.first_seen_at""")
    write_json(store.data_dir / "units" / f"{date}.json", [dict(r) for r in rows])
    return report


def digest(store, cfg, run):
    store.select(run, cfg)
    grouped = {e["channel_id"]: store.units(e["episode_id"]) for e in store.episodes(run["run_id"])}
    path = store.data_dir / "digested" / f"{run['episode_date']}.json"
    write_json(path, grouped)
    return {"selected": sum(len(u) for u in grouped.values()), "artifact": str(path)}


def render_skeleton(channel, units):
    # Explicitly retained M1 skeleton. LLM/prompt/feedback work is M3.
    zh = channel.get("language") == "zh"
    lines = ["Host: 今天的更新。" if zh else "Host: Today's updates."]
    for unit in units:
        prefix = f"Host: 来自{unit['source']}：" if zh else f"Host: From {unit['source']}: "
        lines.append(prefix + unit["title"] + ". " + unit["body"])
    lines.append("Host: 以上就是今天的内容。" if zh else "Host: That's everything for today.")
    return "\n\n".join(lines) + "\n"


def compose(store, cfg, run, channel=None):
    channels = {c["id"]: c for c in cfg["channels"]}
    artifacts = []
    ep_dir = store.data_dir / "episodes" / run["episode_date"]
    for ep in store.episodes(run["run_id"]):
        if channel and channel != ep["channel_id"]:
            continue
        if ep["status"] == "finalized":
            continue
        units = store.units(ep["episode_id"])
        script = ep["script"] or render_skeleton(channels[ep["channel_id"]], units)
        if not all(p.startswith("Host: ") for p in script.strip().split("\n\n")):
            raise FewError("invalid Host labels", "invalid_script", 4)
        script_path = ep_dir / f"{ep['channel_id']}-script.txt"
        atomic_write(script_path, script)
        write_json(ep_dir / f"{ep['channel_id']}-units.json", units)
        with store.db:
            store.db.execute("UPDATE episodes SET status='script_ready',script=?,script_hash=? WHERE episode_id=?",
                             (script, hashlib.sha256(script.encode()).hexdigest(), ep["episode_id"]))
        artifacts.append(str(script_path))
    return {"artifacts": artifacts, "composer": "deterministic_skeleton"}


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audio_probe(path):
    if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
        raise FewError("ffprobe and ffmpeg are required to validate audio", "missing_audio_tools", 4)
    if not Path(path).is_file() or Path(path).stat().st_size == 0:
        raise FewError("TTS did not produce a non-empty audio file", "empty_audio", 4)
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,format_name",
                                 "-of", "json", str(path)], capture_output=True, text=True, timeout=30, check=True)
        fmt = json.loads(result.stdout)["format"]
        duration = float(fmt["duration"])
        if "mp3" not in fmt["format_name"].split(",") or duration <= 0:
            raise ValueError("output must be a non-empty MP3")
        subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
                       capture_output=True, timeout=60, check=True)
        return duration
    except (subprocess.SubprocessError, ValueError, KeyError) as ex:
        raise FewError(f"invalid TTS audio: {ex}", "invalid_audio", 4) from ex


def tts_argv(cfg):
    value = cfg.get("tts_argv")
    if value is None:
        # Compatibility only; parsing into argv, NEVER eval or shell=True.
        value = os.environ.get("FOCU_TTS_CMD") or os.environ.get("THEFEW_TTS_CMD") or os.environ.get("THEVIEW_TTS_CMD")
        if value:
            value = shlex.split(value)
    if not isinstance(value, list) or not value or not all(isinstance(a, str) for a in value):
        raise FewError("audio mode requires tts_argv (or FOCU_TTS_CMD); choose explicit text_only for text output",
                       "missing_tts", 4)
    template = " ".join(value)
    if not ("{input}" in template or "$IN" in template) or not ("{output}" in template or "$OUT" in template):
        raise FewError("TTS argv must contain {input} and {output} placeholders", "invalid_tts", 2)
    return value


def finalize_episodes(store, cfg, run, channel=None):
    ep_dir = store.data_dir / "episodes" / run["episode_date"]
    outcomes = []
    channels = {c["id"]: c for c in cfg["channels"]}
    for ep in store.episodes(run["run_id"]):
        if channel and channel != ep["channel_id"]:
            continue
        if ep["status"] == "finalized":
            outcomes.append({"episode_id": ep["episode_id"], "status": "reused", "manifest": json.loads(ep["artifact_manifest"])})
            continue
        try:
            if ep["status"] != "script_ready":
                raise FewError("compose must succeed before synthesis", "missing_script", 4)
            script_path = ep_dir / f"{ep['channel_id']}-script.txt"
            if not script_path.exists() or file_hash(script_path) != ep["script_hash"]:
                raise FewError("script changed since compose; re-run compose to restore the frozen script", "script_changed", 4)
            manifest = {"schema_version": 1, "episode_id": ep["episode_id"], "mode": run["output_mode"],
                        "script": str(script_path), "script_hash": ep["script_hash"],
                        "units": str(ep_dir / f"{ep['channel_id']}-units.json"),
                        "composer": "deterministic_skeleton", "completed_at": now_utc()}
            if run["output_mode"] == "audio":
                argv = tts_argv(cfg)
                if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
                    raise FewError("ffmpeg and ffprobe are required in audio mode", "missing_audio_tools", 4)
                audio_path = ep_dir / f"{ep['channel_id']}.mp3"
                # Receipt allows a crash between publishing audio and committing
                # coverage to resume without a second TTS request.
                receipt_path = ep_dir / f".{ep['channel_id']}-audio-receipt.json"
                receipt = None
                if receipt_path.exists():
                    try:
                        receipt = json.loads(receipt_path.read_text())
                    except (ValueError, OSError):
                        pass
                if not (receipt and receipt.get("episode_id") == ep["episode_id"] and
                        receipt.get("script_hash") == ep["script_hash"] and audio_path.exists() and
                        receipt.get("audio_hash") == file_hash(audio_path)):
                    fd, tmp = tempfile.mkstemp(dir=ep_dir, suffix=".mp3", prefix=".focu-audio-")
                    os.close(fd)
                    tmp_path = Path(tmp)
                    try:
                        replacements = {"{input}": str(script_path), "{output}": str(tmp_path),
                                        "$IN": str(script_path), "$OUT": str(tmp_path),
                                        "{voice}": str(channels[ep["channel_id"]].get("voice", "default"))}
                        command = []
                        for arg in argv:
                            for key, value in replacements.items():
                                arg = arg.replace(key, value)
                            command.append(arg)
                        subprocess.run(command, check=True, timeout=300, capture_output=True)
                        duration = audio_probe(tmp_path)
                        receipt = {"episode_id": ep["episode_id"], "script_hash": ep["script_hash"],
                                   "audio_hash": file_hash(tmp_path), "duration_seconds": duration}
                        # Write receipt first. A crash before rename invalidates
                        # it against the old/missing MP3; afterwards it is reusable.
                        write_json(receipt_path, receipt)
                        os.replace(tmp_path, audio_path)
                    finally:
                        tmp_path.unlink(missing_ok=True)
                manifest.update(audio=str(audio_path), audio_hash=receipt["audio_hash"],
                                duration_seconds=receipt["duration_seconds"])
            write_json(ep_dir / f"{ep['channel_id']}-manifest.json", manifest)
            store.finalize(ep["episode_id"], manifest)
            outcomes.append({"episode_id": ep["episode_id"], "status": "finalized", "manifest": manifest})
        except (FewError, OSError, subprocess.SubprocessError) as ex:
            with store.db:
                store.db.execute("UPDATE episodes SET last_error=? WHERE episode_id=?", (str(ex), ep["episode_id"]))
            outcomes.append({"episode_id": ep["episode_id"], "status": "failed", "error": str(ex)})
    return outcomes


def run_pipeline(store, cfg, date, mode, input_units=None):
    run = store.ensure_run(date, cfg, mode)
    if run["status"] == "completed":
        return {"status": "reused", "run_id": run["run_id"], "episodes": store.episodes(run["run_id"])}
    selected = store.db.execute("SELECT 1 FROM stage_runs WHERE run_id=? AND stage='select' AND status='success'",
                                (run["run_id"],)).fetchone()
    fetch_report = None
    if not selected:
        fetch_report = ingest(store, cfg, date, input_units)
        store.stage(run["run_id"], "ingest", "success", fetch_report)
        healthy = [s for s in fetch_report["sources"] if s["status"] in {"success", "empty", "partial"}]
        if not healthy:
            ready_backlog = store.db.execute("""SELECT count(DISTINCT c.content_id)
                FROM candidates k JOIN contents c USING(content_id)
                JOIN content_revisions r ON r.revision_id=c.latest_revision_id
                JOIN observations o ON o.content_id=c.content_id
                JOIN subscriptions s USING(source_id)
                WHERE k.state='pending' AND k.expires_at>=? AND s.enabled=1
                AND c.provisional=0 AND length(trim(r.body))>0
                AND NOT EXISTS (SELECT 1 FROM coverage cv WHERE cv.content_id=c.content_id)
                AND NOT EXISTS (SELECT 1 FROM episode_items ei JOIN episodes ep USING(episode_id)
                    WHERE ei.content_id=c.content_id AND ep.status!='finalized')""", (now_utc(),)).fetchone()[0]
            if not ready_backlog:
                raise FewError("all configured sources are unavailable and no ready backlog is available",
                               "sources_unavailable", 3)
    digest_report = digest(store, cfg, run)
    compose_report = compose(store, cfg, run)
    store.stage(run["run_id"], "compose", "success", compose_report)
    outcomes = finalize_episodes(store, cfg, run)
    failed = any(o["status"] == "failed" for o in outcomes)
    store.stage(run["run_id"], "finalize", "failed" if failed else "success", outcomes)
    with store.db:
        store.db.execute("UPDATE runs SET status=?,updated_at=? WHERE run_id=?",
                         ("failed" if failed else "completed", now_utc(), run["run_id"]))
    degraded = fetch_report and any(s["status"] not in {"success", "empty"} for s in fetch_report["sources"])
    return {"status": "failed" if failed else "degraded" if degraded else "completed",
            "run_id": run["run_id"], "fetch": fetch_report, "selection": digest_report,
            "compose": compose_report, "episodes": outcomes,
            "warnings": ([] if outcomes else ["no eligible items fit this episode; check pending/enrichment counts with status"])}
