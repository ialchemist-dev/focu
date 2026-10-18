"""Opt-in OpenAI speech synthesis with local, private credential onboarding.

No network call occurs during setup. The host agent must request consent before
invoking interactive setup; this module cannot force a native Muse dialog.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_CONFIG = Path("data/tts-config.json")
API_URL = "https://api.openai.com/v1/audio/speech"


def config_path() -> Path:
    return Path(os.environ.get("FOCU_TTS_CONFIG", str(DEFAULT_CONFIG)))


def _read_config(path: Path | None = None) -> dict:
    path = path or config_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def status() -> dict:
    configured = bool(os.environ.get("OPENAI_API_KEY") or _read_config().get("api_key"))
    return {"provider": "openai", "configured": configured,
            "credential_source": "environment" if os.environ.get("OPENAI_API_KEY") else
            ("local_private_file" if configured else "missing"),
            "setup_command": ".venv/bin/focu tts setup"}


def setup() -> dict:
    """Explicit, terminal-only opt-in; never echo or log the credential."""
    if not sys.stdin.isatty():
        raise ValueError("Interactive terminal required; ask the user to run '.venv/bin/focu tts setup' or set OPENAI_API_KEY securely")
    print("Focu TTS setup (OpenAI). Your key is stored locally in data/tts-config.json with owner-only permissions. It is never committed or sent during setup.")
    answer = input("Store an API key locally? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        return {"status": "cancelled"}
    key = getpass.getpass("OpenAI API key (hidden): ").strip()
    if not key:
        raise ValueError("API key cannot be empty")
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"provider": "openai", "api_key": key}, f)
    except BaseException:
        raise
    return {"status": "configured", "provider": "openai", "config_path": str(path)}


def synthesize(input_path: str | Path, output_path: str | Path, *, model: str = "gpt-4o-mini-tts",
               voice: str = "alloy") -> dict:
    key = os.environ.get("OPENAI_API_KEY") or _read_config().get("api_key")
    if not key:
        raise ValueError("TTS not configured. Run '.venv/bin/focu tts setup' or set OPENAI_API_KEY.")
    text = Path(input_path).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("TTS input is empty")
    # Speech API has an input-size limit. Fail clearly rather than truncate a podcast.
    if len(text) > 4000:
        raise ValueError("TTS input exceeds 4000 characters; chunking is not implemented yet")
    payload = json.dumps({"model": model, "voice": voice, "input": text,
                          "response_format": "mp3"}).encode("utf-8")
    request = urllib.request.Request(API_URL, data=payload, method="POST",
                                     headers={"Authorization": "Bearer " + key,
                                              "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            audio = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"TTS provider returned HTTP {exc.code}") from None
    except urllib.error.URLError:
        raise RuntimeError("TTS provider network request failed") from None
    if not audio:
        raise RuntimeError("TTS provider returned empty audio")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(audio)
    return {"status": "generated", "output": str(output), "bytes": len(audio)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Focu opt-in TTS setup and synthesis")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("setup")
    gen = sub.add_parser("synthesize")
    gen.add_argument("--input", required=True)
    gen.add_argument("--output", required=True)
    gen.add_argument("--voice", default="alloy")
    args = parser.parse_args(argv)
    try:
        result = (status() if args.command == "status" else setup() if args.command == "setup"
                  else synthesize(args.input, args.output, voice=args.voice))
        print(json.dumps(result))
        return 0
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
