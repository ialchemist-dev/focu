"""Curated source packs: catalog, validation, preview, install, update,
show, uninstall, restore, refresh-check.

A source pack is a versioned, curator-signed list of sources (schema v1,
``schemas/source-pack.schema.json``). This module is the bridge between the
reader-side pack world (``focu/source_packs/*.json``, ``ReaderStore``
semantics: exact-version pinning, dedupe by canonical locator, unsubscribe
preserves shared sources) and the daily pipeline registry (``sources.yaml``,
gated by :func:`focu.daily.config.load_config`).

Design contract (backend design, wave 1):

- Install is one command; everything judgment-shaped (what will be added,
  what was skipped and why, what it costs in attention) is computed before
  the write and shown as a preview.
- Provenance lives in ``packs-installed.json`` beside ``sources.yaml``,
  never inside it; the manifest joins to the registry through the loader's
  own ``stable_id`` identities.
- Fail closed, degrade loudly: a pack that fails validation installs
  nothing; a feed that fails its liveness check installs disabled with the
  failure recorded in its notes.
- Apply is backup -> temp file -> re-validate through ``load_config()`` ->
  atomic rename. Uninstall mirrors ``ReaderStore`` unsubscribe semantics;
  restore is the byte-level escape hatch.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request, urlopen

import yaml

from focu.daily import identity
from focu.daily.config import KNOWN_TYPES, load_config
from focu.daily.errors import FewError
from focu.intents import utcnow
from xml.etree import ElementTree as ET

from focu.source_collection import parse_feed

PACKS_DIR = Path(__file__).with_name("source_packs")
MANIFEST_NAME = "packs-installed.json"
SCHEMA_VERSION = 1
STALE_DAYS = 180
# Cadence-vs-value flags (self-iteration Q4). A source at or above
# HIGH_VOLUME_POSTS_PER_MONTH publishes roughly five times a week: in a
# daily briefing that is a near-daily attention tax, not an occasional
# item. A single source at or above DOMINANT_SHARE of a pack whose total
# is at least DOMINANT_MIN_POSTS_PER_MONTH means installing the pack
# mostly means subscribing to that one source (the geothermal pack's
# ThinkGeoEnergy wire: 78 of ≈92 posts/month, measured 2026-11-17).
# Both flags are preview warnings only — nothing is capped, demoted or
# excluded; the preview is the judgment surface and the user decides
# (the Q6 dedupe-warning precedent). Dominance alone does not flag at
# low absolute volume: a weekly newsletter that is 70% of a ≈6/month
# people pack (Import AI in the Anthropic pack) is the pack working as
# intended, not a tax.
HIGH_VOLUME_POSTS_PER_MONTH = 20
DOMINANT_SHARE = 0.5
DOMINANT_MIN_POSTS_PER_MONTH = 20
# The publishing catalog's owner, used only as the flagged default for
# legacy packs that predate the curator field (design section 3.4).
DEFAULT_CURATOR = {"name": "AI Praxis Lab Source Library",
                   "url": "https://aipraxislab.com/sources/"}

PACK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
CHANNEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$")
DATE_TEXT = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL_FIELDS = ("homepage", "site_url", "feed_url", "affiliation_evidence",
              "profile_url", "company_page")
LOCATOR_KEYS = ("feed_url", "site_url", "channel_id", "handle", "username",
                "profile_url", "company_page")


def _is_date(value) -> bool:
    if not isinstance(value, str) or not DATE_TEXT.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_nonneg_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _tracking_params(url: str) -> list[str]:
    return [k for k, _ in parse_qsl(urlsplit(url).query, keep_blank_values=True)
            if k.lower().startswith("utm_") or k.lower() in identity.TRACKING]


def _url_error(url) -> str | None:
    """Hygiene verdict for one pack URL (design section 6, rules 3-4)."""
    if not isinstance(url, str) or not url.strip():
        return "must be a non-empty URL string"
    parts = urlsplit(url.strip())
    if parts.scheme != "https":
        return "must use HTTPS"
    if not parts.hostname:
        return "must name a host"
    if parts.username or parts.password:
        return "must not contain credentials"
    bad = _tracking_params(url)
    if bad:
        return "carries tracking parameter(s): " + ", ".join(sorted(set(bad)))
    return None


def normalize_pack(raw):
    """Fold legacy aliases into canonical v1 fields.

    ``name`` -> ``title``, ``categories`` -> ``tags``, ``site_url`` ->
    ``homepage`` (with ``site_url`` re-emitted alongside ``homepage``,
    because the current reader code path reads ``site_url`` directly).
    Both forms present with different values is an error. Returns
    ``(pack, warnings)``; raises ValueError on alias disagreement.
    """
    if not isinstance(raw, dict):
        raise ValueError("pack must be a JSON object")
    pack = copy.deepcopy(raw)
    warnings: list[str] = []
    # title/name are the same datum in two spellings: disagreement is an error.
    if "title" in pack and "name" in pack and pack["title"] != pack["name"]:
        raise ValueError("pack fields 'title' and legacy alias 'name' disagree")
    if "title" not in pack and "name" in pack:
        pack["title"] = pack["name"]
    pack.pop("name", None)
    # categories are display labels, tags are canonical slugs: the shipped
    # packs carry both with different values, so categories folds into tags
    # only when tags is absent; it is never an agreement error.
    if "tags" not in pack and "categories" in pack:
        pack["tags"] = pack.pop("categories")
    sources = pack.get("sources")
    if isinstance(sources, list):
        for src in sources:
            if not isinstance(src, dict):
                continue
            if ("homepage" in src and "site_url" in src
                    and src["homepage"] != src["site_url"]):
                raise ValueError(
                    f"source {src.get('id', '?')!r}: 'homepage' and legacy "
                    "alias 'site_url' disagree")
            if "homepage" not in src and "site_url" in src:
                src["homepage"] = src["site_url"]
            if "homepage" in src:
                src["site_url"] = src["homepage"]
    if "curator" not in pack:
        pack["curator"] = dict(DEFAULT_CURATOR)
        warnings.append("curator missing; defaulted to the publishing "
                        "catalog owner (legacy pack)")
    return pack, warnings


def _validate_source(src, errors, warnings, *, new_pack, today):
    if not isinstance(src, dict):
        errors.append("each source must be an object")
        return
    sid = src.get("id")
    label = f"source {sid!r}" if isinstance(sid, str) else "source"
    if not isinstance(sid, str) or not SOURCE_ID.fullmatch(sid):
        errors.append(f"{label}: id must match ^[a-z0-9][a-z0-9-]{{0,63}}$")
    if not isinstance(src.get("name"), str) or not src["name"].strip():
        errors.append(f"{label}: name must be a non-empty string")
    if src.get("type") not in KNOWN_TYPES:
        errors.append(f"{label}: type must be one of {sorted(KNOWN_TYPES)}")
    if not isinstance(src.get("channel"), str) or not CHANNEL_ID.fullmatch(src.get("channel", "")):
        errors.append(f"{label}: channel must be a valid channel id")
    if not isinstance(src.get("platform"), str) or not src["platform"].strip():
        errors.append(f"{label}: platform must be a non-empty string")
    if not isinstance(src.get("enabled"), bool):
        errors.append(f"{label}: enabled must be a boolean")
    for field in URL_FIELDS:
        if src.get(field) is not None:
            err = _url_error(src[field])
            if err:
                errors.append(f"{label}: {field} {err}")
    if src.get("homepage") is None and src.get("feed_url") is None:
        errors.append(f"{label}: homepage is required unless the source "
                      "is feed-only (feed_url present)")
    cadence = src.get("cadence")
    if cadence is None:
        if new_pack:
            errors.append(f"{label}: cadence is required (with a stated basis)")
        else:
            warnings.append(f"{label}: cadence unknown (legacy pack)")
    elif not isinstance(cadence, dict):
        errors.append(f"{label}: cadence must be an object")
    else:
        if not _is_nonneg_number(cadence.get("posts_per_month")):
            errors.append(f"{label}: cadence.posts_per_month must be a number >= 0")
        if not isinstance(cadence.get("basis"), str) or not cadence["basis"].strip():
            errors.append(f"{label}: cadence.basis is required — an estimate "
                          "without a stated basis is not allowed")
        if not _is_date(cadence.get("as_of")):
            errors.append(f"{label}: cadence.as_of must be a YYYY-MM-DD date")
    if src.get("last_post_at") is not None and not _is_date(src["last_post_at"]):
        errors.append(f"{label}: last_post_at must be a YYYY-MM-DD date")
    if not _is_date(src.get("verified_at")):
        errors.append(f"{label}: verified_at must be a YYYY-MM-DD date")
    elif (today - date.fromisoformat(src["verified_at"])).days > STALE_DAYS:
        warnings.append(f"{label}: verified_at is more than {STALE_DAYS} days old")
    if src.get("max_items_per_day") is not None:
        value = src["max_items_per_day"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            errors.append(f"{label}: max_items_per_day must be an integer >= 1")
    for field in ("person", "org", "role", "affiliation_status", "readiness", "notes"):
        if src.get(field) is not None and not isinstance(src[field], str):
            errors.append(f"{label}: {field} must be a string")
    if src.get("enabled") is True:
        if src.get("type") == "rss" and not src.get("feed_url"):
            errors.append(f"{label}: an enabled rss source requires feed_url")
        else:
            try:
                identity.source_url(source_to_yaml_entry(src))
            except (KeyError, TypeError, ValueError, AttributeError) as ex:
                errors.append(f"{label}: enabled source lacks the locator "
                              f"its type requires ({ex})")


def validate_pack(raw, *, today=None):
    """Validate a pack dict against schema v1 and the design's rules.

    Returns ``{"valid", "errors", "warnings", "pack"}`` where ``pack`` is
    the alias-normalized form. Hard errors install nothing; warnings are
    surfaced in previews (design section 6).
    """
    today = today or date.today()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        pack, norm_warnings = normalize_pack(raw)
    except ValueError as ex:
        return {"valid": False, "errors": [str(ex)], "warnings": [], "pack": None}
    warnings.extend(norm_warnings)
    if pack.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not isinstance(pack.get("id"), str) or not PACK_ID.fullmatch(pack.get("id", "")):
        errors.append("id must match ^[a-z0-9][a-z0-9-]{1,63}$")
    if not isinstance(pack.get("version"), str) or not SEMVER.fullmatch(pack.get("version", "")):
        errors.append("version must be a semver string")
    for field in ("title", "description", "coverage"):
        if not isinstance(pack.get(field), str) or not pack[field].strip():
            errors.append(f"{field} must be a non-empty string")
    tags = pack.get("tags")
    if (not isinstance(tags, list) or not tags
            or not all(isinstance(t, str) and t for t in tags)):
        errors.append("tags must be a non-empty list of strings")
    curator = pack.get("curator")
    if (not isinstance(curator, dict) or not isinstance(curator.get("name"), str)
            or not curator["name"].strip()):
        errors.append("curator.name must be a non-empty string")
    elif curator.get("url") is not None:
        err = _url_error(curator["url"])
        if err:
            errors.append(f"curator.url {err}")
    if not _is_date(pack.get("verified_at")):
        errors.append("verified_at must be a YYYY-MM-DD date")
    elif (today - date.fromisoformat(pack["verified_at"])).days > STALE_DAYS:
        warnings.append(f"pack verified_at {pack['verified_at']} is more "
                        f"than {STALE_DAYS} days old")
    estimate = pack.get("attention_estimate")
    if estimate is not None and (
            not isinstance(estimate, dict)
            or not _is_nonneg_number(estimate.get("posts_per_month"))
            or not (isinstance(estimate.get("basis"), str) and estimate["basis"].strip())):
        errors.append("attention_estimate requires posts_per_month >= 0 "
                      "and a non-empty basis")
    sources = pack.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("sources must be a non-empty list")
        sources = []
    # Packs carrying a curator field are held to the full bar (cadence with
    # basis required); older packs get warnings instead (design section 3.4).
    new_pack = isinstance(raw, dict) and "curator" in raw
    seen_ids: set[str] = set()
    seen_identities: dict[str, str] = {}
    enabled_total = 0.0
    for src in sources:
        _validate_source(src, errors, warnings, new_pack=new_pack, today=today)
        if not isinstance(src, dict):
            continue
        sid = src.get("id")
        if isinstance(sid, str):
            if sid in seen_ids:
                errors.append(f"duplicate source id in pack: {sid}")
            seen_ids.add(sid)
        ident = _entry_identity(source_to_yaml_entry(src)) if sid else None
        if ident is not None:
            if ident in seen_identities:
                errors.append(
                    f"sources {seen_identities[ident]!r} and {sid!r} resolve "
                    f"to the same identity ({ident}); the curator dedupes, "
                    "not the user")
            seen_identities[ident] = sid
        cadence = src.get("cadence")
        if (src.get("enabled") is True and isinstance(cadence, dict)
                and _is_nonneg_number(cadence.get("posts_per_month"))):
            enabled_total += cadence["posts_per_month"]
    if (isinstance(estimate, dict)
            and _is_nonneg_number(estimate.get("posts_per_month"))
            and abs(estimate["posts_per_month"] - enabled_total) > 0.05):
        warnings.append(
            f"attention_estimate says {estimate['posts_per_month']} "
            f"posts/month but enabled cadences sum to {enabled_total:g}")
    unverified = pack.get("unverified")
    if unverified is not None:
        if not isinstance(unverified, list):
            errors.append("unverified must be a list")
        else:
            for cand in unverified:
                if not isinstance(cand, dict):
                    errors.append("each unverified candidate must be an object")
                    continue
                label = f"unverified candidate {cand.get('name', '?')!r}"
                if not isinstance(cand.get("name"), str) or not cand["name"].strip():
                    errors.append(f"{label}: name must be a non-empty string")
                if not isinstance(cand.get("reason"), str) or not cand["reason"].strip():
                    errors.append(f"{label}: reason is required — which "
                                  "verification test failed")
                if not _is_date(cand.get("checked_at")):
                    errors.append(f"{label}: checked_at must be a YYYY-MM-DD date")
                if cand.get("homepage") is not None:
                    err = _url_error(cand["homepage"])
                    if err:
                        errors.append(f"{label}: homepage {err}")
    return {"valid": not errors, "errors": errors, "warnings": warnings,
            "pack": pack}


def source_to_yaml_entry(source, *, notes_suffix=None):
    """Map a normalized pack source onto a ``sources.yaml`` entry.

    Only loader-meaningful fields are written (design section 4.3):
    provenance and curation metadata stay in the pack and the manifest.
    """
    entry = {"name": source["name"], "type": source["type"],
             "channel": source["channel"]}
    for key in LOCATOR_KEYS:
        if source.get(key):
            entry[key] = source[key]
    if source.get("homepage") and "site_url" not in entry:
        entry["site_url"] = source["homepage"]
    entry["enabled"] = bool(source.get("enabled", True))
    if source.get("max_items_per_day") is not None:
        entry["max_items_per_day"] = source["max_items_per_day"]
    notes = source.get("notes") or ""
    if notes_suffix:
        notes = (notes + " " + notes_suffix).strip() if notes else notes_suffix
    if notes:
        entry["notes"] = notes
    return entry


def _entry_identity(entry):
    try:
        return identity.stable_id("src", identity.source_url(entry))
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _entry_locator(entry):
    try:
        return identity.source_url(entry)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _locator_set(entry):
    """Every canonical locator an entry names (feed, site, homepage).

    Identity (``_entry_identity``) uses exactly one of these, chosen by
    type — which is how the same publication can hold two identities
    (an rss entry keyed by its feed, a blog entry keyed by its site).
    The planner compares the full sets to spot that case.
    """
    locators = set()
    for key in ("feed_url", "site_url", "homepage"):
        value = entry.get(key) if isinstance(entry, dict) else None
        if isinstance(value, str) and value:
            try:
                locators.add(identity.canonical_url(value))
            except (TypeError, ValueError, AttributeError):
                continue
    return locators


def _host_set(locators):
    hosts = set()
    for url in locators:
        host = urlsplit(url).hostname
        if host:
            hosts.add(host)
    return hosts


# ---------------------------------------------------------------------------
# Liveness (design section 6, rules 8-9). Network results are recorded,
# never raised: a dead feed is data for the plan, not an exception.

def _bounded_fetch_prefix(url):
    """Fetch with source_collection's discipline; return (final_url, bytes,
    oversized). Same UA, timeout and 2 MB read bound as ``_bounded_fetch``,
    but an over-cap response is returned (truncated at the cap) with
    ``oversized`` set instead of raised: refresh-check needs to tell a
    valid feed that outgrew the cap apart from a dead one."""
    req = Request(url, headers={"User-Agent": "Focu/0.2 (+explicit source collection)"})
    with urlopen(req, timeout=15) as response:
        data = response.read(2_000_001)
        return response.geturl(), data, len(data) > 2_000_000


def _bounded_fetch(url):
    """Fetch with source_collection's discipline; return (final_url, bytes)."""
    final_url, data, oversized = _bounded_fetch_prefix(url)
    if oversized:
        raise ValueError("response exceeds 2 MB")
    return final_url, data


