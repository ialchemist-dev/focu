"""Origin-specific audio policy, audience calibration, and single-item QC tests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from focu.audience import calibration, load_profile, mismatch_report, writing_guidance
from focu.intents import IntentStore
from focu.research_requests import capture_request, list_requests
from focu.single_podcast import (record_podcast_request, generate_for_intent,
                                check_fidelity, podcast_prompt, article_sections,
                                _transcript_text)

ARTICLE = """# Editing Model Weights

## Mechanism
A 131,072-weight edit changed a selected parameter subset, not the full network.

## Measurements
Benchmark accuracy rose from 7.9% to 48.1% after the targeted update.

## Negative control
The unedited model was used as a negative control and did not show the improvement.

## Independent verification
A separate implementation reproduced the central measurements.
"""
TRANSCRIPT = """Mechanism. A 131,072-weight edit changed a selected parameter subset.
Measurements. Benchmark accuracy rose from 7.9% to 48.1%.
Negative control. The unedited model was used as a negative control.
Independent verification. A separate implementation reproduced the result."""
BAD = """Mechanism. A 131,072-weight edit changed a selected parameter subset.
Measurements. Benchmark accuracy improved.
Negative control. The control was used.
Independent verification. A separate implementation reproduced the result."""


class FakeClient:
    def __init__(self, transcript=TRANSCRIPT, results=None):
        self.results = list(results or [transcript])
        self.generations = []

    def generate(self, **kwargs):
        self.generations.append(kwargs)
        return {"job_id": f"job-{len(self.generations)}"}

    def job(self, job_id):
        return {"status": "completed", "result": {"episode_id": "episode-" + job_id}}

    def request(self, method, path):
        index = int(path.split("-")[-1]) - 1
        text = self.results[index] if index < len(self.results) else self.results[-1]
        return {"id": "episode-job-" + str(index + 1), "job_status": "completed",
                "audio_url": "http://example.com/audio.mp3",
                "transcript": {"segments": [{"text": text}]}}

    def download(self, episode_id, output):
        Path(output).write_bytes(b"fresh-provider-audio-fixture")
        return {"status": "downloaded", "audio_audit": {"verified": True}}


class RealShapeClient(FakeClient):
    """Same flow as FakeClient, but the episode payload uses Open Notebook's
    real transcript shape: {"transcript": [{"speaker": ..., "dialogue": ...}]}.
    Regression fixture for the 2026-11-05 acceptance finding, where the
    extractor silently produced "" for this shape and QC audited nothing."""

    def request(self, method, path):
        index = int(path.split("-")[-1]) - 1
        text = self.results[index] if index < len(self.results) else self.results[-1]
        segments = [{"speaker": "Professor Sarah Kim", "dialogue": line}
                    for line in text.split("\n") if line.strip()]
        return {"id": "episode-job-" + str(index + 1), "job_status": "completed",
                "audio_url": "http://example.com/audio.mp3",
                "transcript": {"transcript": segments}}


class PodcastPolicyTests(unittest.TestCase):
    def make_request(self, root, *, podcast=False):
        db = Path(root) / "focu.sqlite3"
        request = capture_request(db, "Explain evidence for weight-space editing", podcast=podcast)
        folder = Path(root) / "deliveries" / ("idea-" + request["intent_id"][4:] + "-20261105")
        folder.mkdir(parents=True)
        (folder / "article.md").write_text(ARTICLE)
        (folder / "content.json").write_text(json.dumps({
            "content_id": request["intent_id"], "origin": "user_initiated",
            "title": "Editing Model Weights", "audience_domain": "machine_learning",
            "podcast_mode": "single" if podcast else "none"
        }))
        return db, request, folder

    def test_capture_default_none_and_explicit_single(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "focu.sqlite3"
            first = capture_request(db, "Investigate this topic")
            self.assertEqual(first["podcast_mode"], "none")
            self.assertIsNone(first["podcast_requested_at"])
            repeated = capture_request(db, "Investigate this topic", podcast=True)
            self.assertEqual(first["intent_id"], repeated["intent_id"])
            self.assertEqual(repeated["podcast_mode"], "single")
            self.assertTrue(repeated["podcast_requested_at"])
            third = capture_request(db, "Investigate this topic")
            self.assertEqual(third["podcast_mode"], "single",
                             "repeated no-audio request may not reset explicit choice")
            self.assertEqual(list_requests(db)["requests"][0]["podcast_mode"], "single")

    def test_legacy_db_schema_migrates_without_losing_intent(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "old.sqlite3"
            with sqlite3.connect(db) as conn:
                conn.execute("""CREATE TABLE intents (id TEXT PRIMARY KEY, question TEXT,
                  kind TEXT, status TEXT, created_at TEXT, updated_at TEXT,
                  deliver_after TEXT, evidence_pack_id TEXT, error TEXT)""")
                conn.execute("""INSERT INTO intents(id,question,kind,status,created_at,updated_at)
                    VALUES ('int_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','old','one_time_research',
                            'completed','old','old')""")
            store = IntentStore(db)
            self.assertEqual(store.get("int_" + "a"*32)["podcast_mode"], "none")
            self.assertEqual(store.get("int_" + "a"*32)["question"], "old")

    def test_request_podcast_updates_metadata_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            db, request, folder = self.make_request(root)
            before = IntentStore(db).get(request["intent_id"])
            self.assertEqual(before["podcast_mode"], "none")
            result = record_podcast_request(db, request["intent_id"], folder.parent)
            again = record_podcast_request(db, request["intent_id"], folder.parent)
            self.assertEqual(result["podcast_requested_at"], again["podcast_requested_at"])
            meta = json.loads((folder / "content.json").read_text())
            self.assertEqual(meta["podcast_mode"], "single")
            self.assertEqual(meta["podcast_requested_at"], result["podcast_requested_at"])

    def test_explicit_refusal_when_intent_is_not_single(self):
        with tempfile.TemporaryDirectory() as root:
            db, request, folder = self.make_request(root)
            with self.assertRaisesRegex(ValueError, "podcast_mode is not single"):
                generate_for_intent(db, request["intent_id"], folder.parent,
                                    client=FakeClient())
            self.assertFalse((folder / "podcast.mp3").exists())

    def test_single_item_success_with_audited_fixture_transcript(self):
        with tempfile.TemporaryDirectory() as root:
            db, request, folder = self.make_request(root, podcast=True)
            client = FakeClient()
            result = generate_for_intent(db, request["intent_id"], folder.parent,
                                         client=client)
            self.assertEqual(result["status"], "delivered")
            self.assertEqual((folder / "podcast.mp3").read_bytes(), b"fresh-provider-audio-fixture")
            self.assertTrue((folder / "transcript.json").is_file())
            qc = json.loads((folder / "podcast-qc.json").read_text())
            self.assertTrue(qc["passed"])
            self.assertEqual(qc["attempts"][0]["article_sections"], 4)
            self.assertEqual(len(client.generations), 1)
            self.assertIn("131,072", client.generations[0]["content"])
            self.assertIn("48.1%", client.generations[0]["content"])
            self.assertIn("Assume technical fluency", client.generations[0]["content"])
            metadata = json.loads((folder / "content.json").read_text())
            self.assertEqual(metadata["podcast_mode"], "single")
            self.assertEqual(metadata["audience_profile_version"], load_profile()["version"])

    def test_transcript_text_accepts_real_open_notebook_shape(self):
        real = {"transcript": [{"speaker": "Professor Sarah Kim",
                                "dialogue": "Mechanism."},
                               {"speaker": "Professor Sarah Kim",
                                "dialogue": "A 131,072-weight edit."}]}
        self.assertEqual(_transcript_text(real),
                         "Mechanism.\nA 131,072-weight edit.")
        self.assertEqual(_transcript_text({"transcript": "plain text"}),
                         "plain text")
        self.assertEqual(_transcript_text({"segments": [{"text": "legacy"}]}),
                         "legacy")
        self.assertEqual(_transcript_text("already text"), "already text")
        self.assertEqual(_transcript_text(None), "")
        self.assertEqual(_transcript_text({"unrelated": 1}), "")

    def test_single_item_success_with_real_provider_transcript_shape(self):
        with tempfile.TemporaryDirectory() as root:
            db, request, folder = self.make_request(root, podcast=True)
            client = RealShapeClient()
            result = generate_for_intent(db, request["intent_id"], folder.parent,
                                         client=client)
            self.assertEqual(result["status"], "delivered")
            self.assertEqual((folder / "podcast.mp3").read_bytes(),
                             b"fresh-provider-audio-fixture")
            qc = json.loads((folder / "podcast-qc.json").read_text())
            self.assertTrue(qc["passed"])
            self.assertEqual(qc["attempts"][0]["covered_sections"], 4)

    def test_two_failed_transcripts_leave_item_article_only(self):
        with tempfile.TemporaryDirectory() as root:
            db, request, folder = self.make_request(root, podcast=True)
            client = FakeClient(results=[BAD, BAD])
            with self.assertRaisesRegex(ValueError, "QC failed twice"):
                generate_for_intent(db, request["intent_id"], folder.parent,
                                    client=client)
            self.assertEqual(len(client.generations), 2)
            self.assertFalse((folder / "podcast.mp3").exists())
            qc = json.loads((folder / "podcast-qc.json").read_text())
            self.assertFalse(qc["passed"])
            self.assertTrue(any(e["issue"] == "missing_figures"
                                for attempt in qc["attempts"] for e in attempt["issues"]))
            self.assertTrue((folder / "article.md").is_file())

    def test_qc_fails_missing_section_reorder_and_hard_figures(self):
        passing = check_fidelity(ARTICLE, TRANSCRIPT, "machine_learning")
        self.assertTrue(passing["passed"], passing["issues"])
        self.assertEqual(passing["covered_sections"], 4)
        missing = check_fidelity(ARTICLE, TRANSCRIPT.replace("Negative control.", "Control."), "machine_learning")
        self.assertFalse(missing["passed"])
        reversed_order = check_fidelity(ARTICLE, "Measurements. 7.9% 48.1%. " +
                                         TRANSCRIPT.replace("Measurements.", "Measurements again."), "machine_learning")
        self.assertFalse(reversed_order["passed"])
        figures = check_fidelity(ARTICLE, BAD, "machine_learning")
        self.assertFalse(figures["passed"])
        self.assertTrue(any(i["issue"] == "missing_figures" for i in figures["issues"]))

    def test_audience_expert_novice_and_report_only_mismatch(self):
        profile = load_profile()
        self.assertEqual(calibration("machine_learning")["level"], "expert")
        self.assertEqual(calibration("sociology")["level"], "novice")
        self.assertNotEqual(writing_guidance("machine_learning"),
                            writing_guidance("sociology"))
        self.assertIn("Assume technical fluency", podcast_prompt(ARTICLE, "machine_learning"))
        self.assertIn("Build foundational context", podcast_prompt(ARTICLE, "sociology"))
        expert = mismatch_report("Think of it as a chef cooking a meal.", "machine_learning")
        self.assertTrue(expert["requires_review"])
        self.assertFalse(expert["blocking"])
        novice = mismatch_report("The author invokes habitus without explaining it.", "sociology")
        self.assertTrue(novice["requires_review"])

    def test_only_owner_stated_profile_entries(self):
        profile = load_profile()
        self.assertEqual(profile["domains"]["computer_science"]["provenance"], "owner-stated")
        self.assertEqual(profile["domains"]["programming"]["provenance"], "owner-stated")
        self.assertEqual(profile["domains"]["machine_learning"]["provenance"], "owner-stated")
        self.assertEqual(profile["domains"]["sociology"]["provenance"], "owner-stated")


if __name__ == "__main__":
    unittest.main()
