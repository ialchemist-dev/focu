"""SQLite is the source of truth; JSON files are inspectable exports."""
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from .config import enabled_sources
from .errors import FewError
from .identity import IDENTITY_VERSION, content_identity


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def published_time(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            result = parsedate_to_datetime(str(value))
        except (ValueError, TypeError, OverflowError):
            return None
    # An unspecified zone is not a reliable publication time.
    if result.tzinfo is None:
        return None
    return result.astimezone(timezone.utc).isoformat()


def revision_fields(content_id, item):
    title, body = str(item.get("title") or ""), str(item.get("body") or "")
    published_at = published_time(item.get("published_at"))
    kind = str(item.get("kind") or "article")
    fingerprint = json.dumps([title, body, kind, published_at], ensure_ascii=False)
    body_hash = hashlib.sha256(fingerprint.encode()).hexdigest()
    revision_id = "rev_" + hashlib.sha256((content_id + body_hash).encode()).hexdigest()
    return revision_id, body_hash, title, body, kind, published_at


class Store:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "few.sqlite3"
        self.db = sqlite3.connect(self.db_path, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.execute("PRAGMA synchronous = FULL")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            sql = (Path(__file__).parent / "migrations/001_initial.sql").read_text()
            self.db.executescript("BEGIN IMMEDIATE;\n" + sql + "\nCOMMIT;")
        elif version != 1:
            raise FewError(f"unsupported database schema {version}")

    def close(self):
        self.db.close()

    def sync_sources(self, cfg):
        with self.db:
            self.db.execute("UPDATE subscriptions SET enabled = 0")
            for src in enabled_sources(cfg):
                self.db.execute("""INSERT INTO sources VALUES (?,?,?,?,?)
                    ON CONFLICT(source_id) DO UPDATE SET name=excluded.name, adapter=excluded.adapter""",
                    (src["source_id"], src["canonical_url"], src["name"], src["type"], IDENTITY_VERSION))
                self.db.execute("""INSERT INTO subscriptions VALUES (?,?,1,?)
                    ON CONFLICT(source_id) DO UPDATE SET channel_id=excluded.channel_id,
                    enabled=1, settings_json=excluded.settings_json""",
                    (src["source_id"], src["channel"], json.dumps(src, sort_keys=True)))

    def fetch_state(self, source_id):
        row = self.db.execute("SELECT cursor_json FROM fetch_state WHERE source_id=?", (source_id,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def persist_fetch(self, source, result):
        """Commit the complete batch and safe native cursor in one transaction."""
        timestamp = now_utc()
        inserted = 0
        # All normalization happens in this transaction: a bad item rolls back
        # every insertion and the cursor, rather than silently skipping it.
        with self.db:
            for item in result.items:
                content_id, url, provisional = content_identity(item, source["source_id"])
                revision_id, body_hash, title, body, kind, published_at = revision_fields(content_id, item)
                inserted += self.db.execute("INSERT OR IGNORE INTO contents VALUES (?,?,?,?,NULL)",
                    (content_id, url, int(provisional), timestamp)).rowcount
                self.db.execute("INSERT OR IGNORE INTO content_revisions VALUES (?,?,?,?,?,?,?,?)",
                    (revision_id, content_id, body_hash, title, body, kind, published_at, timestamp))
                # Prefer a fuller body across transports, without downgrading
                # an existing article to a title-only stub from another feed.
                self.db.execute("""UPDATE contents SET latest_revision_id=? WHERE content_id=?
                    AND (latest_revision_id IS NULL OR ? >= (SELECT length(body)
                        FROM content_revisions WHERE revision_id=contents.latest_revision_id))""",
                    (revision_id, content_id, len(body)))
                native_id = str(item.get("native_item_id") or item.get("id") or content_id)
                self.db.execute("INSERT OR IGNORE INTO observations VALUES (?,?,?,?)",
                    (source["source_id"], native_id, content_id, revision_id))
                first_seen = self.db.execute("SELECT first_seen_at FROM contents WHERE content_id=?", (content_id,)).fetchone()[0]
                base = datetime.fromisoformat(published_at or first_seen)
                expires = (base + timedelta(days=source.get("retention_days", 7))).isoformat()
                self.db.execute("""INSERT INTO candidates VALUES (?,'pending',?)
                    ON CONFLICT(content_id) DO UPDATE SET expires_at=max(expires_at,excluded.expires_at)""",
                    (content_id, expires))
            self.db.execute("INSERT INTO fetch_attempts VALUES (?,?,?,?,?,?,?,?)",
                ("fetch_" + uuid.uuid4().hex, source["source_id"], result.status,
                 result.error_code, result.message, len(result.items), result.completeness, timestamp))
            if result.status in {"success", "empty"} and result.completeness == "complete":
                cursor = result.cursor if result.cursor is not None else self.fetch_state(source["source_id"])
                self.db.execute("""INSERT INTO fetch_state VALUES (?,?,?)
                    ON CONFLICT(source_id) DO UPDATE SET cursor_json=excluded.cursor_json,
                    last_success_at=excluded.last_success_at""",
                    (source["source_id"], json.dumps(cursor), timestamp))
        return inserted

    def ensure_run(self, date, cfg, output_mode):
        row = self.db.execute("SELECT * FROM runs WHERE episode_date=?", (date,)).fetchone()
        if row:
            if row["config_hash"] != cfg["config_hash"] or row["output_mode"] != output_mode:
                raise FewError("this date has a frozen run with different configuration/output mode; "
                               "resume with its original config or choose a new date", "frozen_run")
            return dict(row)
        run_id = "run_" + uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO runs VALUES (?,?,?,?,?,'pending',?)",
                (run_id, date, cfg["config_hash"], json.dumps(cfg), output_mode, now_utc()))
        return dict(self.db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone())

    def stage(self, run_id, stage, status, report=None):
        with self.db:
            self.db.execute("""INSERT INTO stage_runs VALUES (?,?,?,?,?)
                ON CONFLICT(run_id,stage) DO UPDATE SET status=excluded.status,
                report_json=excluded.report_json, updated_at=excluded.updated_at""",
                (run_id, stage, status, json.dumps(report), now_utc()))

    def select(self, run, cfg):
        """Freeze selections once; later compose/TTS retries reuse these rows."""
        existing = self.db.execute("SELECT 1 FROM stage_runs WHERE run_id=? AND stage='select' AND status='success'",
                                   (run["run_id"],)).fetchone()
        if existing:
            return self.episodes(run["run_id"])
        with self.db:
            self.db.execute("UPDATE candidates SET state='expired' WHERE state='pending' AND expires_at < ?",
                            (now_utc(),))
            rows = self.db.execute("""SELECT c.content_id,c.canonical_url,r.*,s.source_id,s.name,
                     sub.channel_id,sub.settings_json
                FROM candidates k JOIN contents c USING(content_id)
                JOIN content_revisions r ON r.revision_id=c.latest_revision_id
                JOIN observations o ON o.content_id=c.content_id
                JOIN sources s USING(source_id) JOIN subscriptions sub USING(source_id)
                WHERE k.state='pending' AND sub.enabled=1 AND c.provisional=0 AND length(trim(r.body))>0
                AND NOT EXISTS (SELECT 1 FROM coverage cv WHERE cv.content_id=c.content_id)
                AND NOT EXISTS (SELECT 1 FROM episode_items ei JOIN episodes ep USING(episode_id)
                    WHERE ei.content_id=c.content_id AND ep.status != 'finalized')
                GROUP BY c.content_id,s.source_id""").fetchall()
            candidates = []
            now = datetime.now(timezone.utc)
            channel_order = {ch["id"]: i for i, ch in enumerate(cfg["channels"])}
            for row in rows:
                row = dict(row)
                settings = json.loads(row.pop("settings_json"))
                age = max(0, (now - datetime.fromisoformat(row["published_at"] or row["fetched_at"])).total_seconds() / 86400)
                row["score"] = settings.get("priority", 1) / (1 + age)
                row["cap"] = settings.get("max_items_per_day", 5)
                candidates.append(row)
            candidates.sort(key=lambda r: (-r["score"], -(len(r["body"])),
                                            channel_order[r["channel_id"]], r["content_id"]))
            claimed, source_counts = set(), {}
            channels = {ch["id"]: ch for ch in cfg["channels"]}
            grouped, used_words = {}, {}
            for row in candidates:
                cid, sid, ch = row["content_id"], row["source_id"], row["channel_id"]
                if cid in claimed or source_counts.get(sid, 0) >= row["cap"]:
                    continue
                # This M1 composer is a skeleton, not an LLM summary. Size
                # selection against its actual text; never truncate the body.
                text = row["title"] + " " + row["body"]
                words = sum(1 for c in text if '\u3400' <= c <= '\u9fff') + len(text.split()) + 12
                budget = channels[ch]["max_minutes"] * channels[ch]["words_per_minute"] - 30
                if used_words.get(ch, 0) + words > budget:
                    continue
                claimed.add(cid)
                source_counts[sid] = source_counts.get(sid, 0) + 1
                used_words[ch] = used_words.get(ch, 0) + words
                unit = {"id": cid, "content_id": cid, "revision_id": row["revision_id"],
                        "source_id": sid, "source": row["name"], "channel": ch,
                        "title": row["title"], "body": row["body"], "url": row["canonical_url"],
                        "published_at": row["published_at"], "kind": row["kind"], "score": row["score"]}
                grouped.setdefault(ch, []).append(unit)
            for ch, units in grouped.items():
                episode_id = "ep_" + uuid.uuid4().hex
                self.db.execute("INSERT INTO episodes (episode_id,run_id,channel_id,status) VALUES (?,?,?,'draft')",
                                (episode_id, run["run_id"], ch))
                for pos, unit in enumerate(units):
                    self.db.execute("INSERT INTO episode_items VALUES (?,?,?,?,?)",
                                    (episode_id, unit["content_id"], unit["revision_id"], pos, json.dumps(unit, ensure_ascii=False)))
            self.db.execute("INSERT INTO stage_runs VALUES (?,'select','success',?,?)",
                            (run["run_id"], json.dumps({"selected": len(claimed)}), now_utc()))
        return self.episodes(run["run_id"])

    def episodes(self, run_id):
        return [dict(r) for r in self.db.execute("SELECT * FROM episodes WHERE run_id=? ORDER BY channel_id", (run_id,))]

    def units(self, episode_id):
        return [json.loads(r[0]) for r in self.db.execute("SELECT unit_json FROM episode_items WHERE episode_id=? ORDER BY position", (episode_id,))]

    def finalize(self, episode_id, manifest):
        with self.db:
            episode = self.db.execute("SELECT status FROM episodes WHERE episode_id=?", (episode_id,)).fetchone()
            if episode[0] == "finalized":
                return
            if episode[0] != "script_ready":
                raise FewError("episode must have a validated script before finalization")
            self.db.execute("""INSERT INTO coverage SELECT content_id,episode_id,?
                FROM episode_items WHERE episode_id=?""", (now_utc(), episode_id))
            self.db.execute("UPDATE episodes SET status='finalized', artifact_manifest=?, last_error=NULL WHERE episode_id=?",
                            (json.dumps(manifest), episode_id))

    def status(self):
        counts = {}
        for table in ("sources", "contents", "coverage"):
            counts[table] = self.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        counts["pending"] = self.db.execute("""SELECT count(*) FROM candidates c WHERE state='pending'
            AND NOT EXISTS (SELECT 1 FROM coverage WHERE content_id=c.content_id)""").fetchone()[0]
        counts["needs_enrichment"] = self.db.execute("""SELECT count(*) FROM contents c JOIN content_revisions r
            ON r.revision_id=c.latest_revision_id WHERE trim(r.body)=''""").fetchone()[0]
        return {"counts": counts,
                "runs": [dict(r) for r in self.db.execute("SELECT * FROM runs ORDER BY episode_date DESC")],
                "episodes": [dict(r) for r in self.db.execute("SELECT * FROM episodes")],
                "fetch_attempts": [dict(r) for r in self.db.execute("SELECT * FROM fetch_attempts ORDER BY finished_at DESC LIMIT 100")]}

    def export(self):
        tables = [r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {"schema_version": 1, "identity_version": IDENTITY_VERSION,
                "tables": {name: [dict(r) for r in self.db.execute(f'SELECT * FROM "{name}"')] for name in tables}}
