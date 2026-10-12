"""Versioned URL identities. Unknown query parameters are significant."""
import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

IDENTITY_VERSION = 1
TRACKING = {"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid"}
YOUTUBE = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def canonical_url(url):
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("identity requires an absolute HTTP(S) URL")
    if parts.username or parts.password:
        raise ValueError("credentials must not appear in URLs")
    host = parts.hostname.lower()
    port = parts.port
    netloc = f"[{host}]" if ":" in host else host
    if port and not ((parts.scheme.lower() == "https" and port == 443) or
                     (parts.scheme.lower() == "http" and port == 80)):
        netloc += f":{port}"
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in TRACKING]
    path = parts.path or "/"
    if host in YOUTUBE:
        vid = None
        if host == "youtu.be":
            vid = path.strip("/").split("/")[0]
        elif path == "/watch":
            vid = dict(query).get("v")
        elif path.startswith(("/shorts/", "/embed/", "/live/")):
            vid = path.split("/")[2]
        if vid:
            return "https://www.youtube.com/watch?" + urlencode({"v": vid})
    if host in {"twitter.com", "www.twitter.com", "www.x.com"}:
        netloc = "x.com"
    # Preserve path case, unknown www aliases, trailing slashes and query order:
    # none of these equivalences is guaranteed for arbitrary publishers.
    return urlunsplit((parts.scheme.lower(), netloc, path, urlencode(query), ""))


def stable_id(kind, key):
    return kind + "_" + hashlib.sha256(f"{kind}:v{IDENTITY_VERSION}:{key}".encode()).hexdigest()


def source_url(source):
    if source.get("canonical_url"):
        return canonical_url(source["canonical_url"])
    typ = source["type"]
    if typ == "rss":
        url = source["feed_url"]
    elif typ == "blog":
        url = source.get("site_url") or source["feed_url"]
    elif typ == "youtube":
        if source.get("channel_id"):
            url = "https://www.youtube.com/channel/" + source["channel_id"]
        else:
            url = "https://www.youtube.com/@" + source["handle"].lstrip("@")
    elif typ == "x":
        url = "https://x.com/" + source["username"].lstrip("@").lower()
    else:
        url = source.get("profile_url") or source["company_page"]
    return canonical_url(url)


def content_identity(item, source_id):
    if item.get("url"):
        url = canonical_url(item["url"])
        return stable_id("cnt", url), url, False
    native = item.get("native_item_id") or item.get("id")
    if native:
        return stable_id("cnt", f"{source_id}:{native}"), None, False
    # Never permanently collapse unrelated title-only observations.
    import uuid
    return stable_id("cnt", f"provisional:{uuid.uuid4()}"), None, True
