"""Wave 25 (Q7): sparsity accounting, the explicit stop rule, and
floor validation for the learning engine.

The engine's floors (MIN_DELIVERED / MIN_NEGATIVE_EVENTS /
MIN_NEGATIVE_RATE / MIN_USEFUL_EVENTS) were set by design judgment
and never validated. This harness validates them against shaped
fixtures, per team/pm-plan-3.md Wave 25:

(a) completions-only history at scale fires nothing, and the
    sparsity block shows the gates unmet;
(b) uniform noise (fixed-seed, spread thinly across >=5 sources,
    including marks arriving as per-unit observations fanned out
    from one compilation mark, as post-F1 ingest produces) fires
    nothing — the floors hold against noise;
(c) a concentrated real-shaped signal (12 delivered, 4 not-for-me
    on one source) DOES fire its demotion — the floors are not so
    high they never fire;
(d) the stop rule: a source passing its own floors on a bare
    minimum while the window total stays below
    MIN_ATTRIBUTED_EVENTS drafts zero statistics proposals, and the
    result carries the reason verbatim;
(e) the sparsity block's numbers match the fixtures' counts exactly.

Plus: review proposals (renewal / pause_review) are record-driven
and still generate under the stop rule, and the CLI prints the
sparsity block and the reason on an empty-history scratch store.
"""
import io
import json
import random
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

from focu import learn
from focu.daily.store import Store as DailyStore
from focu.feedback import FeedbackStore

BASE_NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)

# 12 delivered per source over 3 distinct days: above MIN_DELIVERED,
# below the pruning pause's PAUSE_MIN_DELIVERED, so weight floors are
# the only statistics gates in play for these fixtures.
TWELVE = [(1, 4), (8, 4), (15, 4)]


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


class SparsityFixture(unittest.TestCase):
    entries_block = "[]"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db = root / "focu.sqlite3"
        self.daily_dir = root / "daily"
        self.record = root / "learned-preferences.md"
        self.record.write_text(record_text(self.entries_block), encoding="utf-8")

    def generate(self, now=BASE_NOW):
        return learn.generate_proposals(self.db, self.daily_dir, self.record, now=now)


class CompletionsOnlyHistoryTests(SparsityFixture):
    def test_completions_only_history_fires_nothing(self):
        """(a) >=5 sources, >=10 delivered each, completions but zero
        negative/useful marks: zero proposals, and the sparsity block
        shows every gate unmet. The window total clears the stop rule
        (10 attributed completions), so the silence here is the
        per-source gates themselves, not the stop rule."""
        plan = {f"src_{i}": (f"Source {i}", TWELVE) for i in range(5)}
        ids = seed_daily(self.daily_dir, plan)
        events = []
        for source_id in plan:
            events.extend(("observation", cid, "other", 2)
                          for cid in ids[source_id][:2])
        seed_feedback(self.db, events)
        result = self.generate()
        self.assertEqual(result["proposals"], [])
        self.assertIsNone(result["signal_reason"])
        sparsity = result["sparsity"]
        self.assertEqual(sparsity["attributed_events"], 10)
        self.assertEqual(sparsity["unattributed_feedback"], 0)
        for source_id in plan:
            slot = sparsity["sources"][source_id]
            self.assertEqual(slot["delivered"], 12)
            self.assertEqual(slot["delivered_floor"], learn.MIN_DELIVERED)
            self.assertEqual(slot["negative"], 0)
            self.assertEqual(slot["negative_floor"], learn.MIN_NEGATIVE_EVENTS)
            self.assertEqual(slot["useful"], 0)
            self.assertEqual(slot["useful_floor"], learn.MIN_USEFUL_EVENTS)
            self.assertEqual(slot["completed"], 2)


