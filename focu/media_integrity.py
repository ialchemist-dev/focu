"""Validate MP3 duration against the *decoded* audio, not just metadata.

MP3 Xing/VBR headers can advertise a much longer duration than the file
actually decodes after a truncated download. SHA256 checks only prove copied
bytes were unchanged, not that those bytes are complete.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
import shutil
import subprocess


class MediaIntegrityError(ValueError):
    pass


def inspect_mp3(path: str | Path, *, timeout_seconds: int = 120) -> dict:
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise MediaIntegrityError("Audio is missing or a symlink")
    size = path.stat().st_size
    if size < 512 or size > 300 * 1024 * 1024:
        raise MediaIntegrityError("Audio is empty, implausibly small, or over 300 MB")
    if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
        raise MediaIntegrityError("ffprobe and ffmpeg are required for audio validation")
    try:
        metadata = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration,format_name:stream=codec_name,codec_type",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30, check=True)
        info = json.loads(metadata.stdout)
        fmt = info["format"]
        duration = float(fmt["duration"])
        if (not math.isfinite(duration) or duration <= 0
                or "mp3" not in fmt.get("format_name", "").split(",")):
            raise MediaIntegrityError("Not a valid MP3 container")
        streams = info.get("streams", [])
        if not any(s.get("codec_type") == "audio" and
                   s.get("codec_name") == "mp3" for s in streams):
            raise MediaIntegrityError("MP3 audio stream not detected")

        # The progress channel reports the decoded output presentation clock.
        # Avoid parsing human-readable log lines, which vary by ffmpeg locale.
        decoded = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-v", "error", "-xerror",
             "-i", str(path), "-map", "0:a:0", "-f", "null", "-",
             "-progress", "pipe:1"],
            capture_output=True, text=True, timeout=timeout_seconds, check=True)
        clocks = re.findall(r"^out_time_us=(\d+)$", decoded.stdout, re.M)
        if not clocks:
            raise MediaIntegrityError("Could not determine the decoded audio duration")
        decoded_seconds = int(clocks[-1]) / 1_000_000
        if not math.isfinite(decoded_seconds) or decoded_seconds <= 0:
            raise MediaIntegrityError("No decodable audio output")
        # Allow encoder delay and small container rounding, but not missing
        # minutes hidden behind stale Xing/VBR metadata.
        tolerance = max(1.5, duration * 0.03)
        if abs(decoded_seconds - duration) > tolerance:
            raise MediaIntegrityError(
                f"MP3 duration mismatch: metadata {duration:.1f}s, "
                f"actual decoded {decoded_seconds:.1f}s")
        return {"metadata_duration_seconds": round(duration, 3),
                "decoded_duration_seconds": round(decoded_seconds, 3),
                "size_bytes": size, "verified": True}
    except MediaIntegrityError:
        raise
    except (subprocess.SubprocessError, KeyError, ValueError,
            json.JSONDecodeError) as exc:
        raise MediaIntegrityError(
            "MP3 metadata/decode failed: " + type(exc).__name__) from exc




def transcode_ios_cbr(source: str | Path, target: str | Path) -> dict:
    """Create an isolated 128 kb/s mono CBR MP3 for embedded iOS players.

    Experimental compatibility option, *not* proof that WKWebView will emit
    audible output. Preserve the source MP3 and validate complete decoded
    duration on both sides before committing a published artifact.
    """
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve() or target.is_symlink():
        raise MediaIntegrityError("CBR output must be a distinct regular file")
    original = inspect_mp3(source)
    try:
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-y",
             "-i", str(source), "-map", "0:a:0", "-vn",
             "-c:a", "libmp3lame", "-b:a", "128k",
             "-ar", "44100", "-ac", "1", "-write_xing", "0",
             "-id3v2_version", "3", str(target)],
            capture_output=True, text=True, check=True, timeout=600)
        converted = inspect_mp3(target)
        if abs(converted["decoded_duration_seconds"] -
               original["decoded_duration_seconds"]) > max(
                   1.5, original["decoded_duration_seconds"] * 0.01):
            raise MediaIntegrityError("CBR transform changed decoded duration")
        return {"source_audit": original, "published_audit": converted,
                "profile": "mp3_cbr_128k_mono_44100"}
    except (subprocess.SubprocessError, OSError) as exc:
        raise MediaIntegrityError("iOS CBR transform failed: " +
                                  type(exc).__name__) from exc

def main(argv=None) -> int:
    """Audit existing private delivery MP3 files before publishing to Muse."""
    import argparse
    parser = argparse.ArgumentParser(description="Audit actual MP3 decoded durations")
    parser.add_argument("--deliveries", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Optional JSON audit report")
    args = parser.parse_args(argv)
    if not args.deliveries.is_dir():
        parser.error("Delivery directory not found")
    results = []
    for path in sorted(args.deliveries.glob("*/podcast.mp3")):
        try:
            result = {"delivery": path.parent.name, "status": "pass",
                      **inspect_mp3(path)}
        except (MediaIntegrityError, OSError) as exc:
            result = {"delivery": path.parent.name, "status": "fail",
                      "error": str(exc)}
        results.append(result)
    report = {"audited": len(results), "failed": sum(x["status"] == "fail" for x in results),
              "results": results}
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
