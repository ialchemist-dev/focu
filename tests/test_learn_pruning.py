"""Pruning proposals: source_pause drafted from completion-rate evidence.

Backlog P2 residual: the proposal engine drafted source_weight
proposals only; the source_pause class was designed (learning-design
§3.1/§3.3, PRD P2-1) but not generated, pending Phase-2 completion-rate
evidence. That evidence now exists (ingest records attributed
completions as ledger kind "other"; PM sweep F1 fixed compilation
attribution), so this file pins the generation rule:

(1) compute_statistics surfaces completed + completion_rate per source;
(2) a source with >= PAUSE_MIN_DELIVERED delivered over >=
    PAUSE_MIN_DAYS distinct days, zero completions and zero useful
    marks earns exactly one source_pause proposal (value True) whose
    evidence names the window and n;
(3) silence otherwise: a burst (few days), a below-floor source, any
    completion, or any useful mark each veto the proposal;
(4) a source qualifying for a statistics demotion gets the demotion,
    not a pause, in the same batch;
(5) accepting the pause proposal writes one owner-accepted
    source_pause entry that learned_adjustments honors; dismissing it
    snoozes the pause class for 60 days (design §2.3).
"""
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
    """plan: {source_id: (name, [(day_offset, count), ...])} — same
    fixture builder as tests/test_learn.py, duplicated so this file
    runs standalone as well as under discovery."""
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
    FeedbackStore(db_path)
    db = sqlite3.connect(db_path)
    for i, (target_type, target_id, kind, age) in enumerate(events):
        created = (now - timedelta(days=age)).isoformat()
        db.execute("INSERT INTO feedback_events VALUES (?,?,?,?,?,?)",
                   (f"fb_fix{i}_{target_id}_{kind}", target_type, target_id,
                    kind, "", created))
    db.commit()
    db.close()


# 20 items over 10 distinct days: sustained delivery at the pause floor.
SUSTAINED = [(offset, 2) for offset in (1, 4, 7, 10, 13, 16, 19, 22, 25, 28)]


class PruningProposalTests(unittest.TestCase):
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

    def test_statistics_surface_completion_rate(self):
        ids = seed_daily(self.daily_dir, {"src_alpha": ("Alpha", SUSTAINED)})
        seed_feedback(self.db, [("observation", cid, "other", 2)
                                for cid in ids["src_alpha"][:5]])
        stats = learn.compute_statistics(self.db, self.daily_dir, BASE_NOW)
        slot = stats["sources"]["src_alpha"]
        self.assertEqual(slot["delivered"], 20)
        self.assertEqual(slot["days"], 10)
        self.assertEqual(slot["completed"], 5)
        self.assertEqual(slot["completion_rate"], 0.25)

    def test_sustained_zero_completion_proposes_pause(self):
        seed_daily(self.daily_dir, {"src_dead": ("Dead Wire", SUSTAINED)})
        result = self.generate()
        self.assertEqual(len(result["proposals"]), 1)
        proposal = result["proposals"][0]
        self.assertEqual(proposal["kind"], "source_pause")
        self.assertEqual(proposal["target"], "src_dead")
        self.assertIs(proposal["value"], True)
        self.assertIn("0 of 20 items completed", proposal["evidence"])
        self.assertIn("10 delivery days", proposal["evidence"])
        self.assertIn("n=20", proposal["evidence"])
        self.assertIn("Pause Dead Wire", proposal["statement"])

    def test_burst_delivery_is_not_sustained(self):
        # Same volume, three days: a burst is a sample, not a pattern.
        seed_daily(self.daily_dir,
                   {"src_burst": ("Burst", [(1, 8), (2, 6), (3, 6)])})
        self.assertEqual(self.generate()["proposals"], [])

    def test_below_pause_floor_stays_silent(self):
        # Above the weight floor (10) but below the pause floor (20),
        # spread thin: absence at this n proposes nothing.
        seed_daily(self.daily_dir,
                   {"src_thin": ("Thin", [(offset, 1) for offset in range(1, 13)])})
        self.assertEqual(self.generate()["proposals"], [])

    def test_any_completion_vetoes_pause(self):
        ids = seed_daily(self.daily_dir, {"src_alpha": ("Alpha", SUSTAINED)})
        seed_feedback(self.db, [("observation", ids["src_alpha"][0], "other", 2)])
        self.assertEqual(self.generate()["proposals"], [])

    def test_any_useful_mark_vetoes_pause(self):
        ids = seed_daily(self.daily_dir, {"src_alpha": ("Alpha", SUSTAINED)})
        seed_feedback(self.db, [("observation", ids["src_alpha"][0], "useful", 2)])
        self.assertEqual(self.generate()["proposals"], [])

    def test_demotion_takes_precedence_over_pause(self):
        ids = seed_daily(self.daily_dir, {"src_alpha": ("Alpha", SUSTAINED)})
        seed_feedback(self.db, [("observation", cid, "not_useful", 2)
                                for cid in ids["src_alpha"][:5]])
        result = self.generate()
        self.assertEqual(len(result["proposals"]), 1)
        self.assertEqual(result["proposals"][0]["kind"], "source_weight")
        self.assertEqual(result["proposals"][0]["value"], learn.DEMOTE_WEIGHT)

    def test_accepted_pause_writes_pause_entry_and_adjustment(self):
        seed_daily(self.daily_dir, {"src_dead": ("Dead Wire", SUSTAINED)})
        proposal = self.generate()["proposals"][0]
        result = learn.accept_proposal(proposal["id"], self.db, self.record,
                                       now=BASE_NOW)
        entry = result["entry"]
        self.assertEqual(entry["kind"], "source_pause")
        self.assertIs(entry["value"], True)
        self.assertEqual(entry["provenance"], "owner-accepted")
        record = learn.load_record(self.record)
        adjustments = learn.learned_adjustments(record)
        self.assertIn("src_dead", adjustments)
        self.assertIsNotNone(adjustments["src_dead"]["pause"])

    def test_pause_dismissal_snoozes_sixty_days(self):
        seed_daily(self.daily_dir, {"src_dead": ("Dead Wire", SUSTAINED)})
        proposal = self.generate()["proposals"][0]
        result = learn.dismiss_proposal(proposal["id"], self.db, now=BASE_NOW)
        self.assertEqual(result["snooze_until"],
                         (BASE_NOW.date() + timedelta(days=60)).isoformat())
        self.assertEqual(learn.load_record(self.record)["entries"], [])


if __name__ == "__main__":
    unittest.main()
