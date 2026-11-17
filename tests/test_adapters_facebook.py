"""Facebook adapter prototype (focu/adapters/facebook.py).

Covers the adapter contract from the infra design (B.3 + B.5 Seam 1):
no mature open-source tool reads the owner's personal Facebook feed
(facebook-scraper stale since 2024; the Graph API has no personal
feed), so — like RedNote — Focu consumes an export file produced
OUTSIDE Focu, here by the owner's own browser-session tooling on his
logged-in Chrome (the LinkedIn pattern). The module has no platform,
login, or session code at all. Tests pin: export-record normalization
and tolerated aliases, malformed records counted and never crashed
on, the LinkedIn unit shape, per-day URL identity (the 2026-11-15
LinkedIn lesson), Denver day filtering on collection-day semantics,
the hard daily cap of 15 (the lowest of the four platforms), the
owner's-own-post skip, and clean reports (never tracebacks) for
missing / unparseable / wrongly-shaped export files. Fixtures only:
no network, no platform access.
"""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from focu.adapters import facebook
from focu.adapters.facebook import (AdapterConfig, emit, gist_for,
                                    normalize_record, parse_timestamp)
from focu.daily.identity import canonical_url, content_identity

DAY = "2026-11-17"        # a Tuesday; America/Denver is MST (UTC-7)
DAY_BEFORE = "2026-11-16"


def post_record(n=1, author=None, text=None, url=None,
                published_at="2026-11-17T08:30:00-07:00",
                collected_at="2026-11-17T09:12:44-07:00", **extra):
    """One export record in the shape the module docstring defines."""
    record = {
        "post_id": f"post{n}",
        "author": author if author is not None else f"Friend {n}",
        "text": text if text is not None else f"Post text {n}",
        "url": url if url is not None
               else f"https://www.facebook.com/friend{n}/posts/post{n}",
        "published_at": published_at,
        "collected_at": collected_at,
    }
    record.update(extra)
    return record


def write_export(tmp, payload, name="export.json"):
    path = Path(tmp) / name
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False),
                        encoding="utf-8")
    return str(path)


class ParseTimestampTests(unittest.TestCase):
    def test_iso_with_offset_and_zulu(self):
        parsed = parse_timestamp("2026-11-17T09:12:44-07:00")
        self.assertEqual(parsed.utcoffset().total_seconds(), -7 * 3600)
        zulu = parse_timestamp("2026-11-17T16:12:44Z")
        self.assertEqual(zulu, parsed)

    def test_naive_is_read_as_utc_never_localized(self):
        parsed = parse_timestamp("2026-11-17T16:12:44")
        self.assertEqual(parsed.tzinfo, timezone.utc)

    def test_epoch_seconds_and_milliseconds(self):
        expected = datetime(2026, 11, 17, 16, 12, 44, tzinfo=timezone.utc)
        self.assertEqual(parse_timestamp(1794931964), expected)
        self.assertEqual(parse_timestamp(1794931964000), expected)

    def test_non_timestamps_are_none(self):
        self.assertIsNone(parse_timestamp(None))
        self.assertIsNone(parse_timestamp(""))
        self.assertIsNone(parse_timestamp("not a date"))
        self.assertIsNone(parse_timestamp(True))
        self.assertIsNone(parse_timestamp({"at": "2026-11-17"}))


