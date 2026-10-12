#!/usr/bin/env python3
"""Compatibility entry point; all behavior lives in the_few."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from the_few.cli import main

if __name__ == "__main__":
    defaults = ["--config", str(REPO / "sources.yaml"), "--data-dir", str(REPO / "data")]
    raise SystemExit(main(["digest", *defaults, *sys.argv[1:]]))
