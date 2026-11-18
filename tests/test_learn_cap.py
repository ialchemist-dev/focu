"""Cap proposals: source_cap drafted from accounting evidence (wave 39).

The class was designed in Phase 1 (record schema, validator, snooze
table, statement builder, Phase-3 seam) but never generated; the
evidence design is learning-design.md's wave-39 addendum. This file
pins the generation rule:

(1) compute_statistics surfaces over_cap (summed from the
    selection_accounting stage rows) and registry_cap (from the
    newest in-window frozen run config) per source;
(2) the canonical shape — sustained over_cap pressure at the
    registry cap, low-but-nonzero completion, no useful marks, no
    demotion shape — earns exactly one source_cap proposal whose
    value is the observed finish rate per delivery day, rounded up;
(3) every floor vetoes on its own: delivered, days, over_cap,
    completion-rate ceiling, the useful veto, an unknown registry
    cap, and a derived value that is not a true lowering;
(4) zero completions is the pause's shape, not the cap's; a
    demotion-shaped source gets the demotion;
(5) the class is NOT gated by the attributed-events stop rule (its
    evidence is accounting volume, like the pruning pause): the
    canonical fixture carries only 3 attributed events — below
    MIN_ATTRIBUTED_EVENTS — and the proposal still drafts, with the
    signal_reason recorded beside it;
(6) accepting the proposal writes one owner-accepted source_cap
    entry, and Store.select honors min(registry, learned) and
    freezes the factor — end to end on one daily store.
"""
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from focu import learn
from focu.daily.collectors import FetchResult
from focu.daily.config import load_config
from focu.daily.store import Store as DailyStore
from focu.feedback import FeedbackStore

BASE_NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)

# 10 distinct delivery days inside the window.
TEN_DAYS = (1, 4, 7, 10, 13, 16, 19, 22, 25, 28)


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


def seed_daily_cap(daily_dir, plan, caps=None, over_cap=None, now=BASE_NOW):
    """plan: {source_id: (name, [(day_offset, count), ...])};
    caps: {source_id: registry_cap} written into every run's frozen
    config (None -> the legacy "{}" config, registry cap unknown);
    over_cap: {source_id: {day_offset: count}} written as
    selection_accounting stage rows. Mirrors tests/test_learn.py's
    seed_daily, extended with the two records the cap class reads."""
    DailyStore(daily_dir).close()
    db = sqlite3.connect(Path(daily_dir) / "few.sqlite3")
    if caps is None:
        config_json = "{}"
    else:
        config_json = json.dumps({"version": 2, "sources": [
            {"source_id": sid, "name": plan[sid][0], "max_items_per_day": cap}
            for sid, cap in sorted(caps.items())]})
    over_cap = over_cap or {}
    by_day = {}
    for source_id, (name, days) in plan.items():
        for offset, count in days:
            day = (now.date() - timedelta(days=offset)).isoformat()
            by_day.setdefault(day, []).append((source_id, name, count, offset))
    content_ids = {}
    for day, entries in sorted(by_day.items()):
        run_id, ep_id = f"run_fix_{day}", f"ep_fix_{day}"
        db.execute("INSERT INTO runs VALUES (?,?,?,?,'audio','finalized',?)",
                   (run_id, day, "hash", config_json, now.isoformat()))
        db.execute("""INSERT INTO episodes (episode_id, run_id, channel_id, status)
                      VALUES (?,?,'research','finalized')""", (ep_id, run_id))
        pos = 0
        accounting_sources = []
        for source_id, name, count, offset in entries:
            for i in range(count):
                cid = f"cnt_{source_id}_{day}_{i}"
                unit = {"source_id": source_id, "source": name, "content_id": cid,
                        "title": f"Item {i}", "score": 1.0, "gate_priority": "normal"}
                db.execute("INSERT INTO episode_items VALUES (?,?,?,?,?)",
                           (ep_id, cid, f"rev_{cid}", pos, json.dumps(unit)))
                pos += 1
                content_ids.setdefault(source_id, []).append(cid)
            withheld = over_cap.get(source_id, {}).get(offset, 0)
            accounting_sources.append({
                "source_id": source_id, "source": name,
                "considered": count + withheld, "selected": count,
                "withheld": ([{"reason": "over_cap", "count": withheld}]
                             if withheld else []),
                "not_ready": []})
        db.execute("INSERT INTO stage_runs VALUES (?,?,?,?,?)",
                   (run_id, "selection_accounting", "success",
                    json.dumps({"sources": accounting_sources}), now.isoformat()))
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


