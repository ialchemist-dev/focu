import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from focu import learn
from focu.daily.store import Store as DailyStore
from focu.feedback import FeedbackStore

BASE_NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)

VALID_ENTRY = """  - id: lp-001
    kind: source_weight
    target: src_alpha
    value: 0.7
    statement: "Set selection weight to 0.7× for Alpha."
    provenance: owner-accepted
    evidence: "prop-20261117-1 · 4 of 12 items drew negative feedback, 30d window, n=12 delivered"
    created_at: 2026-11-17
    review_after: 2027-02-15
    status: active
"""


def record_text(entries_block="[]", version="2026-11-17.1"):
    if entries_block == "[]":
        entries_yaml = "entries: []"
    else:
        entries_yaml = "entries:\n" + entries_block
    return f"""# Focu learned preferences

**Version:** {version}
**Owner:** one person (Focu's owner)
**Change discipline:** written only by owner acts.

```yaml
version: "{version}"
{entries_yaml}
```

## Changelog

- **2026-11-17 — v2026-11-17.1:** Record created.
"""


def seed_daily(daily_dir, plan, now=BASE_NOW):
    """plan: {source_id: (name, [(day_offset, count), ...])}.

    Builds real runs/episodes/episode_items rows against the daily schema;
    items sharing a day share one episode (channel 'research'), as in
    production. Returns {source_id: [content_id, ...]}.
    """
    DailyStore(daily_dir).close()
    db = sqlite3.connect(Path(daily_dir) / "few.sqlite3")
    by_day = {}
    for source_id, (name, days) in plan.items():
        for offset, count in days:
            day = (now.date() - timedelta(days=offset)).isoformat()
            by_day.setdefault(day, []).append((source_id, name, count))
    content_ids = {}
    for day, entries in sorted(by_day.items()):
        run_id, ep_id = f"run_fix_{day}", f"ep_fix_{day}"
        db.execute("INSERT INTO runs VALUES (?,?,?,?,'audio','finalized',?)",
                   (run_id, day, "hash", "{}", now.isoformat()))
        db.execute("""INSERT INTO episodes (episode_id, run_id, channel_id, status)
                      VALUES (?,?,'research','finalized')""", (ep_id, run_id))
        pos = 0
        for source_id, name, count in entries:
            for i in range(count):
                cid = f"cnt_{source_id}_{day}_{i}"
                unit = {"source_id": source_id, "source": name, "content_id": cid,
                        "title": f"Item {i}", "score": 1.0, "gate_priority": "normal"}
                db.execute("INSERT INTO episode_items VALUES (?,?,?,?,?)",
                           (ep_id, cid, f"rev_{cid}", pos, json.dumps(unit)))
                pos += 1
                content_ids.setdefault(source_id, []).append(cid)
    db.commit()
    db.close()
    return content_ids


def seed_feedback(db_path, events, now=BASE_NOW):
    """events: [(target_type, target_id, kind, age_days)] — direct inserts so
    fixtures control created_at (FeedbackStore.record stamps real time)."""
    FeedbackStore(db_path)
    db = sqlite3.connect(db_path)
    for i, (target_type, target_id, kind, age) in enumerate(events):
        created = (now - timedelta(days=age)).isoformat()
        db.execute("INSERT INTO feedback_events VALUES (?,?,?,?,?,?)",
                   (f"fb_fix{i}_{target_id}_{kind}", target_type, target_id,
                    kind, "", created))
    db.commit()
    db.close()


def negative_events(content_ids, kinds=("not_useful", "not_useful", "not_useful", "too_long")):
    return [("observation", cid, kind, 2) for cid, kind in zip(content_ids, kinds)]


class RecordLoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.record = Path(self.temp.name) / "learned-preferences.md"

    def write(self, text):
        self.record.write_text(text, encoding="utf-8")
        return self.record

    def test_shipped_record_is_valid_and_empty(self):
        data = learn.load_record(learn.RECORD_PATH)
        self.assertEqual(data["entries"], [])
        self.assertTrue(data["version"])
        self.assertEqual(len(data["record_sha256"]), 64)

    def test_valid_entries_load_with_dates_normalized(self):
        self.write(record_text(VALID_ENTRY))
        data = learn.load_record(self.record)
        self.assertEqual(len(data["entries"]), 1)
        entry = data["entries"][0]
        self.assertEqual(entry["created_at"], "2026-11-17")
        self.assertEqual(entry["provenance"], "owner-accepted")

    def test_rejects_unprovenanced_entry(self):
        self.write(record_text(VALID_ENTRY.replace("owner-accepted", "inferred")))
        with self.assertRaises(ValueError):
            learn.load_record(self.record)

    def test_rejects_missing_provenance(self):
        self.write(record_text(VALID_ENTRY.replace("    provenance: owner-accepted\n", "")))
        with self.assertRaises(ValueError):
            learn.load_record(self.record)

    def test_rejects_unknown_kind_and_bad_values(self):
        self.write(record_text(VALID_ENTRY.replace("source_weight", "source_ban")))
        with self.assertRaises(ValueError):
            learn.load_record(self.record)
        self.write(record_text(VALID_ENTRY.replace("value: 0.7", "value: -1")))
        with self.assertRaises(ValueError):
            learn.load_record(self.record)

    def test_rejects_duplicate_ids(self):
        second = VALID_ENTRY.replace("lp-001", "lp-001").replace("src_alpha", "src_beta")
        self.write(record_text(VALID_ENTRY + second))
        with self.assertRaises(ValueError):
            learn.load_record(self.record)

    def test_corrupt_record_fails_closed(self):
        self.write("# no yaml block here\n")
        with self.assertRaises(ValueError):
            learn.load_record(self.record)
        record, error = learn.safe_load_record(self.record)
        self.assertEqual(record["entries"], [])
        self.assertIsNotNone(error)
        self.write(record_text("").replace('version: "2026-11-17.1"', "version: [unclosed"))
        record, error = learn.safe_load_record(self.record)
        self.assertEqual(record["entries"], [])
        self.assertIsNotNone(error)


class ProposalEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db = root / "focu.sqlite3"
        self.daily_dir = root / "daily"
        self.record = root / "learned-preferences.md"
        self.record.write_text(record_text(), encoding="utf-8")

    def generate(self, now=BASE_NOW):
        return learn.generate_proposals(self.db, self.daily_dir, self.record, now=now)

    def test_empty_history_produces_zero_proposals(self):
        result = self.generate()
        self.assertEqual(result["proposals"], [])
        self.assertEqual(result["sources_considered"], 0)

    def test_demotion_proposal_carries_evidence(self):
        ids = seed_daily(self.daily_dir,
                         {"src_alpha": ("Alpha", [(1, 4), (8, 4), (15, 4)])})
        seed_feedback(self.db, negative_events(ids["src_alpha"]))
        result = self.generate()
        self.assertEqual(len(result["proposals"]), 1)
        proposal = result["proposals"][0]
        self.assertEqual(proposal["kind"], "source_weight")
        self.assertEqual(proposal["target"], "src_alpha")
        self.assertEqual(proposal["value"], learn.DEMOTE_WEIGHT)
        self.assertLess(proposal["value"], 1.0)
        self.assertIn("30d window", proposal["evidence"])
        self.assertIn("n=12", proposal["evidence"])
        self.assertIn("Alpha", proposal["statement"])

    def test_promotion_only_from_useful_marks(self):
        ids = seed_daily(self.daily_dir, {
            "src_beta": ("Beta", [(1, 4), (8, 4), (15, 4)]),
            "src_quiet": ("Quiet", [(1, 4), (8, 4), (15, 4)]),
        })
        # One attributed completion on the quiet source brings the
        # window total to MIN_ATTRIBUTED_EVENTS (wave 25 stop rule):
        # the promotion below still rests on useful marks alone — a
        # completion promotes nobody, and the quiet source gets none.
        events = [("observation", cid, "useful", 2)
                  for cid in ids["src_beta"][:3]]
        events.append(("observation", ids["src_quiet"][0], "other", 2))
        seed_feedback(self.db, events)
        result = self.generate()
        self.assertEqual(len(result["proposals"]), 1)
        proposal = result["proposals"][0]
        self.assertEqual(proposal["target"], "src_beta")
        self.assertEqual(proposal["value"], learn.PROMOTE_WEIGHT)
        self.assertIn("useful", proposal["evidence"])

    def test_below_evidence_floor_stays_silent(self):
        ids = seed_daily(self.daily_dir, {"src_small": ("Small", [(1, 5)])})
        seed_feedback(self.db, negative_events(ids["src_small"][:4]))
        result = self.generate()
        self.assertEqual(result["proposals"], [])
        self.assertGreaterEqual(result["sources_below_evidence_floor"], 1)

    def test_negative_rate_floor(self):
        ids = seed_daily(self.daily_dir, {"src_big": ("Big", [(1, 10), (8, 10)])})
        seed_feedback(self.db, negative_events(ids["src_big"][:3],
                                               kinds=("not_useful",) * 3))
        result = self.generate()
        self.assertEqual(result["proposals"], [])

    def test_three_proposal_cap(self):
        plan = {f"src_{i}": (f"Source {i}", [(1, 4), (8, 4), (15, 4)])
                for i in range(5)}
        ids = seed_daily(self.daily_dir, plan)
        events = []
        for source_id in plan:
            events.extend(negative_events(ids[source_id]))
        seed_feedback(self.db, events)
        result = self.generate()
        self.assertEqual(len(result["proposals"]), 3)
        self.assertEqual(len(learn.ProposalStore(self.db).list_open()), 3)

    def test_episode_feedback_attribution(self):
        ids = seed_daily(self.daily_dir, {
            "src_alpha": ("Alpha", [(1, 4), (8, 4), (15, 4)]),
            "src_beta": ("Beta", [(8, 4)]),
        })
        solo_day = (BASE_NOW.date() - timedelta(days=1)).isoformat()
        mixed_day = (BASE_NOW.date() - timedelta(days=8)).isoformat()
        seed_feedback(self.db, [
            ("episode", f"{solo_day}/research", "not_useful", 1),
            ("episode", f"{mixed_day}/research", "not_useful", 8),
        ])
        stats = learn.compute_statistics(self.db, self.daily_dir, BASE_NOW)
        self.assertEqual(stats["sources"]["src_alpha"]["negative_total"], 1)
        self.assertEqual(stats["sources"]["src_beta"]["negative_total"], 0)
        self.assertEqual(stats["unattributed_feedback"], 1)


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db = root / "focu.sqlite3"
        self.daily_dir = root / "daily"
        self.record = root / "learned-preferences.md"
        self.record.write_text(record_text(), encoding="utf-8")

    def make_proposal(self, now=BASE_NOW, source="src_alpha", name="Alpha"):
        ids = seed_daily(self.daily_dir, {source: (name, [(1, 4), (8, 4), (15, 4)])},
                         now=now)
        seed_feedback(self.db, negative_events(ids[source]), now=now)
        result = learn.generate_proposals(self.db, self.daily_dir, self.record, now=now)
        self.assertEqual(len(result["proposals"]), 1)
        return result["proposals"][0]

    def test_accept_writes_exactly_one_provenanced_entry(self):
        proposal = self.make_proposal()
        before = learn.load_record(self.record)
        result = learn.accept_proposal(proposal["id"], self.db, self.record, now=BASE_NOW)
        after = learn.load_record(self.record)
        self.assertEqual(len(before["entries"]), 0)
        self.assertEqual(len(after["entries"]), 1)
        entry = after["entries"][0]
        self.assertEqual(entry["provenance"], "owner-accepted")
        self.assertEqual(entry["value"], learn.DEMOTE_WEIGHT)
        self.assertTrue(entry["evidence"].startswith(proposal["id"]))
        self.assertEqual(entry["id"], "lp-001")
        self.assertEqual(result["record_version"], "2026-11-17.2")
        self.assertIn(f"accepted {proposal['id']}",
                      self.record.read_text(encoding="utf-8"))
        self.assertEqual(learn.ProposalStore(self.db).get(proposal["id"])["state"],
                         "accepted")
        with self.assertRaises(ValueError):
            learn.accept_proposal(proposal["id"], self.db, self.record, now=BASE_NOW)

    def test_accept_with_edited_value(self):
        proposal = self.make_proposal()
        result = learn.accept_proposal(proposal["id"], self.db, self.record,
                                       value=0.8, now=BASE_NOW)
        self.assertEqual(result["entry"]["value"], 0.8)
        self.assertEqual(result["proposal"]["state"], "edited-accepted")
        self.assertIn("edited", result["entry"]["evidence"])

    def test_dismiss_writes_nothing_to_the_record(self):
        proposal = self.make_proposal()
        before = self.record.read_bytes()
        result = learn.dismiss_proposal(proposal["id"], self.db, now=BASE_NOW)
        self.assertEqual(self.record.read_bytes(), before)
        self.assertEqual(result["state"], "dismissed")
        self.assertEqual(result["snooze_until"],
                         (BASE_NOW.date() + timedelta(days=30)).isoformat())

    def test_snooze_blocks_reproposal_until_it_lapses(self):
        proposal = self.make_proposal()
        learn.dismiss_proposal(proposal["id"], self.db, now=BASE_NOW)
        day29 = BASE_NOW + timedelta(days=29)
        ids = seed_daily(self.daily_dir,
                         {"src_alpha": ("Alpha", [(1, 4), (8, 4), (15, 4)])}, now=day29)
        seed_feedback(self.db, negative_events(ids["src_alpha"]), now=day29)
        result = learn.generate_proposals(self.db, self.daily_dir, self.record, now=day29)
        self.assertEqual(result["proposals"], [])
        day30 = BASE_NOW + timedelta(days=30)
        ids = seed_daily(self.daily_dir,
                         {"src_alpha": ("Alpha", [(1, 4), (8, 4), (15, 4)])}, now=day30)
        seed_feedback(self.db, negative_events(ids["src_alpha"]), now=day30)
        result = learn.generate_proposals(self.db, self.daily_dir, self.record, now=day30)
        self.assertEqual(len(result["proposals"]), 1)

    def test_never_dismissal_is_permanent(self):
        proposal = self.make_proposal()
        learn.dismiss_proposal(proposal["id"], self.db, never=True, now=BASE_NOW)
        later = BASE_NOW + timedelta(days=365)
        ids = seed_daily(self.daily_dir,
                         {"src_alpha": ("Alpha", [(1, 4), (8, 4), (15, 4)])}, now=later)
        seed_feedback(self.db, negative_events(ids["src_alpha"]), now=later)
        result = learn.generate_proposals(self.db, self.daily_dir, self.record, now=later)
        self.assertEqual(result["proposals"], [])

    def test_accepted_entry_suppresses_reproposal(self):
        proposal = self.make_proposal()
        learn.accept_proposal(proposal["id"], self.db, self.record, now=BASE_NOW)
        later = BASE_NOW + timedelta(days=40)
        ids = seed_daily(self.daily_dir,
                         {"src_alpha": ("Alpha", [(1, 4), (8, 4), (15, 4)])}, now=later)
        seed_feedback(self.db, negative_events(ids["src_alpha"]), now=later)
        result = learn.generate_proposals(self.db, self.daily_dir, self.record, now=later)
        self.assertEqual(result["proposals"], [])