class UniformNoiseTests(SparsityFixture):
    def test_uniform_noise_fires_nothing(self):
        """(b) Fixed-seed pseudo-random marks spread thinly and evenly
        across 5 sources over 30 days at a low rate, plus one
        compilation mark fanned out to per-unit observations on three
        sources (the post-F1 arrival shape): no demotion and no
        promotion fires — the floors hold against noise."""
        plan = {f"src_{i}": (f"Source {i}", TWELVE) for i in range(5)}
        ids = seed_daily(self.daily_dir, plan)
        # Seed 7 at this rate yields 15 marks over the 5 sources with
        # no source above 2 negative / 2 useful: real noise volume,
        # silenced by the per-source floors (the window total clears
        # the stop rule), which is the behavior under validation.
        rng = random.Random(7)
        expected = {sid: {"not_useful": 0, "useful": 0, "other": 0} for sid in plan}
        events = []
        for source_id in plan:
            for offset in range(1, 30, 2):
                if rng.random() < 0.12:
                    kind = rng.choice(["not_useful", "useful", "other"])
                    cid = rng.choice(ids[source_id])
                    events.append(("observation", cid, kind, offset))
                    expected[source_id][kind] += 1
        # One compilation-level not-for-me mark, fanned out by ingest
        # to one covered unit in each of three sources.
        for source_id in list(plan)[:3]:
            events.append(("observation", ids[source_id][5], "not_useful", 4))
            expected[source_id]["not_useful"] += 1
        seed_feedback(self.db, events)
        # Fixture self-check: the noise really is below every floor, so
        # a proposal below would indict the floors, not the fixture.
        for counts in expected.values():
            self.assertLessEqual(counts["not_useful"], 2)
            self.assertLessEqual(counts["useful"], 2)
        result = self.generate()
        self.assertEqual(result["proposals"], [])
        # The sparsity accounting matches the fixture's own bookkeeping.
        total = 0
        for source_id, counts in expected.items():
            slot = result["sparsity"]["sources"][source_id]
            self.assertEqual(slot["negative"], counts["not_useful"])
            self.assertEqual(slot["useful"], counts["useful"])
            self.assertEqual(slot["completed"], counts["other"])
            total += sum(counts.values())
        self.assertEqual(result["sparsity"]["attributed_events"], total)


class ConcentratedSignalTests(SparsityFixture):
    def test_concentrated_signal_fires_demotion(self):
        """(c) One source, 12 delivered, 4 not-for-me (>=3 events,
        >=20%): the demotion proposal DOES fire — the floors are not
        so high they never fire."""
        ids = seed_daily(self.daily_dir, {
            "src_alpha": ("Alpha", TWELVE),
            "src_beta": ("Beta", TWELVE),
        })
        events = [("observation", cid, "not_useful", 2)
                  for cid in ids["src_alpha"][:4]]
        events += [("observation", cid, "other", 2)
                   for cid in ids["src_beta"][:2]]
        seed_feedback(self.db, events)
        result = self.generate()
        self.assertIsNone(result["signal_reason"])
        self.assertEqual(len(result["proposals"]), 1)
        proposal = result["proposals"][0]
        self.assertEqual(proposal["kind"], "source_weight")
        self.assertEqual(proposal["target"], "src_alpha")
        self.assertEqual(proposal["value"], learn.DEMOTE_WEIGHT)
        slot = result["sparsity"]["sources"]["src_alpha"]
        self.assertEqual(slot["delivered"], 12)
        self.assertEqual(slot["negative"], 4)


class StopRuleTests(SparsityFixture):
    def test_stop_rule_suppresses_and_explains(self):
        """(d) src_alpha passes its own demotion floors exactly (3
        negative events, 25% rate) but the window's total attributed
        signal is 3 — below MIN_ATTRIBUTED_EVENTS. The totals
        contradict the per-source pass: zero statistics proposals,
        and the reason is in the result verbatim."""
        ids = seed_daily(self.daily_dir, {"src_alpha": ("Alpha", TWELVE)})
        seed_feedback(self.db, [("observation", cid, "not_useful", 2)
                                for cid in ids["src_alpha"][:3]])
        result = self.generate()
        self.assertEqual(result["proposals"], [])
        self.assertEqual(result["signal_reason"],
                         "insufficient attributed signal: 3 events in 30 days")
        sparsity = result["sparsity"]
        self.assertEqual(sparsity["attributed_events"], 3)
        self.assertEqual(sparsity["attributed_events_floor"],
                         learn.MIN_ATTRIBUTED_EVENTS)
        slot = sparsity["sources"]["src_alpha"]
        self.assertEqual(slot["negative"], 3)
        self.assertEqual(slot["negative_floor"], learn.MIN_NEGATIVE_EVENTS)
        self.assertEqual(slot["negative_rate"], 0.25)


