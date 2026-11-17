"""Learning loop, Phase 1: proposals over evidence, a record only the owner writes.

Design: docs/dev-team/learning-design.md. The system computes statistics
from the owner's own acts (the explicit feedback ledger in focu/feedback.py
and the daily pipeline's frozen selection history), drafts a small number
of fully-evidenced proposals, and applies NOTHING itself. The only thing
that may ever influence selection is references/learned-preferences.md, a
versioned, human-readable record in the focu/audience.py pattern, and in
this phase its only programmatic writer is the accept path below
(owner-stated entries are entered by hand — the file is the source of
truth). Phase 1 deliberately does not touch selection or scoring:
influence wiring, with its clamps and explain view, is Phase 3.

Phase 2 transport lives here too: ingest_reading_summary imports the
reader's owner-carried reading-summary export (format contract in the
reader's index.html) into the feedback ledger, idempotently, so real
reader signals — completions, not-for-me marks, useful marks — reach
the Phase-1 statistics. It writes only to the ledger. Compilation
(daily briefing) signals fan out to the units the briefing covered —
a compilation id is never a unit id, so without the fan-out every
briefing mark fell into unattributed_feedback (PM sweep F1) — and
research-item marks are reported as out of scope, never recorded:
research lives in the research store, which the statistics never read.

Phase 3 is the record's consumer: learned_adjustments() below is the
ONLY path from the preference record to selection. It applies the
design's §3.3 bounds at the point of consumption (weights clamped to
[0.5, 1.5]; caps carried raw so the seam can only lower the registry
cap; pauses honored as the owner acts they are), and the daily store's
select() freezes every factor it actually applied onto the episode
item, which is what explain() answers from. Phase 3 adds no inference
path of its own: it consumes owner-written entries, nothing else.

Review proposals (PM sweep F5, design §3.4 + §6.1) close the loop's
long horizon. Two extra proposal kinds, both ABOUT an existing record
entry (their value is the entry id, never a new preference):

  renewal      — an active entry past its review_after. Its evidence
                 is current: delivered / completion / useful /
                 negative counts for the entry's target SINCE the
                 entry was created, so renewal is a fresh judgment.
  pause_review — an active source_pause entry aged 90+ days: the
                 quarterly "restore, keep, or remove?" question. At
                 most one pause_review per entry per 90 days, counted
                 over ALL past pause_review proposals for that entry
                 (open, expired, dismissed, or accepted alike).

Acceptance semantics for both kinds, stated once here: accepting a
review proposal REFRESHES the named entry in place — review_after
moves 90 days out, the renewal and its evidence are appended to the
entry's evidence trail, and an owner-supplied --value replaces the
entry's value (validated as usual). It never appends a duplicate
entry and never supersedes the old one; restore/remove remain owner
acts on the record itself. Dismissal snoozes like any other kind.

The 90-day step rule (design §6.1) is explicit, not emergent: a
kind+target whose last ACCEPTED proposal is under 90 days old is not
re-proposed, even if the entry it wrote has since been superseded —
an accept → supersede → re-propose cycle cannot ratchet a source
down inside one quarter.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from focu.feedback import FeedbackStore

RECORD_PATH = Path(__file__).resolve().parents[1] / "references" / "learned-preferences.md"

ENTRY_KINDS = {"source_pause", "source_cap", "source_weight", "topic_weight", "standing_note"}
PROVENANCES = {"owner-stated", "owner-accepted"}
ENTRY_FIELDS = {"id", "kind", "target", "value", "statement", "provenance",
                "evidence", "created_at", "review_after", "status"}
# Dismissal snoozes (design §2.3): "not now" costs the engine 60 days for
# pauses/caps, 30 days for weight changes.
SNOOZE_DAYS = {"source_pause": 60, "source_cap": 60, "source_weight": 30,
               "topic_weight": 30, "standing_note": 30,
               "renewal": 30, "pause_review": 90}

# Review proposals (see module docstring): kinds whose value is an
# existing record entry's id, not a new preference value.
REVIEW_KINDS = {"renewal", "pause_review"}
LONG_PAUSE_DAYS = 90          # a pause this old earns a quarterly review
STEP_RULE_DAYS = 90           # one accepted step per kind+target per quarter
REVIEW_REPROPOSE_DAYS = {"renewal": 30, "pause_review": 90}

WINDOW_DAYS = 30
MIN_DELIVERED = 10            # evidence floor (design §6.2): below this, silence
NEGATIVE_KINDS = ("not_useful", "too_long", "incorrect")
MIN_NEGATIVE_EVENTS = 3
MIN_NEGATIVE_RATE = 0.2
DEMOTE_WEIGHT = 0.7           # statistics may only demote (design §3.3 rule 2)
MIN_USEFUL_EVENTS = 3
PROMOTE_WEIGHT = 1.25         # promotion requires the owner's own useful marks
MAX_OPEN_PROPOSALS = 3        # the weekly attention budget (design §2.2)
REVIEW_AFTER_DAYS = 90
# Anti-spiral constants (design §6.1): at most one accepted demotion
# step per target per 90 days, and a pause earns its quarterly review
# once it is 90 days old.
DEMOTION_STEP_WINDOW_DAYS = 90
PAUSE_REVIEW_MIN_AGE_DAYS = 90
# Proposal-only kinds: accepting one refreshes an existing record entry
# in place; it never appends one. Their target is the entry id (lp-NNN),
# so snoozes and the quarterly gate key per entry, not per source.
RENEWAL_PROPOSAL_KINDS = {"entry_renewal", "pause_review"}


# --------------------------------------------------------------------------
# The preference record: provenance-enforced, fail-closed (audience.py style)
# --------------------------------------------------------------------------

def _as_date(value, field, entry_id):
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise ValueError(f"Learned-preference entry {entry_id}: {field} is not a date: {value!r}")


def _validate_entry(entry):
    if not isinstance(entry, dict):
        raise ValueError("Learned-preference entry must be a mapping")
    unknown = set(entry) - ENTRY_FIELDS
    if unknown:
        raise ValueError(f"Learned-preference entry has unknown fields: {sorted(unknown)}")
    entry_id = entry.get("id")
    if not isinstance(entry_id, str) or not re.fullmatch(r"lp-\d+", entry_id):
        raise ValueError(f"Learned-preference entry id must look like lp-007: {entry_id!r}")
    kind = entry.get("kind")
    if kind not in ENTRY_KINDS:
        raise ValueError(f"Learned-preference entry {entry_id}: unknown kind {kind!r}")
    if entry.get("provenance") not in PROVENANCES:
        raise ValueError(
            f"Learned-preference entry {entry_id}: provenance must be owner-stated "
            f"or owner-accepted, got {entry.get('provenance')!r}")
    target = entry.get("target")
    if kind == "standing_note":
        if not isinstance(entry.get("value"), str) or not entry["value"].strip():
            raise ValueError(f"Learned-preference entry {entry_id}: standing_note value must be text")
    else:
        if not isinstance(target, str) or not target.strip():
            raise ValueError(f"Learned-preference entry {entry_id}: target required")
        value = entry.get("value")
        if kind in {"source_weight", "topic_weight"}:
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"Learned-preference entry {entry_id}: weight must be a positive number")
        elif kind == "source_cap":
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"Learned-preference entry {entry_id}: cap must be a positive integer")
        elif kind == "source_pause":
            if value is not True:
                raise ValueError(f"Learned-preference entry {entry_id}: pause value must be true")
    for field in ("statement", "evidence"):
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            raise ValueError(f"Learned-preference entry {entry_id}: {field} required")
    if entry.get("status") not in {"active", "superseded"}:
        raise ValueError(f"Learned-preference entry {entry_id}: status must be active or superseded")
    entry["created_at"] = _as_date(entry.get("created_at"), "created_at", entry_id)
    entry["review_after"] = _as_date(entry.get("review_after"), "review_after", entry_id)
    return entry


def load_record(path=RECORD_PATH):
    """Strict loader: any malformed or unprovenanced entry raises ValueError."""
    source = Path(path).read_text(encoding="utf-8")
    match = re.search(r"```yaml\s*\n(.*?)\n```", source, re.S)
    if not match:
        raise ValueError("Learned-preference record lacks YAML settings")
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise ValueError("Learned-preference record must be a mapping")
    unknown = set(data) - {"version", "entries"}
    if unknown:
        raise ValueError(f"Learned-preference record has unknown fields: {sorted(unknown)}")
    if not isinstance(data.get("version"), str) or not data["version"]:
        raise ValueError("Learned-preference record lacks a version")
    if not isinstance(data.get("entries"), list):
        raise ValueError("Learned-preference record entries must be a list")
    seen = set()
    for entry in data["entries"]:
        _validate_entry(entry)
        if entry["id"] in seen:
            raise ValueError(f"Learned-preference entry id duplicated: {entry['id']}")
        seen.add(entry["id"])
    data["record_sha256"] = hashlib.sha256(source.encode()).hexdigest()
    return data


def safe_load_record(path=RECORD_PATH):
    """Fail-closed variant: a corrupted record yields ZERO learned influence
    plus the error, never a guess (design §3.1). Returns (record, error)."""
    try:
        return load_record(path), None
    except (ValueError, OSError, yaml.YAMLError) as exc:
        return {"version": None, "entries": [], "record_sha256": None}, str(exc)


def _bump_version(version, today):
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.(\d+)", str(version))
    if match and match.group(1) == today.isoformat():
        return f"{today.isoformat()}.{int(match.group(2)) + 1}"
    return f"{today.isoformat()}.1"


def _write_record(path, data, changelog_line, today):
    """The record's only writer. Called exclusively by accept_proposal."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    new_version = _bump_version(data["version"], today)
    block = yaml.safe_dump({"version": new_version, "entries": data["entries"]},
                           sort_keys=False, allow_unicode=True).rstrip("\n")
    pattern = re.compile(r"```yaml\s*\n.*?\n```", re.S)
    if not pattern.search(text):
        raise ValueError("Learned-preference record lacks a YAML block to rewrite")
    text = pattern.sub(lambda _m: "```yaml\n" + block + "\n```", text, count=1)
    text, count = re.subn(r"\*\*Version:\*\* .*", f"**Version:** {new_version}", text, count=1)
    if count == 0:
        raise ValueError("Learned-preference record lacks a Version header")
    idx = text.rfind("## Changelog")
    if idx == -1:
        raise ValueError("Learned-preference record lacks a Changelog section")
    if "\n## " in text[idx + len("## Changelog"):]:
        raise ValueError("Changelog is not the final section; refusing to guess where to append")
    if not text.endswith("\n"):
        text += "\n"
    text += changelog_line + "\n"
    path.write_text(text, encoding="utf-8")
    return new_version


