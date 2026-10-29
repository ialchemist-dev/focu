"""Research-first delivery archive: canonical evidence, readable report, optional audio transcript."""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from focu.evidence import EvidenceStore
from focu.intents import IntentStore
from focu.research import render_markdown

class DeliveryArchive:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS delivery_artifacts (
                id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL,
                kind TEXT NOT NULL, content TEXT NOT NULL,
                metadata TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(evidence_id, kind, id)
            )""")
    def _db(self):
        return sqlite3.connect(self.db_path, timeout=30)

    def save(self, artifact_id, evidence_id, kind, content, metadata=None):
        if kind not in ("research_markdown", "podcast_transcript", "podcast_outline", "podcast_metadata"):
            raise ValueError("Unsupported delivery artifact kind")
        if not artifact_id or not evidence_id or not isinstance(content, str) or not content.strip():
            raise ValueError("Artifact ID, evidence ID and nonempty content required")
        if EvidenceStore(self.db_path).get(evidence_id) is None:
            raise ValueError("Unknown evidence pack; cannot archive unlinked delivery")
        metadata = metadata or {}
        serialized = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        now = datetime.now(timezone.utc).isoformat()
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO delivery_artifacts VALUES (?, ?, ?, ?, ?, ?)",
                       (artifact_id, evidence_id, kind, content, serialized, now))
            row = db.execute("SELECT evidence_id, kind, content, metadata FROM delivery_artifacts WHERE id=?",
                             (artifact_id,)).fetchone()
            if row != (evidence_id, kind, content, serialized):
                raise ValueError("Artifact ID exists with different content")
        return {"id": artifact_id, "evidence_id": evidence_id, "kind": kind}

    def list(self, evidence_id):
        with self._db() as db:
            rows = db.execute("SELECT id, evidence_id, kind, metadata, created_at FROM delivery_artifacts WHERE evidence_id=? ORDER BY created_at, id",
                              (evidence_id,)).fetchall()
        return [{"id": r[0], "evidence_id": r[1], "kind": r[2],
                 "metadata": json.loads(r[3]), "created_at": r[4]} for r in rows]

    def get(self, artifact_id):
        with self._db() as db:
            row = db.execute("SELECT id, evidence_id, kind, content, metadata, created_at FROM delivery_artifacts WHERE id=?",
                             (artifact_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown artifact ID")
        return {"id": row[0], "evidence_id": row[1], "kind": row[2],
                "content": row[3], "metadata": json.loads(row[4]), "created_at": row[5]}

    def archive_report(self, evidence_id):
        pack = EvidenceStore(self.db_path).get(evidence_id)
        if pack is None:
            raise ValueError("Unknown evidence pack")
        intent = IntentStore(self.db_path).get(pack["intent_id"])
        if not intent:
            raise ValueError("Evidence pack has no linked research intent")
        markdown = render_markdown(pack, intent["question"])
        return self.save("research:" + evidence_id, evidence_id, "research_markdown", markdown,
                         {"format": "markdown", "source": "evidence_pack"})

    def sync_podcast(self, evidence_id, episode):
        """Persist Open Notebook's actual script, outline and metadata; never call them the research report."""
        if not isinstance(episode, dict) or not episode.get("id"):
            raise ValueError("Expected Open Notebook episode with ID")
        if episode.get("job_status") != "completed":
            raise ValueError("Only completed podcast episodes may be archived")
        episode_id = str(episode["id"])
        result = []
        for kind, field in (("podcast_transcript", "transcript"), ("podcast_outline", "outline")):
            value = episode.get(field)
            if value:
                content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) if not isinstance(value, str) else value
                result.append(self.save(kind + ":" + episode_id, evidence_id, kind, content,
                                        {"open_notebook_episode_id": episode_id, "format": "json" if not isinstance(value, str) else "text"}))
        metadata = {key: episode.get(key) for key in ("id", "name", "created", "audio_url", "job_status", "episode_profile", "speaker_profile")}
        result.append(self.save("podcast_metadata:" + episode_id, evidence_id, "podcast_metadata",
                                json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
                                {"open_notebook_episode_id": episode_id}))
        return result