class OnlyWriterTests(unittest.TestCase):
    def test_accept_path_is_the_only_record_writer(self):
        package = Path(learn.__file__).resolve().parent
        offenders = []
        for path in package.rglob("*.py"):
            if path.name == "learn.py":
                continue
            text = path.read_text(encoding="utf-8")
            if "learned-preferences" in text or "_write_record" in text:
                offenders.append(str(path))
        self.assertEqual(offenders, [])
        source = Path(learn.__file__).read_text(encoding="utf-8")
        # One definition plus exactly one call site: accept_proposal.
        self.assertEqual(source.count("_write_record("), 2)
        accept_body = source.split("def accept_proposal", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("_write_record(", accept_body)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db = root / "focu.sqlite3"
        self.daily_dir = root / "daily"
        self.record = root / "learned-preferences.md"
        self.record.write_text(record_text(), encoding="utf-8")

    def args(self, action):
        return [action, "--db", str(self.db), "--daily-dir", str(self.daily_dir),
                "--record", str(self.record)]

    def test_learn_cli_show_proposals_explain(self):
        self.assertEqual(learn.main(self.args("show")), 0)
        self.assertEqual(learn.main(self.args("proposals")), 0)
        self.assertEqual(learn.main(["explain", "cnt_x", "--db", str(self.db)]), 0)

    def test_top_level_cli_dispatch(self):
        from focu.cli import main as cli_main
        code = cli_main(["--db", str(self.db), "learn", "show",
                         "--record", str(self.record),
                         "--daily-dir", str(self.daily_dir)])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
