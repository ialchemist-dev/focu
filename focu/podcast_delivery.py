"""Idempotent completion-based delivery for Muse: report + archived transcript + audio."""
from __future__ import annotations
import json
import time
import urllib.parse
from pathlib import Path
from focu.delivery import DeliveryArchive
from focu.open_notebook import OpenNotebookClient

def deliver(evidence_id: str, episode_id: str, output_dir: str | Path, db_path: str | Path,
            client: OpenNotebookClient | None = None, *, download_audio: bool = True) -> dict:
    client = client or OpenNotebookClient()
    archive = DeliveryArchive(db_path)
    # Fail closed on unlinked evidence and unfinished episodes.
    report = archive.archive_report(evidence_id)
    episode = client.request("GET", "/api/podcasts/episodes/" + urllib.parse.quote(episode_id, safe=""))
    if not isinstance(episode, dict) or str(episode.get("id")) != episode_id:
        raise ValueError("Episode ID mismatch")
    if episode.get("job_status") != "completed":
        raise ValueError("Podcast not completed; delivery is not ready")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "research.md"
    report_path.write_text(archive.get(report["id"])["content"], encoding="utf-8")
    artifacts = archive.sync_podcast(evidence_id, episode)
    transcript_id = "podcast_transcript:" + episode_id
    transcript_path = None
    if any(a["id"] == transcript_id for a in artifacts):
        transcript_path = out / "transcript.json"
        transcript_path.write_text(archive.get(transcript_id)["content"], encoding="utf-8")
    audio_path = None
    if download_audio:
        if not episode.get("audio_url"):
            raise ValueError("Completed episode has no downloadable audio URL")
        audio_path = out / "podcast.mp3"
        client.download(episode_id, audio_path)
    return {"status": "delivered", "evidence_id": evidence_id, "episode_id": episode_id,
            "report": str(report_path), "transcript": str(transcript_path) if transcript_path else None,
            "audio": str(audio_path) if audio_path else None, "artifacts": [a["id"] for a in artifacts]}

def wait_and_deliver(evidence_id, job_id, output_dir, db_path, client=None, *,
                     interval=10, timeout=900):
    client = client or OpenNotebookClient()
    deadline = time.monotonic() + timeout
    while True:
        status = client.job(job_id)
        state = str(status.get("status", "")).lower()
        if state in ("failed", "error", "cancelled", "canceled"):
            raise RuntimeError("Open Notebook generation failed; inspect worker logs and job status")
        if state in ("completed", "success", "succeeded"):
            # Episode ID is not guaranteed in the job payload: match by command/job association
            result = status.get("result")
            candidates = []
            if isinstance(result, dict):
                candidates.extend([result.get("episode_id"), result.get("id")])
            candidates.append(status.get("episode_id"))
            for candidate in candidates:
                if candidate:
                    return deliver(evidence_id, str(candidate), output_dir, db_path, client)
            raise RuntimeError("Job completed but episode ID was not returned. Use 'focu deliver --episode-id' after listing episodes.")
        if time.monotonic() >= deadline:
            raise TimeoutError("Podcast job still running; use 'focu podcast job' and resume delivery later")
        time.sleep(interval)
