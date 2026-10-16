"""Local, content-addressed text snapshots. Hashes prove integrity, not truth."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def save_snapshot(directory: str | Path, *, url: str, text: str, title: str = "") -> dict:
    if not url.startswith(("http://", "https://")) or not text.strip():
        raise ValueError("Snapshot requires an HTTP(S) URL and nonempty text")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    path = root / (digest + ".txt")
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("Existing snapshot is corrupted")
    if not path.exists():
        path.write_text(text, encoding="utf-8")
    metadata = {"url": url, "title": title, "sha256": digest,
                "captured_at": datetime.now(timezone.utc).isoformat(), "path": str(path)}
    (root / (digest + ".json")).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def verify_snapshot(path: str | Path, sha256: str) -> bool:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha256