def completions(ids, n, age=2):
    return [("observation", cid, "other", age) for cid in ids[:n]]


# Canonical shape: 30 delivered over 10 days at a registry cap of 5,
# 15 over_cap withholdings, 3 completions (rate 0.10) -> value 1.
CANONICAL_PLAN = {"src_wire": ("Wire", [(offset, 3) for offset in TEN_DAYS])}
CANONICAL_OVER_CAP = {"src_wire": {offset: n for offset, n in
                                   zip(TEN_DAYS, (2, 2, 1, 2, 1, 2, 1, 2, 1, 1))}}


class CapFixture(unittest.TestCase):
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

    def seed_canonical(self):
        ids = seed_daily_cap(self.daily_dir, CANONICAL_PLAN,
                             caps={"src_wire": 5}, over_cap=CANONICAL_OVER_CAP)
        seed_feedback(self.db, completions(ids["src_wire"], 3))
        return ids


class StatisticsTests(CapFixture):
    def test_statistics_surface_cap_evidence(self):
        self.seed_canonical()
        stats = learn.compute_statistics(self.db, self.daily_dir, BASE_NOW)
        slot = stats["sources"]["src_wire"]
        self.assertEqual(slot["delivered"], 30)
        self.assertEqual(slot["days"], 10)
        self.assertEqual(slot["completed"], 3)
        self.assertEqual(slot["over_cap"], 15)
        self.assertEqual(slot["registry_cap"], 5)


class CanonicalShapeTests(CapFixture):
    def test_canonical_shape_proposes_cap_with_derived_value(self):
        self.seed_canonical()
        result = self.generate()
        self.assertEqual(len(result["proposals"]), 1)
        proposal = result["proposals"][0]
        self.assertEqual(proposal["kind"], "source_cap")
        self.assertEqual(proposal["target"], "src_wire")
        # ceil(3 completions / 10 delivery days) = 1: the observed
        # finish rate, rounded up — a true lowering of the cap of 5.
        self.assertEqual(proposal["value"], 1)
        self.assertIn("3 of 30 items completed", proposal["evidence"])
        self.assertIn("15 candidates withheld over_cap", proposal["evidence"])
        self.assertIn("registry cap of 5/day", proposal["evidence"])
        self.assertIn("n=30", proposal["evidence"])
        self.assertIn("Cap Wire at 1 item(s) per day", proposal["statement"])

    def test_cap_is_not_gated_by_the_stop_rule(self):
        # The canonical window carries exactly 3 attributed events —
        # below MIN_ATTRIBUTED_EVENTS — so the stop rule is active
        # and recorded; the cap proposal drafts anyway, because its
        # evidence is accounting volume, not feedback-event volume.
        self.seed_canonical()
        result = self.generate()
        self.assertEqual(result["attributed_events"], 3)
        self.assertEqual(result["signal_reason"],
                         "insufficient attributed signal: 3 events in 30 days")
        self.assertEqual([p["kind"] for p in result["proposals"]], ["source_cap"])

    def test_sparsity_block_shows_the_cap_gates(self):
        self.seed_canonical()
        slot = self.generate()["sparsity"]["sources"]["src_wire"]
        self.assertEqual(slot["over_cap"], 15)
        self.assertEqual(slot["over_cap_floor"], learn.CAP_MIN_OVER_CAP)
        self.assertEqual(slot["completion_rate"], 0.1)
        self.assertEqual(slot["completion_rate_ceiling"],
                         learn.CAP_MAX_COMPLETION_RATE)
        self.assertEqual(slot["cap_delivered_floor"], learn.CAP_MIN_DELIVERED)
        self.assertEqual(slot["cap_days_floor"], learn.CAP_MIN_DAYS)
        self.assertEqual(slot["registry_cap"], 5)
        self.assertEqual(slot["cap_value"], 1)

    def test_value_derived_from_observed_consumption(self):
        # 44 delivered over 10 days, 11 completions: rate exactly at
        # the 0.25 ceiling (inclusive), value ceil(11/10) = 2.
        plan = {"src_wire": ("Wire", [(offset, n) for offset, n in
                                      zip(TEN_DAYS, (5, 4, 5, 4, 5, 4, 5, 4, 4, 4))])}
        ids = seed_daily_cap(self.daily_dir, plan, caps={"src_wire": 5},
                             over_cap={"src_wire": {1: 6, 7: 6}})
        seed_feedback(self.db, completions(ids["src_wire"], 11))
        result = self.generate()
        self.assertEqual(len(result["proposals"]), 1)
        self.assertEqual(result["proposals"][0]["kind"], "source_cap")
        self.assertEqual(result["proposals"][0]["value"], 2)


