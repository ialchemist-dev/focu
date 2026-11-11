#!/usr/bin/env python3
"""Reproducible, dated community-activity + bundle-weight snapshot for OSS research (#42, #43).

Stdlib only. GitHub data is read through the already-authenticated `gh api` CLI
(no token is read, printed or stored by this script). npm/jsDelivr data is read
from public endpoints. Output is normalized, non-secret JSON.

Metric definitions (all windows are [window_start, captured_at) in UTC):
- stars: repository stargazers_count at capture time.
- commits_90d: commits reachable from the DEFAULT BRANCH with committer date
  >= now-90d (GitHub `commits?since=`), counted by pagination Link `last` page
  with per_page=1. Not pushed_at; not other branches.
- contributors_6mo: distinct commit authors (GitHub login, else author name)
  on the default branch since now-182d. Paginated up to MAX_COMMIT_PAGES*100
  commits; if truncated the value is reported as a LOWER BOUND.
  Bot accounts (login ends with "[bot]") are reported separately.
- latest_release: /releases?per_page=5 newest non-draft (prerelease flagged);
  null if the repository publishes no GitHub releases (tags are not counted).
- issues: GitHub search (is:issue excludes PRs) totals for opened and closed in
  the last 90 days, plus current open issue count.
- responsiveness: the RESPONSIVENESS_SAMPLE most recently created issues in the
  90-day window; first comment whose author_association is OWNER/MEMBER/
  COLLABORATOR (non-bot) is a maintainer response. Maintainers with only
  CONTRIBUTOR association are missed, so the rate is a conservative estimate.
"""
import argparse, datetime as dt, gzip, json, re, statistics, subprocess, sys, time, urllib.request

MAX_COMMIT_PAGES = 20
RESPONSIVENESS_SAMPLE = 15
MAINTAINER = {"OWNER", "MEMBER", "COLLABORATOR"}
UA = {"User-Agent": "focu-oss-research-snapshot/1"}

def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")