class NormalizeRecordTests(unittest.TestCase):
    def test_normalize_record_fields(self):
        post = normalize_record(post_record(7, author_id="u-7"))
        self.assertIsNotNone(post)
        self.assertEqual(post.author, "Friend 7")
        self.assertEqual(post.author_id, "u-7")
        self.assertEqual(post.post_id, "post7")
        self.assertEqual(post.url,
                         "https://www.facebook.com/friend7/posts/post7")
        self.assertEqual(post.published,
                         datetime(2026, 11, 17, 15, 30, tzinfo=timezone.utc))
        self.assertEqual(post.collected,
                         datetime(2026, 11, 17, 16, 12, 44, tzinfo=timezone.utc))

    def test_exporter_aliases_are_tolerated(self):
        post = normalize_record({
            "author": "Alice", "text": "hello",
            "permalink": "https://www.facebook.com/alice/posts/abc",
            "time": 1794931964000})
        self.assertIsNotNone(post)
        self.assertEqual(post.author, "Alice")
        self.assertEqual(post.url, "https://www.facebook.com/alice/posts/abc")
        self.assertEqual(post.published,
                         datetime(2026, 11, 17, 16, 12, 44, tzinfo=timezone.utc))
        self.assertIsNone(post.collected)

    def test_malformed_records_return_none(self):
        self.assertIsNone(normalize_record("not an object"))
        self.assertIsNone(normalize_record(None))
        self.assertIsNone(normalize_record(post_record(author="")))
        self.assertIsNone(normalize_record(post_record(url="")))
        self.assertIsNone(normalize_record(post_record(url="ftp://x/y")))
        record = post_record()
        del record["published_at"], record["collected_at"]
        self.assertIsNone(normalize_record(record))
        self.assertIsNone(normalize_record(
            post_record(published_at="garbage", collected_at=None)))


class GistTests(unittest.TestCase):
    def test_text_is_the_gist_truncated_at_30_words(self):
        text = " ".join(f"word{i}" for i in range(40))
        post = normalize_record(post_record(text=text))
        self.assertEqual(gist_for(post), " ".join(f"word{i}" for i in range(30)))

    def test_textless_post_gets_a_factual_label(self):
        post = normalize_record(post_record(text=""))
        self.assertEqual(gist_for(post), "Post (no text)")


class EmitShapeTests(unittest.TestCase):
    def test_emit_shape_matches_linkedin_unit(self):
        records = [post_record(1, author="alice", text="Earlier post",
                               published_at="2026-11-17T10:00:00-07:00"),
                   post_record(2, author="bob", text="Later post",
                               published_at="2026-11-17T20:00:00-07:00")]
        with tempfile.TemporaryDirectory() as tmp:
            export = write_export(tmp, records)
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, export, out)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(report["units"], 1)
        self.assertEqual(report["failures"], [])
        self.assertEqual(report["feed"]["records"], 2)
        self.assertEqual(report["feed"]["included"], 2)
        self.assertEqual(len(units), 1)
        unit = units[0]
        # Exactly the Seam-1 keys, all strings.
        self.assertEqual(set(unit), {"source", "title", "url", "published_at", "body"})
        for value in unit.values():
            self.assertIsInstance(value, str)
        self.assertEqual(unit["source"], "Facebook Feed")
        self.assertEqual(unit["title"], "Facebook Feed — Tuesday, November 17, 2026")
        self.assertEqual(unit["url"], f"https://www.facebook.com/?day={DAY}")
        # End of the Denver day, full ISO offset (MST in November).
        self.assertEqual(unit["published_at"], "2026-11-17T23:59:00-07:00")
        lines = unit["body"].split("\n")
        self.assertEqual(len(lines), 2)
        # Newest first, LinkedIn line shape: N. author — gist (url).
        self.assertEqual(lines[0], "1. bob — Later post "
                                   "(https://www.facebook.com/friend2/posts/post2)")
        self.assertEqual(lines[1], "2. alice — Earlier post "
                                   "(https://www.facebook.com/friend1/posts/post1)")

    def test_empty_day_still_writes_a_valid_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            export = write_export(tmp, [])
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, export, out)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(units, [])
        self.assertEqual(report["units"], 0)
        self.assertEqual(report["failures"], [])


