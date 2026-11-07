"""Offline contract tests using documented API response shapes (NOT live provider acceptance)."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from focu.daily.collectors import FetchResult
from focu.daily.config import load_config
from focu.daily.store import Store
from focu.decision_gate import (
    GateError, GateLedger, JUDGMENTS, POLICY_VERSION, comparison_report,
    contextual_evidence, evaluate_pending, gate_priorities, pending_candidates,
    recommend, request_judgments,
)


def ratings(value=0.4):
    return {name: value for name in JUDGMENTS}


class ProviderContractTests(unittest.TestCase):
    def test_jev_real_api_shape_from_docs(self):
        seen = []
        def transport(url, payload, token):
            seen.append((url, payload, token))
            return {"model": "jev-latest", "answers": {
                name: {"type": "noul", "noul": 0.6} for name in JUDGMENTS
            }, "usage": {"input_tokens": 50, "output_tokens": 4}}
        with patch.dict("os.environ", {"TYPESAFE_API_KEY": "test"}, clear=False):
            out = request_judgments("jev", "an article", transport=transport)
        self.assertEqual(out["signals"], ratings(0.6))
        self.assertEqual(out["signal_kind"], "model_probability")
        self.assertEqual(seen[0][0], "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(seen[0][1]["questions"]["new_evidence"]["type"], "noul")
        self.assertEqual(seen[0][2], "test")

    def test_decisions_documented_shape(self):
        def transport(url, payload, token):
            self.assertEqual(payload["model"], "gpt-6-luna")
            self.assertEqual(payload["questions"][0]["type"], "predicate")
            return {"model": payload["model"], "answers": [
                {"type": "predicate", "name": name, "probability": 0.8}
                for name in JUDGMENTS], "usage": {"input_tokens": 50}}
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}, clear=False):
            out = request_judgments("openai-decisions", "an article", transport=transport)
        self.assertEqual(out["signals"], ratings(0.8))

    def test_responses_structured_output_shape(self):
        def transport(url, payload, token):
            self.assertEqual(payload["text"]["format"]["type"], "json_schema")
            return {"model": payload["model"], "output": [
                {"type": "message", "content": [
                    {"type": "output_text", "text": json.dumps(ratings(0.3))}
                ]}], "usage": {"input_tokens": 100}}
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}, clear=False):
            out = request_judgments("openai-llm", "an article", transport=transport)
        self.assertEqual(out["signals"], ratings(0.3))
        self.assertEqual(out["signal_kind"], "rubric_rating")

    def test_refusal_and_malformed_answer_rejected(self):
        def refusal(url, payload, token):
            return {"answers": [{"type": "refusal", "name": name}
                                for name in JUDGMENTS]}
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}, clear=False):
            with self.assertRaises(GateError):
                request_judgments("openai-decisions", "text", transport=refusal)
        def out_of_range(url, payload, token):
            return {"answers": {name: {"noul": 2.0} for name in JUDGMENTS}}
        with patch.dict("os.environ", {"TYPESAFE_API_KEY": "test"}, clear=False):
            with self.assertRaises(GateError):
                request_judgments("jev", "text", transport=out_of_range)

    def test_no_api_key_means_no_network(self):
        from focu.decision_gate import post_json
        with self.assertRaises(GateError):
            post_json("https://api.openai.com/v1/decisions", {}, None)

    def test_policy_does_not_conflate_uncertainty_with_irrelevance(self):
        contrary = ratings(0.35)
        contrary["contradicts_prior"] = 0.95
        self.assertEqual(recommend(contrary)["priority"], "promote")
        weak = ratings(0.05)
        self.assertEqual(recommend(weak)["priority"], "defer")


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cfg_file = self.root / "sources.yaml"
        self.cfg_file.write_text(json.dumps({
            "version": 2, "timezone": "UTC", "output_mode": "text_only",
            "channels": [{"id": "a", "language": "en",
                          "max_minutes": 10, "words_per_minute": 150}],
            "sources": [{"name": "Example", "type": "rss", "channel": "a",
                         "feed_url": "https://example.org/rss",
                         "max_items_per_day": 1}]
        }))
        self.cfg = load_config(self.cfg_file)
        self.store = Store(self.root / "data")
        self.store.sync_sources(self.cfg)
        src = self.cfg["sources"][0]
        self.store.persist_fetch(src, FetchResult(items=[
            {"native_item_id": "1", "url": "https://example.org/one",
             "title": "PAPER-A", "body": "Summary of common old findings."},
            {"native_item_id": "2", "url": "https://example.org/two",
             "title": "PAPER-B", "body": "Novel evidence and stronger independent experiment."},
        ]))
        self.day = datetime.now(timezone.utc).date().isoformat()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def fake(self, provider, text):
        signals = ratings(0.2)
        if "PAPER-B" in text:
            signals["new_evidence"] = 0.9
            signals["goal_relevance"] = 0.8
            signals["worth_verifying"] = 0.9
        return {"signals": signals, "provider": provider, "model": "fake",
                "elapsed_ms": 6, "usage": {"input_tokens": 10},
                "signal_kind": "model_probability"}

    def test_shadow_is_noninvasive_and_all_arms_are_logged(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test", "TYPESAFE_API_KEY": "test"}):
            out = evaluate_pending(self.store, self.day, mode="shadow",
                provider="jev", compare=("openai-decisions", "openai-llm"), evaluate_fn=self.fake)
        self.assertEqual(out["evaluated"], 2)
        self.assertEqual(out["errors"], 0)
        with self.assertRaises(GateError):
            gate_priorities(self.store.data_dir, self.day)
        result = comparison_report(self.store.data_dir, self.day)
        self.assertEqual(result["provider_stats"]["jev"]["ok"], 2)
        self.assertEqual(result["provider_stats"]["openai-llm"]["ok"], 2)
        run = self.store.ensure_run(self.day, self.cfg, "text_only")
        self.store.select(run, self.cfg)
        unit = self.store.units(self.store.episodes(run["run_id"])[0]["episode_id"])[0]
        self.assertEqual(unit["gate_priority"], "normal")

    def test_active_ranks_with_current_revision_but_never_suppresses(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}):
            out = evaluate_pending(self.store, self.day, mode="active",
                provider="openai-decisions", evaluate_fn=self.fake)
        ranks = gate_priorities(self.store.data_dir, self.day)
        self.assertEqual(len(ranks), 2)
        run = self.store.ensure_run(self.day, self.cfg, "text_only")
        self.store.select(run, self.cfg, gate_priorities=ranks)
        chosen = self.store.units(self.store.episodes(run["run_id"])[0]["episode_id"])
        self.assertEqual(chosen[0]["title"], "PAPER-B")
        self.assertEqual(chosen[0]["gate_priority"], "promote")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM candidates").fetchone()[0], 2)
        self.assertEqual(len(pending_candidates(self.store)), 1)  # unselected is still in backlog

    def test_stale_revision_has_no_effect(self):
        with patch.dict("os.environ", {"TYPESAFE_API_KEY": "test"}):
            evaluate_pending(self.store, self.day, mode="active", provider="jev", evaluate_fn=self.fake)
        ranks = gate_priorities(self.store.data_dir, self.day)
        changed = {key: {**value, "revision_id": "old-revision"} for key, value in ranks.items()}
        run = self.store.ensure_run(self.day, self.cfg, "text_only")
        self.store.select(run, self.cfg, gate_priorities=changed)
        unit = self.store.units(self.store.episodes(run["run_id"])[0]["episode_id"])[0]
        self.assertEqual(unit["gate_priority"], "normal")

    def test_cached_repeat_is_zero_additional_provider_calls(self):
        calls = []
        def evaluator(provider, text):
            calls.append(provider)
            return self.fake(provider, text)
        with patch.dict("os.environ", {"TYPESAFE_API_KEY": "test"}):
            evaluate_pending(self.store, self.day, mode="shadow", provider="jev",
                             evaluate_fn=evaluator)
            again = evaluate_pending(self.store, self.day, mode="shadow", provider="jev",
                                     evaluate_fn=evaluator)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(r["provider_results"]["jev"]["cached"]
                            for r in again["candidates"]))

    def test_partial_provider_error_keeps_items_and_snapshot(self):
        def bad(provider, text):
            if provider == "jev":
                raise GateError("temporary provider error")
            return self.fake(provider, text)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test", "TYPESAFE_API_KEY": "test"}):
            out = evaluate_pending(self.store, self.day, mode="active", provider="jev",
                                   compare=("openai-decisions",), evaluate_fn=bad)
        self.assertEqual(out["errors"], 2)
        self.assertEqual(gate_priorities(self.store.data_dir, self.day), {})
        self.assertEqual(comparison_report(self.store.data_dir, self.day)["provider_stats"]["jev"]["errors"], 2)

    def test_feedback_is_explicit_and_append_only(self):
        ledger = GateLedger(self.store.data_dir)
        ledger.feedback(self.day, "content-test", "missed", "Important contrary evidence")
        ledger.feedback(self.day, "content-test", "useful", "Follow-up found it")
        self.assertEqual(ledger.db.execute("SELECT count(*) FROM feedback").fetchone()[0], 2)
        with self.assertRaises(GateError):
            ledger.feedback(self.day, "content-test", "engagement", "")
        ledger.close()

    def test_missing_context_does_not_invent_knowledge(self):
        text = contextual_evidence({"title": "A", "url": "https://example.org",
                                    "body": "Test"}, wiki_dir=None)
        self.assertIn("none were supplied", text)
        with self.assertRaises(GateError):
            contextual_evidence({"title": "A"}, wiki_dir=self.root / "not-exist")

    def test_gate_off_has_no_remote_cost_and_no_ranks(self):
        out = evaluate_pending(self.store, self.day, mode="off", provider="off")
        self.assertEqual(out["evaluated"], 0)
        self.assertFalse(out["candidates"])
        self.assertEqual(comparison_report(self.store.data_dir, self.day)["provider_stats"], {})


if __name__ == "__main__":
    unittest.main()
