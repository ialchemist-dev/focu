#!/usr/bin/env python3
"""Build a deterministic, private Muse Artifact staging bundle from Focu deliveries."""
import argparse
import hashlib
import json
import os
import re
from datetime import date
from pathlib import Path
import shutil
import sys
import tempfile

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def episode_date(folder_name):
    match = re.search(r'(?:^|[-_])(\d{8})$', folder_name)
    if not match:
        return ""
    raw = match.group(1)
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8])).isoformat()
    except ValueError:
        return ""


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--deliveries", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--template", type=Path, default=Path(__file__).with_name("index.html"))
    p.add_argument("--limit", type=int, default=15)
    a = p.parse_args()
    try:
        count = build(a.deliveries, a.output, a.template, a.limit)
        print(f"Built {count} episodes at {a.output}")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Publish failed: {exc}", file=sys.stderr)
        sys.exit(1)
