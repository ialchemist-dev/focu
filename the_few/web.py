"""Bounded real-HTTP retrieval; failures are explicit, never fabricated."""
from __future__ import annotations

import re
import socket
import time
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class FetchError(RuntimeError):
    def __init__(self, message: str, *, category: str = "network", status: int | None = None):
        super().__init__(message)
        self.category = category
        self.status = status


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.parts = []
        self._in_title = False
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self._skip += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self._skip = max(0, self._skip - 1)
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if not self._skip:
            self.parts.append(data)


@dataclass(frozen=True)
class WebPage:
    url: str
    title: str
    text: str
    status: int
    content_type: str


def fetch_page(url: str, *, timeout: float = 12, max_bytes: int = 2_000_000, retries: int = 2) -> WebPage:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Only absolute HTTP(S) URLs are supported")
    if retries < 0 or retries > 5:\n        raise ValueError("retries must be between 0 and 5")\n    if timeout <= 0 or max_bytes <= 0:
        raise ValueError("timeout and max_bytes must be positive")
    req = Request(url, headers={"User-Agent": "TheFew/0.2 (+research verification)", "Accept": "text/html,text/plain;q=0.9"})
    for attempt in range(retries + 1):
        try:
            return _retrieve(req, url, timeout, max_bytes)
        except FetchError as exc:
            if attempt == retries or exc.category not in {"timeout", "rate_limit", "server"}:
                raise
            time.sleep(min(0.25 * (2 ** attempt), 2))
    raise AssertionError("unreachable")


def _retrieve(req: Request, url: str, timeout: float, max_bytes: int) -> WebPage:
    try:
        with urlopen(req, timeout=timeout) as response:
            final_url = response.geturl()
            if urlparse(final_url).scheme not in {"http", "https"}:
                raise FetchError("Redirected to unsupported URL scheme")
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "text/plain"}:
                raise FetchError(f"Unsupported content type: {content_type}")
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise FetchError("Response exceeded max_bytes")
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                body = raw.decode(charset, errors="replace")
            except LookupError as exc:
                raise FetchError(f"Unknown charset: {charset}") from exc
            status = response.status
    except HTTPError as exc:
        category = "rate_limit" if exc.code == 429 else "server" if exc.code >= 500 else "http"
        raise FetchError(f"HTTP {exc.code} retrieving {url}", category=category, status=exc.code) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise FetchError(f"Timeout retrieving {url}", category="timeout") from exc
    except URLError as exc:
        category = "timeout" if isinstance(exc.reason, (TimeoutError, socket.timeout)) or "timed out" in str(exc.reason).lower() else "network"
        raise FetchError(f"Could not retrieve {url}: {exc}", category=category) from exc
    except OSError as exc:
        raise FetchError(f"Could not retrieve {url}: {exc}", category="network") from exc
    if content_type == "text/html":
        parser = _TextParser()
        parser.feed(body)
        title = unescape(parser.title).strip()
        text = " ".join(parser.parts)
    else:
        title = ""
        text = body
    text = re.sub(r"\\s+", " ", text).strip()
    if not text:
        raise FetchError("Retrieved page has no extractable text")
    return WebPage(url=final_url, title=title, text=text, status=status, content_type=content_type)
