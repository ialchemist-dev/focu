"""Superlinear Academy source registration (owner request, 2026-11-19).

Superlinear is a host-collected source, like LinkedIn: the community
feed (a Circle community at superlinear.academy/feed) renders only in
a browser, so an agent session collects it and a host unitizer emits
one digest unit per day through the daily --input-units path. The
core must therefore (a) accept type "superlinear" in the registry and
(b) treat it as externally supplied (needs_auth), never fetching it
directly.
"""
import tempfile
import unittest
from pathlib import Path

import yaml

from focu.daily.collectors import collect
from focu.daily.config import load_config


def _config(tmp: Path) -> Path:
    cfg = {
        "version": 1,
        "timezone": "America/Denver",
        "channels": [{"id": "research", "name": "Daily AI Briefing",
                      "language": "en", "max_minutes": 35,
                      "words_per_minute": 150}],
        "sources": [{"name": "Superlinear Academy", "type": "superlinear",
                     "channel": "research",
                     "profile_url": "https://www.superlinear.academy/feed",
                     "max_items_per_day": 1}],
    }
    path = tmp / "sources.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


class SuperlinearRegistrationTests(unittest.TestCase):
    def test_config_loads_superlinear_source(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = load_config(_config(Path(d)))
            src = cfg["sources"][0]
            self.assertEqual(src["type"], "superlinear")
            self.assertEqual(src["name"], "Superlinear Academy")

    def test_collect_is_needs_auth_not_fetched(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = load_config(_config(Path(d)))
            result = collect(cfg["sources"][0])
            self.assertEqual(result.status, "needs_auth")


if __name__ == "__main__":
    unittest.main()