def gh(path, include_headers=False):
    cmd = ["gh", "api", "-H", "Accept: application/vnd.github+json"] + (["-i"] if include_headers else []) + [path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        if "404" in r.stdout + r.stderr or "Not Found" in r.stdout + r.stderr:
            return (None, {}) if include_headers else None
        raise RuntimeError("gh api failed for %s: %s" % (path, (r.stderr or r.stdout)[:200]))
    if not include_headers:
        return json.loads(r.stdout)
    head, _, body = r.stdout.partition("\r\n\r\n") if "\r\n\r\n" in r.stdout else r.stdout.partition("\n\n")
    headers = {}
    for line in head.splitlines()[1:]:
        k, _, v = line.partition(":")
        headers[k.strip().lower()] = v.strip()
    return json.loads(body), headers

_last_search = [0.0]
def search(q, extra=""):
    wait = 2.3 - (time.time() - _last_search[0])
    if wait > 0:
        time.sleep(wait)
    _last_search[0] = time.time()
    return gh("search/issues?q=" + urllib.parse.quote(q) + "&per_page=" + (extra or "1"))

def count_commits(repo, since):
    data, h = gh("repos/%s/commits?since=%s&per_page=1" % (repo, since), include_headers=True)
    if data is None:
        return None
    m = re.search(r'[?&]page=(\d+)>; rel="last"', h.get("link", ""))
    return int(m.group(1)) if m else len(data)

def contributors(repo, since):
    people, bots, truncated, n = set(), set(), False, 0
    for page in range(1, MAX_COMMIT_PAGES + 1):
        data = gh("repos/%s/commits?since=%s&per_page=100&page=%d" % (repo, since, page)) or []
        for c in data:
            n += 1
            login = (c.get("author") or {}).get("login")
            key = login or "name:" + ((c.get("commit") or {}).get("author") or {}).get("name", "?").lower()
            (bots if login and login.endswith("[bot]") else people).add(key)
        if len(data) < 100:
            break
    else:
        truncated = True
    return {"distinct_human": len(people), "distinct_bot": len(bots), "commits_scanned": n,
            "truncated_lower_bound": truncated}

def responsiveness(repo, start):
    res = search("repo:%s is:issue created:>=%s" % (repo, start[:10]), "%d&sort=created&order=desc" % RESPONSIVENESS_SAMPLE)
    sample = []
    for it in res.get("items", []):
        if (it.get("user") or {}).get("login", "").endswith("[bot]"):
            continue
        first = None
        if it.get("comments"):
            for c in gh("repos/%s/issues/%d/comments?per_page=50" % (repo, it["number"])) or []:
                login = (c.get("user") or {}).get("login", "")
                if c.get("author_association") in MAINTAINER and not login.endswith("[bot]") \
                        and login != it["user"]["login"]:
                    first = c["created_at"]
                    break
        created = dt.datetime.fromisoformat(it["created_at"].replace("Z", "+00:00"))
        hours = None
        if first:
            hours = round((dt.datetime.fromisoformat(first.replace("Z", "+00:00")) - created).total_seconds() / 3600, 1)
        sample.append({"number": it["number"], "created_at": it["created_at"], "state": it["state"],
                       "author_association": it.get("author_association"),
                       "first_maintainer_comment_hours": hours})
    # issues opened by maintainers themselves are excluded from the rate denominator
    ext = [s for s in sample if s["author_association"] not in MAINTAINER]
    responded = [s for s in ext if s["first_maintainer_comment_hours"] is not None]
    return {"sample_size": len(sample), "external_issues_in_sample": len(ext),
            "external_with_maintainer_comment": len(responded),
            "external_closed": sum(1 for s in ext if s["state"] == "closed"),
            "median_hours_to_first_maintainer_comment": statistics.median([s["first_maintainer_comment_hours"] for s in responded]) if responded else None,
            "sample": sample}

def repo_snapshot(repo, t):
    s90, s182 = iso(t - dt.timedelta(days=90)), iso(t - dt.timedelta(days=182))
    meta = gh("repos/" + repo)
    if meta is None:
        return {"repo": repo, "error": "not_found"}
    rels = [r for r in (gh("repos/%s/releases?per_page=5" % repo) or []) if not r.get("draft")]
    latest = rels[0] if rels else None
    last = gh("repos/%s/commits?per_page=1" % repo) or []
    out = {
        "repo": meta["full_name"], "html_url": meta["html_url"], "archived": meta["archived"],
        "default_branch": meta["default_branch"], "license_spdx": (meta.get("license") or {}).get("spdx_id"),
        "stars": meta["stargazers_count"], "forks": meta["forks_count"], "pushed_at_not_activity": meta["pushed_at"],
        "last_default_branch_commit": last[0]["commit"]["committer"]["date"] if last else None,
        "commits_90d": count_commits(repo, s90),
        "contributors_6mo": contributors(repo, s182),
        "latest_release": {"tag": latest["tag_name"], "published_at": latest["published_at"],
                           "prerelease": latest["prerelease"], "url": latest["html_url"]} if latest else None,
        "issues_opened_90d": search("repo:%s is:issue created:>=%s" % (repo, s90[:10]))["total_count"],
        "issues_closed_90d": search("repo:%s is:issue closed:>=%s" % (repo, s90[:10]))["total_count"],
        "issues_open_now": search("repo:%s is:issue is:open" % repo)["total_count"],
        "responsiveness_90d": responsiveness(repo, s90),
        "windows": {"commits_90d_since": s90, "contributors_since": s182, "issue_window_since_date": s90[:10]},
    }
    return out

def http_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.loads(r.read().decode())

def package_snapshot(pkg, patterns):
    reg = http_json("https://registry.npmjs.org/" + pkg.replace("/", "%2F") + "/latest")
    ver = reg["version"]
    flat = http_json("https://data.jsdelivr.com/v1/packages/npm/%s@%s?structure=flat" % (pkg, ver))
    files = []
    for pat in patterns:
        for f in flat.get("files", []):
            if re.fullmatch(pat, f["name"]):
                url = "https://cdn.jsdelivr.net/npm/%s@%s%s" % (pkg, ver, f["name"])
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                    raw = r.read()  # measured only; never executed or written to disk
                hosts = sorted({h.decode().lower() for h in re.findall(rb"https?://([A-Za-z0-9.-]+\.[A-Za-z]{2,})", raw)})
                files.append({"path": f["name"], "raw_bytes": len(raw), "gzip9_bytes": len(gzip.compress(raw, 9)),
                              "url": url,
                              # static text scan only: absolute URL hosts mentioned anywhere (comments,
                              # licenses, docs links or runtime fetches). Not proof of runtime requests.
                              "absolute_url_hosts_mentioned": hosts})
    return {"package": pkg, "version": ver, "license": reg.get("license"),
            "npm_unpacked_size_bytes": (reg.get("dist") or {}).get("unpackedSize"),
            "npm_file_count": (reg.get("dist") or {}).get("fileCount"),
            "dependencies": sorted((reg.get("dependencies") or {}).keys()),
            "measured_files": files,
            "unmatched_patterns": [p for p in patterns if not any(re.fullmatch(p, x["path"]) for x in files)]}

def main(argv=None):
    import urllib.parse  # noqa: F401  (ensures urllib.parse is loaded for search())
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args(argv)
    cfg = json.load(open(a.config, encoding="utf-8"))
    t = now()
    out = {"schema": "focu-oss-activity-snapshot/1", "captured_at": iso(t), "issue": cfg.get("issue"),
           "method": __doc__.strip(), "repos": [], "packages": []}
    for repo in cfg.get("repos", []):
        print("repo", repo, file=sys.stderr)
        try:
            out["repos"].append(repo_snapshot(repo, t))
        except Exception as exc:  # record, do not invent
            out["repos"].append({"repo": repo, "error": str(exc)[:300]})
    for pkg in cfg.get("packages", []):
        print("pkg", pkg["name"], file=sys.stderr)
        try:
            out["packages"].append(package_snapshot(pkg["name"], pkg.get("files", [])))
        except Exception as exc:
            out["packages"].append({"package": pkg["name"], "error": str(exc)[:300]})
    out["finished_at"] = iso(now())
    rl = gh("rate_limit")
    out["rate_limit_after"] = {k: {"remaining": rl["resources"][k]["remaining"], "limit": rl["resources"][k]["limit"]}
                               for k in ("core", "search")}
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return 0

if __name__ == "__main__":
    import urllib.parse
    sys.exit(main())
