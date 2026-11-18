"""Learning Phase 3: bounded influence on selection (design §3.3).

Covers the record's only consumer (learn.learned_adjustments), the seam
in focu/daily/store.py Store.select, the frozen learned_factors, the
pause announcement, the fail-closed path, and focu learn explain.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from focu import learn
from focu.daily.collectors import FetchResult
from focu.daily.config import load_config
from focu.daily.pipeline import digest
from focu.daily.store import Store

PRE_PHASE3_UNIT_KEYS = {"id", "content_id", "revision_id", "source_id",
                        "source", "channel", "title", "body", "url",
                        "published_at", "kind", "score", "gate_priority"}


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


def entry_block(entry_id, kind, target, value, created="2026-11-17",
                status="active", provenance="owner-accepted"):
    value_yaml = "true" if value is True else value
    return f"""  - id: {entry_id}
    kind: {kind}
    target: {target}
    value: {value_yaml}
    statement: "Fixture statement for {entry_id}."
    provenance: {provenance}
    evidence: "test fixture"
    created_at: {created}
    review_after: 2027-02-15
    status: {status}
"""


def entry_dict(entry_id, kind, target, value, status="active"):
    return {"id": entry_id, "kind": kind, "target": target, "value": value,
            "statement": "fixture", "provenance": "owner-accepted",
            "evidence": "fixture", "created_at": "2026-11-17",
            "review_after": "2027-02-15", "status": status}


ALPHA = {"name": "Alpha", "type": "rss", "channel": "research",
         "feed_url": "https://alpha.example.org/feed", "max_items_per_day": 5}
BETA = {"name": "Beta", "type": "rss", "channel": "research",
        "feed_url": "https://beta.example.org/feed", "max_items_per_day": 5}


class AdjustmentsTests(unittest.TestCase):
    """The pure consumer: record dict in, bounded adjustments out."""

    def adjustments(self, entries):
        return learn.learned_adjustments({"version": "v", "entries": entries})

    def test_weight_clamped_at_both_bounds(self):
        adj = self.adjustments([entry_dict("lp-001", "source_weight", "src_a", 3.0)])
        self.assertEqual(adj["src_a"]["weight"]["value"], 1.5)
        adj = self.adjustments([entry_dict("lp-001", "source_weight", "src_a", 0.2)])
        self.assertEqual(adj["src_a"]["weight"]["value"], 0.5)

    def test_weight_inside_band_passes_through(self):
        adj = self.adjustments([entry_dict("lp-001", "source_weight", "src_a", 0.7)])
        self.assertEqual(adj["src_a"]["weight"],
                         {"preference_id": "lp-001", "value": 0.7})

    def test_cap_carried_raw_for_the_seam_to_min(self):
        adj = self.adjustments([entry_dict("lp-002", "source_cap", "src_a", 9)])
        self.assertEqual(adj["src_a"]["cap"],
                         {"preference_id": "lp-002", "value": 9})

    def test_pause_entry(self):
        adj = self.adjustments([entry_dict("lp-003", "source_pause", "src_a", True)])
        self.assertEqual(adj["src_a"]["pause"]["preference_id"], "lp-003")
        self.assertIs(adj["src_a"]["pause"]["value"], True)

    def test_superseded_and_non_scoring_kinds_ignored(self):
        adj = self.adjustments([
            entry_dict("lp-001", "source_weight", "src_a", 0.5, status="superseded"),
            entry_dict("lp-002", "topic_weight", "geothermal", 0.5),
            entry_dict("lp-003", "standing_note", "src_a", "prefer primary sources"),
        ])
        self.assertEqual(adj, {})

    def test_later_entry_wins_for_same_kind_and_target(self):
        adj = self.adjustments([
            entry_dict("lp-001", "source_weight", "src_a", 0.6),
            entry_dict("lp-002", "source_weight", "src_a", 0.8),
        ])
        self.assertEqual(adj["src_a"]["weight"],
                         {"preference_id": "lp-002", "value": 0.8})


class LoadAdjustmentsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.record = Path(self.temp.name) / "learned-preferences.md"

    def tearDown(self):
        self.temp.cleanup()

    def test_empty_record_yields_no_adjustments_and_no_error(self):
        self.record.write_text(record_text(), encoding="utf-8")
        adjustments, error, version = learn.load_learned_adjustments(self.record)
        self.assertEqual(adjustments, {})
        self.assertIsNone(error)
        self.assertEqual(version, "2026-11-17.1")

    def test_corrupt_record_fails_closed(self):
        self.record.write_text(record_text(entry_block(
            "lp-001", "source_weight", "src_a", 0.7, provenance="inferred")),
            encoding="utf-8")
        adjustments, error, version = learn.load_learned_adjustments(self.record)
        self.assertEqual(adjustments, {})
        self.assertIsNotNone(error)
        self.assertIsNone(version)

    def test_missing_record_fails_closed(self):
        adjustments, error, version = learn.load_learned_adjustments(self.record)
        self.assertEqual(adjustments, {})
        self.assertIsNotNone(error)


class SelectionFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.counter = 0

    def tearDown(self):
        self.temp.cleanup()

    def build(self, sources, items, record_entries=None, record_raw=None):
        """items: {source_name: [(native_id, title, body, days_ago)]}.

        Returns (store, cfg, record_path, data_dir)."""
        self.counter += 1
        base = self.root / f"case{self.counter}"
        base.mkdir(parents=True)
        cfg_path = base / "sources.yaml"
        cfg_path.write_text(json.dumps({
            "version": 2, "timezone": "UTC", "output_mode": "text_only",
            "channels": [{"id": "research", "language": "en",
                          "max_minutes": 600, "words_per_minute": 150}],
            "sources": sources}))
        cfg = load_config(cfg_path)
        store = Store(base / "data")
        self.addCleanup(store.close)
        store.sync_sources(cfg)
        by_name = {s["name"]: s for s in cfg["sources"]}
        for name, rows in items.items():
            feed_items = []
            for native_id, title, body, days_ago in rows:
                published = (datetime.now(timezone.utc)
                             - timedelta(days=days_ago)).isoformat()
                feed_items.append({
                    "native_item_id": native_id,
                    "url": f"https://{name.lower()}.example.org/item/{native_id}",
                    "title": title, "body": body, "published_at": published})
            store.persist_fetch(by_name[name], FetchResult(items=feed_items))
        record_path = base / "learned-preferences.md"
        if record_raw is not None:
            record_path.write_text(record_raw, encoding="utf-8")
        else:
            record_path.write_text(record_text(record_entries or "[]"),
                                   encoding="utf-8")
        return store, cfg, record_path, base / "data"

    def select(self, store, cfg, record_path):
        day = datetime.now(timezone.utc).date().isoformat()
        run = store.ensure_run(day, cfg, "text_only")
        store.select(run, cfg, learned_record_path=record_path)
        units = []
        for ep in store.episodes(run["run_id"]):
            units.extend(store.units(ep["episode_id"]))
        return run, units

    def stage_report(self, store, run):
        row = store.db.execute(
            "SELECT report_json FROM stage_runs WHERE run_id=? AND stage='select'",
            (run["run_id"],)).fetchone()
        return json.loads(row[0])

    @staticmethod
    def source_id(cfg, name):
        return next(s["source_id"] for s in cfg["sources"] if s["name"] == name)


class EmptyRecordRegressionTests(SelectionFixture):
    def test_empty_record_freezes_pre_phase3_shape(self):
        store, cfg, record, _ = self.build(
            [ALPHA, BETA],
            {"Alpha": [("1", "A one", "Alpha body text.", 1)],
             "Beta": [("1", "B one", "Beta body text.", 1)]})
        run, units = self.select(store, cfg, record)
        self.assertEqual(len(units), 2)
        for unit in units:
            # Byte-identical regression: no learned_factors key, exactly
            # the pre-Phase-3 key set, and the untouched score formula.
            self.assertEqual(set(unit), PRE_PHASE3_UNIT_KEYS)
            self.assertAlmostEqual(unit["score"], 1 / 2, delta=0.01)
        self.assertEqual(self.stage_report(store, run),
                         {"selected": 2})


class WeightInfluenceTests(SelectionFixture):
    ITEMS = {"Alpha": [("1", "A one", "Alpha body text, deliberately longer.", 1)],
             "Beta": [("1", "B one", "Beta body.", 1)]}

    def test_weight_demotes_and_is_frozen(self):
        store, cfg, record, _ = self.build([ALPHA, BETA], self.ITEMS)
        alpha_id = self.source_id(cfg, "Alpha")
        # Rewrite the record with a demotion for Alpha.
        record.write_text(record_text(entry_block(
            "lp-001", "source_weight", alpha_id, 0.5)), encoding="utf-8")
        _, units = self.select(store, cfg, record)
        # Equal priorities and ages: the longer body wins the tie-break
        # without influence; at 0.5x, Beta's score doubles Alpha's.
        self.assertEqual([u["source"] for u in units], ["Beta", "Alpha"])
        alpha_unit = units[1]
        self.assertEqual(alpha_unit["learned_factors"],
                         [{"preference_id": "lp-001", "kind": "source_weight",
                           "value": 0.5}])
        self.assertAlmostEqual(units[0]["score"] / alpha_unit["score"], 2.0,
                               delta=0.05)
        # Beta was under Phase-3 selection but untouched by any factor.
        self.assertEqual(units[0]["learned_factors"], [])

    def test_weight_above_ceiling_applied_clamped(self):
        store, cfg, record, _ = self.build([ALPHA, BETA], self.ITEMS)
        alpha_id = self.source_id(cfg, "Alpha")
        record.write_text(record_text(entry_block(
            "lp-001", "source_weight", alpha_id, 3.0)), encoding="utf-8")
        _, units = self.select(store, cfg, record)
        alpha_unit = next(u for u in units if u["source"] == "Alpha")
        self.assertEqual(alpha_unit["learned_factors"],
                         [{"preference_id": "lp-001", "kind": "source_weight",
                           "value": 1.5}])
        # score = registry priority 1 x clamped 1.5 / (1 + ~1 day)
        self.assertAlmostEqual(alpha_unit["score"], 1.5 / 2, delta=0.02)

    def test_learned_weight_modulates_explicit_priority_not_replaces(self):
        alpha2 = {**ALPHA, "priority": 2}
        store, cfg, record, _ = self.build([alpha2, BETA], self.ITEMS)
        alpha_id = self.source_id(cfg, "Alpha")
        record.write_text(record_text(entry_block(
            "lp-001", "source_weight", alpha_id, 0.5)), encoding="utf-8")
        _, units = self.select(store, cfg, record)
        alpha_unit = next(u for u in units if u["source"] == "Alpha")
        # 2 (explicit registry) x 0.5 (learned) / (1 + ~1 day) = 0.5
        self.assertAlmostEqual(alpha_unit["score"], 0.5, delta=0.02)


class CapInfluenceTests(SelectionFixture):
    ITEMS = {"Alpha": [(str(i), f"A {i}", "Alpha body text.", 1)
                       for i in range(4)],
             "Beta": [("1", "B one", "Beta body.", 1)]}

    def test_learned_cap_above_registry_cap_never_raises(self):
        store, cfg, record, _ = self.build(
            [{**ALPHA, "max_items_per_day": 2}, BETA], self.ITEMS)
        alpha_id = self.source_id(cfg, "Alpha")
        record.write_text(record_text(entry_block(
            "lp-002", "source_cap", alpha_id, 5)), encoding="utf-8")
        _, units = self.select(store, cfg, record)
        alpha_units = [u for u in units if u["source"] == "Alpha"]
        self.assertEqual(len(alpha_units), 2)  # registry cap is the ceiling
        for unit in alpha_units:
            # A cap that changed nothing is not frozen as an influence.
            self.assertEqual(unit["learned_factors"], [])

    def test_learned_cap_lowers_and_is_frozen(self):
        store, cfg, record, _ = self.build([ALPHA, BETA], self.ITEMS)
        alpha_id = self.source_id(cfg, "Alpha")
        record.write_text(record_text(entry_block(
            "lp-002", "source_cap", alpha_id, 1)), encoding="utf-8")
        _, units = self.select(store, cfg, record)
        alpha_units = [u for u in units if u["source"] == "Alpha"]
        self.assertEqual(len(alpha_units), 1)
        self.assertEqual(alpha_units[0]["learned_factors"],
                         [{"preference_id": "lp-002", "kind": "source_cap",
                           "value": 1}])


class PauseInfluenceTests(SelectionFixture):
    def test_pause_removes_source_and_is_announced(self):
        store, cfg, record, _ = self.build(
            [ALPHA, BETA],
            {"Alpha": [("1", "A one", "Alpha body text.", 1)],
             "Beta": [("1", "B one", "Beta body.", 1)]})
        alpha_id = self.source_id(cfg, "Alpha")
        record.write_text(record_text(entry_block(
            "lp-003", "source_pause", alpha_id, True, created="2026-11-24")),
            encoding="utf-8")
        run, units = self.select(store, cfg, record)
        self.assertEqual([u["source"] for u in units], ["Beta"])
        report = self.stage_report(store, run)
        paused = report["learned"]["paused"]
        self.assertEqual(len(paused), 1)
        self.assertEqual(paused[0]["preference_id"], "lp-003")
        self.assertEqual(paused[0]["announcement"],
                         "Paused by you on 2026-11-24: Alpha")
        # The run status surfaces the same one line (digest reads the
        # frozen select report; its own select call is already frozen).
        result = digest(store, cfg, run)
        self.assertEqual(result["learned_paused"],
                         ["Paused by you on 2026-11-24: Alpha"])


class CorruptRecordSelectionTests(SelectionFixture):
    ITEMS = {"Alpha": [("1", "A one", "Alpha body text.", 1)],
             "Beta": [("1", "B one", "Beta body.", 1)]}

    def test_corrupt_record_zero_influence_and_error_surfaced(self):
        bad = record_text(entry_block("lp-001", "source_weight", "src_x", 0.5,
                                      provenance="inferred"))
        store, cfg, record, _ = self.build([ALPHA, BETA], self.ITEMS,
                                           record_raw=bad)
        run, units = self.select(store, cfg, record)
        self.assertEqual(len(units), 2)
        for unit in units:
            self.assertEqual(set(unit), PRE_PHASE3_UNIT_KEYS)
            self.assertAlmostEqual(unit["score"], 1 / 2, delta=0.01)
        report = self.stage_report(store, run)
        self.assertIn("record_error", report["learned"])
        result = digest(store, cfg, run)
        self.assertIn("learned_record_error", result)


class ExplainTests(SelectionFixture):
    ITEMS = {"Alpha": [("1", "A one", "Alpha body text, deliberately longer.", 1)],
             "Beta": [("1", "B one", "Beta body.", 1)]}

    def build_weighted(self):
        store, cfg, record, data_dir = self.build([ALPHA, BETA], self.ITEMS)
        alpha_id = self.source_id(cfg, "Alpha")
        record.write_text(record_text(entry_block(
            "lp-001", "source_weight", alpha_id, 0.5)), encoding="utf-8")
        _, units = self.select(store, cfg, record)
        return units, data_dir

    def test_explain_names_the_frozen_factor(self):
        units, data_dir = self.build_weighted()
        alpha_unit = next(u for u in units if u["source"] == "Alpha")
        result = learn.explain(alpha_unit["content_id"], data_dir)
        self.assertTrue(result["found"])
        self.assertEqual(result["learned_factors"],
                         [{"preference_id": "lp-001", "kind": "source_weight",
                           "value": 0.5}])
        self.assertTrue(result["factors_frozen"])
        self.assertEqual(result["registry_priority"], 1)
        self.assertEqual(result["registry_cap"], 5)
        self.assertEqual(result["gate_priority"], "normal")
        self.assertAlmostEqual(result["age_days"], 1.0, delta=0.05)
        self.assertIn("lp-001", result["note"])

    def test_explain_no_factors_applied(self):
        units, data_dir = self.build_weighted()
        beta_unit = next(u for u in units if u["source"] == "Beta")
        result = learn.explain(beta_unit["content_id"], data_dir)
        self.assertTrue(result["found"])
        self.assertEqual(result["learned_factors"], [])
        self.assertTrue(result["factors_frozen"])
        self.assertEqual(result["note"],
                         "No learned preferences affected this item.")

    def test_explain_predates_phase3(self):
        # An empty-record run freezes units in the pre-Phase-3 shape;
        # explain must say no factor record exists rather than claim
        # a Phase-3 "none applied".
        store, cfg, record, data_dir = self.build([ALPHA, BETA], self.ITEMS)
        _, units = self.select(store, cfg, record)
        result = learn.explain(units[0]["content_id"], data_dir)
        self.assertTrue(result["found"])
        self.assertFalse(result["factors_frozen"])
        self.assertIn("before Phase 3", result["note"])

    def test_explain_unknown_content_and_missing_store(self):
        _, data_dir = self.build_weighted()
        result = learn.explain("cnt_does_not_exist", data_dir)
        self.assertFalse(result["found"])
        result = learn.explain("cnt_x", self.root / "no-such-dir")
        self.assertFalse(result["found"])
        self.assertIn("No daily store", result["note"])


if __name__ == "__main__":
    unittest.main()