class SparsityAccountingTests(SparsityFixture):
    def test_sparsity_numbers_match_fixture_exactly(self):
        """(e) Every number in the sparsity block equals the fixture's
        counts — no off-by-one in the accounting itself."""
        ids = seed_daily(self.daily_dir, {
            "src_alpha": ("Alpha", TWELVE),
            "src_beta": ("Beta", [(1, 7)]),
        })
        alpha = ids["src_alpha"]
        events = [
            ("observation", alpha[0], "not_useful", 2),
            ("observation", alpha[1], "not_useful", 2),
            ("observation", alpha[2], "too_long", 2),
            ("observation", alpha[3], "useful", 2),
            ("observation", alpha[4], "useful", 2),
            ("observation", alpha[5], "useful", 2),
            ("observation", alpha[6], "other", 2),
            ("observation", alpha[7], "other", 2),
            ("observation", ids["src_beta"][0], "not_useful", 2),
            ("observation", "cnt_ghost", "not_useful", 2),  # unattributable
        ]
        seed_feedback(self.db, events)
        result = self.generate()
        sparsity = result["sparsity"]
        a = sparsity["sources"]["src_alpha"]
        self.assertEqual(a["name"], "Alpha")
        self.assertEqual(a["delivered"], 12)
        self.assertEqual(a["delivered_floor"], learn.MIN_DELIVERED)
        self.assertEqual(a["days"], 3)
        self.assertEqual(a["negative"], 3)
        self.assertEqual(a["negative_floor"], learn.MIN_NEGATIVE_EVENTS)
        self.assertEqual(a["negative_rate"], 0.25)
        self.assertEqual(a["negative_rate_floor"], learn.MIN_NEGATIVE_RATE)
        self.assertEqual(a["useful"], 3)
        self.assertEqual(a["useful_floor"], learn.MIN_USEFUL_EVENTS)
        self.assertEqual(a["completed"], 2)
        b = sparsity["sources"]["src_beta"]
        self.assertEqual(b["delivered"], 7)
        self.assertEqual(b["days"], 1)
        self.assertEqual(b["negative"], 1)
        self.assertEqual(b["useful"], 0)
        self.assertEqual(b["completed"], 0)
        self.assertEqual(sparsity["attributed_events"], 9)
        self.assertEqual(sparsity["attributed_events_floor"],
                         learn.MIN_ATTRIBUTED_EVENTS)
        self.assertEqual(sparsity["unattributed_feedback"], 1)
        self.assertEqual(result["unattributed_feedback"], 1)
        self.assertEqual(result["attributed_events"], 9)
        self.assertEqual(result["sources_considered"], 2)


class ReviewUnderStopRuleTests(SparsityFixture):
    entries_block = WEIGHT_ENTRY + PAUSE_ENTRY

    def test_review_proposals_survive_the_stop_rule(self):
        """Review proposals are record-driven, not statistics-driven:
        with an empty feedback window (0 attributed events, stop rule
        active) the renewal and the long-pause review still generate,
        and no source_weight proposal appears."""
        result = self.generate()
        kinds = {p["kind"] for p in result["proposals"]}
        self.assertEqual(kinds, {"renewal", "pause_review"})
        self.assertEqual(result["signal_reason"],
                         "insufficient attributed signal: 0 events in 30 days")
        self.assertEqual(result["sparsity"]["attributed_events"], 0)


class CliEmptyHistoryTests(SparsityFixture):
    def test_proposals_cli_prints_sparsity_and_reason(self):
        """Acceptance: `focu learn proposals` on an empty-history
        scratch store prints the sparsity block and the
        insufficient-signal reason, zero proposals, exit 0."""
        out = io.StringIO()
        with redirect_stdout(out):
            code = learn.main(["proposals", "--db", str(self.db),
                               "--daily-dir", str(self.daily_dir),
                               "--record", str(self.record)])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["proposals"], [])
        self.assertIn("sparsity", payload)
        self.assertEqual(payload["sparsity"]["attributed_events"], 0)
        self.assertTrue(payload["signal_reason"].startswith(
            "insufficient attributed signal"))


if __name__ == "__main__":
    unittest.main()
