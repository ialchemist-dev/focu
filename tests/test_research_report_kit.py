"""Regression tests for docs/research-reports/kit/check_report.py.

The checker is the deterministic (layer A) gate for hand-built research report pages.
These tests prove that the shipped fixture passes and that each integrity rule actually
fails closed when broken. They do not test semantic correctness (not automatable).
"""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "docs" / "research-reports" / "kit"
FIXTURE = ROOT / "docs" / "research-reports" / "fixture" / "sample"

spec = importlib.util.spec_from_file_location("check_report", KIT / "check_report.py")
check_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_report)


class ResearchReportKitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.rd = self.tmp / "sample"
        shutil.copytree(FIXTURE, self.rd)
        self.page = self.rd / "page" / "index.html"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def errors(self):
        return [f"{e['check']}: {e['detail']}" for e in check_report.check(self.rd).errors]

    def assertFailsWith(self, needle):
        errs = self.errors()
        self.assertTrue(any(needle in e for e in errs), f"expected error containing {needle!r}, got {errs}")

    def edit_page(self, old, new):
        text = self.page.read_text(encoding="utf-8")
        self.assertTrue(old in text, f"fixture anchor not found: {old!r}")
        self.page.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_fixture_passes(self):
        self.assertEqual(self.errors(), [])
        self.assertEqual(check_report.main([str(FIXTURE)]), 0)

    def test_template_has_required_slots(self):
        text = (KIT / "template.html").read_text(encoding="utf-8")
        for needle in ('id="overview"', 'id="limits"', 'id="sources"', 'id="provenance"',
                       'class="cite" href="#src-S1"', "data-chart", 'name="viewport"'):
            self.assertIn(needle, text)

    def test_dangling_citation_fails(self):
        self.edit_page('<a class="cite" href="#src-S1">S1</a>，B', '<a class="cite" href="#src-S9">S9</a>，B')
        self.assertFailsWith("no matching li.src#src-S9")

    def test_page_source_url_must_match_registry(self):
        self.edit_page('href="https://example.org/a/reader-report"', 'href="https://example.org/other"')
        self.assertFailsWith("must link the registered URL")

    def test_chart_value_must_equal_claim(self):
        self.edit_page('"value":120,"claim":"C1"', '"value":125,"claim":"C1"')
        self.assertFailsWith("plotted 125 != claim C1")

    def test_charts_require_claims_json(self):
        (self.rd / "claims.json").unlink()
        shutil.rmtree(self.rd / "addenda")
        self.assertFailsWith("numeric charts require claims.json")

    def test_class_label_must_match_claim(self):
        self.edit_page('data-claim="C2" data-class="estimate"', 'data-claim="C2" data-class="reported_fact"')
        self.assertFailsWith("but claims.json says 'estimate'")

    def test_frozen_report_cannot_be_appended(self):
        with (self.rd / "report.md").open("a", encoding="utf-8") as f:
            f.write("\n## Builder addendum appended in place\n")
        self.assertFailsWith("frozen file changed after freeze: report.md")

    def test_addendum_claim_needs_builder_marker_and_registered_source(self):
        p = self.rd / "addenda" / "addendum-1" / "claims.json"
        claims = json.loads(p.read_text(encoding="utf-8"))
        claims[0].pop("added_by")
        claims[0]["source_ids"] = ["S7"]
        p.write_text(json.dumps(claims), encoding="utf-8")
        errs = self.errors()
        self.assertTrue(any("added_by" in e for e in errs), errs)
        self.assertTrue(any("S7 is not registered" in e for e in errs), errs)

    def test_derived_claim_needs_formula_and_inputs(self):
        p = self.rd / "claims.json"
        claims = json.loads(p.read_text(encoding="utf-8"))
        claims[2].pop("formula")
        claims[2]["input_claim_ids"] = ["C99"]
        p.write_text(json.dumps(claims), encoding="utf-8")
        # re-freeze so only the derived-claim rule is under test
        (self.rd / "frozen.sha256").write_text("".join(
            f"{check_report.sha256(self.rd / rel)}  {rel}\n"
            for rel in ("mission.md", "report.md", "notes/sources-key.md", "claims.json")))
        errs = self.errors()
        self.assertTrue(any("needs a formula" in e for e in errs), errs)
        self.assertTrue(any("C99 does not exist" in e for e in errs), errs)

    def test_long_quote_rejected(self):
        p = self.rd / "addenda" / "addendum-1" / "claims.json"
        claims = json.loads(p.read_text(encoding="utf-8"))
        claims[0]["quote"] = "x" * 400
        p.write_text(json.dumps(claims), encoding="utf-8")
        self.assertFailsWith("keep short excerpts")

    def test_external_assets_and_private_paths_rejected(self):
        self.edit_page("</head>", '<script src="https://cdn.example.com/x.js"></script></head>')
        self.edit_page("<h1>", "<p>/Users/someone/notes</p><h1>")
        errs = self.errors()
        self.assertTrue(any("must be self-contained" in e for e in errs), errs)
        self.assertTrue(any("local/private paths" in e for e in errs), errs)

    def test_run_json_cannot_claim_unrun_qa(self):
        p = self.rd / "run.json"
        run = json.loads(p.read_text(encoding="utf-8"))
        run["qa"]["render"] = {"state": "passed", "evidence": None}
        run["qa"]["semantic"] = {"state": "passed", "reviewer": "none"}
        run["preference_source"] = "automatic_memory"
        p.write_text(json.dumps(run), encoding="utf-8")
        errs = self.errors()
        self.assertTrue(any("qa.render.evidence" in e for e in errs), errs)
        self.assertTrue(any("reviewer is 'none'" in e for e in errs), errs)
        self.assertTrue(any("preference_source" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
