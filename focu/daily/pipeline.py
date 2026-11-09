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
from focu import tts as tts_adapter
from focu.media_integrity import inspect_mp3, MediaIntegrityError
from focu.briefing import read_style, render_script, validate_script, BriefingQCError
from focu.audience import load_profile, detect_domain, mismatch_report
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
            # The registered-source collector must not be spoofed into
            # importing user research. The independent daily editorial layer
            # may summarize completed on-demand articles by content ID.
            if item.get("origin") == "user_initiated" or item.get("podcast_mode") in ("single", "none"):
                raise FewError("User-initiated research cannot enter registered-source daily compilation",
                               "invalid_daily_origin", 4)
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


def digest(store, cfg, run, gate_priorities=None):
    store.select(run, cfg, gate_priorities=gate_priorities)
    grouped = {e["channel_id"]: store.units(e["episode_id"]) for e in store.episodes(run["run_id"])}
    path = store.data_dir / "digested" / f"{run['episode_date']}.json"
    write_json(path, grouped)
    return {"selected": sum(len(u) for u in grouped.values()), "artifact": str(path)}


def render_skeleton(channel, units):
    """Compatibility entry point: read the authoritative briefing style on use."""
    return render_script(units, read_style())


def compose(store, cfg, run, channel=None):
    channels = {c["id"]: c for c in cfg["channels"]}
    artifacts = []
    ep_dir = store.data_dir / "episodes" / run["episode_date"]
    try:
        style = read_style()
    except (BriefingQCError, OSError, ValueError) as exc:
        raise FewError("cannot load briefing style: " + str(exc), "invalid_briefing_style", 4) from exc
    for ep in store.episodes(run["run_id"]):
        if channel and channel != ep["channel_id"]:
            continue
        if ep["status"] == "finalized":
            continue
        units = store.units(ep["episode_id"])
        try:
            script = ep["script"]
            if not script:
                # Host-authored script convention: a script the host placed
                # at episodes/<date>/<channel>-script.txt before compose is
                # adopted as the episode script and held to exactly the same
                # coverage QC as a stored or rendered script. Compose itself
                # writes that path only after QC passes, so a file found here
                # on a later resume is either the frozen script or a host
                # replacement, and validation below decides which is usable.
                hosted = ep_dir / f"{ep['channel_id']}-script.txt"
                if hosted.is_file() and hosted.stat().st_size:
                    script = hosted.read_text(encoding="utf-8")
                else:
                    script = render_script(units, style)
            qc = validate_script(script, units, style)
        except (BriefingQCError, ValueError, KeyError) as exc:
            raise FewError("briefing composition failed: " + str(exc), "briefing_qc_failed", 4) from exc
        if not qc["passed"]:
            raise FewError("briefing script omitted source items or figures: " +
                           json.dumps(qc["issues"], ensure_ascii=False),
                           "briefing_qc_failed", 4)
        if not all(p.startswith(style["speaker_label"]) for p in script.strip().split("\n\n")):
            raise FewError("invalid single-speaker turn labels", "invalid_script", 4)
        # Diagnostic only: the owner's profile is independent of briefing
        # style, and can flag beginner exposition without weakening coverage QC.
        profile = load_profile()
        domain = detect_domain(" ".join(u.get("title", "") + " " + u.get("body", "")
                                        for u in units))
        audience_qc = mismatch_report(script, domain, profile)
        script_path = ep_dir / f"{ep['channel_id']}-script.txt"
        script_digest = hashlib.sha256(script.encode()).hexdigest()
        qc["script_sha256"] = script_digest
        atomic_write(script_path, script)
        write_json(ep_dir / f"{ep['channel_id']}-units.json", units)
        write_json(ep_dir / f"{ep['channel_id']}-briefing-qc.json", qc)
        write_json(ep_dir / f"{ep['channel_id']}-audience-qc.json", audience_qc)
        with store.db:
            store.db.execute("UPDATE episodes SET status='script_ready',script=?,script_hash=? WHERE episode_id=?",
                             (script, script_digest, ep["episode_id"]))
        artifacts.append(str(script_path))
    return {"artifacts": artifacts, "composer": "secretary_briefing_v1",
            "style_version": style["version"], "style_sha256": style["style_sha256"]}


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audio_probe(path):
    try:
        return inspect_mp3(path)["decoded_duration_seconds"]
    except MediaIntegrityError as exc:
        raise FewError("invalid TTS audio: " + str(exc), "invalid_audio", 4) from exc


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