def _parse_item_date(text):
    if not text:
        return None
    parsed = None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed.date().isoformat()


def check_liveness(pack, *, fetch=None):
    """Feed and homepage liveness for a normalized pack, keyed by source id."""
    fetch = fetch or _bounded_fetch
    results = {}
    for src in pack.get("sources", []):
        result = {}
        if src.get("enabled") is True and src.get("feed_url"):
            try:
                final_url, data = fetch(src["feed_url"])
                records = parse_feed(data, final_url)
                dates = [d for d in (_parse_item_date(r.get("published_at"))
                                     for r in records) if d]
                result["feed"] = {"status": "live", "items": len(records),
                                  "newest": max(dates) if dates else None}
            except HTTPError as ex:
                result["feed"] = {"status": "dead", "error": f"HTTP {ex.code}"}
            except (ValueError, ET.ParseError) as ex:
                # parse_feed raises ET.ParseError (a SyntaxError, not a
                # ValueError) when a feed URL answers with an HTML
                # interstitial instead of XML; that is data, not a crash.
                result["feed"] = {"status": "not_a_feed", "error": str(ex)}
            except (URLError, TimeoutError, OSError) as ex:
                result["feed"] = {"status": "unreachable", "error": str(ex)}
        if src.get("homepage"):
            try:
                fetch(src["homepage"])
                result["homepage"] = {"status": "live"}
            except HTTPError as ex:
                result["homepage"] = {"status": "dead", "error": f"HTTP {ex.code}"}
            except Exception as ex:  # homepage liveness is advisory only
                result["homepage"] = {"status": "unreachable", "error": str(ex)}
        if result:
            results[src["id"]] = result
    return results


# ---------------------------------------------------------------------------
# Install manifest (design section 4.3): provenance beside sources.yaml.

def manifest_path(config_path) -> Path:
    return Path(config_path).with_name(MANIFEST_NAME)


