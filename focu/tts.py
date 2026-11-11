"""Opt-in OpenAI speech synthesis with local, private credential onboarding.

No network call occurs during setup. The host agent must request consent before
invoking interactive setup; this module cannot force a native Muse dialog.

Synthesis has two entry points sharing one provider seam (_request_speech):
``synthesize`` keeps the original single-request behavior (scripts up to
MAX_INPUT_CHARS), while ``synthesize_long`` chunks longer scripts at
paragraph/sentence boundaries, synthesizes the chunks in order with the same
voice/model, and concatenates them into one MP3 with normalized
chunk-boundary silences. A failed chunk aborts the whole synthesis and no
partial MP3 is left behind.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_CONFIG = Path("data/tts-config.json")
API_URL = "https://api.openai.com/v1/audio/speech"
# The Speech API rejects inputs above this size; longer scripts are chunked.
MAX_INPUT_CHARS = 4000
# Target silence between concatenated chunks: long enough to hear the break,
# short enough that chunked narration does not feel stalled.
BOUNDARY_GAP_SECONDS = 0.7
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


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


def _api_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY") or _read_config().get("api_key")


def _request_speech(text: str, *, key: str, model: str, voice: str) -> bytes:
    """The single provider seam: one Speech API request for one text input."""
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
    return audio


def synthesize(input_path: str | Path, output_path: str | Path, *, model: str = "gpt-4o-mini-tts",
               voice: str = "alloy") -> dict:
    key = _api_key()
    if not key:
        raise ValueError("TTS not configured. Run '.venv/bin/focu tts setup' or set OPENAI_API_KEY.")
    text = Path(input_path).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("TTS input is empty")
    # Speech API has an input-size limit. Fail clearly rather than truncate a podcast.
    if len(text) > MAX_INPUT_CHARS:
        raise ValueError("TTS input exceeds 4000 characters; long-form chunking "
                         "is available via synthesize-long")
    audio = _request_speech(text, key=key, model=model, voice=voice)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(audio)
    return {"status": "generated", "output": str(output), "bytes": len(audio)}


def _split_long_piece(piece: str, limit: int) -> list[str]:
    """Split one over-limit paragraph at sentence, then word, boundaries."""
    sentences = [s for s in _SENTENCE_BOUNDARY.split(piece) if s.strip()]
    pieces, current = [], ""
    for sentence in sentences:
        if len(sentence) > limit:
            if current:
                pieces.append(current)
                current = ""
            rest = sentence
            while len(rest) > limit:
                cut = rest.rfind(" ", 0, limit + 1)
                if cut <= 0:
                    cut = limit
                pieces.append(rest[:cut].strip())
                rest = rest[cut:].strip()
            current = rest
        elif not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= limit:
            current = current + " " + sentence
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return [p for p in pieces if p]


def chunk_script(text: str, limit: int = MAX_INPUT_CHARS) -> list[str]:
    """Split a script into provider-sized chunks without breaking sentences.

    Paragraphs are packed greedily; a paragraph that alone exceeds the limit
    is split at sentence boundaries (then word boundaries) by
    _split_long_piece. Order is preserved and every chunk is non-empty and
    within the limit.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    chunks, current = [], ""
    for paragraph in paragraphs:
        if len(paragraph) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_piece(paragraph, limit))
        elif not current:
            current = paragraph
        elif len(current) + 2 + len(paragraph) <= limit:
            current = current + "\n\n" + paragraph
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks


def _trim_boundary_silence(source: Path, target: Path) -> None:
    """Decode to WAV with leading/trailing silence trimmed (areverse trick)."""
    trim = ("silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.1,"
            "areverse,"
            "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.1,"
            "areverse")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source),
                    "-af", trim, "-ar", "44100", "-ac", "1", str(target)],
                   check=True, capture_output=True, timeout=300)


