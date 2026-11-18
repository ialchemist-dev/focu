"""Q11 cold start (wave 34): the first two weeks on an empty registry.

Implements the acceptance battery of
docs/dev-team/q11-cold-start-design.md §7 against the composed system,
on scratch state only (temp dirs, no network — pack liveness off, the
daily run consumes a local units file):

  §7.1 fresh-store walkthrough: empty registry + empty ledger + the
       shipped empty record -> preview -> install one starter pack ->
       one daily cycle -> briefing exists, day_status row exists,
       proposals print the sparsity block and the stop-rule string,
       zero proposals drafted.
  §7.2 the preference record's bytes are identical before and after
       the whole walkthrough, install included.
  §7.3 the default is stated: install output AND the first briefing's
       status surface each name the pack and the literal uninstall
       command (and later briefings do not repeat it; --json, which
       prints the stored record byte-for-byte, never carries it).
  §7.4 one-pack bound: exactly one manifest entry; the registry holds
       no source the pack did not name.
  §7.5 uninstall of the starter pack returns sources.yaml to its
       pre-install bytes.
  §7.7 sparsity framing: every gate as count-beside-floor, and no
       percentage, no projected date, no recommended action.
  §7.8 thin-day honesty: a zero-item day yields the nothing-new
       sentence verbatim and no fabricated briefing content.

§7.6 (no floor moved) is a diff property, not a runtime test: this
wave touches no learn.py constant, and the wave-25 sparsity harness
pins the floors' behavior.

Surface choices, recorded per the wave brief: the design names no new
command (§3 routes the install through the existing preview -> install
path; §8 forbids pre-picking the pack), so none was added — `focu pack
catalog` already lists the candidates with their prices. The one
missing buildable surface was §7.3's second half: `focu daily
day-status` now appends the installed-pack statement to its TEXT
output for the first briefing's run only.
"""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from focu.daily.cli import main as daily_main
from focu.daily.config import load_config
from focu.daily.store import Store
from focu.learn import main as learn_main
from focu.packs import main as pack_main
from focu.packs import manifest_path

REPO = Path(__file__).resolve().parent.parent
SHIPPED_RECORD = REPO / "references" / "learned-preferences.md"

PACK_ID = "cold-start-pack"
PACK = {
    "schema_version": 1, "id": PACK_ID, "title": "Cold Start Pack",
    "version": "1.0.0", "curator": {"name": "Cold Start Curator"},
    "description": "A pack used only by the cold-start walkthrough.",
    "tags": ["test"], "coverage": "Only cold-start fixtures.",
    "verified_at": "2026-11-01",
    "sources": [{
        "id": "alice", "name": "Alice Example", "type": "rss",
        "channel": "research", "platform": "Ghost",
        "homepage": "https://alice.example.com/",
        "feed_url": "https://alice.example.com/feed",
        "cadence": {"posts_per_month": 1.0,
                    "basis": "feed items dated 2026-10-01",
                    "as_of": "2026-11-01"},
        "verified_at": "2026-11-01", "enabled": True}],
}

# The starter registry in the serializer's canonical form (the form
# _apply_config writes), so the §7.5 byte round trip measures the
# uninstall semantics rather than YAML formatting drift.
STARTER_DOC = {"version": 2, "timezone": "UTC",
               "output_mode": "text_only",
               "channels": [{"id": "research", "language": "en",
                             "max_minutes": 12}],
               "sources": []}


