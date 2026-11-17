"""PM sweep F5: renewal + long-pause review proposals, the explicit
90-day step rule, and entry ages in `focu learn show`.

Acceptance (team/pm-sweep-2.md, Finding F5):
(1) generate_proposals emits a renewal proposal for an active entry
    past its review_after, carrying current evidence (delivered /
    completion since the entry was created), within the <=3 budget;
(2) a source paused >90 days yields at most one restore/keep/remove
    (pause_review) proposal per quarter;
(3) re-proposal of a kind+target whose last accepted step is <90 days
    old is suppressed even when the earlier entry was superseded;
(4) `focu learn show` prints each active entry's age in days;
(5) renewal acceptance refreshes review_after in place — never a
    duplicate append, never a supersede.
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


def negative_events(content_ids, kinds=("not_useful", "not_useful", "not_useful", "too_long")):
    return [("observation", cid, kind, 2) for cid, kind in zip(content_ids, kinds)]

WEIGHT_ENTRY = """  - id: lp-001
    kind: source_weight
    target: src_alpha
    value: 0.7
    statement: "Set selection weight to 0.7× for Alpha."
    provenance: owner-accepted
    evidence: "prop-20260801-1 · fixture evidence"
    created_at: 2026-08-01
    review_after: 2026-10-30
    status: active
"""

PAUSE_ENTRY = """  - id: lp-002
    kind: source_pause
    target: src_beta
    value: true
    statement: "Pause Beta."
    provenance: owner-accepted
    evidence: "prop-20260801-2 · fixture evidence"
    created_at: 2026-08-01
    review_after: 2026-10-30
    status: active