def _concatenate(chunk_paths: list[Path], output: Path, work: Path,
                 gap_seconds: float = BOUNDARY_GAP_SECONDS) -> None:
    """Join chunk MP3s with a fixed, short silence gap at each boundary.

    Each chunk's own leading/trailing silence is trimmed first, so the only
    pause at a boundary is the inserted gap (target ~0.7s, never the sum of
    two provider pauses). A chunk that trims to nothing falls back to its
    untrimmed decode.
    """
    gap = work / "gap.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "anullsrc=r=44100:cl=mono", "-t", str(gap_seconds), str(gap)],
                   check=True, capture_output=True, timeout=60)
    sequence = []
    for index, chunk in enumerate(chunk_paths):
        trimmed = work / f"chunk-{index:03d}.wav"
        try:
            _trim_boundary_silence(chunk, trimmed)
            if trimmed.stat().st_size <= 200:  # header only: nothing audible left
                raise RuntimeError("chunk trimmed to silence")
        except (subprocess.SubprocessError, OSError, RuntimeError):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(chunk),
                            "-ar", "44100", "-ac", "1", str(trimmed)],
                           check=True, capture_output=True, timeout=300)
        if index:
            sequence.append(gap)
        sequence.append(trimmed)
    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{path}'\n" for path in sequence), encoding="utf-8")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(listing), "-codec:a", "libmp3lame", "-b:a", "128k",
                     "-ar", "44100", "-ac", "1", "-write_xing", "0",
                    str(output)], check=True, capture_output=True, timeout=600)


def synthesize_long(input_path: str | Path, output_path: str | Path, *,
                    model: str = "gpt-4o-mini-tts", voice: str = "alloy",
                    speech_fn=None) -> dict:
    """Synthesize scripts of any length via chunking (see module docstring).

    ``speech_fn`` is the provider seam for tests and host adapters: it takes
    one chunk of text and returns MP3 bytes. The default is the OpenAI Speech
    API through _request_speech with the configured key. Any chunk failure
    aborts the synthesis; the output file is replaced only on full success,
    so a failed run never leaves a partial MP3.
    """
    text = Path(input_path).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("TTS input is empty")
    if speech_fn is None and len(text) <= MAX_INPUT_CHARS:
        result = synthesize(input_path, output_path, model=model, voice=voice)
        return {**result, "chunks": 1, "long_form": False}
    if speech_fn is None:
        key = _api_key()
        if not key:
            raise ValueError("TTS not configured. Run '.venv/bin/focu tts setup' or set OPENAI_API_KEY.")
        speech_fn = lambda chunk: _request_speech(chunk, key=key, model=model, voice=voice)
    chunks = chunk_script(text)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".focu-tts-", dir=output.parent) as temp:
        work = Path(temp)
        chunk_paths = []
        total_bytes = 0
        for index, chunk in enumerate(chunks):
            audio = speech_fn(chunk)
            if not audio:
                raise RuntimeError("TTS provider returned empty audio")
            path = work / f"part-{index:03d}.mp3"
            path.write_bytes(audio)
            chunk_paths.append(path)
            total_bytes += len(audio)
        staged = work / "combined.mp3"
        if len(chunk_paths) == 1:
            staged = chunk_paths[0]
        else:
            _concatenate(chunk_paths, staged, work)
        final = work / "final.mp3"
        final.write_bytes(staged.read_bytes())
        os.replace(final, output)
    return {"status": "generated", "output": str(output), "bytes": total_bytes,
            "chunks": len(chunks), "long_form": len(chunks) > 1}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Focu opt-in TTS setup and synthesis")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("setup")
    gen = sub.add_parser("synthesize")
    gen.add_argument("--input", required=True)
    gen.add_argument("--output", required=True)
    gen.add_argument("--voice", default="alloy")
    long_gen = sub.add_parser("synthesize-long",
                              help="chunked long-form synthesis for scripts over 4000 characters")
    long_gen.add_argument("--input", required=True)
    long_gen.add_argument("--output", required=True)
    long_gen.add_argument("--voice", default="alloy")
    args = parser.parse_args(argv)
    try:
        result = (status() if args.command == "status" else setup() if args.command == "setup"
                  else synthesize_long(args.input, args.output, voice=args.voice)
                  if args.command == "synthesize-long"
                  else synthesize(args.input, args.output, voice=args.voice))
        print(json.dumps(result))
        return 0
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