class VetoTests(CapFixture):
    def test_below_delivered_floor_stays_silent(self):
        plan = {"src_wire": ("Wire", [(offset, 2) for offset in TEN_DAYS[:9]]
                                     + [(28, 1)])}  # 19 delivered, 10 days
        ids = seed_daily_cap(self.daily_dir, plan, caps={"src_wire": 5},
                             over_cap=CANONICAL_OVER_CAP)
        seed_feedback(self.db, completions(ids["src_wire"], 2))
        result = self.generate()
        self.assertEqual(result["proposals"], [])
        self.assertEqual(result["sparsity"]["sources"]["src_wire"]["delivered"], 19)

    def test_below_days_floor_stays_silent(self):
        plan = {"src_wire": ("Wire", [(offset, 3)
                                      for offset in TEN_DAYS[:9]])}  # 27 over 9 days
        ids = seed_daily_cap(self.daily_dir, plan, caps={"src_wire": 5},
                             over_cap=CANONICAL_OVER_CAP)
        seed_feedback(self.db, completions(ids["src_wire"], 2))
        self.assertEqual(self.generate()["proposals"], [])

    def test_below_over_cap_floor_stays_silent(self):
        ids = seed_daily_cap(self.daily_dir, CANONICAL_PLAN, caps={"src_wire": 5},
                             over_cap={"src_wire": {1: 9}})
        seed_feedback(self.db, completions(ids["src_wire"], 3))
        result = self.generate()
        self.assertEqual(result["proposals"], [])
        slot = result["sparsity"]["sources"]["src_wire"]
        self.assertEqual(slot["over_cap"], 9)
        self.assertEqual(slot["over_cap_floor"], learn.CAP_MIN_OVER_CAP)

    def test_completion_rate_above_ceiling_stays_silent(self):
        ids = seed_daily_cap(self.daily_dir, CANONICAL_PLAN, caps={"src_wire": 5},
                             over_cap=CANONICAL_OVER_CAP)
        seed_feedback(self.db, completions(ids["src_wire"], 9))  # rate 0.30
        self.assertEqual(self.generate()["proposals"], [])

    def test_any_useful_mark_vetoes_cap(self):
        ids = self.seed_canonical()
        seed_feedback(self.db, [("observation", ids["src_wire"][5], "useful", 2)])
        self.assertEqual(self.generate()["proposals"], [])

    def test_derived_value_must_be_a_lowering(self):
        # Registry cap already 1: the derived value (1) cannot lower
        # it, so there is nothing to propose — and the sparsity block
        # shows exactly that collision.
        ids = seed_daily_cap(self.daily_dir, CANONICAL_PLAN, caps={"src_wire": 1},
                             over_cap=CANONICAL_OVER_CAP)
        seed_feedback(self.db, completions(ids["src_wire"], 3))
        result = self.generate()
        self.assertEqual(result["proposals"], [])
        slot = result["sparsity"]["sources"]["src_wire"]
        self.assertEqual(slot["registry_cap"], 1)
        self.assertEqual(slot["cap_value"], 1)

    def test_unknown_registry_cap_stays_silent(self):
        # Legacy "{}" run configs: over_cap pressure is on record but
        # no registry cap can be read, so no lowering can be proven.
        ids = seed_daily_cap(self.daily_dir, CANONICAL_PLAN, caps=None,
                             over_cap=CANONICAL_OVER_CAP)
        seed_feedback(self.db, completions(ids["src_wire"], 3))
        result = self.generate()
        self.assertEqual(result["proposals"], [])
        slot = result["sparsity"]["sources"]["src_wire"]
        self.assertEqual(slot["over_cap"], 15)
        self.assertIsNone(slot["registry_cap"])


class PrecedenceTests(CapFixture):
    def test_zero_completions_propose_pause_not_cap(self):
        plan = {"src_wire": ("Wire", [(offset, 2) for offset in TEN_DAYS])}
        seed_daily_cap(self.daily_dir, plan, caps={"src_wire": 5},
                       over_cap=CANONICAL_OVER_CAP)
        result = self.generate()
        self.assertEqual(len(result["proposals"]), 1)
        self.assertEqual(result["proposals"][0]["kind"], "source_pause")

    def test_demotion_takes_precedence_over_cap(self):
        ids = self.seed_canonical()
        seed_feedback(self.db, [("observation", cid, "not_useful", 2)
                                for cid in ids["src_wire"][3:9]])  # 6 of 30 = 0.20
        result = self.generate()
        self.assertEqual(len(result["proposals"]), 1)
        proposal = result["proposals"][0]
        self.assertEqual(proposal["kind"], "source_weight")
        self.assertEqual(proposal["value"], learn.DEMOTE_WEIGHT)


