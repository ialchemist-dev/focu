import hashlib
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import FewError
from .identity import source_url, stable_id

KNOWN_TYPES = {"rss", "blog", "youtube", "x", "linkedin"}


def load_config(path):
    import yaml
    try:
        cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as ex:
        raise FewError(f"cannot load config {path}: {ex}") from ex
    if not isinstance(cfg, dict):
        raise FewError("config must be a YAML mapping")
    if cfg.get("version", 1) not in (1, 2):
        raise FewError("supported config versions: 1 and 2")
    cfg.setdefault("timezone", "UTC")
    cfg.setdefault("output_mode", "audio")
    if cfg["output_mode"] not in {"audio", "text_only"}:
        raise FewError("output_mode must be audio or text_only")
    try:
        ZoneInfo(cfg["timezone"])
    except (ZoneInfoNotFoundError, TypeError, ValueError) as ex:
        raise FewError("timezone must be a valid IANA name") from ex
    channels = cfg.get("channels", [])
    sources = cfg.get("sources", [])
    if not isinstance(channels, list) or not isinstance(sources, list):
        raise FewError("channels and sources must be lists")
    ids = set()
    for ch in channels:
        if not isinstance(ch, dict) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", str(ch.get("id", ""))):
            raise FewError("channel id must be a safe filename component")
        if ch["id"] in ids:
            raise FewError("duplicate channel id")
        ids.add(ch["id"])
        for key, default in [("max_minutes", 12), ("words_per_minute", 150)]:
            ch.setdefault(key, default)
            if isinstance(ch[key], bool) or not isinstance(ch[key], (int, float)) or ch[key] <= 0:
                raise FewError(f"{key} must be positive")
    if not ids:
        raise FewError("define at least one channel")
    names, source_ids = set(), set()
    for src in sources:
        if not isinstance(src, dict):
            raise FewError("each source must be a mapping")
        if "enabled" in src and not isinstance(src["enabled"], bool):
            raise FewError("source enabled must be a boolean")
        # Disabled placeholders are deliberately permitted to lack a locator.
        if src.get("enabled", True) is False:
            continue
        if src.get("type") not in KNOWN_TYPES:
            raise FewError(f"unknown source type: {src.get('type')}")
        if not isinstance(src.get("name"), str) or not src["name"].strip() or src["name"] in names:
            raise FewError("enabled source names must be non-empty and unique")
        if src.get("channel") not in ids:
            raise FewError(f"unknown channel for {src['name']}")
        for key, default in [("max_items_per_day", 5), ("retention_days", 7)]:
            src.setdefault(key, default)
            if isinstance(src[key], bool) or not isinstance(src[key], int) or src[key] <= 0:
                raise FewError(f"{src['name']}: {key} must be a positive integer")
        src.setdefault("priority", 1)
        if isinstance(src["priority"], bool) or not isinstance(src["priority"], (int, float)) or src["priority"] <= 0:
            raise FewError("source priority must be positive")
        try:
            src["canonical_url"] = source_url(src)
        except (KeyError, TypeError, ValueError, AttributeError) as ex:
            raise FewError(f"missing/invalid locator for {src['name']}: {ex}") from ex
        src["source_id"] = stable_id("src", src["canonical_url"])
        if src["source_id"] in source_ids:
            raise FewError("duplicate source identity; merge into one subscription")
        if src["type"] == "rss" and not src.get("feed_url"):
            raise FewError("RSS requires feed_url independently of canonical_url")
        names.add(src["name"])
        source_ids.add(src["source_id"])
    # A broken TTS command can be repaired without invalidating frozen content.
    content_cfg = {k: v for k, v in cfg.items() if k not in {"tts_argv"}}
    cfg["config_hash"] = hashlib.sha256(json.dumps(content_cfg, sort_keys=True).encode()).hexdigest()
    return cfg


def enabled_sources(cfg):
    return [s for s in cfg.get("sources", []) if s.get("enabled", True)]
