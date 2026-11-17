"""Pack fetch target guard (PM sweep F3).

The default pack fetch refuses non-public targets: a literal
non-public address is a validate-time error (offline, no DNS), and
the guarded fetch resolves every hop — entry URL and each redirect —
refusing any host that resolves to a non-public address, any
non-HTTPS hop, redirect loops, and chains over MAX_REDIRECTS.
Refusals are FetchRefused (a URLError), so liveness and
refresh-check record them as "unreachable" with the reason attached.

No live network: the resolver and the opener are fakes throughout.
"""
import socket
import unittest
from datetime import date
from urllib.error import HTTPError, URLError

import focu.packs as packs
from focu.packs import (MAX_REDIRECTS, MAX_SOURCES_PER_PACK, check_liveness,
                        refresh_check, validate_pack)

TODAY = date(2026, 11, 17)

RSS = (b'<?xml version="1.0" encoding="UTF-8"?>\n'
       b'<rss version="2.0"><channel><title>Example</title>'
       b'<item><title>Post</title><link>https://a.example.com/post</link>'
       b'<pubDate>Mon, 12 Oct 2026 07:00:00 GMT</pubDate></item>'
       b'</channel></rss>')

PUBLIC = {"a.example.com": ["93.184.216.34"],
          "b.example.com": ["93.184.216.35"],
          "c.example.com": ["93.184.216.36"],
          "d.example.com": ["93.184.216.37"],
          "e.example.com": ["93.184.216.38"],
          "internal.example.com": ["10.0.0.5"],
          "mixed.example.com": ["93.184.216.34", "192.168.1.10"],
          "alice.example.com": ["93.184.216.40"]}


def fake_resolver(host):
    return PUBLIC[host]


class FakeResponse:
    def __init__(self, url, data):
        self._url, self._data = url, data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, _limit=-1):
        return self._data

    def geturl(self):
        return self._url