def load_manifest(config_path):
    path = manifest_path(config_path)
    if not path.is_file():
        return {"packs": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as ex:
        raise ValueError(f"cannot read install manifest {path}: {ex}") from ex
    if not isinstance(data, dict) or not isinstance(data.get("packs"), list):
        raise ValueError(f"install manifest {path} is malformed")
    return data


def _write_manifest(config_path, manifest):
    path = manifest_path(config_path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def _load_registry(config_path):
    """Return (cfg, raw_doc, existing) for the current registry.

    ``existing`` aligns the loader's view with the raw YAML entries:
    enabled sources carry the ``source_id`` ``load_config`` computed;
    disabled ones get their would-be identity computed directly, so a
    deliberately disabled entry still dedupes.
    """
    config_path = Path(config_path)
    if not config_path.is_file():
        raise ValueError(f"config not found: {config_path}")
    try:
        cfg = load_config(config_path)
    except FewError as ex:
        raise ValueError(f"existing registry does not load: {ex}") from ex
    raw_doc = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    raw_sources = raw_doc.get("sources") or []
    loaded_sources = cfg.get("sources", [])
    existing = []
    for idx, raw_src in enumerate(raw_sources):
        if not isinstance(raw_src, dict):
            continue
        loaded = loaded_sources[idx] if idx < len(loaded_sources) else {}
        sid = loaded.get("source_id") or _entry_identity(raw_src)
        existing.append({"name": raw_src.get("name"), "source_id": sid,
                         "locator": _entry_locator(raw_src),
                         "enabled": raw_src.get("enabled", True) is not False,
                         "entry": raw_src})
    return cfg, raw_doc, existing


def _apply_config(config_path, raw_doc, *, backup_stamp):
    """Backup -> temp write -> load_config gate -> atomic rename.

    On any failure the original file is left untouched. Returns the
    backup path (kept even on failure: it is a faithful pre-change copy).
    """
    config_path = Path(config_path)
    backup = config_path.with_name(f"{config_path.name}.bak-{backup_stamp}")
    counter = 1
    while backup.exists():
        backup = config_path.with_name(
            f"{config_path.name}.bak-{backup_stamp}-{counter}")
        counter += 1
    backup.write_bytes(config_path.read_bytes())
    fd, tmp_name = tempfile.mkstemp(dir=str(config_path.parent),
                                    prefix=config_path.name + ".",
                                    suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(raw_doc, fh, sort_keys=False, allow_unicode=True)
        try:
            load_config(tmp_name)
        except FewError as ex:
            raise ValueError(
                "merged config failed validation; original left "
                f"untouched: {ex}") from ex
        os.replace(tmp_name, config_path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return backup


def _backup_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ---------------------------------------------------------------------------
# Install planning and application (design section 4.2).

def plan_install(pack, config_path, *, channel_override=None, liveness=None):
    """Pure install plan: reads the registry and manifest, writes nothing.

    ``pack`` must be normalized (see validate_pack). ``liveness`` is the
    output of check_liveness, keyed by pack source id.
    """
    cfg, _raw_doc, existing = _load_registry(config_path)
    channels = {ch["id"] for ch in cfg.get("channels", [])}
    manifest = load_manifest(config_path)
    providers: dict[str, set[str]] = {}
    for record in manifest["packs"]:
        for entry in record.get("entries", []):
            if entry.get("source_id"):
                providers.setdefault(entry["source_id"], set()).add(record["pack_id"])
    existing_by_id = {e["source_id"]: e for e in existing if e["source_id"]}
    existing_names = {e["name"]: e for e in existing if e["name"]}
    # Cross-locator index (self-iteration Q6): identity is type-dependent,
    # so the same publication can reappear under a different identity via
    # a different locator (feed vs site, trailing-slash variant). Track
    # every locator and host already claimed — by the registry and by
    # sources planned earlier in this same pack — so the preview can
    # warn instead of silently subscribing twice.
    claimed: list[dict] = []
    for e in existing:
        locators = _locator_set(e["entry"])
        if e.get("locator"):
            locators.add(e["locator"])
        claimed.append({"name": e["name"], "source_id": e["source_id"],
                        "locators": locators, "hosts": _host_set(locators),
                        "where": "registry"})
    plan = {"pack": {"id": pack["id"], "title": pack["title"],
                     "version": pack["version"]},
            "adds": [], "duplicates": [], "errors": [], "warnings": [],
            "unverified": [{"name": c.get("name"), "reason": c.get("reason")}
                           for c in pack.get("unverified", [])],
            "attention_posts_per_month": 0.0, "attention_unknown": [],
            "preexisting_source_ids": sorted(existing_by_id)}
    planned_ids: dict[str, str] = {}
    planned_names: dict[str, str] = {}
    for src in pack["sources"]:
        channel = channel_override or src["channel"]
        if channel not in channels:
            plan["errors"].append(
                f"source {src['id']!r}: channel {channel!r} does not exist "
                f"in {Path(config_path).name} (channels: "
                f"{', '.join(sorted(channels))}); create it or pass --channel")
            continue
        live = (liveness or {}).get(src["id"], {}).get("feed")
        enabled = bool(src.get("enabled", True))
        suffix = None
        if enabled and live is not None and live.get("status") != "live":
            enabled = False
            suffix = (f"Installed disabled: feed liveness check at install "
                      f"time returned {live['status']} "
                      f"({live.get('error', 'no detail')}).")
        entry = source_to_yaml_entry(src, notes_suffix=suffix)
        entry["channel"] = channel
        entry["enabled"] = enabled
        sid = _entry_identity(entry)
        if sid is not None and sid in planned_ids:
            plan["errors"].append(
                f"source {src['id']!r}: duplicates pack source "
                f"{planned_ids[sid]!r} after channel mapping")
            continue
        if sid is not None and sid in existing_by_id:
            plan["duplicates"].append(
                {"pack_source_id": src["id"], "name": src["name"],
                 "source_id": sid,
                 "existing_name": existing_by_id[sid]["name"],
                 "locator": existing_by_id[sid]["locator"],
                 "existing_enabled": existing_by_id[sid]["enabled"],
                 "provided_by": sorted(providers.get(sid, set())) or ["manual"]})
            continue
        name = src["name"]
        if name in existing_names:
            other = existing_names[name]
            if enabled or other["enabled"]:
                plan["errors"].append(
                    f"source {src['id']!r}: name {name!r} already exists in "
                    "the registry with a different identity; rename one of "
                    "them (the loader requires enabled names to be unique)")
                continue
            plan["warnings"].append(
                f"source {src['id']!r}: disabled entry shares the name "
                f"{name!r} with a disabled registry entry")
        if name in planned_names:
            plan["errors"].append(
                f"source {src['id']!r}: name {name!r} collides with pack "
                f"source {planned_names[name]!r}")
            continue
        if sid is not None:
            planned_ids[sid] = src["id"]
        planned_names[name] = src["id"]
        new_locators = _locator_set(src)
        new_locators |= _locator_set(entry)
        new_hosts = _host_set(new_locators)
        for other in claimed:
            if sid is not None and other["source_id"] == sid:
                continue
            if new_locators & other["locators"] or new_hosts & other["hosts"]:
                plan["warnings"].append(
                    f"source {src['id']!r}: shares a site with "
                    f"{other['where']} source {other['name']!r} but under "
                    f"a different identity — installing both would "
                    f"subscribe the same publication twice; if these are "
                    f"genuinely different publications on a shared host, "
                    f"ignore this warning")
                break
        claimed.append({"name": name, "source_id": sid,
                        "locators": new_locators, "hosts": new_hosts,
                        "where": "pack"})
        cadence = src.get("cadence") if isinstance(src.get("cadence"), dict) else None
        ppm = cadence.get("posts_per_month") if cadence else None
        plan["adds"].append(
            {"pack_source_id": src["id"], "name": name, "source_id": sid,
             "locator": _entry_locator(entry), "enabled": enabled,
             "entry": entry, "cadence_posts_per_month": ppm,
             "last_post_at": src.get("last_post_at"), "liveness": live})
        if enabled:
            if ppm is None:
                plan["attention_unknown"].append(name)
            else:
                plan["attention_posts_per_month"] = round(
                    plan["attention_posts_per_month"] + ppm, 4)
    plan["warnings"].extend(cadence_warnings(
        [(add["name"], add["cadence_posts_per_month"],
          add["entry"].get("max_items_per_day"))
         for add in plan["adds"] if add["enabled"]],
        total=plan["attention_posts_per_month"]))
    return plan


def install_pack(raw_pack, config_path, *, channel_override=None,
                 dry_run=False, check_feeds=True, fetch=None,
                 pack_sha256=None, confirm=None, today=None):
    """Validate, plan and (unless dry_run or confirm declines) install.

    ``confirm`` is called with the plan before anything is written; a
    false return aborts the apply. Returns the report dict.
    """
    report = validate_pack(raw_pack, today=today)
    if not report["valid"]:
        raise ValueError("pack validation failed: "
                         + "; ".join(report["errors"]))
    pack = report["pack"]
    liveness = check_liveness(pack, fetch=fetch) if check_feeds else None
    plan = plan_install(pack, config_path, channel_override=channel_override,
                        liveness=liveness)
    plan["warnings"] = report["warnings"] + plan["warnings"]
    if plan["errors"]:
        raise ValueError("install plan failed: " + "; ".join(plan["errors"]))
    result = {"plan": plan, "dry_run": dry_run, "applied": False}
    if dry_run:
        return result
    if confirm is not None and not confirm(plan):
        result["aborted"] = True
        return result
    config_path = Path(config_path)
    _cfg, raw_doc, _existing = _load_registry(config_path)
    if not isinstance(raw_doc.get("sources", []), list):
        raise ValueError("config sources must be a list")
    raw_doc["sources"] = list(raw_doc.get("sources") or []) + [
        add["entry"] for add in plan["adds"]]
    backup = _apply_config(config_path, raw_doc, backup_stamp=_backup_stamp())
    manifest = load_manifest(config_path)
    entries = []
    for add in plan["adds"]:
        entries.append({"source_id": add["source_id"], "name": add["name"],
                        "locator": add["locator"], "enabled": add["enabled"],
                        "added": True, "entry": add["entry"]})
    for dup in plan["duplicates"]:
        entries.append({"source_id": dup["source_id"], "name": dup["name"],
                        "locator": dup.get("locator"),
                        "enabled": dup.get("existing_enabled", True),
                        "added": False})
    manifest["packs"].append(
        {"pack_id": pack["id"], "version": pack["version"],
         "sha256": pack_sha256, "installed_at": utcnow(),
         "backup": backup.name,
         "preexisting_source_ids": plan["preexisting_source_ids"],
         "entries": entries})
    _write_manifest(config_path, manifest)
    result.update({"applied": True, "backup": str(backup),
                   "manifest": str(manifest_path(config_path))})
    return result


# ---------------------------------------------------------------------------
# Uninstall and restore (design section 4.4).

def _manifest_entry_matches(entry, raw_src, sid) -> bool:
    """Does a manifest entry describe this registry source?

    Identity match when both sides have one; locator-less disabled
    entries fall back to equality with the exact dict install wrote.
    """
    if entry.get("source_id") is not None and sid is not None:
        return entry["source_id"] == sid
    if entry.get("source_id") is None and sid is None:
        return entry.get("entry") == raw_src
    return False


def uninstall_pack(pack_id, config_path, *, dry_run=False, confirm=None):
    """Remove exactly what a pack added, preserving shared sources.

    A source survives when another installed pack also provides it, or
    when it was present before this pack was installed. Manual entries
    are never removed.
    """
    config_path = Path(config_path)
    manifest = load_manifest(config_path)
    records = [r for r in manifest["packs"] if r.get("pack_id") == pack_id]
    if not records:
        raise ValueError(f"pack is not installed: {pack_id}")
    other_providers: dict = {}
    for record in manifest["packs"]:
        if record.get("pack_id") == pack_id:
            continue
        for entry in record.get("entries", []):
            key = entry.get("source_id") or ("name", entry.get("name"))
            other_providers.setdefault(key, set()).add(record["pack_id"])
    preexisting = set(records[0].get("preexisting_source_ids", []))
    added = [e for r in records for e in r.get("entries", []) if e.get("added")]
    provided = [e for r in records for e in r.get("entries", [])
                if not e.get("added")]
    _cfg, raw_doc, existing = _load_registry(config_path)
    existing_by_entry = {id(e["entry"]): e for e in existing}
    removes, keeps, kept_sources = [], [], []
    for raw_src in raw_doc.get("sources") or []:
        if not isinstance(raw_src, dict):
            kept_sources.append(raw_src)
            continue
        info = existing_by_entry.get(id(raw_src), {})
        sid = info.get("source_id")
        match, was_added = None, False
        for entry in added:
            if _manifest_entry_matches(entry, raw_src, sid):
                match, was_added = entry, True
                break
        if match is None:
            for entry in provided:
                if _manifest_entry_matches(entry, raw_src, sid):
                    match = entry
                    break
        if match is None:
            kept_sources.append(raw_src)
            continue
        if not was_added:
            # The pack listed this source but did not install it (it was
            # already present); uninstall reports it and leaves it alone.
            reason = ("was present before this pack was installed"
                      if sid is not None and sid in preexisting
                      else "provided by another entry; this pack only "
                           "listed it")
            keeps.append({"name": raw_src.get("name"), "reason": reason})
            kept_sources.append(raw_src)
            continue
        if sid is not None and sid in preexisting:
            keeps.append({"name": raw_src.get("name"),
                          "reason": "was present before this pack was installed"})
            kept_sources.append(raw_src)
            continue
        providers = other_providers.get(
            sid if sid is not None else ("name", raw_src.get("name")))
        if providers:
            keeps.append({"name": raw_src.get("name"),
                          "reason": "also provided by "
                                    + ", ".join(sorted(providers))})
            kept_sources.append(raw_src)
            continue
        removes.append({"name": raw_src.get("name"), "source_id": sid})
    report = {"pack_id": pack_id, "removes": removes, "keeps": keeps,
              "dry_run": dry_run, "applied": False}
    if dry_run:
        return report
    if confirm is not None and not confirm(report):
        report["aborted"] = True
        return report
    if removes:
        raw_doc["sources"] = kept_sources
        backup = _apply_config(config_path, raw_doc,
                               backup_stamp=_backup_stamp())
        report["backup"] = str(backup)
    manifest["packs"] = [r for r in manifest["packs"]
                         if r.get("pack_id") != pack_id]
    _write_manifest(config_path, manifest)
    report["applied"] = True
    return report


def list_backups(config_path):
    config_path = Path(config_path)
    return sorted(config_path.parent.glob(config_path.name + ".bak-*"))


def restore_backup(config_path, backup=None, *, dry_run=False, confirm=None):
    """Byte-level rollback to a timestamped backup (the escape hatch).

    The preview names what the rollback discards (a name-level diff
    against the manifest era); the manifest itself is left unchanged and
    the report says so.
    """
    config_path = Path(config_path)
    if backup is not None:
        chosen = Path(backup)
        if not chosen.is_file():
            raise ValueError(f"backup not found: {backup}")
    else:
        candidates = list_backups(config_path)
        if not candidates:
            raise ValueError(f"no backups found for {config_path.name}")
        chosen = candidates[-1]
    try:
        load_config(chosen)
    except FewError as ex:
        raise ValueError(f"backup does not load; refusing to restore: {ex}") from ex

    def names(path):
        doc = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return [s.get("name") for s in doc.get("sources", [])
                if isinstance(s, dict)]

    current_names = names(config_path) if config_path.is_file() else []
    backup_names = names(chosen)
    report = {"backup": str(chosen), "dry_run": dry_run, "applied": False,
              "removed_names": [n for n in current_names if n not in backup_names],
              "added_names": [n for n in backup_names if n not in current_names],
              "manifest_unchanged": True}
    if dry_run:
        return report
    if confirm is not None and not confirm(report):
        report["aborted"] = True
        return report
    config_path.write_bytes(chosen.read_bytes())
    report["applied"] = True
    return report


# ---------------------------------------------------------------------------
# Catalog and show (design section 4.1): read-only views over the bundled
# packs and the install manifest.

def _attention_total(pack):
    """Enabled sources' cadence sum, plus the names it cannot price."""
    total = 0.0
    unknown = []
    for src in pack.get("sources", []):
        if src.get("enabled") is not True:
            continue
        cadence = src.get("cadence")
        ppm = cadence.get("posts_per_month") if isinstance(cadence, dict) else None
        if _is_nonneg_number(ppm):
            total += ppm
        else:
            unknown.append(src.get("name"))
    return round(total, 4), unknown


def cadence_warnings(items, total=None):
    """Q4 cadence-vs-value flags over enabled sources with known cadence.

    ``items`` is an iterable of (name, posts_per_month, max_items_per_day)
    triples for ENABLED sources only; unknown cadences are skipped (they
    are reported separately as unknown, never flagged on a guess).
    ``total`` is the attention total the items are shares of; when omitted
    it is the sum of the known cadences. Returns one warning per flagged
    source, loudest first. Warnings only: this function decides nothing.
    """
    known = [(name, ppm, cap) for name, ppm, cap in items
             if _is_nonneg_number(ppm)]
    if total is None:
        total = round(sum(ppm for _name, ppm, _cap in known), 4)
    warnings = []
    for name, ppm, cap in sorted(known, key=lambda row: -row[1]):
        share = (ppm / total) if total else 0.0
        dominant = (total >= DOMINANT_MIN_POSTS_PER_MONTH
                    and share >= DOMINANT_SHARE)
        high_volume = ppm >= HIGH_VOLUME_POSTS_PER_MONTH
        if not (dominant or high_volume):
            continue
        if dominant:
            text = (f"source {name!r} dominates this pack: "
                    f"≈{ppm:g} posts/month is {share:.0%} of its "
                    f"≈{total:g} posts/month — installing the pack mostly "
                    f"means subscribing to this one source")
        else:
            text = (f"source {name!r} is high-volume: ≈{ppm:g} posts/month "
                    f"({share:.0%} of this pack's ≈{total:g} posts/month) "
                    f"— it will claim briefing space most days")
        if cap is not None:
            text += f" (curator cap: {cap}/day)"
        text += ("; the choice stays yours — install as-is, or ask the "
                 "curator for a lower max_items_per_day")
        warnings.append(text)
    return warnings


def pack_catalog(config_path=None):
    """Every bundled pack, with install state from the manifest.

    Read-only. ``config_path`` locates the manifest beside the registry;
    without one (or without a manifest) every pack reports uninstalled.
    The latest manifest record per pack is its installed state.
    """
    manifest = (load_manifest(config_path) if config_path is not None
                else {"packs": []})
    installed = {}
    for record in manifest["packs"]:
        if record.get("pack_id"):
            installed[record["pack_id"]] = record
    packs = []
    for path in sorted(PACKS_DIR.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            packs.append({"file": path.name, "error": "unreadable"})
            continue
        if not isinstance(raw, dict):
            packs.append({"file": path.name, "error": "pack must be a JSON object"})
            continue
        report = validate_pack(raw)
        pack = report["pack"]
        if pack is None:
            packs.append({"file": path.name, "id": raw.get("id"),
                          "error": "; ".join(report["errors"])})
            continue
        total, unknown = _attention_total(pack)
        record = installed.get(pack["id"])
        packs.append(
            {"id": pack["id"], "title": pack["title"],
             "version": pack["version"], "verified_at": pack["verified_at"],
             "file": path.name, "sources": len(pack["sources"]),
             "enabled_sources": sum(1 for s in pack["sources"]
                                    if s.get("enabled") is True),
             "attention_posts_per_month": total,
             "attention_unknown": unknown,
             "valid": report["valid"], "errors": report["errors"],
             "warnings": report["warnings"],
             "installed": record is not None,
             "installed_version": record.get("version") if record else None,
             "installed_at": record.get("installed_at") if record else None,
             "update_available": bool(
                 record and record.get("version") != pack["version"])})
    return {"packs": packs,
            "manifest": (str(manifest_path(config_path))
                         if config_path is not None else None)}


def show_pack(raw_pack, config_path=None, *, check_feeds=True, fetch=None,
              pack_sha256=None, today=None):
    """Full detail for one pack: membership, cadence, unverified, state.

    Feed status comes from a live check when ``check_feeds`` (the same
    bounded fetch as install); otherwise each source reports ``unchecked``
    (has a feed) or ``no_feed``. Install state is read from the manifest
    beside ``config_path`` when one is given.
    """
    report = validate_pack(raw_pack, today=today)
    if not report["valid"]:
        raise ValueError("pack validation failed: "
                         + "; ".join(report["errors"]))
    pack = report["pack"]
    liveness = check_liveness(pack, fetch=fetch) if check_feeds else {}
    sources = []
    for src in pack["sources"]:
        live = liveness.get(src["id"], {})
        feed = live.get("feed")
        if feed:
            feed_status = feed["status"]
        elif src.get("feed_url"):
            feed_status = "unchecked"
        else:
            feed_status = "no_feed"
        cadence = src.get("cadence") if isinstance(src.get("cadence"), dict) else {}
        sources.append(
            {"id": src["id"], "name": src["name"], "type": src["type"],
             "channel": src["channel"], "platform": src.get("platform"),
             "person": src.get("person"), "org": src.get("org"),
             "role": src.get("role"),
             "homepage": src.get("homepage"), "feed_url": src.get("feed_url"),
             "enabled": bool(src.get("enabled", True)),
             "feed_status": feed_status, "liveness": live or None,
             "cadence_posts_per_month": cadence.get("posts_per_month"),
             "cadence_basis": cadence.get("basis"),
             "last_post_at": src.get("last_post_at"),
             "verified_at": src.get("verified_at"),
             "readiness": src.get("readiness"), "notes": src.get("notes"),
             "max_items_per_day": src.get("max_items_per_day")})
    total, unknown = _attention_total(pack)
    installed = {"installed": False}
    if config_path is not None:
        manifest = load_manifest(config_path)
        records = [r for r in manifest["packs"]
                   if r.get("pack_id") == pack["id"]]
        if records:
            record = records[-1]
            installed = {"installed": True,
                         "installed_version": record.get("version"),
                         "available_version": pack["version"],
                         "update_available":
                             record.get("version") != pack["version"],
                         "installed_at": record.get("installed_at")}
    return {"pack": {"id": pack["id"], "title": pack["title"],
                     "version": pack["version"],
                     "description": pack["description"],
                     "tags": pack["tags"], "curator": pack["curator"],
                     "coverage": pack["coverage"],
                     "verified_at": pack["verified_at"],
                     "sha256": pack_sha256,
                     "attention_estimate": pack.get("attention_estimate")},
            "sources": sources,
            "unverified": [{"name": c.get("name"), "reason": c.get("reason"),
                            "checked_at": c.get("checked_at"),
                            "homepage": c.get("homepage")}
                           for c in pack.get("unverified", [])],
            "attention_posts_per_month": total,
            "attention_unknown": unknown,
            "warnings": report["warnings"] + cadence_warnings(
                [(s["name"], s["cadence_posts_per_month"],
                  s["max_items_per_day"]) for s in sources if s["enabled"]],
                total=total),
            "installed": installed}


# ---------------------------------------------------------------------------
# Refresh check: packs rot — feeds die, feeds outgrow the fetch cap,
# authors move. This is a REPORT ONLY: it re-probes every source's feed
# through the same bounded fetch as validation and diffs what it finds
# against the pack's recorded state (last_post_at, verified_at). It
# writes nothing — refreshing a pack stays a curator's research act,
# never an automatic rewrite.
#
# Feed status taxonomy:
#   live        fetched and parsed as RSS/Atom
#   not_a_feed  fetched, but the body does not parse as a feed (an HTML
#               interstitial, malformed XML, oversized non-feed content)
#   http_error  the host answered with an HTTP error status
#   unreachable no answer at all from here (DNS/connect/reset/timeout) —
#               a property of this vantage point as much as of the feed
#   oversized   the response begins as a feed document but exceeds the
#               2 MB fetch cap, so Focu cannot consume it (a Substack
#               full-text feed measured ~2.87 MB live, 2026-11-17)
#   no_feed     the source records no feed_url; nothing to probe

_FEED_ROOT = re.compile(rb"<(rss|feed|rdf:RDF)(?=[\s>])")


def _looks_like_feed_prefix(data):
    """Does this (possibly truncated) body begin as a feed document?

    Skips a BOM, an XML prolog, a DOCTYPE and leading comments, then
    asks whether the root element is rss / Atom feed / rdf:RDF. Used
    only for over-cap responses, where a full parse is impossible.
    """
    prefix = data[:8192]
    if prefix.startswith(b"\xef\xbb\xbf"):
        prefix = prefix[3:]
    prefix = prefix.lstrip()
    for opener, closer in ((b"<?xml", b"?>"), (b"<!DOCTYPE", b">"),
                           (b"<!--", b"-->")):
        if prefix.startswith(opener):
            end = prefix.find(closer)
            if end == -1:
                return False
            prefix = prefix[end + len(closer):].lstrip()
    return bool(_FEED_ROOT.match(prefix))


def _probe_feed(url, fetch):
    """One bounded feed probe; every outcome is data, never an exception."""
    try:
        result = fetch(url)
    except HTTPError as ex:
        return {"status": "http_error", "error": f"HTTP {ex.code}"}
    except (URLError, TimeoutError, OSError) as ex:
        return {"status": "unreachable", "error": str(ex)}
    except ValueError as ex:
        # An injected fetch with _bounded_fetch's contract raises on
        # oversize instead of returning the prefix; the cap is still
        # the finding, the prefix is just unavailable for sniffing.
        if "exceeds" in str(ex):
            return {"status": "oversized",
                    "error": "response exceeds the 2 MB fetch cap"}
        return {"status": "not_a_feed", "error": str(ex)}
    if len(result) == 3:
        final_url, data, oversized = result
    else:  # check_liveness-style (final_url, bytes) fixtures
        final_url, data = result
        oversized = len(data) > 2_000_000
    if oversized:
        if _looks_like_feed_prefix(data):
            return {"status": "oversized",
                    "error": "feed document exceeds the 2 MB fetch cap"}
        return {"status": "not_a_feed",
                "error": "response exceeds the 2 MB fetch cap and does "
                         "not begin as a feed document"}
    try:
        records = parse_feed(data, final_url)
    except (ValueError, ET.ParseError) as ex:
        return {"status": "not_a_feed", "error": str(ex)}
    dates = [d for d in (_parse_item_date(r.get("published_at"))
                         for r in records) if d]
    return {"status": "live", "items": len(records),
            "newest": max(dates) if dates else None}


def _age_days(value, today):
    if not _is_date(value):
        return None
    return (today - date.fromisoformat(value)).days


def _refresh_signals(src, feed, *, today, vantage_ok):
    """Stale signals for one source: current probe vs recorded state.

    An enabled source's feed health is a pack claim (it costs the user
    attention), so a broken enabled feed signals; a disabled source's
    feed state is already priced into the pack, so only resumed
    activity (newer items than recorded) signals there. Unreachable
    signals only when at least one other probe was answered — when
    nothing at all was reached, unreachability describes our vantage
    point, not the pack, and the verdict says so instead.
    """
    signals = []
    enabled = src.get("enabled") is True
    recorded = src.get("last_post_at")
    status = feed["status"]
    if status == "live":
        newest = feed.get("newest")
        if newest and (recorded is None or newest > recorded):
            detail = (f"feed's newest item {newest} is newer than the "
                      f"recorded last_post_at {recorded} — cadence "
                      "evidence has moved" if recorded else
                      f"pack records no last_post_at; the feed's "
                      f"newest item is {newest}")
            signals.append({"kind": "newer_items", "detail": detail})
        elif enabled and newest and recorded and newest < recorded:
            signals.append(
                {"kind": "newest_mismatch",
                 "detail": f"recorded last_post_at {recorded} is newer "
                           f"than the feed's newest item {newest} — "
                           "the record and the feed disagree"})
    elif enabled:
        kind = {"http_error": "feed_http_error",
                "not_a_feed": "feed_not_a_feed",
                "unreachable": "feed_unreachable",
                "oversized": "feed_oversized"}.get(status)
        if kind == "feed_unreachable" and not vantage_ok:
            kind = None
        if kind:
            detail = {"feed_http_error":
                      f"enabled feed now answers {feed.get('error')}",
                      "feed_not_a_feed":
                      f"enabled feed no longer parses as RSS/Atom: "
                      f"{feed.get('error')}",
                      "feed_unreachable":
                      f"enabled feed unreachable from here: "
                      f"{feed.get('error')}",
                      "feed_oversized":
                      "enabled feed is a valid feed document but "
                      "exceeds the 2 MB fetch cap; Focu cannot "
                      "consume it"}[kind]
            signals.append({"kind": kind, "detail": detail})
    verified_age = _age_days(src.get("verified_at"), today)
    if verified_age is not None and verified_age > STALE_DAYS:
        signals.append(
            {"kind": "verification_stale",
             "detail": f"source verified_at {src['verified_at']} is "
                       f"{verified_age} days old (stale after "
                       f"{STALE_DAYS})"})
    return signals


def refresh_check(raw_pack, config_path=None, *, fetch=None, today=None):
    """Re-verify one pack against the live web; report only, no writes.

    Every source with a feed_url is probed serially through the bounded
    fetch (an injectable ``fetch`` may return ``(final_url, bytes)`` or
    ``(final_url, bytes, oversized)``). The verdict is one line:
    ``current``, ``N stale signal(s)``, or ``unverifiable from here``
    (no probe was answered, or the pack has no feeds to probe).
    Install state is read from the manifest beside ``config_path``
    when one is given, exactly as in :func:`show_pack`.
    """
    today = today or date.today()
    fetch = fetch or _bounded_fetch_prefix
    report = validate_pack(raw_pack, today=today)
    if not report["valid"]:
        raise ValueError("pack validation failed: "
                         + "; ".join(report["errors"]))
    pack = report["pack"]
    probed = []
    for src in pack["sources"]:
        if src.get("feed_url"):
            feed = _probe_feed(src["feed_url"], fetch)
        else:
            feed = {"status": "no_feed"}
        probed.append((src, feed))
    answered = sum(1 for _src, feed in probed
                   if feed["status"] not in ("no_feed", "unreachable"))
    vantage_ok = answered > 0
    sources = []
    stale = 0
    for src, feed in probed:
        signals = _refresh_signals(src, feed, today=today,
                                   vantage_ok=vantage_ok)
        stale += len(signals)
        sources.append(
            {"id": src["id"], "name": src["name"],
             "enabled": bool(src.get("enabled", True)),
             "feed_url": src.get("feed_url"),
             "recorded_last_post_at": src.get("last_post_at"),
             "verified_at": src.get("verified_at"),
             "verified_age_days": _age_days(src.get("verified_at"), today),
             "feed": feed, "signals": signals})
    pack_signals = []
    pack_age = _age_days(pack.get("verified_at"), today)
    if pack_age is not None and pack_age > STALE_DAYS:
        pack_signals.append(
            {"kind": "verification_stale",
             "detail": f"pack verified_at {pack['verified_at']} is "
                       f"{pack_age} days old (stale after {STALE_DAYS})"})
        stale += 1
    if not vantage_ok:
        # Nothing answered (or nothing to probe): from here we cannot
        # tell a rotten pack from a healthy one, and the verdict must
        # not pretend otherwise.
        verdict = "unverifiable from here"
    elif stale:
        verdict = f"{stale} stale signal" + ("s" if stale != 1 else "")
    else:
        verdict = "current"
    installed = {"installed": False}
    if config_path is not None:
        manifest = load_manifest(config_path)
        records = [r for r in manifest["packs"]
                   if r.get("pack_id") == pack["id"]]
        if records:
            record = records[-1]
            installed = {"installed": True,
                         "installed_version": record.get("version"),
                         "available_version": pack["version"],
                         "update_available":
                             record.get("version") != pack["version"],
                         "installed_at": record.get("installed_at")}
    return {"pack": {"id": pack["id"], "title": pack["title"],
                     "version": pack["version"],
                     "verified_at": pack["verified_at"],
                     "verified_age_days": pack_age},
            "checked_at": today.isoformat(),
            "sources": sources, "signals": pack_signals,
            "stale_signals": stale, "verdict": verdict,
            "installed": installed}


def refresh_check_bundled(config_path=None, *, fetch=None, today=None):
    """Refresh-check every bundled pack; per-file failures are entries,
    not exceptions (the :func:`pack_catalog` precedent). Report only."""
    today = today or date.today()
    packs = []
    for path in sorted(PACKS_DIR.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            packs.append({"file": path.name, "error": "unreadable"})
            continue
        if not isinstance(raw, dict):
            packs.append({"file": path.name,
                          "error": "pack must be a JSON object"})
            continue
        try:
            report = refresh_check(raw, config_path, fetch=fetch,
                                   today=today)
        except ValueError as ex:
            packs.append({"file": path.name, "id": raw.get("id"),
                          "error": str(ex)})
            continue
        report["file"] = path.name
        packs.append(report)
    return {"packs": packs, "checked_at": today.isoformat()}


# ---------------------------------------------------------------------------
# Update (design section 7): explicit, pinned, previewed. The diff is
# computed against the manifest snapshot (the latest install record for
# the pack); removed sources are detached only when this pack solely
# provides them — the same ReaderStore rule uninstall applies.

def _planned_entry(src, channel, liveness):
    """The registry entry install/update would write for a pack source.

    Mirrors plan_install: an enabled source whose feed fails its
    liveness check is planned disabled with the failure in its notes.
    Returns (entry, enabled, live_feed_result).
    """
    live = (liveness or {}).get(src["id"], {}).get("feed")
    enabled = bool(src.get("enabled", True))
    suffix = None
    if enabled and live is not None and live.get("status") != "live":
        enabled = False
        suffix = (f"Installed disabled: feed liveness check at install "
                  f"time returned {live['status']} "
                  f"({live.get('error', 'no detail')}).")
    entry = source_to_yaml_entry(src, notes_suffix=suffix)
    entry["channel"] = channel
    entry["enabled"] = enabled
    return entry, enabled, live


def plan_update(pack, config_path, *, liveness=None, records=None):
    """Pure update plan: diff the installed snapshot against a new pack.

    ``pack`` must be normalized (see validate_pack). ``records`` is the
    manifest history for this pack; the latest record is the installed
    snapshot. Snapshot entries match new sources by loader identity
    first, then by name (a name match with a new identity is a locator
    change). Writes nothing.
    """
    cfg, _raw_doc, existing = _load_registry(config_path)
    channels = {ch["id"] for ch in cfg.get("channels", [])}
    manifest = load_manifest(config_path)
    if records is None:
        records = [r for r in manifest["packs"]
                   if r.get("pack_id") == pack["id"]]
    if not records:
        raise ValueError(f"pack is not installed: {pack['id']}")
    snapshot = records[-1]
    installed_version = snapshot.get("version")
    old_entries = list(snapshot.get("entries", []))
    first_preexisting = set(records[0].get("preexisting_source_ids", []))
    other_providers: dict = {}
    for record in manifest["packs"]:
        if record.get("pack_id") == pack["id"]:
            continue
        for entry in record.get("entries", []):
            key = entry.get("source_id") or ("name", entry.get("name"))
            other_providers.setdefault(key, set()).add(record["pack_id"])
    providers: dict[str, set[str]] = {}
    for record in manifest["packs"]:
        for entry in record.get("entries", []):
            if entry.get("source_id"):
                providers.setdefault(entry["source_id"], set()).add(
                    record["pack_id"])
    existing_by_id = {e["source_id"]: e for e in existing if e["source_id"]}
    existing_names = {e["name"]: e for e in existing if e["name"]}

    def registry_match(old):
        for e in existing:
            if _manifest_entry_matches(old, e["entry"], e["source_id"]):
                return e
        return None

    plan = {"pack": {"id": pack["id"], "title": pack["title"],
                     "version": pack["version"]},
            "installed_version": installed_version,
            "already_current": installed_version == pack["version"],
            "adds": [], "removes": [], "keeps": [], "changed": [],
            "unchanged": [], "duplicates": [],
            "unverified": [{"name": c.get("name"), "reason": c.get("reason")}
                           for c in pack.get("unverified", [])],
            "errors": [], "warnings": [],
            "attention_posts_per_month": 0.0, "attention_unknown": [],
            "preexisting_source_ids": sorted(existing_by_id)}
    if plan["already_current"]:
        return plan

    attention_items = []

    def note_attention(src, enabled):
        if not enabled:
            return
        cadence = src.get("cadence") if isinstance(src.get("cadence"), dict) else None
        ppm = cadence.get("posts_per_month") if cadence else None
        if ppm is None:
            plan["attention_unknown"].append(src["name"])
        else:
            plan["attention_posts_per_month"] = round(
                plan["attention_posts_per_month"] + ppm, 4)
            attention_items.append(
                (src["name"], ppm, src.get("max_items_per_day")))

    old_by_identity = {}
    old_by_name = {}
    for old in old_entries:
        if old.get("source_id"):
            old_by_identity.setdefault(old["source_id"], old)
        if old.get("name"):
            old_by_name.setdefault(old["name"], old)
    matched_old: set[int] = set()
    pending = []
    for src in pack["sources"]:
        channel = src["channel"]
        if channel not in channels:
            plan["errors"].append(
                f"source {src['id']!r}: channel {channel!r} does not exist "
                f"in {Path(config_path).name} (channels: "
                f"{', '.join(sorted(channels))}); create it or pass --channel")
            continue
        entry, enabled, live = _planned_entry(src, channel, liveness)
        sid = _entry_identity(entry)
        old = None
        identity_changed = False
        candidate = old_by_identity.get(sid) if sid is not None else None
        if candidate is not None and id(candidate) not in matched_old:
            old = candidate
        else:
            candidate = old_by_name.get(src["name"])
            if candidate is not None and id(candidate) not in matched_old:
                old = candidate
                identity_changed = True
        if old is None:
            pending.append((src, entry, enabled, live, sid))
            continue
        matched_old.add(id(old))
        if registry_match(old) is None:
            plan["keeps"].append(
                {"name": old.get("name"),
                 "reason": "installed entry no longer present in the registry"})
            pending.append((src, entry, enabled, live, sid))
            continue
        if identity_changed:
            if old.get("added"):
                plan["changed"].append(
                    {"pack_source_id": src["id"], "name": src["name"],
                     "old_source_id": old.get("source_id"),
                     "new_source_id": sid, "identity_changed": True,
                     "replace": True,
                     "old_locator": old.get("locator"),
                     "locator": _entry_locator(entry), "entry": entry,
                     "old_manifest_entry": old,
                     "cadence_posts_per_month":
                         (src.get("cadence") or {}).get("posts_per_month"),
                     "last_post_at": src.get("last_post_at"),
                     "liveness": live})
                note_attention(src, enabled)
            else:
                plan["keeps"].append(
                    {"name": src["name"],
                     "reason": "locator changed in the pack, but this pack "
                               "only listed the installed entry; left "
                               "unchanged"})
                plan["unchanged"].append(
                    {"pack_source_id": src["id"], "name": src["name"],
                     "source_id": old.get("source_id"),
                     "locator": old.get("locator"),
                     "enabled": old.get("enabled", True)})
            continue
        old_entry = old.get("entry")
        if old_entry is not None:
            if old_entry == entry:
                plan["unchanged"].append(
                    {"pack_source_id": src["id"], "name": src["name"],
                     "source_id": sid, "locator": _entry_locator(entry),
                     "enabled": enabled})
                note_attention(src, enabled)
            elif old.get("added"):
                plan["changed"].append(
                    {"pack_source_id": src["id"], "name": src["name"],
                     "old_source_id": old.get("source_id"),
                     "new_source_id": sid, "identity_changed": False,
                     "replace": True,
                     "old_locator": old.get("locator"),
                     "locator": _entry_locator(entry), "entry": entry,
                     "old_manifest_entry": old,
                     "cadence_posts_per_month":
                         (src.get("cadence") or {}).get("posts_per_month"),
                     "last_post_at": src.get("last_post_at"),
                     "liveness": live})
                note_attention(src, enabled)
            else:
                plan["keeps"].append(
                    {"name": src["name"],
                     "reason": "changed in the pack, but this pack only "
                               "listed the installed entry; left unchanged"})
                plan["unchanged"].append(
                    {"pack_source_id": src["id"], "name": src["name"],
                     "source_id": old.get("source_id"),
                     "locator": old.get("locator"),
                     "enabled": old.get("enabled", True)})
            continue
        # Snapshot entry without a written dict: it was a duplicate at
        # install time, so this pack never owned the registry entry.
        if (_entry_locator(entry) == old.get("locator")
                and enabled == old.get("enabled", True)):
            plan["unchanged"].append(
                {"pack_source_id": src["id"], "name": src["name"],
                 "source_id": old.get("source_id"),
                 "locator": old.get("locator"),
                 "enabled": old.get("enabled", True)})
            note_attention(src, enabled)
        else:
            plan["keeps"].append(
                {"name": src["name"],
                 "reason": "changed in the pack, but this pack only "
                           "listed the installed entry; left unchanged"})
            plan["unchanged"].append(
                {"pack_source_id": src["id"], "name": src["name"],
                 "source_id": old.get("source_id"),
                 "locator": old.get("locator"),
                 "enabled": old.get("enabled", True)})

    # Snapshot entries no new source claims: removals or keeps.
    freed_names = set()
    for old in old_entries:
        if id(old) in matched_old:
            continue
        name = old.get("name")
        sid = old.get("source_id")
        if registry_match(old) is None:
            plan["keeps"].append(
                {"name": name,
                 "reason": "no longer present in the registry"})
            continue
        if not old.get("added"):
            reason = ("was present before this pack was installed"
                      if sid is not None and sid in first_preexisting
                      else "provided by another entry; this pack only "
                           "listed it")
            plan["keeps"].append({"name": name, "reason": reason})
            continue
        if sid is not None and sid in first_preexisting:
            plan["keeps"].append(
                {"name": name,
                 "reason": "was present before this pack was installed"})
            continue
        shared = other_providers.get(
            sid if sid is not None else ("name", name))
        if shared:
            plan["keeps"].append(
                {"name": name,
                 "reason": "also provided by " + ", ".join(sorted(shared))})
            continue
        plan["removes"].append({"name": name, "source_id": sid,
                                "manifest_entry": old})
        freed_names.add(name)

    # New sources with no snapshot counterpart: adds, with install's
    # dedupe and name-collision rules against the surviving registry.
    planned_names: dict[str, str] = {}
    for src, entry, enabled, live, sid in pending:
        if sid is not None and sid in existing_by_id:
            plan["duplicates"].append(
                {"pack_source_id": src["id"], "name": src["name"],
                 "source_id": sid,
                 "existing_name": existing_by_id[sid]["name"],
                 "locator": existing_by_id[sid]["locator"],
                 "existing_enabled": existing_by_id[sid]["enabled"],
                 "provided_by": sorted(providers.get(sid, set())) or ["manual"]})
            continue
        name = src["name"]
        if name in existing_names and name not in freed_names:
            other = existing_names[name]
            if enabled or other["enabled"]:
                plan["errors"].append(
                    f"source {src['id']!r}: name {name!r} already exists in "
                    "the registry with a different identity; rename one of "
                    "them (the loader requires enabled names to be unique)")
                continue
            plan["warnings"].append(
                f"source {src['id']!r}: disabled entry shares the name "
                f"{name!r} with a disabled registry entry")
        if name in planned_names:
            plan["errors"].append(
                f"source {src['id']!r}: name {name!r} collides with pack "
                f"source {planned_names[name]!r}")
            continue
        planned_names[name] = src["id"]
        cadence = src.get("cadence") if isinstance(src.get("cadence"), dict) else None
        ppm = cadence.get("posts_per_month") if cadence else None
        plan["adds"].append(
            {"pack_source_id": src["id"], "name": name, "source_id": sid,
             "locator": _entry_locator(entry), "enabled": enabled,
             "entry": entry, "cadence_posts_per_month": ppm,
             "last_post_at": src.get("last_post_at"), "liveness": live})
        note_attention(src, enabled)
    plan["warnings"].extend(cadence_warnings(
        attention_items, total=plan["attention_posts_per_month"]))
    return plan


def update_pack(raw_pack, config_path, *, dry_run=False, check_feeds=True,
                fetch=None, pack_sha256=None, confirm=None, today=None):
    """Validate, diff and (unless dry_run or confirm declines) update.

    The installed version is the latest manifest record for the pack.
    An equal available version is reported ``already_current`` and
    changes nothing — no backup, no manifest write. Apply goes through
    the same backup -> temp write -> load_config gate -> atomic rename
    as install, and appends a manifest record for the new version, so
    history stays auditable and uninstall keeps working.
    """
    report = validate_pack(raw_pack, today=today)
    if not report["valid"]:
        raise ValueError("pack validation failed: "
                         + "; ".join(report["errors"]))
    pack = report["pack"]
    manifest = load_manifest(config_path)
    records = [r for r in manifest["packs"]
               if r.get("pack_id") == pack["id"]]
    if not records:
        raise ValueError(f"pack is not installed: {pack['id']}")
    installed_version = records[-1].get("version")
    if installed_version == pack["version"]:
        return {"already_current": True, "applied": False,
                "dry_run": dry_run,
                "pack": {"id": pack["id"], "title": pack["title"],
                         "version": pack["version"]},
                "installed_version": installed_version}
    liveness = check_liveness(pack, fetch=fetch) if check_feeds else None
    plan = plan_update(pack, config_path, liveness=liveness, records=records)
    plan["warnings"] = report["warnings"] + plan["warnings"]
    if plan["errors"]:
        raise ValueError("update plan failed: " + "; ".join(plan["errors"]))
    result = {"plan": plan, "dry_run": dry_run, "applied": False,
              "already_current": False}
    if dry_run:
        return result
    if confirm is not None and not confirm(plan):
        result["aborted"] = True
        return result
    config_path = Path(config_path)
    _cfg, raw_doc, existing = _load_registry(config_path)
    existing_by_entry = {id(e["entry"]): e for e in existing}
    raw_sources = list(raw_doc.get("sources") or [])

    def find_raw(manifest_entry):
        for raw_src in raw_sources:
            if not isinstance(raw_src, dict):
                continue
            info = existing_by_entry.get(id(raw_src), {})
            if _manifest_entry_matches(manifest_entry, raw_src,
                                       info.get("source_id")):
                return raw_src
        return None

    remove_ids = set()
    for item in plan["removes"]:
        target = find_raw(item["manifest_entry"])
        if target is not None:
            remove_ids.add(id(target))
    replacements = {}
    replaced = set()
    for index, item in enumerate(plan["changed"]):
        if not item["replace"]:
            continue
        target = find_raw(item["old_manifest_entry"])
        if target is not None:
            replacements[id(target)] = item["entry"]
            replaced.add(index)
    new_sources = []
    for raw_src in raw_sources:
        if id(raw_src) in remove_ids:
            continue
        new_sources.append(replacements.get(id(raw_src), raw_src))
    present_ids = {_entry_identity(s) for s in new_sources
                   if isinstance(s, dict)} - {None}
    for index, item in enumerate(plan["changed"]):
        # A changed source whose installed entry vanished between plan
        # and apply is appended like an add rather than dropped.
        if (item["replace"] and index not in replaced
                and item["new_source_id"] not in present_ids):
            new_sources.append(item["entry"])
            present_ids.add(item["new_source_id"])
    for add in plan["adds"]:
        if add["source_id"] is not None and add["source_id"] in present_ids:
            continue
        new_sources.append(add["entry"])
        present_ids.add(add["source_id"])
    raw_doc["sources"] = new_sources
    backup = _apply_config(config_path, raw_doc, backup_stamp=_backup_stamp())
    entries = []
    for add in plan["adds"]:
        entries.append({"source_id": add["source_id"], "name": add["name"],
                        "locator": add["locator"], "enabled": add["enabled"],
                        "added": True, "entry": add["entry"]})
    for item in plan["changed"]:
        if item["replace"]:
            entries.append({"source_id": item["new_source_id"],
                            "name": item["name"],
                            "locator": item["locator"],
                            "enabled": item["entry"].get("enabled", True),
                            "added": True, "entry": item["entry"]})
        # Changed-but-not-replaced sources are recorded below as
        # unchanged: the plan lists them in both "keeps" and "unchanged",
        # and the registry still holds the old entry.
    for item in plan["unchanged"]:
        entries.append({"source_id": item["source_id"], "name": item["name"],
                        "locator": item["locator"],
                        "enabled": item["enabled"], "added": False})
    for dup in plan["duplicates"]:
        entries.append({"source_id": dup["source_id"], "name": dup["name"],
                        "locator": dup.get("locator"),
                        "enabled": dup.get("existing_enabled", True),
                        "added": False})
    manifest = load_manifest(config_path)
    manifest["packs"].append(
        {"pack_id": pack["id"], "version": pack["version"],
         "sha256": pack_sha256, "installed_at": utcnow(),
         "backup": backup.name,
         "preexisting_source_ids": plan["preexisting_source_ids"],
         "entries": entries})
    _write_manifest(config_path, manifest)
    result.update({"applied": True, "backup": str(backup),
                   "manifest": str(manifest_path(config_path))})
    return result


# ---------------------------------------------------------------------------
# CLI: `focu pack ...` (thin argparse wrappers, like focu.reader / focu.daily).

def _load_pack_argument(argument):
    """Resolve a pack argument to (raw dict, sha256, origin description)."""
    path = Path(argument)
    if path.is_file():
        data = path.read_bytes()
        origin = str(path)
    elif argument.startswith("https://"):
        _final_url, data = _bounded_fetch(argument)
        origin = argument
    else:
        candidate = PACKS_DIR / (argument if argument.endswith(".json")
                                 else argument + ".json")
        if not candidate.is_file():
            raise ValueError(f"pack not found: {argument} (not a file, an "
                             "HTTPS URL, or a bundled pack id)")
        data = candidate.read_bytes()
        origin = str(candidate)
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as ex:
        raise ValueError(f"pack {origin} is not valid JSON: {ex}") from ex
    return raw, hashlib.sha256(data).hexdigest(), origin


def format_plan(plan) -> str:
    pack = plan["pack"]
    lines = [f"Pack {pack['id']} v{pack['version']} — {pack['title']}"]
    for add in plan["adds"]:
        state = "enabled" if add["enabled"] else "disabled"
        ppm = add["cadence_posts_per_month"]
        cadence = f"≈{ppm:g} posts/month" if ppm is not None else "cadence unknown"
        lines.append(f"  + {add['name']} ({state}, {cadence})")
    for dup in plan["duplicates"]:
        lines.append(f"  = {dup['name']} already present as "
                     f"{dup['existing_name']!r} (provided by "
                     f"{', '.join(dup['provided_by'])}); skipped")
    for cand in plan["unverified"]:
        lines.append(f"  ! excluded, unverified: {cand['name']} — {cand['reason']}")
    total = plan["attention_posts_per_month"]
    attention = f"Attention: adds ≈{total:g} posts/month"
    if plan["attention_unknown"]:
        attention += ("; cadence unknown for "
                      + ", ".join(plan["attention_unknown"]))
    lines.append(attention)
    for warning in plan["warnings"]:
        lines.append(f"  warning: {warning}")
    return "\n".join(lines)


def format_catalog(catalog) -> str:
    lines = []
    for item in catalog["packs"]:
        if item.get("error"):
            lines.append(f"{item.get('id') or item['file']}: "
                         f"error — {item['error']}")
            continue
        attention = f"≈{item['attention_posts_per_month']:g} posts/month"
        if item["attention_unknown"]:
            attention += ("; cadence unknown for "
                          + ", ".join(item["attention_unknown"]))
        state = "not installed"
        if item["installed"]:
            state = f"installed v{item['installed_version']}"
            if item["update_available"]:
                state += f"; update available → v{item['version']}"
        lines.append(f"{item['id']} v{item['version']} — {item['title']} "
                     f"(verified {item['verified_at']}; "
                     f"{item['sources']} sources; {attention}) [{state}]")
    return "\n".join(lines)


def format_show(report) -> str:
    pack = report["pack"]
    lines = [f"Pack {pack['id']} v{pack['version']} — {pack['title']}",
             f"  {pack['description']}",
             f"  curator: {pack['curator']['name']}; "
             f"verified {pack['verified_at']}; "
             f"tags: {', '.join(pack['tags'])}",
             f"  coverage: {pack['coverage']}"]
    installed = report["installed"]
    if installed.get("installed"):
        state = (f"  installed: v{installed['installed_version']} "
                 f"(at {installed['installed_at']})")
        if installed["update_available"]:
            state += f"; update available → v{installed['available_version']}"
        lines.append(state)
    else:
        lines.append("  installed: no")
    attention = f"  attention: ≈{report['attention_posts_per_month']:g} posts/month"
    if report["attention_unknown"]:
        attention += ("; cadence unknown for "
                      + ", ".join(report["attention_unknown"]))
    lines.append(attention)
    lines.append("  sources:")
    for src in report["sources"]:
        state = "enabled" if src["enabled"] else "disabled"
        ppm = src["cadence_posts_per_month"]
        cadence = (f"≈{ppm:g} posts/month" if ppm is not None
                   else "cadence unknown")
        lines.append(f"    - {src['name']} [{src['type']}/"
                     f"{src['platform']}, {state}, "
                     f"feed: {src['feed_status']}, {cadence}]")
        if src["feed_url"]:
            lines.append(f"        feed: {src['feed_url']}")
        if src["cadence_basis"]:
            lines.append(f"        cadence basis: {src['cadence_basis']}")
        if src["readiness"]:
            lines.append(f"        readiness: {src['readiness']}")
    if report["unverified"]:
        lines.append("  unverified (never installed):")
        for cand in report["unverified"]:
            lines.append(f"    ! {cand['name']} — {cand['reason']}")
    for warning in report["warnings"]:
        lines.append(f"  warning: {warning}")
    return "\n".join(lines)


def format_refresh(report) -> str:
    pack = report["pack"]
    lines = [f"Pack {pack['id']} v{pack['version']} — {pack['title']}",
             f"  verified {pack['verified_at']} "
             f"({pack['verified_age_days']} days ago); "
             f"checked {report['checked_at']}"]
    installed = report["installed"]
    if installed.get("installed"):
        state = f"  installed: v{installed['installed_version']}"
        if installed["update_available"]:
            state += f"; update available → v{installed['available_version']}"
        lines.append(state)
    for src in report["sources"]:
        feed = src["feed"]
        state = "enabled" if src["enabled"] else "disabled"
        detail = feed["status"]
        if feed["status"] == "live":
            detail += (f" ({feed['items']} items, "
                       f"newest {feed['newest']})")
        elif feed.get("error"):
            detail += f" — {feed['error']}"
        lines.append(f"  - {src['name']} [{state}] feed: {detail}")
        lines.append(f"      recorded last post: "
                     f"{src['recorded_last_post_at'] or 'none'}")
        for sig in src["signals"]:
            lines.append(f"      ! {sig['kind']}: {sig['detail']}")
    for sig in report["signals"]:
        lines.append(f"  ! {sig['kind']}: {sig['detail']}")
    lines.append(f"  verdict: {report['verdict']}")
    return "\n".join(lines)


def format_refresh_all(report) -> str:
    blocks = []
    for item in report["packs"]:
        if item.get("error"):
            blocks.append(f"{item.get('id') or item['file']}: "
                          f"error — {item['error']}")
        else:
            blocks.append(format_refresh(item))
    return "\n".join(blocks)


def format_update_plan(plan) -> str:
    pack = plan["pack"]
    lines = [f"Pack {pack['id']} v{plan['installed_version']} → "
             f"v{pack['version']} — {pack['title']}"]
    for add in plan["adds"]:
        state = "enabled" if add["enabled"] else "disabled"
        ppm = add["cadence_posts_per_month"]
        cadence = (f"≈{ppm:g} posts/month" if ppm is not None
                   else "cadence unknown")
        lines.append(f"  + {add['name']} ({state}, {cadence})")
    for item in plan["changed"]:
        if item["identity_changed"]:
            detail = (f"locator changed: {item['old_locator']} → "
                      f"{item['locator']}")
        else:
            detail = "entry updated"
        lines.append(f"  ~ {item['name']} ({detail})")
    for item in plan["removes"]:
        lines.append(f"  - {item['name']} (removed from the pack; "
                     "will be detached)")
    for item in plan["keeps"]:
        lines.append(f"  = keep {item['name']} ({item['reason']})")
    for dup in plan["duplicates"]:
        lines.append(f"  = {dup['name']} already present as "
                     f"{dup['existing_name']!r} (provided by "
                     f"{', '.join(dup['provided_by'])}); skipped")
    for cand in plan["unverified"]:
        lines.append(f"  ! excluded, unverified: {cand['name']} — "
                     f"{cand['reason']}")
    if plan["unchanged"]:
        lines.append(f"  ({len(plan['unchanged'])} unchanged)")
    total = plan["attention_posts_per_month"]
    attention = f"Attention after update: ≈{total:g} posts/month"
    if plan["attention_unknown"]:
        attention += ("; cadence unknown for "
                      + ", ".join(plan["attention_unknown"]))
    lines.append(attention)
    for warning in plan["warnings"]:
        lines.append(f"  warning: {warning}")
    return "\n".join(lines)


def _confirm(prompt_text):
    print(prompt_text)
    try:
        answer = input("Apply this change? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in {"y", "yes"}


def _print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="focu pack",
        description="Curated source packs for sources.yaml")
    sub = parser.add_subparsers(dest="action", required=True)
    validate = sub.add_parser(
        "validate", help="Schema, URL hygiene and liveness report; no writes")
    validate.add_argument("pack")
    validate.add_argument("--no-liveness", action="store_true")
    validate.add_argument("--json", action="store_true")
    for name, helptext in (("install", "Install a pack into sources.yaml"),
                           ("preview", "Show the install plan; writes nothing")):
        cmd = sub.add_parser(name, help=helptext)
        cmd.add_argument("pack")
        cmd.add_argument("--config", default="sources.yaml")
        cmd.add_argument("--channel", default=None,
                         help="Override the channel for every pack source")
        cmd.add_argument("--no-liveness", action="store_true")
        cmd.add_argument("--yes", action="store_true",
                         help="Apply without the interactive confirmation")
        cmd.add_argument("--json", action="store_true")
    uninstall = sub.add_parser(
        "uninstall", help="Remove a pack's sources, preserving shared ones")
    uninstall.add_argument("pack_id")
    uninstall.add_argument("--config", default="sources.yaml")
    uninstall.add_argument("--dry-run", action="store_true")
    uninstall.add_argument("--yes", action="store_true")
    uninstall.add_argument("--json", action="store_true")
    restore = sub.add_parser(
        "restore", help="Roll sources.yaml back to a timestamped backup")
    restore.add_argument("--config", default="sources.yaml")
    restore.add_argument("--backup", default=None)
    restore.add_argument("--dry-run", action="store_true")
    restore.add_argument("--yes", action="store_true")
    restore.add_argument("--json", action="store_true")
    listing = sub.add_parser("list", help="Bundled packs and installed packs")
    listing.add_argument("--config", default="sources.yaml")
    listing.add_argument("--json", action="store_true")
    catalog = sub.add_parser(
        "catalog", help="Bundled packs with attention cost and install state")
    catalog.add_argument("--config", default="sources.yaml")
    catalog.add_argument("--json", action="store_true")
    show = sub.add_parser(
        "show", help="One pack in full: sources, cadence, unverified, state")
    show.add_argument("pack")
    show.add_argument("--config", default="sources.yaml")
    show.add_argument("--no-liveness", action="store_true")
    show.add_argument("--json", action="store_true")
    update = sub.add_parser(
        "update", help="Update an installed pack to the available version")
    update.add_argument("pack")
    update.add_argument("--config", default="sources.yaml")
    update.add_argument("--no-liveness", action="store_true")
    update.add_argument("--dry-run", action="store_true")
    update.add_argument("--yes", action="store_true",
                        help="Apply without the interactive confirmation")
    update.add_argument("--json", action="store_true")
    refresh = sub.add_parser(
        "refresh-check",
        help="Re-verify pack(s) against live feeds; report only, "
             "writes nothing")
    refresh.add_argument("pack", nargs="?", default=None,
                         help="One pack (file, HTTPS URL or bundled id); "
                              "default: every bundled pack")
    refresh.add_argument("--config", default="sources.yaml")
    refresh.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.action == "validate":
        raw, _sha, _origin = _load_pack_argument(args.pack)
        report = validate_pack(raw)
        if report["valid"] and not args.no_liveness:
            report["liveness"] = check_liveness(report["pack"])
        if args.json:
            _print_json(report)
        else:
            pack = report["pack"] or {}
            print(f"Pack {pack.get('id', '?')} v{pack.get('version', '?')}: "
                  + ("valid" if report["valid"] else "INVALID"))
            for err in report["errors"]:
                print(f"  error: {err}")
            for warning in report["warnings"]:
                print(f"  warning: {warning}")
            for sid, result in report.get("liveness", {}).items():
                print(f"  liveness {sid}: {result}")
        return 0 if report["valid"] else 1
    if args.action in {"install", "preview"}:
        raw, sha, _origin = _load_pack_argument(args.pack)
        dry_run = args.action == "preview"
        confirm = None
        if not dry_run and not args.yes:
            confirm = lambda plan: _confirm(format_plan(plan))  # noqa: E731
        result = install_pack(raw, args.config,
                              channel_override=args.channel,
                              dry_run=dry_run,
                              check_feeds=not args.no_liveness,
                              pack_sha256=sha, confirm=confirm)
        if args.json:
            _print_json(result)
        else:
            print(format_plan(result["plan"]))
            if result.get("applied"):
                print(f"Installed. Backup: {result['backup']}")
                print(f"Undo: focu pack uninstall "
                      f"{result['plan']['pack']['id']} --config {args.config}")
            elif result.get("aborted"):
                print("Aborted; nothing written.")
            elif dry_run:
                print("Preview only; nothing written.")
        return 0
    if args.action == "uninstall":
        confirm = None
        if not args.dry_run and not args.yes:
            def confirm(report):
                text = [f"Uninstall pack {report['pack_id']}:"]
                text += [f"  - remove {r['name']}" for r in report["removes"]]
                text += [f"  = keep {k['name']} ({k['reason']})"
                         for k in report["keeps"]]
                return _confirm("\n".join(text))
        result = uninstall_pack(args.pack_id, args.config,
                                dry_run=args.dry_run, confirm=confirm)
        if args.json:
            _print_json(result)
        else:
            for item in result["removes"]:
                print(f"  - remove {item['name']}")
            for item in result["keeps"]:
                print(f"  = keep {item['name']} ({item['reason']})")
            print("Applied." if result["applied"]
                  else "Preview only; nothing written."
                  if result["dry_run"] else "Aborted; nothing written.")
        return 0
    if args.action == "restore":
        confirm = None
        if not args.dry_run and not args.yes:
            def confirm(report):
                text = [f"Restore {args.config} from {report['backup']}:",
                        "  discards: " + (", ".join(report["removed_names"])
                                           or "nothing")]
                return _confirm("\n".join(text))
        result = restore_backup(args.config, args.backup,
                                dry_run=args.dry_run, confirm=confirm)
        if args.json:
            _print_json(result)
        else:
            print(f"Backup: {result['backup']}")
            print("Applied." if result["applied"]
                  else "Preview only; nothing written."
                  if result["dry_run"] else "Aborted; nothing written.")
        return 0
    if args.action == "list":
        bundled = []
        for path in sorted(PACKS_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                bundled.append({"id": data.get("id"),
                                "version": data.get("version"),
                                "title": data.get("title") or data.get("name"),
                                "file": path.name})
            except (OSError, json.JSONDecodeError):
                bundled.append({"file": path.name, "error": "unreadable"})
        manifest = load_manifest(args.config)
        installed = [{"pack_id": r.get("pack_id"), "version": r.get("version"),
                      "installed_at": r.get("installed_at")}
                     for r in manifest["packs"]]
        if args.json:
            _print_json({"bundled": bundled, "installed": installed})
        else:
            for item in bundled:
                print(f"bundled: {item.get('id')} v{item.get('version')} "
                      f"— {item.get('title')}")
            for item in installed:
                print(f"installed: {item['pack_id']} v{item['version']} "
                      f"(at {item['installed_at']})")
        return 0
    if args.action == "catalog":
        result = pack_catalog(args.config)
        if args.json:
            _print_json(result)
        else:
            print(format_catalog(result))
        return 0
    if args.action == "show":
        raw, sha, _origin = _load_pack_argument(args.pack)
        result = show_pack(raw, args.config,
                           check_feeds=not args.no_liveness,
                           pack_sha256=sha)
        if args.json:
            _print_json(result)
        else:
            print(format_show(result))
        return 0
    if args.action == "refresh-check":
        if args.pack:
            raw, _sha, _origin = _load_pack_argument(args.pack)
            result = refresh_check(raw, args.config)
            if args.json:
                _print_json(result)
            else:
                print(format_refresh(result))
        else:
            result = refresh_check_bundled(args.config)
            if args.json:
                _print_json(result)
            else:
                print(format_refresh_all(result))
        return 0
    if args.action == "update":
        raw, sha, _origin = _load_pack_argument(args.pack)
        confirm = None
        if not args.dry_run and not args.yes:
            confirm = lambda plan: _confirm(format_update_plan(plan))  # noqa: E731
        result = update_pack(raw, args.config, dry_run=args.dry_run,
                             check_feeds=not args.no_liveness,
                             pack_sha256=sha, confirm=confirm)
        if args.json:
            _print_json(result)
        elif result.get("already_current"):
            print(f"Pack {result['pack']['id']} is already current "
                  f"(v{result['installed_version']}); nothing changed.")
        else:
            print(format_update_plan(result["plan"]))
            if result.get("applied"):
                print(f"Updated. Backup: {result['backup']}")
                print(f"Undo: focu pack uninstall "
                      f"{result['plan']['pack']['id']} "
                      f"--config {args.config}")
            elif result.get("aborted"):
                print("Aborted; nothing written.")
            elif args.dry_run:
                print("Preview only; nothing written.")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
