"""Secretary briefing style/coverage contract tests: offline and deterministic."""
import json
import tempfile
import unittest
from pathlib import Path

from focu.briefing import (
    BriefingQCError, DEFAULT_STYLE, key_figures, make_prompt, ordered_units,
    read_style, render_script, validate_script,
)


def units():
    return [
        {"id": "follow-1", "origin": "interest_follow_up", "source": "Research notes",
         "title": "Memory pressure follow-up",
         "body": "The saved follow-up notes recorded a 17% measured change."},
        {"id": "source-1", "origin": "registered_source", "source": "Research Source A",
         "title": "Daily update",
         "body": "The source reports 948 items and 20 exceptions, with $1.2M attributed."},
        {"id": "request-1", "origin": "user_initiated", "source": "Technical paper B",
         "title": "Requested investigation results",
         "body": "The requested paper reports a sample size of 5,034."},
        {"id": "source-2", "origin": "registered_source", "source": "Research Source C",
         "title": "Daily update",
         "body": "A separate source reports 32 improvements in the test series."},
    ]


class BriefingTests(unittest.TestCase):
    def test_five_item_sample_episode_matches_golden_script_and_qc(self):
        root = Path(__file__).resolve().parents[1]
        items = json.loads((root / "examples/secretary-briefing-demo-units.json").read_text())
        golden = (root / "examples/secretary-briefing-demo-script.txt").read_text()
        style = read_style()
        self.assertEqual(render_script(items, style), golden)
        qc = validate_script(golden, items, style)
        self.assertTrue(qc["passed"], qc["issues"])
        self.assertEqual(qc["item_count"], 5)
        self.assertEqual(qc["covered_sections"], 5)
        self.assertTrue(all(not row["missing_figures"] for row in qc["sections"]))
        self.assertIn("You asked me to research this.", golden)
        self.assertNotIn("welcome back", golden.casefold())

    def test_style_loads_from_single_versioned_source(self):
        style = read_style()
        self.assertEqual(style["language"], "en")
        self.assertEqual(style["speaker_label"], "Host: ")
        self.assertIn("Changelog", style["style_document"])
        self.assertIn("2026-11-05", style["style_document"])
        self.assertEqual(len(style["style_sha256"]), 64)

    def test_all_items_covered_once_in_requested_order(self):
        style = read_style()
        script = render_script(units(), style)
        report = validate_script(script, units(), style)
        self.assertTrue(report["passed"], report["issues"])
        self.assertEqual(report["item_count"], 4)
        self.assertEqual(report["covered_sections"], 4)
        self.assertEqual(script.count("Daily update."), 2)  # repeated headlines are legal
        self.assertLess(script.index("Research Source C"), script.index("You asked me"))
        self.assertLess(script.index("You asked me"), script.index("Memory pressure follow-up"))
        self.assertIn("948", script)
        self.assertIn("$1.2M", script)
        self.assertIn("5,034", script)
        self.assertNotIn("welcome back", script.casefold())
        self.assertNotIn("next time", script.casefold())
        self.assertIn("Source: Technical paper B", script)

    def test_qc_rejects_dropped_item_even_when_script_sounds_complete(self):
        style = read_style()
        script = render_script(units(), style)
        shortened = script.replace(
            "Host: Requested investigation results. The requested paper reports a sample size of 5,034. "
            "You asked me to research this. Source: Technical paper B.\n\n", "")
        report = validate_script(shortened, units(), style)
        self.assertFalse(report["passed"])
        self.assertTrue(any(x["issue"] == "missing_headline_or_wrong_order" for x in report["issues"]))

    def test_qc_rejects_missing_hard_figures_per_item(self):
        style = read_style()
        script = render_script(units(), style)
        altered = script.replace("a sample size of 5,034", "a sample size")
        report = validate_script(altered, units(), style)
        self.assertFalse(report["passed"])
        self.assertTrue(any(x["issue"] == "missing_key_figures" and "5,034" in x["values"]
                            for x in report["issues"]))

    def test_qc_rejects_show_packaging_and_unattributed_claim(self):
        style = read_style()
        script = render_script(units(), style)
        show = "Host: Welcome back to today's episode.\n\n" + script
        self.assertFalse(validate_script(show, units(), style)["passed"])
        self.assertTrue(any(x["issue"] == "forbidden_show_packaging"
                            for x in validate_script(show, units(), style)["issues"]))
        stripped = script.replace("Source: Technical paper B.", "Source: Unknown.")
        self.assertFalse(validate_script(stripped, units(), style)["passed"])

    def test_editing_style_file_changes_both_script_and_prompt_without_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "briefing-style.md"
            file.write_text(DEFAULT_STYLE.read_text(encoding="utf-8"), encoding="utf-8")
            initial = read_style(file)
            first_script = render_script(units(), initial)
            first_prompt = make_prompt(units(), initial)
            changed = file.read_text().replace(
                'opening: "Here\'s what came in."',
                'opening: "A brief update for you."',
            )
            changed += "\n- **2026-11-05 — demo-only:** shorter opening after owner feedback.\n"
            file.write_text(changed, encoding="utf-8")
            revised = read_style(file)
            self.assertNotEqual(initial["style_sha256"], revised["style_sha256"])
            self.assertNotEqual(first_script, render_script(units(), revised))
            self.assertNotEqual(first_prompt, make_prompt(units(), revised))
            self.assertIn("A brief update for you", render_script(units(), revised))
            self.assertTrue(validate_script(render_script(units(), revised), units(), revised)["passed"])

    def test_prompt_includes_exact_style_and_all_numbers(self):
        style = read_style()
        prompt = make_prompt(units(), style)
        self.assertIn(style["style_document"], prompt)
        self.assertIn("5,034", prompt)
        self.assertIn("948", prompt)
        self.assertIn("follow-1", prompt)

    def test_rejects_duplicate_ids_and_invalid_style(self):
        style = read_style()
        with self.assertRaisesRegex(BriefingQCError, "unique stable"):
            ordered_units(units() + [units()[0]])
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "style.md"
            p.write_text("missing YAML settings")
            with self.assertRaises(BriefingQCError):
                read_style(p)


if __name__ == "__main__":
    unittest.main()
