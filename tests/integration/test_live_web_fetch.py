"""Opt-in external-network smoke test; intentionally not part of default CI."""
import os
import unittest
from the_few.web import fetch_page


@unittest.skipUnless(os.getenv("THE_FEW_LIVE_TESTS") == "1", "Set THE_FEW_LIVE_TESTS=1 to allow real internet access")
class LiveWebFetchTests(unittest.TestCase):
    def test_python_documentation_is_retrievable(self):
        page = fetch_page("https://docs.python.org/3/", timeout=20)
        self.assertEqual(page.status, 200)
        self.assertIn("python", (page.title + " " + page.text[:2000]).lower())
        self.assertGreater(len(page.text), 200)
        self.assertTrue(page.url.startswith("https://"))


if __name__ == "__main__":
    unittest.main()
