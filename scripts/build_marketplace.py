#!/usr/bin/env python3
"""Regenerate marketplace/catalog.json, default.json and index.html.

Usage: .venv/bin/python scripts/build_marketplace.py [--out marketplace]
The outputs are generated from focu/source_packs/*.json via
focu.marketplace; never hand-edit them — edit a pack, then re-run.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from focu.marketplace import write_marketplace  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="marketplace")
    args = parser.parse_args(argv)
    catalog = write_marketplace(args.out)
    print(f"marketplace: {len(catalog['packs'])} packs -> {args.out}/"
          "catalog.json, default.json, index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
