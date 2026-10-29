"""Small, stdlib-only Open Notebook podcast API adapter.

The host agent performs research. Open Notebook generates audio from approved
content and named profiles. No credentials or source content are logged.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:5055"
MAX_CONTENT_BYTES = 2_000_000


class OpenNotebookClient:
    def __init__(self, base_url: str | None = None, password: str | None = None,
                 timeout: float = 30):
        self.base_url = (base_url or os.getenv("OPEN_NOTEBOOK_URL") or DEFAULT_URL).rstrip("/")
        parsed = urllib.parse.urlsplit(self.base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("OPEN_NOTEBOOK_URL must be a plain HTTP(S) base URL")
        self.password = password if password is not None else os.getenv("OPEN_NOTEBOOK_PASSWORD", "")
        self.timeout = timeout

    def request(self, method: str, path: str, data: dict | None = None,
                *, binary: bool = False):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Invalid API path")
        headers = {"Accept": "application/json"}
        if self.password:
            headers["Authorization"] = "Bearer " + self.password
        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Open Notebook returned HTTP {exc.code} for {path}") from None
        except urllib.error.URLError:
            raise RuntimeError("Cannot connect to Open Notebook. Check OPEN_NOTEBOOK_URL and start its API/worker.") from None
        if binary:
            return payload
        try:
            return json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            raise RuntimeError("Open Notebook returned invalid JSON") from None

    def doctor(self) -> dict:
        health = self.request("GET", "/health")
        episode_profiles = self.request("GET", "/api/episode-profiles")
        speaker_profiles = self.request("GET", "/api/speaker-profiles")
        if not isinstance(episode_profiles, list) or not isinstance(speaker_profiles, list):
            raise RuntimeError("Open Notebook profile endpoints returned unexpected data")
        return {"health": health, "episode_profiles": [p.get("name") for p in episode_profiles],
                "speaker_profiles": [p.get("name") for p in speaker_profiles],
                "ready_for_generation": bool(episode_profiles and speaker_profiles),
                "worker_status": "not_verified"}

    def generate(self, *, episode_name: str, episode_profile: str, speaker_profile: str,
                 content: str, briefing_suffix: str | None = None) -> dict:
        if not all(isinstance(x, str) and x.strip() for x in
                   (episode_name, episode_profile, speaker_profile, content)):
            raise ValueError("Episode name, both profile names, and content are required")
        if len(content.encode("utf-8")) > MAX_CONTENT_BYTES:
            raise ValueError("Podcast input exceeds the 2 MB safety limit")
        body = {"episode_name": episode_name, "episode_profile": episode_profile,
                "speaker_profile": speaker_profile, "content": content}
        if briefing_suffix:
            body["briefing_suffix"] = briefing_suffix
        result = self.request("POST", "/api/podcasts/generate", body)
        if not isinstance(result, dict) or not result.get("job_id"):
            raise RuntimeError("Open Notebook did not return a podcast job ID")
        return result

    def job(self, job_id: str) -> dict:
        return self.request("GET", "/api/podcasts/jobs/" + urllib.parse.quote(job_id, safe=""))

    def episodes(self) -> list:
        result = self.request("GET", "/api/podcasts/episodes")
        if not isinstance(result, list):
            raise RuntimeError("Expected list of episodes")
        return result

    def download(self, episode_id: str, output: Path) -> dict:
        if not episode_id:
            raise ValueError("Episode ID required")
        path = "/api/podcasts/episodes/" + urllib.parse.quote(episode_id, safe="") + "/audio"
        audio = self.request("GET", path, binary=True)
        if not audio:
            raise RuntimeError("Empty audio response")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(audio)
        return {"status": "downloaded", "output": str(output), "bytes": len(audio)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="focu podcast", description="Open Notebook podcast handoff")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    generate = sub.add_parser("generate")
    generate.add_argument("--content-file", required=True)
    generate.add_argument("--episode-name", required=True)
    generate.add_argument("--episode-profile", required=True)
    generate.add_argument("--speaker-profile", required=True)
    generate.add_argument("--briefing-suffix")
    job = sub.add_parser("job")
    job.add_argument("job_id")
    sub.add_parser("episodes")
    download = sub.add_parser("download")
    download.add_argument("episode_id")
    download.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        client = OpenNotebookClient()
        if args.command == "doctor":
            result = client.doctor()
        elif args.command == "generate":
            content = Path(args.content_file).read_text(encoding="utf-8")
            result = client.generate(episode_name=args.episode_name,
                episode_profile=args.episode_profile, speaker_profile=args.speaker_profile,
                content=content, briefing_suffix=args.briefing_suffix)
        elif args.command == "job":
            result = client.job(args.job_id)
        elif args.command == "episodes":
            result = client.episodes()
        else:
            result = client.download(args.episode_id, Path(args.output))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
