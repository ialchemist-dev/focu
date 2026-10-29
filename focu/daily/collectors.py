"""M1 collectors. Broader retries/HTML adapters are scheduled for M2."""
import html
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.request import Request, urlopen


@dataclass
class FetchResult:
    items: list = field(default_factory=list)
    cursor: object = None
    status: str = "success"
    completeness: str = "complete"
    error_code: str | None = None
    message: str | None = None


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


def plain_text(text):
    parser = TextExtractor()
    parser.feed(text or "")
    return " ".join(html.unescape(" ".join(parser.text)).split())


def rss_from_bytes(source, payload):
    import feedparser
    feed = feedparser.parse(payload)
    if feed.bozo or not getattr(feed, "version", ""):
        return FetchResult(status="error", completeness="failed", error_code="parse_error", message="invalid RSS/Atom response")
    items = []
    for entry in feed.entries:
        native = entry.get("id") or entry.get("link")
        if not native:
            return FetchResult(items=items, status="partial", completeness="partial", error_code="missing_item_id")
        content = entry.get("content") or []
        body = content[0].get("value", "") if content else entry.get("summary", "")
        items.append({"native_item_id": native, "title": entry.get("title", ""),
                      "url": entry.get("link", ""), "published_at": entry.get("published") or entry.get("updated"),
                      "body": plain_text(body), "kind": "article"})
    # Always scan the current window, including items reordered ahead/behind a
    # cursor; database identities do the dedup. The cursor remains a native hint.
    return FetchResult(items=items, cursor={"native_item_id": items[0]["native_item_id"]} if items else None,
                       status="success" if items else "empty")


def collect(source, state=None):
    typ = source["type"]
    if typ == "rss" or (typ == "blog" and source.get("feed_url")):
        request = Request(source["feed_url"], headers={"User-Agent": "Focu/0.2"})
        with urlopen(request, timeout=20) as response:
            payload = response.read(8 * 1024 * 1024 + 1)
        if len(payload) > 8 * 1024 * 1024:
            return FetchResult(status="error", completeness="failed", error_code="response_too_large")
        return rss_from_bytes(source, payload)
    if typ == "youtube":
        return collect_youtube(source)
    return FetchResult(status="needs_auth" if typ in {"x", "linkedin"} else "unsupported",
                       completeness="failed", error_code="collector_not_implemented",
                       message="M1 supports RSS/blog-with-feed and the experimental YouTube collector")


def collect_youtube(source):
    # Keep v0.1's optional collector, with native IDs and no daily selection cap.
    import yt_dlp
    from youtube_transcript_api import YouTubeTranscriptApi
    url = source["canonical_url"].rstrip("/") + "/videos"
    options = {"extract_flat": True, "quiet": True, "playlistend": 10}
    items = []
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    for video in info.get("entries") or []:
        vid = video.get("id")
        if not vid:
            continue
        body = ""
        try:
            fetched = YouTubeTranscriptApi().fetch(vid, languages=["en", "zh-Hans", "zh-Hant"])
            body = " ".join(s.text for s in fetched)
        except Exception:
            # Title-only discoveries are durable but never ready for selection.
            pass
        items.append({"native_item_id": vid, "title": video.get("title", ""), "body": body,
                      "url": f"https://www.youtube.com/watch?v={vid}", "kind": "video"})
    return FetchResult(items=items, status="partial", completeness="windowed",
                       error_code="experimental_window", message="latest ten videos only; full backfill is not implemented")