def capture(func, argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = func(argv)
    return code, out.getvalue()


class ColdStartCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.today = datetime.now(timezone.utc).date()
        self.config = self.root / "sources.yaml"
        self.config.write_text(
            yaml.safe_dump(STARTER_DOC, sort_keys=False,
                           allow_unicode=True),
            encoding="utf-8")
        self.pack_file = self.root / "pack.json"
        self.pack_file.write_text(json.dumps(PACK), encoding="utf-8")
        self.data_dir = self.root / "data"
        self.feedback_db = self.root / "focu.sqlite3"
        # The shipped empty record, copied to scratch: the walkthrough
        # must leave its bytes exactly as they were (§7.2).
        self.record = self.root / "learned-preferences.md"
        self.record.write_bytes(SHIPPED_RECORD.read_bytes())

    # -- steps -----------------------------------------------------------

    def preview(self):
        return capture(pack_main, ["preview", str(self.pack_file),
                                   "--config", str(self.config),
                                   "--no-liveness"])

    def install(self):
        return capture(pack_main, ["install", str(self.pack_file),
                                   "--config", str(self.config),
                                   "--yes", "--no-liveness"])

    def run_day(self, day, units):
        units_file = self.root / f"units-{day}.json"
        units_file.write_text(json.dumps(units), encoding="utf-8")
        return capture(daily_main, [
            "run", "--config", str(self.config),
            "--data-dir", str(self.data_dir), "--date", day,
            "--text-only", "--input-units", str(units_file), "--json"])

    def day_status(self, *extra):
        return capture(daily_main, [
            "day-status", "--data-dir", str(self.data_dir),
            "--config", str(self.config), *extra])

    def proposals(self):
        return capture(learn_main, [
            "proposals", "--db", str(self.feedback_db),
            "--daily-dir", str(self.data_dir),
            "--record", str(self.record)])

    def uninstall_command(self):
        return (f"focu pack uninstall {PACK_ID} "
                f"--config {self.config}")

    @staticmethod
    def unit(native_id, url):
        return {"native_item_id": native_id, "source": "Alice Example",
                "url": url, "title": f"Alice post {native_id}",
                "body": "Alice published a short update."}


class WalkthroughTests(ColdStartCase):
    def test_fresh_store_walkthrough(self):
        record_before = self.record.read_bytes()

        # Day 0: preview first — the price is visible before any
        # commitment (design §3), and preview writes nothing.
        code, preview = self.preview()
        self.assertEqual(code, 0)
        self.assertIn(PACK_ID, preview)
        self.assertIn("posts/month", preview)
        self.assertFalse(manifest_path(self.config).exists())

        code, installed = self.install()
        self.assertEqual(code, 0)
        # §7.3, install half: the output names the pack and the
        # literal one-action removal.
        self.assertIn(PACK_ID, installed)
        self.assertIn(self.uninstall_command(), installed)

        # §7.4: exactly one pack installed, and the registry holds
        # only what that pack named.
        manifest = json.loads(
            manifest_path(self.config).read_text(encoding="utf-8"))
        self.assertEqual([r["pack_id"] for r in manifest["packs"]],
                         [PACK_ID])
        cfg = load_config(self.config)
        self.assertEqual([s["name"] for s in cfg["sources"]],
                         ["Alice Example"])
        source_id = cfg["sources"][0]["source_id"]

        # Day 1: one real daily cycle on the one-pack registry.
        code, _run = self.run_day(
            self.today.isoformat(),
            [self.unit("1", "https://alice.example.com/post-1")])
        self.assertEqual(code, 0)
        store = Store(self.data_dir)
        self.addCleanup(store.close)
        run = dict(store.db.execute(
            "SELECT * FROM runs WHERE episode_date=?",
            (self.today.isoformat(),)).fetchone())
        # §7.1(a): a briefing exists — an episode with a script and
        # the day's one selected unit.
        episodes = store.episodes(run["run_id"])
        self.assertEqual(len(episodes), 1)
        self.assertTrue(episodes[0]["script"])
        units = store.units(episodes[0]["episode_id"])
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["source_id"], source_id)
        # §7.1(b): the day_status stage row exists for the date.
        row = store.db.execute(
            "SELECT report_json FROM stage_runs WHERE run_id=? "
            "AND stage='day_status'", (run["run_id"],)).fetchone()
        self.assertIsNotNone(row)

        # §7.1(c)(d) + §7.7: proposals on the cold store draft nothing
        # and say why, with every gate shown as count beside floor.
        code, out = self.proposals()
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["proposals"], [])
        self.assertEqual(
            result["signal_reason"],
            "insufficient attributed signal: 0 events in 30 days")
        self.assertIn("insufficient attributed signal: "
                      "0 events in 30 days", out)
        sparsity = result["sparsity"]
        self.assertEqual(sparsity["attributed_events"], 0)
        self.assertEqual(sparsity["attributed_events_floor"], 4)
        self.assertEqual(sparsity["unattributed_feedback"], 0)
        slot = sparsity["sources"][source_id]
        self.assertEqual(slot["delivered"], 1)
        self.assertEqual(slot["delivered_floor"], 10)
        self.assertEqual(slot["negative"], 0)
        self.assertEqual(slot["negative_floor"], 3)
        self.assertEqual(slot["useful"], 0)
        self.assertEqual(slot["useful_floor"], 3)
        self.assertEqual(slot["pause_delivered_floor"], 20)
        self.assertEqual(slot["pause_days_floor"], 10)
        # §7.7 framing: an instrument readout — no percentage of a
        # profile, no projected "smart by" date, no recommended action.
        self.assertNotIn("%", out)
        self.assertNotIn("smart by", out)
        self.assertNotIn("recommend", out.lower())

        # §7.2: the record is byte-identical after install, the daily
        # cycle, and the proposals batch — nothing wrote to it.
        self.assertEqual(self.record.read_bytes(), record_before)

    def test_first_briefing_status_surface_states_the_default(self):
        self.install()
        day1 = self.today.isoformat()
        day2 = (self.today + timedelta(days=1)).isoformat()
        code, _ = self.run_day(
            day1, [self.unit("1", "https://alice.example.com/post-1")])
        self.assertEqual(code, 0)
        code, _ = self.run_day(
            day2, [self.unit("2", "https://alice.example.com/post-2")])
        self.assertEqual(code, 0)

        # §7.3, briefing half: the first briefing's status surface
        # names the pack and the literal uninstall command.
        code, out = self.day_status("--date", day1)
        self.assertEqual(code, 0)
        self.assertIn(f"Installed pack: {PACK_ID}", out)
        self.assertIn(self.uninstall_command(), out)

        # Later briefings do not repeat the statement.
        code, out = self.day_status()
        self.assertEqual(code, 0)
        self.assertNotIn("Installed pack:", out)

        # --json prints the stored record and nothing else: the
        # statement never rides the byte-for-byte path.
        code, out = self.day_status("--date", day1, "--json")
        self.assertEqual(code, 0)
        self.assertNotIn("Installed pack", out)
        store = Store(self.data_dir)
        self.addCleanup(store.close)
        raw = store.db.execute(
            "SELECT report_json FROM stage_runs WHERE stage='day_status' "
            "ORDER BY rowid LIMIT 1").fetchone()[0]
        self.assertEqual(json.loads(out), json.loads(raw))

    def test_uninstall_returns_registry_to_pre_install_bytes(self):
        before = self.config.read_bytes()
        code, _ = self.install()
        self.assertEqual(code, 0)
        self.assertNotEqual(self.config.read_bytes(), before)
        code, _ = capture(pack_main, [
            "uninstall", PACK_ID, "--config", str(self.config), "--yes"])
        self.assertEqual(code, 0)
        # §7.5: one action, and the registry is exactly what it was.
        self.assertEqual(self.config.read_bytes(), before)
        manifest = json.loads(
            manifest_path(self.config).read_text(encoding="utf-8"))
        self.assertEqual(manifest["packs"], [])

    def test_thin_day_is_reported_thin_not_padded(self):
        self.install()
        code, _ = self.run_day(self.today.isoformat(), [])
        self.assertEqual(code, 0)
        # §7.8: the nothing-new sentence, verbatim, on the surface.
        code, out = self.day_status()
        self.assertEqual(code, 0)
        self.assertIn(f"Nothing new for {self.today.isoformat()}: "
                      "no source reported new items", out)
        # And nothing was fabricated to fill the day: no episode
        # carries a single unit.
        store = Store(self.data_dir)
        self.addCleanup(store.close)
        count = store.db.execute(
            "SELECT count(*) FROM episode_items").fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