def _statement_for(kind, target_name, value):
    name = target_name or "the target"
    if kind == "source_weight":
        return f"Set selection weight to {value}× for {name}."
    if kind == "topic_weight":
        return f"Set topic weight to {value}× for {name}."
    if kind == "source_cap":
        return f"Cap {name} at {value} item(s) per day."
    if kind == "source_pause":
        return f"Pause {name}."
    return str(value)


# --------------------------------------------------------------------------
# The proposals store: working state beside the feedback ledger (design §3.2)
# --------------------------------------------------------------------------

class ProposalStore:
    def __init__(self, db_path: str | Path = "data/focu.sqlite3") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS learn_proposals (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                target TEXT NOT NULL,
                target_name TEXT NOT NULL DEFAULT '',
                value TEXT NOT NULL,
                statement TEXT NOT NULL,
                evidence TEXT NOT NULL,
                state TEXT NOT NULL,
                snooze_until TEXT,
                never INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                decided_at TEXT
            )""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _decode(row):
        item = dict(row)
        item["value"] = json.loads(item["value"])
        item["never"] = bool(item["never"])
        return item

    def expire_open(self) -> None:
        """Proposals die at the next batch; a dead proposal is not renewed."""
        with self._connect() as db:
            db.execute("UPDATE learn_proposals SET state='expired' WHERE state='proposed'")

    def add(self, proposal: dict) -> dict:
        with self._connect() as db:
            db.execute("""INSERT INTO learn_proposals
                (id, kind, target, target_name, value, statement, evidence,
                 state, snooze_until, never, created_at, decided_at)
                VALUES (?,?,?,?,?,?,?,'proposed',NULL,0,?,NULL)""",
                       (proposal["id"], proposal["kind"], proposal["target"],
                        proposal.get("target_name", ""), json.dumps(proposal["value"]),
                        proposal["statement"], proposal["evidence"], proposal["created_at"]))
        return self.get(proposal["id"])

    def get(self, proposal_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM learn_proposals WHERE id=?", (proposal_id,)).fetchone()
        return self._decode(row) if row else None

    def list_open(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("""SELECT * FROM learn_proposals WHERE state='proposed'
                ORDER BY created_at, id""").fetchall()
        return [self._decode(row) for row in rows]

    def decide(self, proposal_id: str, state: str, *, snooze_until: str | None = None,
               never: bool = False, decided_at: str) -> dict:
        with self._connect() as db:
            db.execute("""UPDATE learn_proposals SET state=?, snooze_until=?,
                never=?, decided_at=? WHERE id=?""",
                       (state, snooze_until, int(never), decided_at, proposal_id))
        return self.get(proposal_id)

    def history(self) -> list[dict]:
        """Every proposal ever stored, oldest first, any state. The
        review-proposal cadence (one pause_review per entry per
        quarter) and the explicit 90-day step rule are computed over
        this full history, not just over open or dismissed rows: an
        expired proposal still counts as having been asked."""
        with self._connect() as db:
            rows = db.execute("""SELECT * FROM learn_proposals
                ORDER BY created_at, id""").fetchall()
        return [self._decode(row) for row in rows]

    def snoozes(self) -> dict:
        """(kind, target) -> {'never': bool, 'until': date|None} from dismissals."""
        result = {}
        with self._connect() as db:
            rows = db.execute("""SELECT kind, target, snooze_until, never
                FROM learn_proposals WHERE state='dismissed'""").fetchall()
        for row in rows:
            entry = result.setdefault((row["kind"], row["target"]),
                                      {"never": False, "until": None})
            if row["never"]:
                entry["never"] = True
            if row["snooze_until"]:
                until = date.fromisoformat(row["snooze_until"])
                if entry["until"] is None or until > entry["until"]:
                    entry["until"] = until
        return result


# --------------------------------------------------------------------------
# Statistics: feedback ledger + frozen selection history (both already on-VM)
# --------------------------------------------------------------------------

def _selection_history(daily_dir, start: date, end: date):
    """Per-source delivered counts from frozen episode items in the window.

    Returns (delivered, content_source, episode_sources): delivered maps
    source_id -> {"name", "delivered", "days"}; content_source maps an
    in-window content_id to its source_id; episode_sources maps
    (episode_date, channel_id) to the set of source_ids in that episode.
    A missing daily database is a legitimate empty history, not an error.
    """
    delivered: dict[str, dict] = {}
    content_source: dict[str, str] = {}
    episode_sources: dict[tuple[str, str], set] = {}
    db_file = Path(daily_dir) / "few.sqlite3"
    if not db_file.is_file():
        return delivered, content_source, episode_sources
    db = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    try:
        rows = db.execute("""SELECT r.episode_date, e.channel_id, ei.content_id, ei.unit_json
            FROM episode_items ei
            JOIN episodes e USING(episode_id)
            JOIN runs r USING(run_id)""").fetchall()
    finally:
        db.close()
    for episode_date, channel_id, content_id, unit_json in rows:
        if not (start.isoformat() <= str(episode_date) <= end.isoformat()):
            continue
        try:
            unit = json.loads(unit_json)
        except (TypeError, json.JSONDecodeError):
            continue
        source_id = unit.get("source_id")
        if not source_id:
            continue
        slot = delivered.setdefault(source_id, {"name": unit.get("source") or source_id,
                                                "delivered": 0, "days": set()})
        slot["delivered"] += 1
        slot["days"].add(str(episode_date))
        content_source[content_id] = source_id
        episode_sources.setdefault((str(episode_date), channel_id), set()).add(source_id)
    for slot in delivered.values():
        slot["days"] = len(slot["days"])
    return delivered, content_source, episode_sources


def _attribute_feedback(events, content_source, episode_sources, start: date, end: date):
    """Attribute feedback events to sources, honestly or not at all.

    observation events name a content_id; episode events name
    '<episode_date>/<channel_id>' and are attributed only when every item
    in that episode came from one source — mixed-source episode feedback is
    counted as unattributed rather than smeared across sources.
    """
    per_source: dict[str, dict] = {}
    unattributed = 0
    for event in events:
        try:
            created = datetime.fromisoformat(str(event["created_at"])).date()
        except ValueError:
            unattributed += 1
            continue
        if not (start <= created <= end):
            continue
        source_id = None
        if event["target_type"] == "observation":
            source_id = content_source.get(event["target_id"])
        elif event["target_type"] == "episode":
            parts = str(event["target_id"]).split("/", 1)
            if len(parts) == 2:
                sources = episode_sources.get((parts[0], parts[1]), set())
                if len(sources) == 1:
                    source_id = next(iter(sources))
        if source_id is None:
            unattributed += 1
            continue
        kinds = per_source.setdefault(source_id, {})
        kinds[event["kind"]] = kinds.get(event["kind"], 0) + 1
    return per_source, unattributed


def compute_statistics(db_path, daily_dir, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    end = now.date()
    start = end - timedelta(days=WINDOW_DAYS - 1)
    delivered, content_source, episode_sources = _selection_history(daily_dir, start, end)
    events = FeedbackStore(db_path).list()
    per_source, unattributed = _attribute_feedback(
        events, content_source, episode_sources, start, end)
    sources = {}
    for source_id in set(delivered) | set(per_source):
        slot = delivered.get(source_id, {"name": source_id, "delivered": 0, "days": 0})
        kinds = per_source.get(source_id, {})
        sources[source_id] = {
            "name": slot["name"],
            "delivered": slot["delivered"],
            "days": slot["days"],
            "negative": {k: kinds.get(k, 0) for k in NEGATIVE_KINDS if kinds.get(k, 0)},
            "negative_total": sum(kinds.get(k, 0) for k in NEGATIVE_KINDS),
            "useful": kinds.get("useful", 0),
        }
    return {"window": {"start": start.isoformat(), "end": end.isoformat(),
                       "days": WINDOW_DAYS},
            "sources": sources, "unattributed_feedback": unattributed}


# --------------------------------------------------------------------------
# The proposal engine: statistics in, at most 3 evidenced proposals out
# --------------------------------------------------------------------------

def _entry_current_evidence(entry, db_path, daily_dir, today: date) -> str:
    """Current evidence for a review proposal: what the entry's target
    has done SINCE the entry was created (design §3.4: renewal is a
    fresh judgment, not a rubber stamp). Delivered counts come from
    the frozen selection history; completion / useful / negative
    counts from the attributed feedback ledger over the same span.
    A target with no recorded history says so, plainly."""
    created = date.fromisoformat(entry["created_at"])
    age = (today - created).days
    base = (f"entry {entry['id']} ({entry['kind']}) created "
            f"{created.isoformat()}, {age}d old, review_after "
            f"{entry['review_after']}")
    target = entry.get("target")
    if not target:
        return base + "; standing note: no delivered history applies"
    delivered, content_source, episode_sources = _selection_history(
        daily_dir, created, today)
    slot = delivered.get(target)
    events = FeedbackStore(db_path).list()
    per_source, _unattributed = _attribute_feedback(
        events, content_source, episode_sources, created, today)
    kinds = per_source.get(target, {})
    negative = sum(kinds.get(k, 0) for k in NEGATIVE_KINDS)
    feedback = (f"feedback since: {kinds.get('other', 0)} completion(s), "
                f"{kinds.get('useful', 0)} useful, {negative} negative")
    if slot:
        return (base + f"; since then {slot['delivered']} items delivered "
                f"over {slot['days']} day(s); " + feedback)
    return base + "; since then 0 items delivered recorded; " + feedback


def _review_candidates(record, history, db_path, daily_dir, today: date):
    """Renewal and long-pause candidates from the record itself.

    A pause aged 90+ days gets pause_review INSTEAD of renewal (one
    question per entry per batch, the sharper one). An entry with a
    review proposal created inside its repropose window (30d renewal,
    90d pause_review, over the full proposal history) is not asked
    about again yet — expiry of the earlier proposal does not reset
    the clock."""
    recently_reviewed = set()
    for past in history:
        if past["kind"] not in REVIEW_KINDS:
            continue
        try:
            asked = datetime.fromisoformat(past["created_at"]).date()
        except ValueError:
            continue
        if (today - asked).days < REVIEW_REPROPOSE_DAYS[past["kind"]]:
            recently_reviewed.add(past["value"])
    candidates = []
    for entry in record["entries"]:
        if entry.get("status") != "active" or entry["id"] in recently_reviewed:
            continue
        created = date.fromisoformat(entry["created_at"])
        age = (today - created).days
        name = entry.get("target") or entry["id"]
        if entry["kind"] == "source_pause" and age >= LONG_PAUSE_DAYS:
            candidates.append({
                "rank": (-2, -age),
                "kind": "pause_review", "target": entry["target"],
                "target_name": entry["target"], "value": entry["id"],
                "statement": (
                    f"Keep {name} paused (entry {entry['id']}, paused "
                    f"{age} days) and review again in 90 days — or "
                    f"restore or remove it by your word."),
                "evidence": _entry_current_evidence(
                    entry, db_path, daily_dir, today),
            })
        elif date.fromisoformat(entry["review_after"]) <= today:
            candidates.append({
                "rank": (-1, -age),
                "kind": "renewal", "target": entry.get("target") or entry["id"],
                "target_name": entry.get("target") or "",
                "value": entry["id"],
                "statement": (
                    f"Keep entry {entry['id']} in force "
                    f"({entry['statement']}) and review again in "
                    f"{REVIEW_AFTER_DAYS} days."),
                "evidence": _entry_current_evidence(
                    entry, db_path, daily_dir, today),
            })
    return candidates


def generate_proposals(db_path="data/focu.sqlite3", daily_dir="data",
                       record_path=RECORD_PATH, now: datetime | None = None) -> dict:
    """Run one weekly batch. Prior open proposals expire; snoozes and
    never-dismissals are honored; pairs already in the record are not
    re-proposed; a kind+target accepted under 90 days ago is not
    re-proposed even if its entry was superseded (the explicit 90-day
    step rule); review proposals for stale record entries compete in
    the same 3-proposal budget, ahead of new statistics proposals.
    Empty history correctly produces an empty batch."""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    store = ProposalStore(db_path)
    store.expire_open()
    stats = compute_statistics(db_path, daily_dir, now)
    snoozes = store.snoozes()
    record, record_error = safe_load_record(record_path)
    in_record = {(e["kind"], e["target"]) for e in record["entries"]
                 if e.get("status") == "active"}
    history = store.history()
    last_accepted: dict[tuple[str, str], date] = {}
    for past in history:
        if past["state"] not in ("accepted", "edited-accepted"):
            continue
        if not past.get("decided_at"):
            continue
        try:
            decided = datetime.fromisoformat(past["decided_at"]).date()
        except ValueError:
            continue
        key = (past["kind"], past["target"])
        if key not in last_accepted or decided > last_accepted[key]:
            last_accepted[key] = decided

    candidates = _review_candidates(record, history, db_path, daily_dir, today)
    below_floor = 0
    for source_id, slot in stats["sources"].items():
        if slot["delivered"] < MIN_DELIVERED:
            if slot["delivered"] or slot["negative_total"] or slot["useful"]:
                below_floor += 1
            continue
        negative = slot["negative_total"]
        if (negative >= MIN_NEGATIVE_EVENTS
                and negative / slot["delivered"] >= MIN_NEGATIVE_RATE):
            breakdown = ", ".join(f"{k} ×{n}" for k, n in sorted(slot["negative"].items()))
            candidates.append({
                "rank": (0, -negative, -slot["delivered"]),
                "kind": "source_weight", "target": source_id,
                "target_name": slot["name"], "value": DEMOTE_WEIGHT,
                "evidence": (f"{negative} of {slot['delivered']} items drew negative "
                             f"feedback ({breakdown}), {WINDOW_DAYS}d window, "
                             f"n={slot['delivered']} delivered"),
            })
        elif slot["useful"] >= MIN_USEFUL_EVENTS:
            candidates.append({
                "rank": (1, -slot["useful"], -slot["delivered"]),
                "kind": "source_weight", "target": source_id,
                "target_name": slot["name"], "value": PROMOTE_WEIGHT,
                "evidence": (f"{slot['useful']} owner 'useful' marks on "
                             f"{slot['delivered']} delivered items, {WINDOW_DAYS}d "
                             f"window, n={slot['delivered']} delivered"),
            })

    created = []
    for cand in sorted(candidates, key=lambda c: c["rank"]):
        if len(created) >= MAX_OPEN_PROPOSALS:
            break
        key = (cand["kind"], cand["target"])
        if key in in_record:
            continue
        accepted_on = last_accepted.get(key)
        if accepted_on is not None and (today - accepted_on).days < STEP_RULE_DAYS:
            continue
        snooze = snoozes.get(key)
        if snooze and (snooze["never"] or (snooze["until"] and today < snooze["until"])):
            continue
        proposal = {
            "id": f"prop-{today.strftime('%Y%m%d')}-{len(created) + 1}",
            "kind": cand["kind"], "target": cand["target"],
            "target_name": cand["target_name"], "value": cand["value"],
            "statement": cand.get("statement") or _statement_for(
                cand["kind"], cand["target_name"], cand["value"]),
            "evidence": cand["evidence"],
            "created_at": now.isoformat(),
        }
        created.append(store.add(proposal))
    return {"proposals": created, "window": stats["window"],
            "sources_considered": len(stats["sources"]),
            "sources_below_evidence_floor": below_floor,
            "unattributed_feedback": stats["unattributed_feedback"],
            "record_error": record_error}


# --------------------------------------------------------------------------
# Owner decisions: accept (the record's only writer) and dismiss (snooze)
# --------------------------------------------------------------------------

def accept_proposal(proposal_id, db_path="data/focu.sqlite3",
                    record_path=RECORD_PATH, value=None,
                    now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = now.date()
    store = ProposalStore(db_path)
    proposal = store.get(proposal_id)
    if proposal is None:
        raise ValueError(f"Proposal not found: {proposal_id}")
    if proposal["state"] != "proposed":
        raise ValueError(f"Proposal {proposal_id} is not open (state: {proposal['state']})")
    record = load_record(record_path)  # strict: never write into a broken record
    renewed = proposal["kind"] in REVIEW_KINDS
    if renewed:
        # Review acceptance semantics (module docstring): refresh the
        # named entry IN PLACE — review_after moves out by
        # REVIEW_AFTER_DAYS, the renewal and its evidence join the
        # entry's evidence trail, and an owner-supplied value replaces
        # the entry's value. No duplicate is appended, nothing is
        # superseded; the entry keeps its id, kind, target, and
        # provenance. For a review proposal the `value` argument is
        # the ENTRY's new value, not a replacement for the proposal's
        # value (which is the entry id).
        entry = next((e for e in record["entries"]
                      if e["id"] == proposal["value"]
                      and e.get("status") == "active"), None)
        if entry is None:
            raise ValueError(
                f"Proposal {proposal_id} reviews entry {proposal['value']!r}, "
                "which is not an active record entry")
        edited = value is not None and value != entry["value"]
        if edited:
            entry["value"] = value
            entry["statement"] = _statement_for(
                entry["kind"], proposal["target_name"], value)
        entry["review_after"] = (
            today + timedelta(days=REVIEW_AFTER_DAYS)).isoformat()
        entry["evidence"] = (
            f"{entry['evidence']} · renewed by {proposal_id} on "
            f"{today.isoformat()}: {proposal['evidence']}"
            + (" · value edited by owner at accept" if edited else ""))
        _validate_entry(dict(entry))
        changelog = (f"- **{today.isoformat()} — renewed {entry['id']} via "
                     f"{proposal_id}:** {entry['statement']} "
                     f"Evidence: {entry['evidence']}")
    else:
        edited = value is not None and value != proposal["value"]
        final_value = proposal["value"] if value is None else value
        numbers = [int(e["id"][3:]) for e in record["entries"]
                   if re.fullmatch(r"lp-\d+", str(e.get("id", "")))]
        entry = {
            "id": f"lp-{max(numbers, default=0) + 1:03d}",
            "kind": proposal["kind"],
            "target": proposal["target"],
            "value": final_value,
            "statement": _statement_for(proposal["kind"], proposal["target_name"], final_value),
            "provenance": "owner-accepted",
            "evidence": f"{proposal_id} · {proposal['evidence']}"
                        + (" · value edited by owner at accept" if edited else ""),
            "created_at": today.isoformat(),
            "review_after": (today + timedelta(days=REVIEW_AFTER_DAYS)).isoformat(),
            "status": "active",
        }
        _validate_entry(dict(entry))
        record["entries"].append(entry)
        changelog = (f"- **{today.isoformat()} — accepted {proposal_id}:** "
                     f"{entry['statement']} Evidence: {entry['evidence']}")
    new_version = _write_record(record_path, record, changelog, today)
    decided = store.decide(proposal_id, "edited-accepted" if edited else "accepted",
                           decided_at=now.isoformat())
    result = {"proposal": decided, "entry": entry, "record_version": new_version}
    if renewed:
        result["renewed"] = True
    return result


def dismiss_proposal(proposal_id, db_path="data/focu.sqlite3", never: bool = False,
                     now: datetime | None = None) -> dict:
    """Dismissal writes nothing to the record; it only snoozes the engine."""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    store = ProposalStore(db_path)
    proposal = store.get(proposal_id)
    if proposal is None:
        raise ValueError(f"Proposal not found: {proposal_id}")
    if proposal["state"] != "proposed":
        raise ValueError(f"Proposal {proposal_id} is not open (state: {proposal['state']})")
    snooze_until = None
    if not never:
        days = SNOOZE_DAYS.get(proposal["kind"], 30)
        snooze_until = (today + timedelta(days=days)).isoformat()
    return store.decide(proposal_id, "dismissed", snooze_until=snooze_until,
                        never=never, decided_at=now.isoformat())


def show(db_path="data/focu.sqlite3", record_path=RECORD_PATH,
         now: datetime | None = None) -> dict:
    """The record, inspectable: every active entry carries its age in
    days (design §3.4 — staleness is visible even when no renewal
    proposal has been sent)."""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    record, error = safe_load_record(record_path)
    entries = []
    for entry in record["entries"]:
        if entry.get("status") != "active":
            continue
        shown = dict(entry)
        try:
            shown["age_days"] = (
                today - date.fromisoformat(entry["created_at"])).days
        except (KeyError, ValueError):
            shown["age_days"] = None
        entries.append(shown)
    result = {
        "record_path": str(record_path),
        "record_version": record["version"],
        "record_sha256": record["record_sha256"],
        "entries": entries,
        "superseded_entries": sum(1 for e in record["entries"]
                                  if e.get("status") == "superseded"),
        "open_proposals": ProposalStore(db_path).list_open(),
    }
    if error:
        result["record_error"] = error
    return result


# --------------------------------------------------------------------------
# Phase 3: bounded influence — the record's only consumer (design §3.3)
# --------------------------------------------------------------------------

# Rule 1's band: a learned source_weight modulates the registry priority
# from inside [WEIGHT_MIN, WEIGHT_MAX], never outside it. The clamp lives
# here, at the single point of consumption, so a hand-edited record value
# of 3.0 is applied as 1.5 (and the clamp is what gets frozen + explained).
WEIGHT_MIN = 0.5
WEIGHT_MAX = 1.5


def learned_adjustments(record: dict) -> dict:
    """Pure: a loaded preference record -> per-source selection adjustments.

    Returns {source_id: {"weight": {"preference_id", "value"} | None,
                         "cap": {"preference_id", "value"} | None,
                         "pause": {"preference_id", "value", "created_at"} | None}}.

    Only active source_weight / source_cap / source_pause entries appear:
    topic_weight has no topic seam in selection and standing_note carries
    no scoring effect by design (§3.1), so neither is returned. Weights
    are clamped to [0.5, 1.5] HERE; caps are carried raw — the seam takes
    min(registry cap, learned cap), so a learned cap can only ever lower
    the registry value, never raise it. When several active entries share
    a kind+target, the later one in the record wins: the record is
    append-only history and the newest owner act is the current decision.
    """
    adjustments: dict[str, dict] = {}
    for entry in record.get("entries", []):
        if entry.get("status") != "active":
            continue
        kind = entry.get("kind")
        if kind not in ("source_weight", "source_cap", "source_pause"):
            continue
        slot = adjustments.setdefault(
            entry["target"], {"weight": None, "cap": None, "pause": None})
        if kind == "source_weight":
            value = min(WEIGHT_MAX, max(WEIGHT_MIN, float(entry["value"])))
            slot["weight"] = {"preference_id": entry["id"], "value": value}
        elif kind == "source_cap":
            slot["cap"] = {"preference_id": entry["id"],
                           "value": int(entry["value"])}
        else:
            slot["pause"] = {"preference_id": entry["id"], "value": True,
                             "created_at": entry.get("created_at")}
    return adjustments


def load_learned_adjustments(record_path=None):
    """Fail-closed loader for selection: (adjustments, error, record_version).

    A corrupted or unprovenanced record yields ZERO adjustments plus the
    error string — selection then proceeds exactly as it did before
    Phase 3, and the caller surfaces the error in the run record
    (design §6.8: a broken user model degrades to the pre-learning
    system, never to strange behavior).
    """
    record, error = safe_load_record(record_path or RECORD_PATH)
    if error:
        return {}, error, None
    return learned_adjustments(record), None, record.get("version")


def explain(content_id: str | None = None, daily_dir="data") -> dict:
    """Answer "why is this here, ranked here?" from the FROZEN record.

    Everything reported here was frozen at selection time: registry
    priority and cap from the run's frozen config, the gate decision and
    score from the episode item, and each learned factor the item
    carries (design §3.3 rule 3). The age component is recovered from
    the frozen score — score = priority × learned weight / (1 + age) —
    never recomputed from live state. An item frozen before Phase 3 has
    no learned_factors key; explain says so plainly instead of guessing
    that none applied.
    """
    if not content_id:
        return {"content_id": None, "found": False,
                "note": "Pass a content_id: explain reads the frozen "
                        "episode item recorded for that content."}
    db_file = Path(daily_dir) / "few.sqlite3"
    if not db_file.is_file():
        return {"content_id": content_id, "found": False,
                "note": f"No daily store at {db_file}: nothing has been "
                        "selected there, so no frozen record exists for "
                        "this item."}
    db = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        row = db.execute("""SELECT r.episode_date, r.config_json,
                e.channel_id, ei.unit_json, sr.report_json
            FROM episode_items ei
            JOIN episodes e USING(episode_id)
            JOIN runs r USING(run_id)
            LEFT JOIN stage_runs sr
                ON sr.run_id = r.run_id AND sr.stage = 'select'
            WHERE ei.content_id = ?
            ORDER BY r.episode_date DESC LIMIT 1""", (content_id,)).fetchone()
    finally:
        db.close()
    if row is None:
        return {"content_id": content_id, "found": False,
                "note": "No frozen episode item carries this content_id: "
                        "it was never selected (or predates the selection "
                        "records). No learned preference affected it."}
    unit = json.loads(row["unit_json"])
    try:
        cfg = json.loads(row["config_json"] or "{}")
    except json.JSONDecodeError:
        cfg = {}
    source_cfg = next((s for s in cfg.get("sources", [])
                       if s.get("source_id") == unit.get("source_id")), {})
    priority = source_cfg.get("priority", 1)
    factors = unit.get("learned_factors")
    factors_frozen = factors is not None
    factors = factors or []
    weight = 1.0
    for factor in factors:
        if factor.get("kind") == "source_weight":
            weight *= float(factor.get("value", 1.0))
    score = unit.get("score")
    age_days = None
    if isinstance(score, (int, float)) and score > 0 and priority:
        age_days = round(priority * weight / score - 1, 2)
    result = {
        "content_id": content_id,
        "found": True,
        "episode_date": row["episode_date"],
        "channel_id": row["channel_id"],
        "source": unit.get("source"),
        "source_id": unit.get("source_id"),
        "registry_priority": priority,
        "registry_cap": source_cfg.get("max_items_per_day"),
        "score": score,
        "age_days": age_days,
        "gate_priority": unit.get("gate_priority"),
        "learned_factors": factors,
        "factors_frozen": factors_frozen,
    }
    try:
        stage_report = json.loads(row["report_json"] or "{}")
    except (json.JSONDecodeError, TypeError):
        stage_report = {}
    record_error = (stage_report.get("learned") or {}).get("record_error")
    if record_error:
        result["record_error"] = record_error
    if not factors_frozen:
        if record_error:
            result["note"] = ("The preference record failed to load during "
                              "this item's selection run, so learned "
                              "preferences were applied not at all "
                              "(fail-closed); the error is in the run's "
                              "select report.")
        else:
            result["note"] = ("This item was frozen before Phase 3 wired "
                              "learned preferences into selection; no "
                              "learned-factor record exists for it, and none "
                              "can be reconstructed after the fact.")
    elif not factors:
        result["note"] = "No learned preferences affected this item."
    else:
        described = ", ".join(
            f"{f['preference_id']} ({f['kind']} "
            f"{'×' if f['kind'] == 'source_weight' else ''}{f['value']})"
            for f in factors)
        result["note"] = f"Learned preferences affected this item: {described}."
    return result


# --------------------------------------------------------------------------
# Phase 2 transport: ingest the reader's owner-carried reading summary
# --------------------------------------------------------------------------

READING_SUMMARY_FORMAT = "focu-reading-summary"
READING_SUMMARY_VERSION = 1
READER_STATUSES = {"consumed", "not_for_me", "in_progress"}


def _load_reading_summary(export_path):
    """Parse and validate the export envelope and every item BEFORE any
    write: a corrupt export is a clean error with nothing recorded."""
    path = Path(export_path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Reading summary cannot be read: {path} ({exc})") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Reading summary is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Reading summary must be a JSON object")
    if data.get("format") != READING_SUMMARY_FORMAT:
        raise ValueError(f"Reading summary format must be {READING_SUMMARY_FORMAT!r}, "
                         f"got {data.get('format')!r}")
    if data.get("version") != READING_SUMMARY_VERSION:
        raise ValueError(f"Reading summary version must be {READING_SUMMARY_VERSION}, "
                         f"got {data.get('version')!r}")
    if not isinstance(data.get("exported_at"), str) or not data["exported_at"].strip():
        raise ValueError("Reading summary lacks an exported_at timestamp")
    if not isinstance(data.get("items"), list):
        raise ValueError("Reading summary items must be a list")
    for index, item in enumerate(data["items"]):
        if not isinstance(item, dict):
            raise ValueError(f"Reading summary item {index} is not an object")
        content_id = item.get("content_id")
        if not isinstance(content_id, str) or not content_id.strip():
            raise ValueError(f"Reading summary item {index} lacks a content_id")
        if item.get("status") not in READER_STATUSES:
            raise ValueError(f"Reading summary item {content_id}: unknown status "
                             f"{item.get('status')!r}")
        covered = item.get("covered_content_ids")
        if covered is not None and (
                not isinstance(covered, list)
                or not all(isinstance(x, str) and x.strip() for x in covered)):
            raise ValueError(f"Reading summary item {content_id}: "
                             "covered_content_ids must be a list of content IDs")
    return data


def _reader_source(item):
    source = item.get("source")
    if isinstance(source, str) and source.strip():
        return source.strip()
    nfm = item.get("not_for_me")
    if isinstance(nfm, dict) and isinstance(nfm.get("source"), str):
        return nfm["source"].strip()
    return ""


# The publisher assigns this source label to every user_initiated item in
# the reader bundle (experiments/muse-artifact-reader/publish.py), and the
# marks record it at mark time — it is how the export identifies research.
RESEARCH_SOURCE_LABEL = "Your research"


def _covered_unit_ids(item):
    """The daily-unit content ids a compilation item covers, when the
    export carries them (additive v1 field, present only on compilations;
    absent or malformed yields no coverage)."""
    covered = item.get("covered_content_ids")
    if not isinstance(covered, list):
        return []
    return [x.strip() for x in covered if isinstance(x, str) and x.strip()]


def _is_research_item(item):
    """User-initiated research: no daily-unit coverage, and the publisher's
    research label as its source. Research items are keyed by intent ids
    in the research store, which the statistics never read, so their
    marks are out of scope for the proposal engine — ingest reports them
    (see ingest_reading_summary) and records nothing for them."""
    return (not _covered_unit_ids(item)
            and _reader_source(item) == RESEARCH_SOURCE_LABEL)


def _reader_event_id(item, signal, target_id=None):
    """Deterministic ledger id for one reader signal on one target.

    Dedupe basis (the reader format contract): target content_id +
    updated_at + signal class. Re-ingesting an export whose item state
    has not changed reproduces the same ids, so the second ingest
    records nothing new. When updated_at is absent, a fingerprint of the
    item's signal-bearing fields stands in, so identical state still
    dedupes. exported_at is deliberately NOT part of the basis: a
    fresher export of an unchanged state must not double-count.

    Fan-out events (a compilation's signal attributed to a covered unit)
    key on the covered unit's id with the compilation item's state
    basis, so re-ingesting an unchanged compilation reproduces the same
    per-unit ids — and a compilation state change yields a fresh set.
    """
    basis = item.get("updated_at")
    if not isinstance(basis, str) or not basis.strip():
        fingerprint = {key: item.get(key) for key in
                       ("status", "via", "source", "not_for_me", "useful", "audio")}
        basis = "fp:" + hashlib.sha256(
            json.dumps(fingerprint, sort_keys=True, default=str).encode()).hexdigest()
    else:
        basis = basis.strip()
    raw = f"{target_id or item['content_id']}|{basis}|{signal}"
    return "rs_" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def _reader_events(item):
    """One export item -> (ledger candidates, disposition).

    Each candidate carries "targets": the content ids its ledger events
    are recorded against — normally just the item itself.

    Mapping (Phase 2, honest semantics):
      not_for_me            -> observation / not_useful: the unambiguous
                               negative signal the design requires.
      consumed, via!=manual -> observation / other: a completion record
                               with via preserved in the note. Kind
                               "other" is inert in Phase-1 statistics,
                               which count only negative and useful
                               kinds; the record exists for later phases.
      consumed, via=manual  -> nothing: the reader's Archive act
                               conflates done and dismissed, so a manual
                               archive must not become consumption
                               evidence (the design's exclusion).
      in_progress           -> nothing: a saved position is not evidence.
      useful (any status)   -> observation / useful: the owner's own
                               mark, the only promotion evidence the
                               Phase-1 engine counts.

    Compilation fan-out (PM sweep F1): an item with covered_content_ids
    is a compiled daily briefing, and its candidates target the covered
    units instead — one event per covered unit, the note recording the
    compilation it came via. A mark on a briefing is weak evidence
    about each covered source (the owner rejected or endorsed the
    bundle, not necessarily every item in it), but it is real evidence,
    and the proposal engine's floors (>=10 delivered, >=3 events,
    >=20%) already gate weak signals, so attribution is full rather
    than fractional. Without the fan-out the signal was lost entirely:
    _attribute_feedback joins on unit content ids, and a compilation
    id is never a unit id, so every briefing mark — the owner's main
    surface — landed in unattributed_feedback.

    Research items (user_initiated) are out of scope: their candidates
    are still computed (so the ingest report can count the signals)
    but returned with disposition "research_out_of_scope", and ingest
    records nothing for them. Their content ids are intent ids in the
    research store, which the statistics never read; recording them
    would only pollute unattributed_feedback and make the real leak
    indistinguishable from this deliberate exclusion.
    """
    source = _reader_source(item)
    status = item["status"]
    candidates = []
    disposition = status
    if status == "not_for_me":
        nfm = item.get("not_for_me") if isinstance(item.get("not_for_me"), dict) else {}
        note = "reader not_for_me"
        if source:
            note += f"; source: {source}"
        at = nfm.get("at")
        if isinstance(at, str) and at.strip():
            note += f"; marked at {at.strip()}"
        candidates.append({"signal": "not_useful", "kind": "not_useful", "note": note})
    elif status == "consumed":
        via = item.get("via")
        if via == "manual":
            disposition = "manual_excluded"
        else:
            note = "reader completion; via: " + (
                via if isinstance(via, str) and via else "unknown")
            if source:
                note += f"; source: {source}"
            audio = item.get("audio")
            if isinstance(audio, str) and audio:
                note += f"; audio: {audio}"
            candidates.append({"signal": "completed", "kind": "other", "note": note})
    if item.get("useful"):
        note = "reader useful mark"
        if source:
            note += f"; source: {source}"
        useful = item["useful"]
        if isinstance(useful, dict):
            at = useful.get("at")
            if isinstance(at, str) and at.strip():
                note += f"; marked at {at.strip()}"
        candidates.append({"signal": "useful", "kind": "useful", "note": note})
    covered = _covered_unit_ids(item)
    for cand in candidates:
        if covered:
            cand["targets"] = covered
            cand["note"] += f"; via compilation {item['content_id']}"
        else:
            cand["targets"] = [item["content_id"]]
    if _is_research_item(item):
        disposition = "research_out_of_scope"
    return candidates, disposition


def ingest_reading_summary(export_path, db_path="data/focu.sqlite3") -> dict:
    """Import a reader reading-summary export into the feedback ledger.

    The export reaches the VM only because the owner carried it (the
    reader's sole transport). Ingest writes ONLY to the feedback ledger;
    the preference record is never touched here. Idempotent by
    content_id + updated_at (see _reader_event_id): an item whose state
    has not changed since a previous ingest produces no new events.

    Compilation items fan out: their signals are recorded once per
    covered unit, so the statistics can attribute them to the covered
    units' sources. Research items are out of scope and record nothing;
    the report counts them (and their would-be signals) separately, so
    the exclusion is visible rather than silent.
    """
    data = _load_reading_summary(export_path)
    store = FeedbackStore(db_path)
    existing = {event["id"]: event for event in store.list()}
    recorded = already = 0
    by_kind: dict[str, int] = {}
    skipped_in_progress = 0
    excluded_manual = 0
    fanned_out = 0
    out_of_scope_items = 0
    out_of_scope_signals = 0
    conflicts = []
    for item in data["items"]:
        candidates, disposition = _reader_events(item)
        if disposition == "in_progress":
            skipped_in_progress += 1
        elif disposition == "manual_excluded":
            excluded_manual += 1
        elif disposition == "research_out_of_scope":
            out_of_scope_items += 1
            out_of_scope_signals += len(candidates)
            continue
        if candidates and _covered_unit_ids(item):
            fanned_out += 1
        for cand in candidates:
            for target_id in cand["targets"]:
                event_id = _reader_event_id(item, cand["signal"], target_id)
                prior = existing.get(event_id)
                if prior is not None:
                    if (prior["target_type"] == "observation"
                            and prior["target_id"] == target_id
                            and prior["kind"] == cand["kind"]
                            and prior["note"] == cand["note"]):
                        already += 1
                    else:
                        conflicts.append(target_id)
                    continue
                event = store.record(target_type="observation",
                                     target_id=target_id,
                                     kind=cand["kind"], note=cand["note"],
                                     event_id=event_id)
                existing[event_id] = event
                recorded += 1
                by_kind[cand["kind"]] = by_kind.get(cand["kind"], 0) + 1
    return {
        "format": data["format"], "version": data["version"],
        "exported_at": data["exported_at"],
        "items": len(data["items"]),
        "events_recorded": recorded,
        "events_already_recorded": already,
        "events_by_kind": by_kind,
        "skipped_in_progress": skipped_in_progress,
        "excluded_manual_archives": excluded_manual,
        "fanned_out_compilations": fanned_out,
        "out_of_scope_research_items": out_of_scope_items,
        "out_of_scope_research_signals": out_of_scope_signals,
        "conflicts": conflicts,
        "notes": [
            "in_progress items record no events in Phase 2: a saved position is not evidence.",
            "Manual archives (via=manual) record no completion: the reader's Archive act conflates done and dismissed.",
            "Compilation (daily briefing) signals are fanned out to the units the briefing covered, one event per covered unit, so they attribute to those units' sources; a briefing mark is weak per-source evidence, gated by the proposal floors.",
            "Research-item marks are out of scope, not unattributed: research lives in the research store, which the learning statistics never read, so ingest records nothing for them and counts them above.",
            "Ingest writes only to the feedback ledger; the preference record is untouched.",
        ],
    }


# --------------------------------------------------------------------------
# CLI: focu learn show / proposals / accept / dismiss / explain / ingest
# --------------------------------------------------------------------------

def _parse_value(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def main(argv: list[str] | None = None, db_path: str | None = None) -> int:
    import argparse
    import sys
    parser = argparse.ArgumentParser(
        prog="focu learn",
        description="Owner-approved learning loop: evidenced proposals, "
                    "a preference record only owner acts can write")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=None,
                        help="Feedback/proposals SQLite DB (default: focu --db)")
    common.add_argument("--daily-dir", default="data",
                        help="Daily pipeline data dir holding few.sqlite3")
    common.add_argument("--record", default=str(RECORD_PATH),
                        help="Learned-preference record (markdown)")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("show", parents=[common],
                   help="Print the preference record and open proposals")
    sub.add_parser("proposals", parents=[common],
                   help="Run a proposal batch and list what it drafted")
    accept = sub.add_parser("accept", parents=[common],
                            help="Accept a proposal (writes one record entry)")
    accept.add_argument("proposal_id")
    accept.add_argument("--value", default=None,
                        help="Edited value (JSON) to record instead of the proposed one")
    dismiss = sub.add_parser("dismiss", parents=[common],
                             help="Dismiss a proposal and snooze its class+target")
    dismiss.add_argument("proposal_id")
    dismiss.add_argument("--never", action="store_true",
                         help="Exempt this target from this proposal class permanently")
    explain_cmd = sub.add_parser("explain", parents=[common],
                                 help="Why an item was selected, answered "
                                      "from its frozen selection record")
    explain_cmd.add_argument("content_id", nargs="?")
    ingest = sub.add_parser("ingest", parents=[common],
                            help="Import a reader reading-summary export "
                                 "into the feedback ledger (idempotent)")
    ingest.add_argument("export", help="Path to focu-reading-summary.json")
    args = parser.parse_args(argv)
    db = args.db or db_path or "data/focu.sqlite3"
    try:
        if args.action == "show":
            result = show(db, args.record)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1 if "record_error" in result else 0
        if args.action == "proposals":
            result = generate_proposals(db, args.daily_dir, args.record)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.action == "accept":
            value = _parse_value(args.value) if args.value is not None else None
            result = accept_proposal(args.proposal_id, db, args.record, value=value)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.action == "dismiss":
            result = dismiss_proposal(args.proposal_id, db, never=args.never)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.action == "explain":
            print(json.dumps(explain(args.content_id, args.daily_dir),
                             ensure_ascii=False, indent=2))
            return 0
        if args.action == "ingest":
            result = ingest_reading_summary(args.export, db)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        return 2
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