class IdentityTests(unittest.TestCase):
    def test_per_day_url_identity_differs(self):
        units_by_day = {}
        with tempfile.TemporaryDirectory() as tmp:
            for day, record in (
                    (DAY_BEFORE, post_record(
                        16, published_at="2026-11-16T12:00:00-07:00",
                        collected_at="2026-11-16T10:00:00-07:00")),
                    (DAY, post_record(
                        17, published_at="2026-11-17T12:00:00-07:00",
                        collected_at="2026-11-17T10:00:00-07:00"))):
                export = write_export(tmp, [record], name=f"export-{day}.json")
                out = str(Path(tmp) / f"units-{day}.json")
                emit(day, export, out)
                units_by_day[day] = json.loads(
                    Path(out).read_text(encoding="utf-8"))[0]
        url16, url17 = units_by_day[DAY_BEFORE]["url"], units_by_day[DAY]["url"]
        self.assertNotEqual(url16, url17)
        self.assertTrue(url16.endswith(f"?day={DAY_BEFORE}"))
        self.assertTrue(url17.endswith(f"?day={DAY}"))
        # The pipeline's own identity function must keep the days apart:
        # canonicalization preserves ?day=, so the stable content
        # identities differ (the 2026-11-15 LinkedIn lesson).
        self.assertNotEqual(canonical_url(url16), canonical_url(url17))
        id16, _, _ = content_identity(units_by_day[DAY_BEFORE], "src_test")
        id17, _, _ = content_identity(units_by_day[DAY], "src_test")
        self.assertNotEqual(id16, id17)


class DayBoundaryTests(unittest.TestCase):
    def test_collection_day_across_the_denver_boundary(self):
        # 05:30 UTC on the 18th is 22:30 MST on the 17th; 06:59 UTC on
        # the 17th is 23:59 MST on the 16th. Day membership follows
        # collected_at in Denver, whatever the publication date was.
        records = [post_record(17, published_at="2026-11-10T12:00:00-07:00",
                               collected_at="2026-11-18T05:30:00Z"),
                   post_record(16, published_at="2026-11-10T12:00:00-07:00",
                               collected_at="2026-11-17T06:59:00Z")]
        with tempfile.TemporaryDirectory() as tmp:
            export = write_export(tmp, records)
            out17 = str(Path(tmp) / "u17.json")
            report17 = emit(DAY, export, out17)
            units17 = json.loads(Path(out17).read_text(encoding="utf-8"))
            out16 = str(Path(tmp) / "u16.json")
            emit(DAY_BEFORE, export, out16)
            units16 = json.loads(Path(out16).read_text(encoding="utf-8"))
        self.assertEqual(len(units17), 1)
        self.assertIn("/post17", units17[0]["body"])
        self.assertNotIn("/post16", units17[0]["body"])
        self.assertEqual(report17["feed"]["off_day"], 1)
        self.assertEqual(len(units16), 1)
        self.assertIn("/post16", units16[0]["body"])

    def test_published_day_is_the_fallback_without_collected_at(self):
        record = post_record(1, published_at="2026-11-17T20:00:00-07:00")
        del record["collected_at"]
        # 20:00 MST is still the 17th in Denver.
        with tempfile.TemporaryDirectory() as tmp:
            export = write_export(tmp, [record])
            out = str(Path(tmp) / "units.json")
            emit(DAY, export, out)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(len(units), 1)
        self.assertIn("/post1", units[0]["body"])


class CapTests(unittest.TestCase):
    def test_default_cap_is_15_and_keeps_the_newest(self):
        records = [post_record(i, published_at=f"2026-11-17T{i % 24:02d}:00:00-07:00")
                   for i in range(20)]
        with tempfile.TemporaryDirectory() as tmp:
            export = write_export(tmp, records)
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, export, out)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(report["feed"]["cap"], 15)
        self.assertEqual(report["feed"]["included"], 15)
        self.assertEqual(report["feed"]["over_cap"], 5)
        self.assertEqual(len(units[0]["body"].split("\n")), 15)

    def test_config_cap_override(self):
        records = [post_record(i) for i in range(6)]
        with tempfile.TemporaryDirectory() as tmp:
            export = write_export(tmp, records)
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, export, out, config=AdapterConfig(max_per_day=3))
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(report["feed"]["included"], 3)
        self.assertEqual(len(units[0]["body"].split("\n")), 3)

    def test_duplicate_urls_collapse_before_the_cap(self):
        records = [post_record(1), post_record(1), post_record(2)]
        with tempfile.TemporaryDirectory() as tmp:
            export = write_export(tmp, records)
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, export, out)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(report["feed"]["duplicates"], 1)
        self.assertEqual(report["feed"]["included"], 2)
        self.assertEqual(len(units[0]["body"].split("\n")), 2)