class DecisionTests(CapFixture):
    def test_cap_dismissal_snoozes_sixty_days(self):
        self.seed_canonical()
        proposal = self.generate()["proposals"][0]
        result = learn.dismiss_proposal(proposal["id"], self.db, now=BASE_NOW)
        self.assertEqual(result["snooze_until"],
                         (BASE_NOW.date() + timedelta(days=60)).isoformat())
        self.assertEqual(learn.load_record(self.record)["entries"], [])

    def test_accepted_cap_flows_to_selection(self):
        """End to end on one real daily store: history seeded under
        the pipeline's own source identity, the proposal accepted,
        and a fresh Store.select honors min(registry 5, learned 1)
        and freezes the cap factor on the selected unit."""
        root = Path(self.temp.name)
        base = root / "e2e"
        base.mkdir()
        cfg_path = base / "sources.yaml"
        cfg_path.write_text(json.dumps({
            "version": 2, "timezone": "UTC", "output_mode": "text_only",
            "channels": [{"id": "research", "language": "en",
                          "max_minutes": 600, "words_per_minute": 150}],
            "sources": [{"name": "Alpha", "type": "rss", "channel": "research",
                         "feed_url": "https://alpha.example.org/feed",
                         "max_items_per_day": 5}]}), encoding="utf-8")
        cfg = load_config(cfg_path)
        alpha_id = cfg["sources"][0]["source_id"]
        daily_dir = base / "data"
        store = DailyStore(daily_dir)
        self.addCleanup(store.close)
        store.sync_sources(cfg)
        store.close()
        # History: the canonical shape under Alpha's real identity,
        # runs carrying the pipeline's own frozen (normalized) config.
        plan = {alpha_id: ("Alpha", [(offset, 3) for offset in TEN_DAYS])}
        ids = seed_daily_cap(daily_dir, plan, caps=None,
                             over_cap={alpha_id: CANONICAL_OVER_CAP["src_wire"]})
        db = sqlite3.connect(daily_dir / "few.sqlite3")
        db.execute("UPDATE runs SET config_json=?", (json.dumps(cfg),))
        db.commit()
        db.close()
        seed_feedback(self.db, completions(ids[alpha_id], 3))
        result = learn.generate_proposals(self.db, daily_dir, self.record,
                                          now=BASE_NOW)
        self.assertEqual(len(result["proposals"]), 1)
        proposal = result["proposals"][0]
        self.assertEqual(proposal["kind"], "source_cap")
        self.assertEqual(proposal["target"], alpha_id)
        self.assertEqual(proposal["value"], 1)
        accepted = learn.accept_proposal(proposal["id"], self.db, self.record,
                                         now=BASE_NOW)
        entry = accepted["entry"]
        self.assertEqual(entry["kind"], "source_cap")
        self.assertEqual(entry["value"], 1)
        self.assertEqual(entry["provenance"], "owner-accepted")
        adjustments = learn.learned_adjustments(learn.load_record(self.record))
        self.assertEqual(adjustments[alpha_id]["cap"]["value"], 1)
        # Fresh selection: three new Alpha items, registry cap 5,
        # learned cap 1 -> exactly one selected, factor frozen.
        store = DailyStore(daily_dir)
        self.addCleanup(store.close)
        alpha = cfg["sources"][0]
        items = []
        for i in range(3):
            items.append({
                "native_item_id": f"fresh{i}",
                "url": f"https://alpha.example.org/item/fresh{i}",
                "title": f"Fresh {i}", "body": "Alpha body text.",
                "published_at": datetime.now(timezone.utc).isoformat()})
        store.persist_fetch(alpha, FetchResult(items=items))
        day = datetime.now(timezone.utc).date().isoformat()
        run = store.ensure_run(day, cfg, "text_only")
        store.select(run, cfg, learned_record_path=self.record)
        units = []
        for ep in store.episodes(run["run_id"]):
            units.extend(store.units(ep["episode_id"]))
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["learned_factors"],
                         [{"preference_id": entry["id"], "kind": "source_cap",
                           "value": 1}])


if __name__ == "__main__":
    unittest.main()