def builtin_audio_attempt(ep, ep_dir, script_path, voice):
    """D1 script-first audio route (owner decision, 2026-11-08).

    Runs script fidelity QC -> focu tts synthesis -> post-audio audit for one
    compilation episode. Returns (record, audio_info); audio_info is None
    unless every stage passed. Audio-stage problems never raise: each is
    recorded with its stage name so the caller can still finalize the
    episode as text_only and the run can succeed. The explicit tts_argv
    route keeps its original fail-hard contract and does not come through
    here.
    """
    channel = ep["channel_id"]
    audio_path = ep_dir / f"{channel}.mp3"
    receipt_path = ep_dir / f".{channel}-audio-receipt.json"
    record = {"backend": "focu_tts", "status": "failed", "stage": "script_qc"}
    # 1. Script-stage fidelity QC on the actual script text. The briefing
    # style requires externally authored scripts to run the same validator
    # before audio synthesis; the frozen script hash was already verified by
    # the caller, so this verdict describes the exact text being voiced.
    try:
        style = read_style()
        units = json.loads((ep_dir / f"{channel}-units.json").read_text(encoding="utf-8"))
        script_text = script_path.read_text(encoding="utf-8")
        qc = validate_script(script_text, units, style)
    except (OSError, ValueError, BriefingQCError) as exc:
        record["reason"] = "script QC could not run: " + str(exc)[:200]
        return record, None
    record["script_qc"] = {"passed": qc["passed"], "item_count": qc["item_count"],
                           "covered_sections": qc["covered_sections"],
                           "issues": qc["issues"], "style_version": qc["style_version"],
                           "style_sha256": qc["style_sha256"]}
    if not qc["passed"]:
        record["reason"] = "script failed fidelity QC; no audio synthesized"
        return record, None
    # Receipt reuse mirrors the argv route: a crash between publishing audio
    # and committing coverage resumes without a second provider request.
    receipt = None
    if receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text())
        except (ValueError, OSError):
            receipt = None
    if (receipt and receipt.get("episode_id") == ep["episode_id"] and
            receipt.get("script_hash") == ep["script_hash"] and audio_path.exists() and
            receipt.get("audio_hash") == file_hash(audio_path)):
        record.update(status="generated", stage="complete", reused=True)
        return record, {"audio": str(audio_path), "audio_hash": receipt["audio_hash"],
                        "duration_seconds": receipt["duration_seconds"]}
    # 2. Unconfigured TTS is a recorded skip, never a failed run.
    record["stage"] = "tts_config"
    if not tts_adapter.status().get("configured"):
        record.update(status="skipped",
                      reason="focu tts is not configured on this host; episode stays text-only")
        return record, None
    # 3. Synthesis (long-form chunking lives in focu.tts), then 4. the
    # post-audio audit on decoded audio, shared with the argv route.
    fd, tmp = tempfile.mkstemp(dir=ep_dir, suffix=".mp3", prefix=".focu-tts-")
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        record["stage"] = "tts_synthesis"
        kwargs = {} if not voice or voice == "default" else {"voice": voice}
        result = tts_adapter.synthesize_long(script_path, tmp_path, **kwargs)
        record["stage"] = "audio_audit"
        duration = audio_probe(tmp_path)
    except (FewError, ValueError, RuntimeError, OSError,
            subprocess.SubprocessError) as exc:
        tmp_path.unlink(missing_ok=True)
        record["reason"] = str(exc)[:300]
        return record, None
    receipt = {"episode_id": ep["episode_id"], "script_hash": ep["script_hash"],
               "audio_hash": file_hash(tmp_path), "duration_seconds": duration,
               "backend": "focu_tts", "chunks": result.get("chunks")}
    write_json(receipt_path, receipt)
    os.replace(tmp_path, audio_path)
    record.update(status="generated", stage="complete")
    return record, {"audio": str(audio_path), "audio_hash": receipt["audio_hash"],
                    "duration_seconds": duration}


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
            qc_path = ep_dir / f"{ep['channel_id']}-briefing-qc.json"
            if not qc_path.is_file():
                raise FewError("missing briefing QC; re-run compose", "briefing_qc_missing", 4)
            qc = json.loads(qc_path.read_text(encoding="utf-8"))
            if not qc.get("passed") or qc.get("script_sha256") != ep["script_hash"]:
                raise FewError("briefing QC is stale or failed; re-run compose", "briefing_qc_failed", 4)
            manifest = {"schema_version": 1, "episode_id": ep["episode_id"], "mode": run["output_mode"],
                        "briefing_style_version": qc["style_version"],
                        "briefing_style_sha256": qc["style_sha256"],
                        "script": str(script_path), "script_hash": ep["script_hash"],
                        "units": str(ep_dir / f"{ep['channel_id']}-units.json"),
                        "composer": "secretary_briefing_v1", "completed_at": now_utc()}
            # The script-stage QC verdict travels with the episode, not only
            # in the sidecar files: coverage, figures, style identity, and
            # the audience calibration that was applied to this script.
            manifest["script_qc"] = {"passed": qc["passed"], "item_count": qc["item_count"],
                                     "covered_sections": qc["covered_sections"],
                                     "issues": qc["issues"],
                                     "style_version": qc["style_version"],
                                     "style_sha256": qc["style_sha256"],
                                     "script_sha256": qc.get("script_sha256") or ep["script_hash"]}
            audience_path = ep_dir / f"{ep['channel_id']}-audience-qc.json"
            if audience_path.is_file():
                try:
                    audience_qc = json.loads(audience_path.read_text(encoding="utf-8"))
                    manifest["audience_qc"] = {key: audience_qc.get(key) for key in
                                                ("domain", "level", "profile_version",
                                                 "profile_sha256", "blocking",
                                                 "requires_review", "matches")}
                except (ValueError, OSError):
                    pass
            # Backend resolution for audio mode: an explicitly configured
            # tts_argv command (including a host connector helper exposing
            # the same input->MP3 contract) keeps the original fail-hard
            # argv route. Without one, the built-in focu tts route is
            # fail-soft: a skip or failure is recorded and the episode
            # still finalizes as text_only.
            audio_backend = None
            if run["output_mode"] == "audio":
                try:
                    tts_argv(cfg)
                    audio_backend = "argv"
                except FewError as ex:
                    if ex.code != "missing_tts":
                        raise
                    audio_backend = "focu_tts"
            if run["output_mode"] == "audio" and audio_backend == "argv":
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
            elif run["output_mode"] == "audio":
                record, audio_info = builtin_audio_attempt(
                    ep, ep_dir, script_path, channels[ep["channel_id"]].get("voice"))
                manifest["audio_attempt"] = record
                if audio_info:
                    manifest.update(audio=audio_info["audio"],
                                    audio_hash=audio_info["audio_hash"],
                                    duration_seconds=audio_info["duration_seconds"],
                                    audio_backend="focu_tts")
                else:
                    manifest["mode"] = "text_only"
            write_json(ep_dir / f"{ep['channel_id']}-manifest.json", manifest)
            store.finalize(ep["episode_id"], manifest)
            outcomes.append({"episode_id": ep["episode_id"], "status": "finalized", "manifest": manifest})
        except (FewError, OSError, subprocess.SubprocessError) as ex:
            with store.db:
                store.db.execute("UPDATE episodes SET last_error=? WHERE episode_id=?", (str(ex), ep["episode_id"]))
            outcomes.append({"episode_id": ep["episode_id"], "status": "failed", "error": str(ex)})
    return outcomes


def run_pipeline(store, cfg, date, mode, input_units=None, gate_options=None):
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
    gate_report = None
    gate_priorities = None
    if not selected and gate_options and gate_options["mode"] != "off":
        from focu.decision_gate import evaluate_pending, gate_priorities as load_gate_priorities
        gate_report = evaluate_pending(store, date, **gate_options)
        store.stage(run["run_id"], "gate", "success", {
            "mode": gate_report["mode"], "provider": gate_report["provider"],
            "evaluated": gate_report["evaluated"], "errors": gate_report["errors"],
            "output": gate_report["output"],
        })
        if gate_options["mode"] == "active":
            gate_priorities = load_gate_priorities(store.data_dir, date)
    digest_report = digest(store, cfg, run, gate_priorities=gate_priorities)
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
            "run_id": run["run_id"], "fetch": fetch_report, "gate": gate_report,
            "selection": digest_report,
            "compose": compose_report, "episodes": outcomes,
            "warnings": ([] if outcomes else ["no eligible items fit this episode; check pending/enrichment counts with status"])}