"""


class ReviewFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db = root / "focu.sqlite3"
        self.daily_dir = root / "daily"
        self.record = root / "learned-preferences.md"

    def write_record(self, entries_block):
        self.record.write_text(record_text(entries_block), encoding="utf-8")

    def generate(self, now=BASE_NOW):
        return learn.generate_proposals(self.db, self.daily_dir, self.record, now=now)


class RenewalProposalTests(ReviewFixture):
    def test_renewal_emitted_past_review_after_with_current_evidence(self):
        self.write_record(WEIGHT_ENTRY)
        ids = seed_daily(self.daily_dir,
                         {"src_alpha": ("Alpha", [(1, 4), (8, 4), (15, 4)])})
        # One completion (kind "other") since the entry was created.
        seed_feedback(self.db, [("observation", ids["src_alpha"][0], "other", 2)])
        result = self.generate()
        self.assertEqual(len(result["proposals"]), 1)
        proposal = result["proposals"][0]
        self.assertEqual(proposal["kind"], "renewal")
        self.assertEqual(proposal["target"], "src_alpha")
        self.assertEqual(proposal["value"], "lp-001")
        self.assertIn("108d old", proposal["evidence"])
        self.assertIn("12 items delivered", proposal["evidence"])
        self.assertIn("1 completion(s)", proposal["evidence"])
        self.assertIn("lp-001", proposal["statement"])

    def test_no_renewal_before_review_after(self):
        self.write_record(WEIGHT_ENTRY.replace("2026-10-30", "2027-02-15"))
        result = self.generate()
        self.assertEqual(result["proposals"], [])

    def test_renewal_competes_inside_the_three_proposal_budget(self):
        self.write_record(WEIGHT_ENTRY)
        plan = {f"src_{i}": (f"Source {i}", [(1, 4), (8, 4), (15, 4)])
                for i in range(4)}
        ids = seed_daily(self.daily_dir, plan)
        events = []
        for source_id in plan:
            events.extend(negative_events(ids[source_id]))
        seed_feedback(self.db, events)
        result = self.generate()
        self.assertEqual(len(result["proposals"]), 3)
        self.assertEqual(result["proposals"][0]["kind"], "renewal")

    def test_renewal_statement_states_never_semantics(self):
        # The proposal text itself must say what a 'never' dismissal
        # does and does not do: the question retires, the entry stays
        # active until the owner edits the record by hand.
        self.write_record(WEIGHT_ENTRY)
        proposal = self.generate()["proposals"][0]
        self.assertIn("'never'", proposal["statement"])
        self.assertIn("stays active", proposal["statement"])
        self.assertIn("by hand", proposal["statement"])

    def test_expired_renewal_is_not_reasked_inside_30_days(self):
        self.write_record(WEIGHT_ENTRY)
        first = self.generate()
        self.assertEqual(len(first["proposals"]), 1)
        # Next batch expires the open proposal; the entry is still past
        # review_after, but the question was asked 10 days ago.
        result = self.generate(now=BASE_NOW + timedelta(days=10))
        self.assertEqual(result["proposals"], [])
        # After the 30-day repropose window it may be asked again.
        result = self.generate(now=BASE_NOW + timedelta(days=31))
        self.assertEqual(len(result["proposals"]), 1)
        self.assertEqual(result["proposals"][0]["kind"], "renewal")


class RenewalAcceptanceTests(ReviewFixture):
    def make_renewal(self):
        self.write_record(WEIGHT_ENTRY)
        result = self.generate()
        self.assertEqual(len(result["proposals"]), 1)
        return result["proposals"][0]

    def test_accept_refreshes_in_place_never_duplicates(self):
        proposal = self.make_renewal()
        result = learn.accept_proposal(proposal["id"], self.db, self.record,
                                       now=BASE_NOW)
        self.assertTrue(result["renewed"])
        after = learn.load_record(self.record)
        self.assertEqual(len(after["entries"]), 1)
        entry = after["entries"][0]
        self.assertEqual(entry["id"], "lp-001")
        self.assertEqual(entry["status"], "active")
        self.assertEqual(entry["value"], 0.7)
        self.assertEqual(entry["created_at"], "2026-08-01")
        self.assertEqual(entry["review_after"],
                         (BASE_NOW.date() + timedelta(days=90)).isoformat())
        self.assertIn(f"renewed by {proposal['id']}", entry["evidence"])
        self.assertIn("renewed lp-001",
                      self.record.read_text(encoding="utf-8"))

    def test_accept_with_edited_value_updates_the_same_entry(self):
        proposal = self.make_renewal()
        result = learn.accept_proposal(proposal["id"], self.db, self.record,
                                       value=0.8, now=BASE_NOW)
        self.assertEqual(result["proposal"]["state"], "edited-accepted")
        after = learn.load_record(self.record)
        self.assertEqual(len(after["entries"]), 1)
        self.assertEqual(after["entries"][0]["value"], 0.8)
        self.assertIn("0.8", after["entries"][0]["statement"])

    def test_accept_for_a_superseded_entry_is_a_clean_error(self):
        proposal = self.make_renewal()
        self.write_record(WEIGHT_ENTRY.replace("status: active",
                                               "status: superseded"))
        with self.assertRaises(ValueError):
            learn.accept_proposal(proposal["id"], self.db, self.record,
                                  now=BASE_NOW)


class RenewalDismissalTests(ReviewFixture):
    def make_renewal(self):
        self.write_record(WEIGHT_ENTRY)
        result = self.generate()
        self.assertEqual(len(result["proposals"]), 1)
        return result["proposals"][0]

    def test_dismissed_renewal_snoozes_like_its_kind(self):
        proposal = self.make_renewal()
        result = learn.dismiss_proposal(proposal["id"], self.db, now=BASE_NOW)
        self.assertEqual(result["snooze_until"],
                         (BASE_NOW.date() + timedelta(days=30)).isoformat())
        self.assertEqual(self.generate(now=BASE_NOW + timedelta(days=10))["proposals"],
                         [])
        result = self.generate(now=BASE_NOW + timedelta(days=31))
        self.assertEqual(len(result["proposals"]), 1)
        self.assertEqual(result["proposals"][0]["kind"], "renewal")

    def test_never_dismissal_retires_the_question_not_the_entry(self):
        proposal = self.make_renewal()
        learn.dismiss_proposal(proposal["id"], self.db, never=True, now=BASE_NOW)
        result = self.generate(now=BASE_NOW + timedelta(days=200))
        self.assertEqual(result["proposals"], [])
        entry = learn.load_record(self.record)["entries"][0]
        self.assertEqual(entry["status"], "active")
        self.assertEqual(entry["review_after"], "2026-10-30")


class LongPauseReviewTests(ReviewFixture):
    def test_pause_over_90_days_yields_one_review_per_quarter(self):
        self.write_record(PAUSE_ENTRY)
        first = self.generate()
        self.assertEqual(len(first["proposals"]), 1)
        proposal = first["proposals"][0]
        self.assertEqual(proposal["kind"], "pause_review")
        self.assertEqual(proposal["target"], "src_beta")
        self.assertEqual(proposal["value"], "lp-002")
        self.assertIn("108 days", proposal["statement"])
        # Asked once this quarter: a batch 30 days later (the first
        # proposal long expired) must not ask again.
        result = self.generate(now=BASE_NOW + timedelta(days=30))
        self.assertEqual(result["proposals"], [])
        # Next quarter it may be asked again.
        result = self.generate(now=BASE_NOW + timedelta(days=91))
        self.assertEqual(len(result["proposals"]), 1)
        self.assertEqual(result["proposals"][0]["kind"], "pause_review")

    def test_pause_under_90_days_gets_no_review(self):
        young = PAUSE_ENTRY.replace("2026-08-01", "2026-10-01").replace(
            "2026-10-30", "2026-12-30")
        self.write_record(young)
        result = self.generate()
        self.assertEqual(result["proposals"], [])

    def test_pause_review_takes_precedence_over_renewal(self):
        # The pause entry is also past review_after; exactly one
        # question is asked about it, and it is the pause question.
        self.write_record(PAUSE_ENTRY)
        result = self.generate()
        kinds = [p["kind"] for p in result["proposals"]]
        self.assertEqual(kinds, ["pause_review"])

    def test_pause_review_accept_keeps_the_pause_and_reschedules(self):
        self.write_record(PAUSE_ENTRY)
        proposal = self.generate()["proposals"][0]
        result = learn.accept_proposal(proposal["id"], self.db, self.record,
                                       now=BASE_NOW)
        self.assertTrue(result["renewed"])
        after = learn.load_record(self.record)
        self.assertEqual(len(after["entries"]), 1)
        entry = after["entries"][0]
        self.assertEqual(entry["kind"], "source_pause")
        self.assertEqual(entry["value"], True)
        self.assertEqual(entry["review_after"],
                         (BASE_NOW.date() + timedelta(days=90)).isoformat())


class StepRuleTests(ReviewFixture):
    def test_superseded_entry_does_not_reset_the_90_day_step_rule(self):
        self.write_record("[]")
        ids = seed_daily(self.daily_dir,
                         {"src_alpha": ("Alpha", [(1, 4), (8, 4), (15, 4)])})
        seed_feedback(self.db, negative_events(ids["src_alpha"]))
        proposal = self.generate()["proposals"][0]
        learn.accept_proposal(proposal["id"], self.db, self.record, now=BASE_NOW)
        # The owner supersedes the entry by hand 10 days later; the
        # engine must still honor the accepted step's 90-day window.
        text = self.record.read_text(encoding="utf-8")
        self.record.write_text(text.replace("status: active",
                                            "status: superseded"),
                               encoding="utf-8")
        day40 = BASE_NOW + timedelta(days=40)
        ids = seed_daily(self.daily_dir,
                         {"src_alpha": ("Alpha", [(1, 4), (8, 4), (15, 4)])},
                         now=day40)
        seed_feedback(self.db, negative_events(ids["src_alpha"]), now=day40)
        result = learn.generate_proposals(self.db, self.daily_dir,
                                          self.record, now=day40)
        self.assertEqual(result["proposals"], [])
        # Once the accepted step is 90+ days old, re-proposal is legal.
        day100 = BASE_NOW + timedelta(days=100)
        ids = seed_daily(self.daily_dir,
                         {"src_alpha": ("Alpha", [(1, 4), (8, 4), (15, 4)])},
                         now=day100)
        seed_feedback(self.db, negative_events(ids["src_alpha"]), now=day100)
        result = learn.generate_proposals(self.db, self.daily_dir,
                                          self.record, now=day100)
        self.assertEqual(len(result["proposals"]), 1)
        self.assertEqual(result["proposals"][0]["kind"], "source_weight")


class ShowAgeTests(ReviewFixture):
    def test_show_prints_each_active_entry_age_in_days(self):
        self.write_record(WEIGHT_ENTRY + PAUSE_ENTRY)
        result = learn.show(self.db, self.record, now=BASE_NOW)
        ages = {e["id"]: e["age_days"] for e in result["entries"]}
        self.assertEqual(ages, {"lp-001": 108, "lp-002": 108})

    def test_show_prints_days_until_or_past_review(self):
        self.write_record(WEIGHT_ENTRY + PAUSE_ENTRY)
        result = learn.show(self.db, self.record, now=BASE_NOW)
        distances = {e["id"]: e["review_in_days"] for e in result["entries"]}
        # review_after 2026-10-30 is 18 days before BASE_NOW (2026-11-17).
        self.assertEqual(distances, {"lp-001": -18, "lp-002": -18})

    def test_show_ages_do_not_leak_into_the_record(self):
        self.write_record(WEIGHT_ENTRY)
        learn.show(self.db, self.record, now=BASE_NOW)
        entry = learn.load_record(self.record)["entries"][0]
        self.assertNotIn("age_days", entry)
        self.assertNotIn("review_in_days", entry)


if __name__ == "__main__":
    unittest.main()
