#!/usr/bin/env python3
"""Deterministic structure / citation-integrity check for a FOCU research report.

Usage:
    python3 docs/research-reports/kit/check_report.py <research_dir> [--json OUT]

Exit code 0 = no errors (warnings allowed), 1 = at least one error, 2 = usage error.
Standard library only. See docs/research-reports/README.md for the contract.

Scope: this is QA layer A (structure). It checks that citations resolve, that
chart numbers equal registered claims, that frozen research files are unchanged,
that addenda are versioned and registered, and that run.json records QA states
honestly. It does NOT prove that a quote supports a claim, that a source is
reliable, or that the page answers the owner's question (layers B and C).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

CLAIM_CLASSES = {"reported_fact", "estimate", "vendor_claim", "derived"}
SOURCE_TYPES = {"primary", "secondary", "vendor"}
QA_STATES = {"passed", "failed", "not_run"}
OWNER_STATES = {"pending", "accepted", "rejected"}
REVIEWERS = {"independent", "same_worker", "none"}
PREFERENCE_SOURCES = {"manual_current_context"}
FROZEN_REQUIRED = ["mission.md", "report.md", "notes/sources-key.md"]
REQUIRED_PAGE_IDS = ["overview", "limits", "sources", "provenance"]
MAX_QUOTE_CHARS = 300
PRIVATE_PATH_RE = re.compile(r"(/Users/[^/\s\"'<>]+|/home/[^/\s\"'<>]+|file://|[A-Za-z]:\\\\Users\\\\)")
SOURCE_ROW_RE = re.compile(r"^\|\s*(S\d+[A-Za-z0-9-]*)\s*\|")


class Result:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, level: str, check: str, detail: str) -> None:
        self.items.append({"level": level, "check": check, "detail": detail})

    def error(self, check: str, detail: str) -> None:
        self.add("error", check, detail)

    def warn(self, check: str, detail: str) -> None:
        self.add("warning", check, detail)

    def ok(self, check: str, detail: str) -> None:
        self.add("ok", check, detail)

    @property
    def errors(self) -> list[dict]:
        return [i for i in self.items if i["level"] == "error"]


# ---------------------------------------------------------------- sources

def parse_sources_key(path: Path, res: Result, label: str) -> dict[str, dict]:
    """Parse a Markdown table: | ID | Title | Publisher | URL | Published | Accessed | Type |"""
    sources: dict[str, dict] = {}
    if not path.exists():
        return sources
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not SOURCE_ROW_RE.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 7:
            res.error("sources-key", f"{label}:{n}: expected 7 columns (ID, Title, Publisher, URL, Published, Accessed, Type), got {len(cells)}")
            continue
        sid, title, publisher, url, published, accessed, typ = cells[:7]
        if sid in sources:
            res.error("sources-key", f"{label}: duplicate source id {sid}")
        base_type = typ.split()[0].strip("();,").lower() if typ else ""
        if base_type not in SOURCE_TYPES:
            res.error("sources-key", f"{label}: {sid} type must start with one of {sorted(SOURCE_TYPES)}, got {typ!r}")
        if not title or not url:
            res.error("sources-key", f"{label}: {sid} needs a title and URL (or an explicit document reference)")
        if not accessed:
            res.error("sources-key", f"{label}: {sid} needs an accessed date")
        sources[sid] = {"title": title, "publisher": publisher, "url": url, "published": published,
                        "accessed": accessed, "type": typ, "origin": label}
    return sources


# ---------------------------------------------------------------- claims

def load_claims(path: Path, res: Result, label: str) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        res.error("claims", f"{label}: invalid JSON: {exc}")
        return []
    if not isinstance(data, list):
        res.error("claims", f"{label}: top level must be a JSON array of claim objects")
        return []
    for c in data:
        c["_origin"] = label
    return data


def validate_claims(claims: list[dict], sources: dict[str, dict], res: Result) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    for c in claims:
        cid = c.get("claim_id")
        where = f"{c.get('_origin')}:{cid}"
        if not cid or not isinstance(cid, str):
            res.error("claims", f"{c.get('_origin')}: claim without string claim_id")
            continue
        if cid in by_id:
            res.error("claims", f"duplicate claim_id {cid} ({by_id[cid]['_origin']} and {c.get('_origin')})")
            continue
        by_id[cid] = c
        for field in ("text", "value", "unit", "class", "source_ids"):
            if field not in c:
                res.error("claims", f"{where}: missing field {field!r}")
        cls = c.get("class")
        if cls not in CLAIM_CLASSES:
            res.error("claims", f"{where}: class must be one of {sorted(CLAIM_CLASSES)}, got {cls!r}")
        sids = c.get("source_ids") or []
        if not isinstance(sids, list) or not sids:
            res.error("claims", f"{where}: source_ids must be a non-empty list")
            sids = []
        for sid in sids:
            if sid not in sources:
                res.error("claims", f"{where}: source {sid} is not registered in any sources-key")
        if cls != "derived" and not c.get("as_of"):
            res.error("claims", f"{where}: non-derived claims need as_of")
        quote = c.get("quote")
        if cls != "derived":
            if not quote:
                res.warn("claims", f"{where}: no supporting quote; reviewers cannot spot-check it quickly")
            elif len(quote) > MAX_QUOTE_CHARS:
                res.error("claims", f"{where}: quote is {len(quote)} chars; keep short excerpts (<= {MAX_QUOTE_CHARS}) and cite, do not copy articles")
        if cls == "estimate" and not (c.get("estimator") or c.get("note")):
            res.warn("claims", f"{where}: estimate should name the estimator/method (estimator or note)")
        if c.get("_origin", "").startswith("addenda/") and c.get("added_by") != "builder":
            res.error("claims", f"{where}: addendum claims must carry added_by: \"builder\"")
    # second pass: derived claims need formula + resolvable inputs
    for cid, c in by_id.items():
        if c.get("class") != "derived":
            continue
        if not c.get("formula"):
            res.error("claims", f"{cid}: derived claim needs a formula")
        inputs = c.get("input_claim_ids") or []
        if not inputs:
            res.error("claims", f"{cid}: derived claim needs input_claim_ids")
        for i in inputs:
            if i not in by_id:
                res.error("claims", f"{cid}: input claim {i} does not exist")
            elif i == cid:
                res.error("claims", f"{cid}: derived claim cannot use itself as input")
    return by_id


def claim_value(claim: dict, key: str | None):
    v = claim.get("value")
    if key is not None:
        if not isinstance(v, dict) or key not in v:
            return None
        return v[key]
    return v


# ---------------------------------------------------------------- page

class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.cites: list[str] = []
        self.src_items: dict[str, list[str]] = {}
        self.claim_refs: list[tuple[str, str | None]] = []
        self.external: list[str] = []
        self.charts: list[str] = []
        self.has_viewport = False
        self._src_stack: list[str | None] = []
        self._chart_buf: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if a.get("id"):
            self.ids.append(a["id"])
        if tag == "meta" and a.get("name") == "viewport":
            self.has_viewport = True
        if tag == "a" and "cite" in classes:
            self.cites.append(a.get("href") or "")
        if tag == "li":
            if "src" in classes and (a.get("id") or "").startswith("src-"):
                sid = a["id"][4:]
                self.src_items[sid] = []
                self._src_stack.append(sid)
            else:
                self._src_stack.append(None)
        if tag == "a" and self._src_stack and self._src_stack[-1] and a.get("href"):
            self.src_items[self._src_stack[-1]].append(a["href"])
        if "data-claim" in a:
            for cid in (a["data-claim"] or "").split():
                self.claim_refs.append((cid, a.get("data-class")))
        if tag == "script" and a.get("src"):
            self.external.append(f"script src={a['src']}")
        if tag == "link" and (a.get("rel") or "").lower() in {"stylesheet", "preload", "modulepreload"} and a.get("href"):
            self.external.append(f"link href={a['href']}")
        if tag in {"img", "iframe", "video", "audio", "source"} and a.get("src") and not a["src"].startswith("data:"):
            self.external.append(f"{tag} src={a['src']}")
        if tag == "script" and a.get("type") == "application/json" and "data-chart" in a:
            self._chart_buf = []

    def handle_endtag(self, tag):
        if tag == "li" and self._src_stack:
            self._src_stack.pop()
        if tag == "script" and self._chart_buf is not None:
            self.charts.append("".join(self._chart_buf))
            self._chart_buf = None

    def handle_data(self, data):
        if self._chart_buf is not None:
            self._chart_buf.append(data)


def check_page(page: Path, sources: dict[str, dict], claims: dict[str, dict], res: Result) -> None:
    if not page.exists():
        res.error("page", f"missing deliverable {page.name} (expected page/index.html)")
        return
    text = page.read_text(encoding="utf-8")
    p = PageParser()
    p.feed(text)
    if not p.has_viewport:
        res.error("page", "missing <meta name=viewport> (responsive layout required)")
    dup = sorted({i for i in p.ids if p.ids.count(i) > 1})
    if dup:
        res.error("page", f"duplicate element ids: {dup}")
    for rid in REQUIRED_PAGE_IDS:
        if rid not in p.ids:
            res.error("page", f"missing required element id={rid!r}")
    if p.external:
        res.error("page", f"page loads external/relative resources (must be self-contained): {p.external[:5]}")
    leaks = sorted(set(PRIVATE_PATH_RE.findall(text)))
    if leaks:
        res.error("privacy", f"page contains local/private paths: {leaks[:5]}")
    # citations
    if not p.cites:
        res.error("citations", "page has no a.cite citations")
    for href in p.cites:
        if not href.startswith("#src-"):
            res.error("citations", f"cite href must be '#src-<ID>', got {href!r}")
            continue
        sid = href[5:]
        if sid not in p.src_items:
            res.error("citations", f"cite {href} has no matching li.src#src-{sid} in the sources list")
    for sid, hrefs in p.src_items.items():
        reg = sources.get(sid)
        if not reg:
            res.error("citations", f"page lists source {sid} that is not registered in sources-key (base or addendum)")
            continue
        if reg["url"].startswith("http") and reg["url"] not in hrefs:
            res.error("citations", f"page source {sid} must link the registered URL {reg['url']}")
    cited = {h[5:] for h in p.cites if h.startswith("#src-")}
    unlisted = sorted(set(sources) - set(p.src_items))
    if unlisted:
        res.warn("citations", f"registered sources not shown on page (fine if deliberately excluded; say so in limits): {unlisted}")
    uncited = sorted(set(p.src_items) - cited)
    if uncited:
        res.warn("citations", f"sources listed but never cited in text: {uncited}")
    # claim refs
    for cid, cls in p.claim_refs:
        c = claims.get(cid)
        if not c:
            res.error("claims-on-page", f"data-claim={cid} not found in claims.json or addenda")
        elif cls and cls != c.get("class"):
            res.error("claims-on-page", f"data-claim={cid} shows class {cls!r} but claims.json says {c.get('class')!r}")
    # charts
    if p.charts and not claims:
        res.error("charts", "numeric charts require claims.json (structured claims are mandatory for plotted numbers)")
    for n, raw in enumerate(p.charts, 1):
        try:
            spec = json.loads(raw)
        except json.JSONDecodeError as exc:
            res.error("charts", f"chart #{n}: invalid JSON: {exc}")
            continue
        series = spec.get("series")
        if not spec.get("title") or not isinstance(series, list) or not series:
            res.error("charts", f"chart #{n}: needs title and non-empty series")
            continue
        for pt in series:
            cid, key, val = pt.get("claim"), pt.get("key"), pt.get("value")
            if not cid or cid not in claims:
                res.error("charts", f"chart #{n} {pt.get('label')!r}: claim {cid!r} not registered")
                continue
            expected = claim_value(claims[cid], key)
            if not isinstance(val, (int, float)) or not isinstance(expected, (int, float)) or not math.isclose(val, expected, rel_tol=1e-9, abs_tol=1e-9):
                res.error("charts", f"chart #{n} {pt.get('label')!r}: plotted {val!r} != claim {cid}{'.' + key if key else ''} value {expected!r}")
    if not res.errors:
        res.ok("page", f"{len(p.cites)} citations, {len(p.src_items)} sources, {len(p.claim_refs)} claim refs, {len(p.charts)} charts")


# ---------------------------------------------------------------- frozen / addenda / run

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_frozen(rd: Path, res: Result) -> None:
    manifest = rd / "frozen.sha256"
    if not manifest.exists():
        res.error("frozen", "missing frozen.sha256 (freeze research before building the page)")
        return
    listed: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            res.error("frozen", f"bad manifest line: {line!r}")
            continue
        listed[parts[1].strip().lstrip("*")] = parts[0]
    required = list(FROZEN_REQUIRED) + (["claims.json"] if (rd / "claims.json").exists() else [])
    for rel in required:
        if rel not in listed:
            res.error("frozen", f"{rel} is not listed in frozen.sha256")
    for rel, digest in listed.items():
        if rel.startswith(("page/", "addenda/")) or rel == "run.json":
            res.error("frozen", f"{rel} must not be frozen with the research inputs")
        f = rd / rel
        if not f.exists():
            res.error("frozen", f"frozen file missing: {rel}")
        elif sha256(f) != digest:
            res.error("frozen", f"frozen file changed after freeze: {rel} (put builder additions in addenda/addendum-N/, never edit originals)")


def load_addenda(rd: Path, res: Result) -> tuple[list[tuple[str, Path]], list[tuple[str, Path]]]:
    srcs, claims = [], []
    ad = rd / "addenda"
    if not ad.exists():
        return srcs, claims
    for d in sorted(ad.iterdir()):
        if not d.is_dir():
            continue
        if not re.fullmatch(r"addendum-\d+", d.name):
            res.error("addenda", f"addenda/{d.name}: directories must be named addendum-N")
            continue
        if not (d / "report.md").exists():
            res.error("addenda", f"addenda/{d.name}: needs report.md describing what was added and why")
        if (d / "sources-key.md").exists():
            srcs.append((f"addenda/{d.name}/sources-key.md", d / "sources-key.md"))
        if (d / "claims.json").exists():
            claims.append((f"addenda/{d.name}/claims.json", d / "claims.json"))
    return srcs, claims


def check_run(rd: Path, res: Result) -> None:
    f = rd / "run.json"
    if not f.exists():
        res.error("run", "missing run.json")
        return
    try:
        run = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        res.error("run", f"invalid JSON: {exc}")
        return
    for field in ("slug", "profile_version", "applied_preference_ids", "preference_source", "tools_actually_used", "qa"):
        if field not in run:
            res.error("run", f"missing field {field!r}")
    if run.get("preference_source") not in PREFERENCE_SOURCES:
        res.error("run", f"preference_source must be one of {sorted(PREFERENCE_SOURCES)} (no automatic product memory exists yet)")
    qa = run.get("qa") or {}
    render, semantic, owner = qa.get("render") or {}, qa.get("semantic") or {}, qa.get("owner") or {}
    if render.get("state") not in QA_STATES:
        res.error("run", f"qa.render.state must be one of {sorted(QA_STATES)}")
    elif render.get("state") != "not_run" and not render.get("evidence"):
        res.error("run", "qa.render.state is passed/failed but qa.render.evidence (result file / screenshot dir) is empty")
    if semantic.get("state") not in QA_STATES:
        res.error("run", f"qa.semantic.state must be one of {sorted(QA_STATES)}")
    if semantic.get("reviewer") not in REVIEWERS:
        res.error("run", f"qa.semantic.reviewer must be one of {sorted(REVIEWERS)}")
    elif semantic.get("state") != "not_run" and semantic.get("reviewer") == "none":
        res.error("run", "qa.semantic has a result but reviewer is 'none'")
    elif semantic.get("state") == "not_run" and semantic.get("reviewer") != "none":
        res.error("run", "qa.semantic.state is not_run but a reviewer is named")
    if owner.get("state") not in OWNER_STATES:
        res.error("run", f"qa.owner.state must be one of {sorted(OWNER_STATES)}")
    leaks = sorted(set(PRIVATE_PATH_RE.findall(f.read_text(encoding="utf-8"))))
    if leaks:
        res.warn("privacy", f"run.json contains local paths (do not commit it to a public repo as-is): {leaks[:3]}")


# ---------------------------------------------------------------- main

def check(rd: Path) -> Result:
    res = Result()
    for rel in FROZEN_REQUIRED:
        if not (rd / rel).exists():
            res.error("layout", f"missing {rel}")
    check_frozen(rd, res)
    add_srcs, add_claims = load_addenda(rd, res)
    sources = parse_sources_key(rd / "notes/sources-key.md", res, "notes/sources-key.md")
    if not sources:
        res.error("sources-key", "no source rows found in notes/sources-key.md")
    for label, path in add_srcs:
        for sid, s in parse_sources_key(path, res, label).items():
            if sid in sources:
                res.error("addenda", f"{label}: source id {sid} already registered")
            sources[sid] = s
    claims_list = load_claims(rd / "claims.json", res, "claims.json")
    for label, path in add_claims:
        claims_list += load_claims(path, res, label)
    claims = validate_claims(claims_list, sources, res)
    check_page(rd / "page" / "index.html", sources, claims, res)
    check_run(rd, res)
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("research_dir", type=Path)
    ap.add_argument("--json", type=Path, help="write the full result as JSON")
    args = ap.parse_args(argv)
    if not args.research_dir.is_dir():
        print(f"not a directory: {args.research_dir}", file=sys.stderr)
        return 2
    res = check(args.research_dir)
    summary = {
        "layer": "A-structure",
        "research_dir": args.research_dir.name,
        "status": "failed" if res.errors else "passed",
        "errors": len(res.errors),
        "warnings": sum(1 for i in res.items if i["level"] == "warning"),
        "items": res.items,
        "not_checked": ["semantic support of quotes for claims (layer B)",
                        "source reliability and completeness",
                        "visual rendering, overflow, console errors (use render_qa.mjs)",
                        "owner intent / usefulness (layer C)"],
    }
    if args.json:
        args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    for i in res.items:
        if i["level"] != "ok":
            print(f"{i['level'].upper():7} {i['check']}: {i['detail']}")
    print(f"layer A structure: {summary['status']} ({summary['errors']} errors, {summary['warnings']} warnings). "
          "Semantic support and owner intent are NOT checked.")
    return 1 if res.errors else 0


if __name__ == "__main__":
    sys.exit(main())
