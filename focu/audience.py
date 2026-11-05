"""Versioned, owner-authorized audience calibration for writing, audio and QC."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import yaml

PROFILE_PATH = Path(__file__).resolve().parents[1] / "references" / "audience-profile.md"

EXPERT_PATTERNS = {
    "chef_analogy": r"\b(?:like|imagine|think of)\b.{0,45}\b(?:chef|cooking|kitchen|recipe)\b",
    "sculptor_analogy": r"\b(?:like|imagine|think of)\b.{0,45}\b(?:sculptor|sculpture|carving)\b",
    "detective_analogy": r"\b(?:like|imagine|think of)\b.{0,45}\bdetective\b",
    "basics_exposition": r"\b(?:what is a neural network|let.s first explain what (?:AI|machine learning) is|AI stands for artificial intelligence|imagine a computer that)\b",
}
NOVICE_PATTERNS = {
    "unexplained_domain_jargon": r"\b(?:habitus|anomie|intersectionality|operationalization)\b",
}


def load_profile(path=PROFILE_PATH):
    source = Path(path).read_text(encoding="utf-8")
    marker = chr(96) * 3
    match = re.search(re.escape(marker) + r"yaml\s*\n(.*?)\n" + re.escape(marker),
                      source, re.S)
    if not match:
        raise ValueError("Audience profile lacks YAML settings")
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict) or not isinstance(data.get("domains"), dict):
        raise ValueError("Audience profile must define domains")
    if set(data.get("levels", {})) != {"expert", "working_knowledge", "novice"}:
        raise ValueError("Audience profile lacks required calibration levels")
    if data.get("default_level") not in data["levels"]:
        raise ValueError("Unknown audience default level")
    for name, value in data["domains"].items():
        if not isinstance(value, dict) or value.get("level") not in data["levels"]:
            raise ValueError("Invalid domain level: " + name)
        if value.get("provenance") != "owner-stated":
            raise ValueError("Unapproved audience domain provenance")
    data["profile_sha256"] = hashlib.sha256(source.encode()).hexdigest()
    return data


def calibration(domain=None, profile=None):
    profile = profile or load_profile()
    key = str(domain or "").lower().replace("-", "_").replace(" ", "_")
    names = {name: name for name in profile["domains"]}
    for name, value in profile["domains"].items():
        for alias in value.get("aliases", []):
            names[str(alias).lower().replace("-", "_").replace(" ", "_")] = name
    selected = names.get(key)
    level = profile["domains"][selected]["level"] if selected else profile["default_level"]
    return {"domain": selected or key or "unspecified", "level": level,
            "rules": profile["levels"][level], "profile_version": profile["version"],
            "profile_sha256": profile["profile_sha256"],
            "preferences": profile.get("preferences", [])}


def writing_guidance(domain=None, profile=None):
    choice = calibration(domain, profile)
    return (
        "AUDIENCE — one specific reader; apply these constraints to the ENTIRE "
        "article/podcast rather than merely describing them. "
        f"Domain: {choice['domain']}; level: {choice['level']}. "
        f"{choice['rules']} "
        "Profile preferences: " + " ".join(choice["preferences"]) +
        f" Profile version {choice['profile_version']}."
    )


def mismatch_report(text, domain=None, profile=None):
    choice = calibration(domain, profile)
    checks = EXPERT_PATTERNS if choice["level"] == "expert" else (
        NOVICE_PATTERNS if choice["level"] == "novice" else {}
    )
    matches = []
    for pattern_name, regex in checks.items():
        for match in re.finditer(regex, text or "", flags=re.I | re.S):
            matches.append({"pattern": pattern_name, "excerpt": match.group()[:180]})
    return {**{k: choice[k] for k in ("domain", "level", "profile_version",
                                      "profile_sha256")},
            "blocking": False, "patterns_checked": list(checks),
            "matches": matches, "requires_review": bool(matches)}
