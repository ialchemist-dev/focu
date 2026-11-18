"""Phase 2 transport: focu learn ingest of reader reading-summary exports.

The reader's consumption store lives on the owner's device; the only path
across is the owner-carried export file (format contract documented in
experiments/muse-artifact-reader/index.html above buildReadingSummary).
These tests pin the ingest mapping, the envelope validation, and the
idempotency rule: content_id + updated_at + signal class.
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


def seed_daily(daily_dir, plan, now):
    """plan: {source_id: (name, [(day_offset, count), ...])} — same fixture
    shape as test_learn.py; returns {source_id: [content_id, ...]}."""
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


def make_item(content_id, **overrides):
    item = {"content_id": content_id, "source": "Alpha",
            "status": "in_progress", "via": None, "archived": False,
            "not_for_me": None, "audio": None, "audio_pos_seconds": None,
            "article_pos_px": None, "updated_at": "2026-11-17T10:00:00+00:00"}
    item.update(overrides)
    return item


def write_export(directory, items, exported_at="2026-11-17T12:00:00+00:00",
                 name="focu-reading-summary.json", **envelope):
    doc = {"format": "focu-reading-summary", "version": 1,
           "exported_at": exported_at, "items": items}
    doc.update(envelope)
    path = Path(directory) / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "focu.sqlite3"

    def events(self):
        return FeedbackStore(self.db).list()

    def test_not_for_me_becomes_negative_event_with_source(self):
        item = make_item(
            "cnt_a", status="not_for_me", archived=True,
            not_for_me={"at": "2026-11-17T09:30:00+00:00", "source": "Alpha"})
        path = write_export(self.root, [item])
        result = learn.ingest_reading_summary(path, self.db)
        self.assertEqual(result["events_recorded"], 1)
        self.assertEqual(result["events_by_kind"], {"not_useful": 1})
        events = self.events()
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["target_type"], "observation")
        self.assertEqual(event["target_id"], "cnt_a")
        self.assertEqual(event["kind"], "not_useful")
        self.assertIn("Alpha", event["note"])
        self.assertTrue(event["id"].startswith("rs_"))

    def test_manual_archive_is_not_a_consumption_signal(self):
        manual = make_item("cnt_m", status="consumed", via="manual", archived=True)
        audio = make_item("cnt_a", status="consumed", via="audio", archived=True,
                          audio="completed")
        path = write_export(self.root, [manual, audio])
        result = learn.ingest_reading_summary(path, self.db)
        self.assertEqual(result["excluded_manual_archives"], 1)
        self.assertEqual(result["events_recorded"], 1)
        events = self.events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["target_id"], "cnt_a")
        self.assertEqual(events[0]["kind"], "other")
        self.assertIn("via: audio", events[0]["note"])

    def test_in_progress_contributes_nothing(self):
        item = make_item("cnt_p", status="in_progress", audio="partial",
                         audio_pos_seconds=120)
        path = write_export(self.root, [item])
        result = learn.ingest_reading_summary(path, self.db)
        self.assertEqual(result["events_recorded"], 0)
        self.assertEqual(result["skipped_in_progress"], 1)
        self.assertTrue(any("in_progress" in note for note in result["notes"]))
        self.assertEqual(self.events(), [])

    def test_useful_mark_becomes_useful_event(self):
        item = make_item("cnt_u", status="consumed", via="article", useful=True)
        path = write_export(self.root, [item])
        result = learn.ingest_reading_summary(path, self.db)
        self.assertEqual(result["events_recorded"], 2)
        kinds = sorted(e["kind"] for e in self.events())
        self.assertEqual(kinds, ["other", "useful"])

    def test_useful_marks_feed_the_promotion_rule(self):
        now = datetime.now(timezone.utc)
        daily_dir = self.root / "daily"
        ids = seed_daily(daily_dir, {"src_beta": ("Beta", [(1, 4), (8, 4), (15, 4)])},
                         now=now)
        items = [make_item(cid, source="Beta", status="consumed", via="article",
                           useful=True) for cid in ids["src_beta"][:3]]
        path = write_export(self.root, items)
        learn.ingest_reading_summary(path, self.db)
        record = self.root / "learned-preferences.md"
        record.write_text("# record\n\n```yaml\nversion: \"2026-11-17.1\"\n"
                          "entries: []\n```\n\n**Version:** 2026-11-17.1\n\n"
                          "## Changelog\n", encoding="utf-8")
        result = learn.generate_proposals(self.db, daily_dir, record, now=now)
        self.assertEqual(len(result["proposals"]), 1)
        self.assertEqual(result["proposals"][0]["target"], "src_beta")
        self.assertEqual(result["proposals"][0]["value"], learn.PROMOTE_WEIGHT)

    def test_double_ingest_is_idempotent(self):
        items = [
            make_item("cnt_a", status="not_for_me", archived=True,
                      not_for_me={"at": "2026-11-17T09:30:00+00:00",
                                  "source": "Alpha"}),
            make_item("cnt_b", status="consumed", via="audio", audio="completed"),
        ]
        path = write_export(self.root, items)
        first = learn.ingest_reading_summary(path, self.db)
        self.assertEqual(first["events_recorded"], 2)
        second = learn.ingest_reading_summary(path, self.db)
        self.assertEqual(second["events_recorded"], 0)
        self.assertEqual(second["events_already_recorded"], 2)
        self.assertEqual(len(self.events()), 2)
        # A fresher export of the SAME item states must not double-count:
        # exported_at is not part of the dedupe basis.
        later = write_export(self.root, items, name="later.json",
                             exported_at="2026-11-18T12:00:00+00:00")
        third = learn.ingest_reading_summary(later, self.db)
        self.assertEqual(third["events_recorded"], 0)
        self.assertEqual(len(self.events()), 2)

    def test_changed_state_produces_a_new_event(self):
        path = write_export(self.root, [make_item("cnt_a")])
        first = learn.ingest_reading_summary(path, self.db)
        self.assertEqual(first["events_recorded"], 0)
        changed = make_item("cnt_a", status="consumed", via="audio",
                            audio="completed",
                            updated_at="2026-11-17T18:00:00+00:00")
        path2 = write_export(self.root, [changed], name="second.json",
                             exported_at="2026-11-17T19:00:00+00:00")
        second = learn.ingest_reading_summary(path2, self.db)
        self.assertEqual(second["events_recorded"], 1)
        self.assertEqual(len(self.events()), 1)

    def test_conflicting_event_id_is_reported_not_raised(self):
        item = make_item("cnt_a", status="not_for_me", archived=True,
                         not_for_me={"at": "2026-11-17T09:30:00+00:00",
                                     "source": "Alpha"})
        store = FeedbackStore(self.db)
        store.record(target_type="observation", target_id="cnt_a",
                     kind="not_useful", note="someone else's note",
                     event_id=learn._reader_event_id(item, "not_useful"))
        path = write_export(self.root, [item])
        result = learn.ingest_reading_summary(path, self.db)
        self.assertEqual(result["events_recorded"], 0)
        self.assertEqual(result["conflicts"], ["cnt_a"])
        self.assertEqual(len(self.events()), 1)

    def test_ingest_never_touches_the_record(self):
        record = self.root / "learned-preferences.md"
        record.write_text("record bytes stay put\n", encoding="utf-8")
        before = record.read_bytes()
        path = write_export(self.root, [make_item("cnt_a", status="consumed",
                                                  via="article")])
        learn.ingest_reading_summary(path, self.db)
        self.assertEqual(record.read_bytes(), before)


class CompilationAttributionTests(unittest.TestCase):
    """PM sweep F1: marks on a compiled daily briefing must attribute to
    the covered units' sources (fan-out), and research-item marks must
    be reported out of scope — neither may leak into
    unattributed_feedback."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "focu.sqlite3"
        self.now = datetime.now(timezone.utc)
        self.daily_dir = self.root / "daily"
        self.ids = seed_daily(self.daily_dir, {
            "src_alpha": ("Alpha", [(1, 3)]),
            "src_beta": ("Beta", [(1, 3)]),
        }, now=self.now)

    def events(self):
        return FeedbackStore(self.db).list()

    def compilation_item(self, covered, **overrides):
        item = make_item(
            "daily-2026-11-16", source="Focu", status="not_for_me",
            archived=True,
            not_for_me={"at": "2026-11-17T09:30:00+00:00", "source": "Focu"},
            covered_content_ids=covered)
        item.update(overrides)
        return item

    def test_briefing_not_for_me_fans_out_to_covered_sources(self):
        covered = [self.ids["src_alpha"][0], self.ids["src_beta"][0]]
        path = write_export(self.root, [self.compilation_item(covered)])
        result = learn.ingest_reading_summary(path, self.db)
        self.assertEqual(result["events_recorded"], 2)
        self.assertEqual(result["events_by_kind"], {"not_useful": 2})
        self.assertEqual(result["fanned_out_compilations"], 1)
        events = self.events()
        self.assertEqual(sorted(e["target_id"] for e in events), sorted(covered))
        for event in events:
            self.assertEqual(event["kind"], "not_useful")
            self.assertIn("via compilation daily-2026-11-16", event["note"])
        stats = learn.compute_statistics(self.db, self.daily_dir, now=self.now)
        self.assertEqual(stats["sources"]["src_alpha"]["negative_total"], 1)
        self.assertEqual(stats["sources"]["src_beta"]["negative_total"], 1)
        self.assertEqual(stats["unattributed_feedback"], 0)

    def test_briefing_useful_fans_out_to_covered_sources(self):
        covered = self.ids["src_alpha"][:2]
        item = self.compilation_item(
            covered, status="in_progress", archived=False, not_for_me=None,
            useful={"at": "2026-11-17T09:30:00+00:00", "source": "Focu"})
        path = write_export(self.root, [item])
        result = learn.ingest_reading_summary(path, self.db)
        self.assertEqual(result["events_recorded"], 2)
        self.assertEqual(result["events_by_kind"], {"useful": 2})
        self.assertEqual(sorted(e["target_id"] for e in self.events()),
                         sorted(covered))
        stats = learn.compute_statistics(self.db, self.daily_dir, now=self.now)
        self.assertEqual(stats["sources"]["src_alpha"]["useful"], 2)
        self.assertEqual(stats["unattributed_feedback"], 0)

    def test_fan_out_ingest_is_idempotent(self):
        covered = [self.ids["src_alpha"][0], self.ids["src_beta"][0]]
        path = write_export(self.root, [self.compilation_item(covered)])
        first = learn.ingest_reading_summary(path, self.db)
        self.assertEqual(first["events_recorded"], 2)
        second = learn.ingest_reading_summary(path, self.db)
        self.assertEqual(second["events_recorded"], 0)
        self.assertEqual(second["events_already_recorded"], 2)
        self.assertEqual(len(self.events()), 2)

    def test_compilation_without_covered_ids_keeps_legacy_path(self):
        # An export written before the covered-ids field existed: the
        # signal records against the compilation id exactly as before
        # (it will surface as unattributed in statistics — unavoidable
        # without the coverage data, and now distinguishable from the
        # research exclusion).
        item = self.compilation_item([])
        del item["covered_content_ids"]
        path = write_export(self.root, [item])
        result = learn.ingest_reading_summary(path, self.db)
        self.assertEqual(result["events_recorded"], 1)
        self.assertEqual(result["fanned_out_compilations"], 0)
        self.assertEqual(self.events()[0]["target_id"], "daily-2026-11-16")

    def test_research_marks_are_out_of_scope_not_unattributed(self):
        item = make_item(
            "int_abc123", source="Your research", status="not_for_me",
            archived=True,
            not_for_me={"at": "2026-11-17T09:30:00+00:00",
                        "source": "Your research"},
            useful={"at": "2026-11-17T09:31:00+00:00",
                    "source": "Your research"})
        path = write_export(self.root, [item])
        result = learn.ingest_reading_summary(path, self.db)
        self.assertEqual(result["events_recorded"], 0)
        self.assertEqual(result["out_of_scope_research_items"], 1)
        self.assertEqual(result["out_of_scope_research_signals"], 2)
        self.assertTrue(any("out of scope" in note for note in result["notes"]))
        self.assertEqual(self.events(), [])
        stats = learn.compute_statistics(self.db, self.daily_dir, now=self.now)
        self.assertEqual(stats["unattributed_feedback"], 0)

    def test_malformed_covered_ids_rejected_before_any_write(self):
        good = self.compilation_item([self.ids["src_alpha"][0]])
        bad = self.compilation_item("not-a-list", content_id="daily-2026-11-15")
        with self.assertRaises(ValueError):
            learn.ingest_reading_summary(write_export(self.root, [good, bad]),
                                         self.db)
        self.assertEqual(self.events(), [])
        bad2 = self.compilation_item([123], content_id="daily-2026-11-15")
        with self.assertRaises(ValueError):
            learn.ingest_reading_summary(
                write_export(self.root, [bad2], name="bad2.json"), self.db)
        self.assertEqual(self.events(), [])


class EnvelopeValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "focu.sqlite3"

    def assert_clean_error(self, path):
        with self.assertRaises(ValueError):
            learn.ingest_reading_summary(path, self.db)
        self.assertEqual(FeedbackStore(self.db).list(), [])

    def test_wrong_format_and_version_rejected(self):
        self.assert_clean_error(write_export(self.root, [], name="a.json",
                                             format="something-else"))
        self.assert_clean_error(write_export(self.root, [], name="b.json",
                                             version=2))

    def test_items_must_be_a_list_with_exported_at(self):
        self.assert_clean_error(write_export(self.root, {}, name="a.json"))
        doc = {"format": "focu-reading-summary", "version": 1, "items": []}
        path = self.root / "b.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        self.assert_clean_error(path)

    def test_malformed_items_rejected_before_any_write(self):
        good = make_item("cnt_g", status="consumed", via="article")
        bad = make_item("cnt_b", status="mystery")
        self.assert_clean_error(write_export(self.root, [good, bad], name="a.json"))
        no_id = make_item("cnt_x")
        del no_id["content_id"]
        self.assert_clean_error(write_export(self.root, [no_id], name="b.json"))

    def test_corrupt_and_missing_files_are_clean_errors(self):
        path = self.root / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        self.assert_clean_error(path)
        self.assert_clean_error(self.root / "does-not-exist.json")


class IngestCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "focu.sqlite3"

    def test_learn_cli_ingest(self):
        path = write_export(self.root, [make_item("cnt_a", status="consumed",
                                                  via="article")])
        self.assertEqual(learn.main(["ingest", str(path), "--db", str(self.db)]), 0)
        self.assertEqual(len(FeedbackStore(self.db).list()), 1)

    def test_learn_cli_ingest_corrupt_returns_1(self):
        path = self.root / "broken.json"
        path.write_text("{nope", encoding="utf-8")
        self.assertEqual(learn.main(["ingest", str(path), "--db", str(self.db)]), 1)
        self.assertEqual(FeedbackStore(self.db).list(), [])

    def test_top_level_cli_dispatch(self):
        from focu.cli import main as cli_main
        path = write_export(self.root, [make_item("cnt_a", status="consumed",
                                                  via="audio", audio="completed")])
        code = cli_main(["--db", str(self.db), "learn", "ingest", str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(len(FeedbackStore(self.db).list()), 1)


if __name__ == "__main__":
    unittest.main()
