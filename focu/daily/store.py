"""SQLite is the source of truth; JSON files are inspectable exports."""
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from focu.learn import load_learned_adjustments

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
        # Persist the policy when a registered-source content row is first
        # created. Existing rows are migrated without changing their identity.
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(contents)")}
        if "podcast_mode" not in columns:
            with self.db:
                self.db.execute("""ALTER TABLE contents ADD COLUMN podcast_mode TEXT
                    NOT NULL DEFAULT 'daily_compilation'
                    CHECK(podcast_mode IN ('daily_compilation','single','none'))""")

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
                inserted += self.db.execute("""INSERT OR IGNORE INTO contents
                    (content_id, canonical_url, provisional, first_seen_at,
                     latest_revision_id, podcast_mode)
                    VALUES (?,?,?,?,NULL,'daily_compilation')""",
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

    def select(self, run, cfg, gate_priorities=None, learned_record_path=None):
        """Freeze selections once; later compose/TTS retries reuse these rows."""
        existing = self.db.execute("SELECT 1 FROM stage_runs WHERE run_id=? AND stage='select' AND status='success'",
                                   (run["run_id"],)).fetchone()
        if existing:
            return self.episodes(run["run_id"])
        with self.db:
            # Day-status accounting (self-iteration Q5): selection records,
            # per source, exactly what it considered, claimed, and withheld
            # — and why — so the run's assembled day status can reconcile
            # counts instead of trusting a bare selected total. Written as
            # its own stage row inside this transaction; the 'select'
            # report keeps its exact prior shape.
            accounting = {}

            def _acct(source_id, name):
                return accounting.setdefault(source_id, {
                    "source_id": source_id, "source": name, "considered": 0,
                    "selected": 0, "withheld": {}, "not_ready": {}})

            def _add(counter, reason, n=1):
                counter[reason] = counter.get(reason, 0) + n

            stamp = now_utc()
            for source_id, name, n in self.db.execute("""SELECT s.source_id,s.name,count(DISTINCT c.content_id)
                    FROM candidates k JOIN contents c USING(content_id)
                    JOIN observations o ON o.content_id=c.content_id
                    JOIN sources s USING(source_id) JOIN subscriptions sub USING(source_id)
                    WHERE k.state='pending' AND k.expires_at < ? AND sub.enabled=1
                    GROUP BY s.source_id""", (stamp,)):
                _add(_acct(source_id, name)["not_ready"], "expired", n)
            self.db.execute("UPDATE candidates SET state='expired' WHERE state='pending' AND expires_at < ?",
                            (stamp,))
            rows = self.db.execute("""SELECT c.content_id,c.canonical_url,c.podcast_mode,r.*,s.source_id,s.name,
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
            # Pending candidates the pool query above excludes on readiness
            # grounds: provisional items, and items whose latest revision
            # has no body yet (a title-only YouTube discovery awaiting its
            # transcript, an article awaiting its body) — needs_enrichment
            # in store.status() vocabulary. Counted here so they are named
            # in the day status instead of silently absent from selection.
            for provisional, ready, source_id, name in self.db.execute(
                    """SELECT c.provisional,length(trim(r.body))>0,s.source_id,s.name
                    FROM candidates k JOIN contents c USING(content_id)
                    JOIN content_revisions r ON r.revision_id=c.latest_revision_id
                    JOIN observations o ON o.content_id=c.content_id
                    JOIN sources s USING(source_id) JOIN subscriptions sub USING(source_id)
                    WHERE k.state='pending' AND sub.enabled=1
                    AND NOT EXISTS (SELECT 1 FROM coverage cv WHERE cv.content_id=c.content_id)
                    AND NOT EXISTS (SELECT 1 FROM episode_items ei JOIN episodes ep USING(episode_id)
                        WHERE ei.content_id=c.content_id AND ep.status != 'finalized')
                    GROUP BY c.content_id,s.source_id"""):
                if provisional:
                    _add(_acct(source_id, name)["not_ready"], "provisional")
                elif not ready:
                    _add(_acct(source_id, name)["not_ready"], "needs_enrichment")
            # Learned influence (learning Phase 3, design §3.3): the ONLY
            # consumer of the preference record. Fail-closed — a corrupted
            # record yields no adjustments and its error is frozen into the
            # stage report below; selection then runs exactly as before.
            # Registry values are never replaced: a learned weight is a
            # clamped multiplier applied after the registry priority, a
            # learned cap can only lower the registry cap, and a pause
            # exists only as an owner-written record entry.
            adjustments, learn_error, record_version = load_learned_adjustments(
                learned_record_path)
            candidates = []
            paused, paused_seen = [], set()
            now = datetime.now(timezone.utc)
            channel_order = {ch["id"]: i for i, ch in enumerate(cfg["channels"])}
            for row in rows:
                row = dict(row)
                acct = _acct(row["source_id"], row["name"])
                acct["considered"] += 1
                settings = json.loads(row.pop("settings_json"))
                adj = adjustments.get(row["source_id"]) or {}
                if adj.get("pause"):
                    _add(acct["withheld"], "paused_by_learning")
                    if row["source_id"] not in paused_seen:
                        paused_seen.add(row["source_id"])
                        paused.append({
                            "source_id": row["source_id"], "source": row["name"],
                            "preference_id": adj["pause"]["preference_id"],
                            "created_at": adj["pause"].get("created_at")})
                    continue
                age = max(0, (now - datetime.fromisoformat(row["published_at"] or row["fetched_at"])).total_seconds() / 86400)
                factors = []
                weight = 1.0
                if adj.get("weight"):
                    weight = adj["weight"]["value"]
                    if weight != 1.0:
                        factors.append({"preference_id": adj["weight"]["preference_id"],
                                        "kind": "source_weight", "value": weight})
                row["score"] = settings.get("priority", 1) * weight / (1 + age)
                # Active gate only reorders revision-matched candidates; it never
                # deletes, suppresses or claims coverage for a source.
                signal = (gate_priorities or {}).get(row["content_id"], {})
                row["gate_priority"] = (signal.get("priority", "normal")
                                        if signal.get("revision_id") == row["revision_id"]
                                        else "normal")
                row["gate_rank"] = {"promote": 1, "normal": 0, "defer": -1}.get(
                    row["gate_priority"], 0)
                cap = settings.get("max_items_per_day", 5)
                if adj.get("cap"):
                    lowered = min(cap, adj["cap"]["value"])
                    if lowered < cap:
                        factors.append({"preference_id": adj["cap"]["preference_id"],
                                        "kind": "source_cap", "value": lowered})
                    cap = lowered
                row["cap"] = cap
                row["learned_factors"] = factors
                candidates.append(row)
            candidates.sort(key=lambda r: (-r["gate_rank"], -r["score"], -(len(r["body"])),
                                            channel_order[r["channel_id"]], r["content_id"]))
            claimed, source_counts = set(), {}
            channels = {ch["id"]: ch for ch in cfg["channels"]}
            grouped, used_words = {}, {}
            for row in candidates:
                cid, sid, ch = row["content_id"], row["source_id"], row["channel_id"]
                acct = _acct(sid, row["name"])
                if cid in claimed:
                    _add(acct["withheld"], "already_selected")
                    continue
                if source_counts.get(sid, 0) >= row["cap"]:
                    _add(acct["withheld"], "over_cap")
                    continue
                # This M1 composer is a skeleton, not an LLM summary. Size
                # selection against its actual text; never truncate the body.
                text = row["title"] + " " + row["body"]
                words = sum(1 for c in text if '\u3400' <= c <= '\u9fff') + len(text.split()) + 12
                budget = channels[ch]["max_minutes"] * channels[ch]["words_per_minute"] - 30
                if used_words.get(ch, 0) + words > budget:
                    _add(acct["withheld"], "over_budget")
                    continue
                claimed.add(cid)
                acct["selected"] += 1
                source_counts[sid] = source_counts.get(sid, 0) + 1
                used_words[ch] = used_words.get(ch, 0) + words
                unit = {"id": cid, "content_id": cid, "revision_id": row["revision_id"],
                        "source_id": sid, "source": row["name"], "channel": ch,
                        "title": row["title"], "body": row["body"], "url": row["canonical_url"],
                        "published_at": row["published_at"], "kind": row["kind"], "score": row["score"],
                        "gate_priority": row["gate_priority"]}
                # Freeze the learned factors that actually applied to this
                # item (design §3.3 rule 3): focu learn explain answers from
                # exactly this list. When any adjustment was in force the
                # key is frozen even when empty for this item, so explain
                # can tell a Phase-3 run from a pre-Phase-3 item; with an
                # empty record no key appears at all and the frozen units
                # stay byte-identical to the pre-Phase-3 engine.
                if row["learned_factors"] or adjustments:
                    unit["learned_factors"] = row["learned_factors"]
                grouped.setdefault(ch, []).append(unit)
            for ch, units in grouped.items():
                episode_id = "ep_" + uuid.uuid4().hex
                self.db.execute("INSERT INTO episodes (episode_id,run_id,channel_id,status) VALUES (?,?,?,'draft')",
                                (episode_id, run["run_id"], ch))
                for pos, unit in enumerate(units):
                    self.db.execute("INSERT INTO episode_items VALUES (?,?,?,?,?)",
                                    (episode_id, unit["content_id"], unit["revision_id"], pos, json.dumps(unit, ensure_ascii=False)))
            select_report = {"selected": len(claimed)}
            learned_block = {}
            if learn_error:
                learned_block["record_error"] = learn_error
            if adjustments:
                learned_block["record_version"] = record_version
            if paused:
                # A pause is never silent (Phase-3 acceptance): the run
                # record carries the one-line announcement the briefing
                # status surfaces, naming the day the owner recorded it.
                learned_block["paused"] = [
                    {**entry, "announcement":
                     f"Paused by you on {entry['created_at']}: {entry['source']}"}
                    for entry in paused]
            if learned_block:
                select_report["learned"] = learned_block
            self.db.execute("INSERT INTO stage_runs VALUES (?,'select','success',?,?)",
                            (run["run_id"], json.dumps(select_report), now_utc()))
            accounting_report = {"sources": [
                {"source_id": a["source_id"], "source": a["source"],
                 "considered": a["considered"], "selected": a["selected"],
                 "withheld": [{"reason": r, "count": n}
                              for r, n in sorted(a["withheld"].items())],
                 "not_ready": [{"reason": r, "count": n}
                               for r, n in sorted(a["not_ready"].items())]}
                for a in (accounting[sid] for sid in sorted(accounting))]}
            self.db.execute("INSERT INTO stage_runs VALUES (?,'selection_accounting','success',?,?)",
                            (run["run_id"], json.dumps(accounting_report), now_utc()))
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
            # OR IGNORE: re-finalizing the same episode (e.g. after a host script
            # revision) must not fail on the coverage rows its first finalize
            # already recorded. Digest never re-selects covered content, so no
            # other episode can claim the same content_id.
            self.db.execute("""INSERT OR IGNORE INTO coverage SELECT content_id,episode_id,?
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