class FakeOpener:
    """Routes exact URLs to a FakeResponse or an exception to raise."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def open(self, req, timeout=None):
        self.calls.append(req.full_url)
        route = self.routes[req.full_url]
        if isinstance(route, Exception):
            raise route
        return route


def redirect(url, location, code=302):
    return HTTPError(url, code, "Redirect", {"Location": location}, None)


def make_source(**overrides):
    source = {"id": "alice", "name": "Alice Example", "type": "rss",
              "channel": "research", "platform": "Ghost",
              "homepage": "https://alice.example.com/",
              "feed_url": "https://alice.example.com/feed",
              "cadence": {"posts_per_month": 1.0,
                          "basis": "feed items dated 2026-09-01 and "
                                   "2026-10-01",
                          "as_of": "2026-11-17"},
              "verified_at": "2026-11-17", "enabled": True}
    source.update(overrides)
    return source


def make_pack(sources=None, **overrides):
    pack = {"schema_version": 1, "id": "test-pack", "title": "Test Pack",
            "version": "1.0.0", "curator": {"name": "Test Curator"},
            "description": "A pack used by tests.", "tags": ["test"],
            "coverage": "Only test fixtures.", "verified_at": "2026-11-17",
            "sources": sources if sources is not None else [make_source()]}
    pack.update(overrides)
    return pack


def guarded_fetch(opener, resolver=fake_resolver):
    return lambda url: packs._bounded_fetch_prefix(
        url, opener=opener, resolver=resolver)


class GuardedFetchTests(unittest.TestCase):
    def test_public_direct_fetch(self):
        opener = FakeOpener(
            {"https://a.example.com/feed":
             FakeResponse("https://a.example.com/feed", RSS)})
        final, data, oversized = packs._bounded_fetch_prefix(
            "https://a.example.com/feed", opener=opener,
            resolver=fake_resolver)
        self.assertEqual(final, "https://a.example.com/feed")
        self.assertEqual(data, RSS)
        self.assertFalse(oversized)

    def test_direct_private_host_refused_before_any_fetch(self):
        opener = FakeOpener({})
        with self.assertRaises(packs.FetchRefused) as ctx:
            packs._bounded_fetch_prefix(
                "https://internal.example.com/feed", opener=opener,
                resolver=fake_resolver)
        self.assertIn("non-public", str(ctx.exception))
        self.assertEqual(opener.calls, [])

    def test_mixed_public_and_private_resolution_refused(self):
        opener = FakeOpener({})
        with self.assertRaises(packs.FetchRefused):
            packs._bounded_fetch_prefix(
                "https://mixed.example.com/feed", opener=opener,
                resolver=fake_resolver)
        self.assertEqual(opener.calls, [])

    def test_multicast_resolution_refused(self):
        opener = FakeOpener({})
        with self.assertRaises(packs.FetchRefused):
            packs._bounded_fetch_prefix(
                "https://a.example.com/feed", opener=opener,
                resolver=lambda host: ["224.0.0.1"])
        self.assertEqual(opener.calls, [])

    def test_literal_nonpublic_ip_refused_without_resolution(self):
        def resolver(host):
            raise AssertionError("literal IPs must not be resolved")

        opener = FakeOpener({})
        with self.assertRaises(packs.FetchRefused) as ctx:
            packs._bounded_fetch_prefix(
                "https://169.254.169.254/latest/meta-data", opener=opener,
                resolver=resolver)
        self.assertIn("169.254.169.254", str(ctx.exception))
        self.assertEqual(opener.calls, [])

    def test_unresolvable_host_refused(self):
        def resolver(host):
            raise socket.gaierror("name or service not known")

        with self.assertRaises(packs.FetchRefused) as ctx:
            packs._bounded_fetch_prefix(
                "https://a.example.com/feed", opener=FakeOpener({}),
                resolver=resolver)
        self.assertIn("cannot resolve", str(ctx.exception))

    def test_non_https_entry_refused(self):
        with self.assertRaises(packs.FetchRefused):
            packs._bounded_fetch_prefix(
                "http://a.example.com/feed", opener=FakeOpener({}),
                resolver=fake_resolver)

    def test_public_redirect_chain_within_bound_succeeds(self):
        opener = FakeOpener({
            "https://a.example.com/feed": redirect(
                "https://a.example.com/feed", "https://b.example.com/feed"),
            "https://b.example.com/feed": redirect(
                "https://b.example.com/feed", "https://c.example.com/final"),
            "https://c.example.com/final": FakeResponse(
                "https://c.example.com/final", RSS)})
        final, data, _oversized = packs._bounded_fetch_prefix(
            "https://a.example.com/feed", opener=opener,
            resolver=fake_resolver)
        self.assertEqual(final, "https://c.example.com/final")
        self.assertEqual(data, RSS)
        self.assertEqual(opener.calls, ["https://a.example.com/feed",
                                        "https://b.example.com/feed",
                                        "https://c.example.com/final"])

    def test_relative_redirect_followed_and_checked(self):
        opener = FakeOpener({
            "https://a.example.com/feed": redirect(
                "https://a.example.com/feed", "/feed2"),
            "https://a.example.com/feed2": FakeResponse(
                "https://a.example.com/feed2", RSS)})
        final, _data, _oversized = packs._bounded_fetch_prefix(
            "https://a.example.com/feed", opener=opener,
            resolver=fake_resolver)
        self.assertEqual(final, "https://a.example.com/feed2")

    def test_redirect_to_private_refused_and_never_fetched(self):
        opener = FakeOpener({
            "https://a.example.com/feed": redirect(
                "https://a.example.com/feed",
                "https://internal.example.com/feed")})
        with self.assertRaises(packs.FetchRefused) as ctx:
            packs._bounded_fetch_prefix(
                "https://a.example.com/feed", opener=opener,
                resolver=fake_resolver)
        self.assertIn("non-public", str(ctx.exception))
        self.assertEqual(opener.calls, ["https://a.example.com/feed"])

    def test_redirect_to_http_refused(self):
        opener = FakeOpener({
            "https://a.example.com/feed": redirect(
                "https://a.example.com/feed", "http://b.example.com/feed")})
        with self.assertRaises(packs.FetchRefused) as ctx:
            packs._bounded_fetch_prefix(
                "https://a.example.com/feed", opener=opener,
                resolver=fake_resolver)
        self.assertIn("HTTPS", str(ctx.exception))
        self.assertEqual(opener.calls, ["https://a.example.com/feed"])

    def test_redirect_hop_bound_enforced(self):
        hosts = ["a", "b", "c", "d", "e"]
        routes = {}
        for i in range(len(hosts) - 1):
            here = f"https://{hosts[i]}.example.com/feed"
            routes[here] = redirect(
                here, f"https://{hosts[i + 1]}.example.com/feed")
        opener = FakeOpener(routes)
        with self.assertRaises(packs.FetchRefused) as ctx:
            packs._bounded_fetch_prefix(
                "https://a.example.com/feed", opener=opener,
                resolver=fake_resolver)
        self.assertIn(f"more than {MAX_REDIRECTS} redirects",
                      str(ctx.exception))
        # Entry plus MAX_REDIRECTS followed hops were fetched; the
        # (MAX_REDIRECTS + 1)th redirect answer is refused, not followed.
        self.assertEqual(len(opener.calls), MAX_REDIRECTS + 1)

    def test_redirect_loop_refused(self):
        opener = FakeOpener({
            "https://a.example.com/feed": redirect(
                "https://a.example.com/feed", "https://b.example.com/feed"),
            "https://b.example.com/feed": redirect(
                "https://b.example.com/feed", "https://a.example.com/feed")})
        with self.assertRaises(packs.FetchRefused) as ctx:
            packs._bounded_fetch_prefix(
                "https://a.example.com/feed", opener=opener,
                resolver=fake_resolver)
        self.assertIn("loop", str(ctx.exception))

    def test_http_error_status_still_raises_http_error(self):
        opener = FakeOpener({
            "https://a.example.com/feed": HTTPError(
                "https://a.example.com/feed", 404, "Not Found", {}, None)})
        with self.assertRaises(HTTPError):
            packs._bounded_fetch_prefix(
                "https://a.example.com/feed", opener=opener,
                resolver=fake_resolver)

    def test_refusal_is_a_url_error(self):
        # The property every caller relies on: refusals land in the
        # URLError handling liveness/refresh already have.
        self.assertTrue(issubclass(packs.FetchRefused, URLError))


class RefusalSurfacesTests(unittest.TestCase):
    """A refused feed is recorded in the existing vocabulary, with the
    reason — through the real liveness and refresh paths, composed
    with the real guarded fetch over fake network pieces."""

    def _setup(self):
        source = make_source(feed_url="https://a.example.com/feed",
                             homepage="https://a.example.com/")
        pack = validate_pack(make_pack([source]), today=TODAY)["pack"]
        opener = FakeOpener({
            "https://a.example.com/feed": redirect(
                "https://a.example.com/feed",
                "https://internal.example.com/feed"),
            "https://a.example.com/": FakeResponse(
                "https://a.example.com/", b"<html>home</html>")})
        return pack, guarded_fetch(opener)

    def test_liveness_records_unreachable_with_reason(self):
        pack, fetch = self._setup()
        result = check_liveness(pack, fetch=fetch)
        feed = result["alice"]["feed"]
        self.assertEqual(feed["status"], "unreachable")
        self.assertIn("non-public", feed["error"])
        self.assertEqual(result["alice"]["homepage"]["status"], "live")

    def test_refresh_check_records_unreachable_with_reason(self):
        _pack, fetch = self._setup()
        source = make_source(feed_url="https://a.example.com/feed",
                             homepage="https://a.example.com/")
        report = refresh_check(make_pack([source]), fetch=fetch,
                               today=TODAY)
        feed = report["sources"][0]["feed"]
        self.assertEqual(feed["status"], "unreachable")
        self.assertIn("non-public", feed["error"])


class ValidateGuardTests(unittest.TestCase):
    def test_literal_private_feed_url_is_a_hard_error(self):
        pack = make_pack([make_source(
            feed_url="https://192.168.1.10/feed")])
        report = validate_pack(pack, today=TODAY)
        self.assertFalse(report["valid"])
        self.assertTrue(any("non-public" in e for e in report["errors"]))

    def test_literal_loopback_homepage_is_a_hard_error(self):
        pack = make_pack([make_source(homepage="https://127.0.0.1/")])
        report = validate_pack(pack, today=TODAY)
        self.assertFalse(report["valid"])
        self.assertTrue(any("non-public" in e for e in report["errors"]))

    def test_literal_public_ip_is_allowed(self):
        pack = make_pack([make_source(
            feed_url="https://93.184.216.34/feed")])
        report = validate_pack(pack, today=TODAY)
        self.assertTrue(report["valid"], report["errors"])

    def test_hostname_is_not_resolved_at_validate_time(self):
        # Validation is offline and deterministic: a hostname that
        # would resolve privately is the fetch guard's problem, not a
        # validation error.
        pack = make_pack([make_source(
            feed_url="https://internal.example.com/feed")])
        report = validate_pack(pack, today=TODAY)
        self.assertTrue(report["valid"], report["errors"])

    def test_source_count_at_bound_is_allowed(self):
        sources = [make_source(
            id=f"src-{i:02d}", name=f"Source {i}",
            homepage=f"https://s{i}.example.com/",
            feed_url=f"https://s{i}.example.com/feed")
            for i in range(MAX_SOURCES_PER_PACK)]
        report = validate_pack(make_pack(sources), today=TODAY)
        self.assertTrue(report["valid"], report["errors"])

    def test_source_count_over_bound_is_a_hard_error(self):
        sources = [make_source(
            id=f"src-{i:02d}", name=f"Source {i}",
            homepage=f"https://s{i}.example.com/",
            feed_url=f"https://s{i}.example.com/feed")
            for i in range(MAX_SOURCES_PER_PACK + 1)]
        report = validate_pack(make_pack(sources), today=TODAY)
        self.assertFalse(report["valid"])
        self.assertTrue(any(f"at most {MAX_SOURCES_PER_PACK}" in e
                            for e in report["errors"]))


if __name__ == "__main__":
    unittest.main()
