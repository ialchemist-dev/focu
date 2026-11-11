"""Offline checks for docs/research evidence (issues #42/#43): JSON shape, no secrets, local links."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "docs" / "research"
SNAPSHOTS = ["issue-42-activity-snapshot.json", "issue-42-activity-snapshot-batch2.json",
             "issue-43-activity-snapshot.json", "issue-43-bundle-snapshot.json"]
REPO_KEYS = {"repo", "license_spdx", "stars", "commits_90d", "contributors_6mo", "latest_release",
             "issues_opened_90d", "issues_closed_90d", "responsiveness_90d", "windows"}
DOCS = ["ISSUE_42_ARTICLE_PODCAST_OSS_LANDSCAPE_2026-11-11.md", "ISSUE_43_WEBVIEW_READER_SHELL_LANDSCAPE_2026-11-11.md"]


class ResearchArtifactTests(unittest.TestCase):
    def test_snapshots_have_dated_windows_and_required_metrics(self):
        for name in SNAPSHOTS:
            data = json.loads((RESEARCH / "evidence" / name).read_text(encoding="utf-8"))
            self.assertEqual(data["schema"], "focu-oss-activity-snapshot/1")
            self.assertRegex(data["captured_at"], r"^2\d{3}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
            for repo in data["repos"]:
                self.assertNotIn("error", repo, name)
                self.assertTrue(REPO_KEYS <= repo.keys(), (name, repo.get("repo")))
                self.assertIn("truncated_lower_bound", repo["contributors_6mo"])
                self.assertLess(repo["windows"]["commits_90d_since"], data["captured_at"])
            for pkg in data["packages"]:
                self.assertNotIn("error", pkg, name)
                for f in pkg["measured_files"]:
                    self.assertGreater(f["raw_bytes"], f["gzip9_bytes"])

    def test_no_credentials_or_emails_in_evidence(self):
        for path in (RESEARCH / "evidence").glob("*.json"):
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_|Authorization", text), path)
            self.assertIsNone(re.search(r"[\w.+-]+@[A-Za-z][\w-]*\.(?:com|org|net|io|dev)\b", text), path)

    def test_relative_links_in_research_docs_resolve(self):
        for name in DOCS:
            doc = RESEARCH / name
            for target in re.findall(r"\]\((?!https?://|#)([^)#\s]+)", doc.read_text(encoding="utf-8")):
                self.assertTrue((doc.parent / target).resolve().exists(), (name, target))


if __name__ == "__main__":
    unittest.main()