class OwnPostTests(unittest.TestCase):
    def test_owners_own_posts_are_skipped_by_name_and_id(self):
        records = [post_record(1, author="Jerry", author_id="u-other"),
                   post_record(2, author="Someone Else", author_id="JERRY"),
                   post_record(3, author="alice", author_id="u-alice")]
        with tempfile.TemporaryDirectory() as tmp:
            export = write_export(tmp, records)
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, export, out, config=AdapterConfig(owner="jerry"))
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        # Case-insensitive against both the display name and the id.
        self.assertEqual(report["feed"]["skipped_own"], 2)
        self.assertEqual(report["feed"]["included"], 1)
        self.assertIn("/post3", units[0]["body"])

    def test_no_owner_configured_skips_nothing(self):
        records = [post_record(1, author="Jerry Yu")]
        with tempfile.TemporaryDirectory() as tmp:
            export = write_export(tmp, records)
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, export, out)
        self.assertEqual(report["feed"]["skipped_own"], 0)
        self.assertEqual(report["feed"]["included"], 1)


class MalformedTests(unittest.TestCase):
    def test_malformed_records_are_counted_never_crashed_on(self):
        records = [post_record(1), "junk", 42, None,
                   post_record(author=""), post_record(url=""),
                   post_record(published_at="garbage", collected_at=None),
                   post_record(2)]
        with tempfile.TemporaryDirectory() as tmp:
            export = write_export(tmp, records)
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, export, out)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(report["feed"]["records"], 8)
        self.assertEqual(report["feed"]["malformed"], 6)
        self.assertEqual(report["feed"]["included"], 2)
        self.assertEqual(report["failures"], [])
        self.assertEqual(len(units), 1)
        self.assertIn("/post1", units[0]["body"])
        self.assertIn("/post2", units[0]["body"])


class FailureTests(unittest.TestCase):
    def test_missing_export_is_a_clean_report_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "no-such-export.json")
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, missing, out)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(units, [])
        self.assertEqual(report["units"], 0)
        self.assertEqual(len(report["failures"]), 1)
        self.assertEqual(report["failures"][0]["error"], "ExportFileNotFound")

    def test_unparseable_export_is_a_clean_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            export = write_export(tmp, "{not json")
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, export, out)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(units, [])
        self.assertEqual(len(report["failures"]), 1)
        self.assertEqual(report["failures"][0]["error"], "ExportParseError")

    def test_non_list_export_is_a_clean_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            export = write_export(tmp, {"posts": []})
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, export, out)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(units, [])
        self.assertEqual(len(report["failures"]), 1)
        self.assertEqual(report["failures"][0]["error"], "ExportShapeError")


class CliTests(unittest.TestCase):
    def test_module_cli_emit(self):
        with tempfile.TemporaryDirectory() as tmp:
            export = write_export(tmp, [post_record(1)])
            out = str(Path(tmp) / "units.json")
            code = facebook.main(["emit", "--day", DAY, "--export", export,
                                  "--out", out])
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["source"], "Facebook Feed")

    def test_module_cli_owner_and_cap_flags(self):
        records = [post_record(1, author="Jerry Yu"), post_record(2),
                   post_record(3)]
        with tempfile.TemporaryDirectory() as tmp:
            export = write_export(tmp, records)
            out = str(Path(tmp) / "units.json")
            code = facebook.main(["emit", "--day", DAY, "--export", export,
                                  "--out", out, "--owner", "jerry yu",
                                  "--max-per-day", "1"])
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(len(units[0]["body"].split("\n")), 1)
        self.assertNotIn("/post1", units[0]["body"])

    def test_focu_cli_dispatch(self):
        from focu.cli import main as focu_main
        with tempfile.TemporaryDirectory() as tmp:
            export = write_export(tmp, [post_record(1)])
            out = str(Path(tmp) / "units.json")
            code = focu_main(["facebook-adapter", "emit", "--day", DAY,
                              "--export", export, "--out", out])
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(len(units), 1)


if __name__ == "__main__":
    unittest.main()
