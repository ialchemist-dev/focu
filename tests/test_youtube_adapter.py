"""YouTube adapter prototype (focu/adapters/youtube.py).

Covers the adapter contract from the infra design (B.5 Seam 1) with the
LinkedIn emitter as reference: RSS discovery, the hard per-channel daily
cap, transcript-missing withholding as pending (never emitted empty),
per-day URL identity (the 2026-11-15 LinkedIn lesson), the LinkedIn
unit shape, the production transcript ladder, and per-channel failure
isolation. Network is fully fixtured: feed bytes and transcripts come
from fakes, so nothing here touches YouTube.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from focu.adapters import youtube
from focu.adapters.youtube import (AdapterConfig, emit, fetch_transcript,
                                   parse_feed, vtt_to_text)
from focu.daily.identity import canonical_url, content_identity

DAY = "2026-11-17"        # a Tuesday; America/Denver is MST (UTC-7)
DAY_BEFORE = "2026-11-16"
CHANNEL_ID = "UCtestchannel"
LONG = " ".join(["a real transcript sentence"] * 30)  # ~840 chars > 200


def feed_xml(channel_title, entries):
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" '
             'xmlns="http://www.w3.org/2005/Atom">',
             f"<title>{channel_title}</title>"]
    for video_id, title, published in entries:
        parts.append(
            "<entry>"
            f"<id>yt:video:{video_id}</id><yt:videoId>{video_id}</yt:videoId>"
            f"<yt:channelId>{CHANNEL_ID}</yt:channelId>"
            f"<title>{title}</title>"
            f'<link rel="alternate" href="https://www.youtube.com/watch?v={video_id}"/>'
            f"<author><name>{channel_title}</name></author>"
            f"<published>{published}</published><updated>{published}</updated>"
            "</entry>")
    parts.append("</feed>")
    return "".join(parts).encode("utf-8")


class FakeNetwork:
    """Injectable fetchers: feeds by channel id, transcripts by video id."""

    def __init__(self, feeds, transcripts):
        self.feeds = feeds
        self.transcripts = transcripts
        self.feed_calls = []
        self.transcript_calls = []

    def fetch_feed(self, channel_id):
        self.feed_calls.append(channel_id)
        result = self.feeds[channel_id]
        if isinstance(result, Exception):
            raise result
        return result

    def fetch_transcript(self, video_id):
        self.transcript_calls.append(video_id)
        return self.transcripts.get(video_id, ("", ""))


def one_channel_feed(entries, title="Test Channel"):
    return {CHANNEL_ID: feed_xml(title, entries)}


class ParseFeedTests(unittest.TestCase):
    def test_parse_feed_extracts_entries(self):
        payload = feed_xml("Test Channel", [
            ("VID1", "First video", "2026-11-17T15:00:00+00:00"),
            ("VID2", "Second video", "2026-11-16T15:00:00+00:00"),
            ("VID3", "Broken entry", "not-a-date"),
        ])
        title, entries = parse_feed(payload)
        self.assertEqual(title, "Test Channel")
        # The entry with an unparseable timestamp is skipped, never guessed.
        self.assertEqual([e.video_id for e in entries], ["VID1", "VID2"])
        first = entries[0]
        self.assertEqual(first.title, "First video")
        self.assertEqual(first.author, "Test Channel")
        self.assertEqual(first.link, "https://www.youtube.com/watch?v=VID1")
        self.assertEqual(first.published.isoformat(), "2026-11-17T15:00:00+00:00")


class EmitShapeTests(unittest.TestCase):
    def test_emit_shape_matches_linkedin_unit(self):
        net = FakeNetwork(
            one_channel_feed([("VID1", "First video", "2026-11-17T15:00:00+00:00")]),
            {"VID1": (LONG, "api")})
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, [{"name": "Test Source", "channel_id": CHANNEL_ID}],
                          out, fetch_feed=net.fetch_feed,
                          fetch_transcript=net.fetch_transcript)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(report["units"], 1)
        self.assertEqual(len(units), 1)
        unit = units[0]
        # The LinkedIn emitter's keys, all present with the same types.
        for key in ("source", "title", "url", "published_at", "body"):
            self.assertIn(key, unit)
            self.assertIsInstance(unit[key], str)
        self.assertEqual(unit["source"], "Test Source")
        self.assertEqual(unit["title"], "Test Source — Tuesday, November 17, 2026")
        self.assertEqual(unit["url"],
                         f"https://www.youtube.com/channel/{CHANNEL_ID}?day={DAY}")
        # End of the Denver day, full ISO offset (MST in November).
        self.assertEqual(unit["published_at"], "2026-11-17T23:59:00-07:00")
        self.assertIn("First video", unit["body"])
        self.assertIn("https://www.youtube.com/watch?v=VID1", unit["body"])
        self.assertIn(LONG, unit["body"])
        self.assertEqual(report["channels"][0]["transcript_via"], ["api"])

    def test_denver_day_boundary(self):
        # 05:30 UTC on the 17th is still the 16th in Denver; 06:59 UTC on
        # the 18th is 23:59 MST on the 17th.
        entries = [("VIDUTC", "UTC date only", "2026-11-17T05:30:00+00:00"),
                   ("VIDLATE", "Late Denver", "2026-11-18T06:59:00+00:00")]
        transcripts = {"VIDUTC": (LONG, "api"), "VIDLATE": (LONG, "api")}
        with tempfile.TemporaryDirectory() as tmp:
            net = FakeNetwork(one_channel_feed(entries), transcripts)
            out17 = str(Path(tmp) / "u17.json")
            emit(DAY, [{"channel_id": CHANNEL_ID}], out17,
                 fetch_feed=net.fetch_feed, fetch_transcript=net.fetch_transcript)
            units17 = json.loads(Path(out17).read_text(encoding="utf-8"))
            net2 = FakeNetwork(one_channel_feed(entries), transcripts)
            out16 = str(Path(tmp) / "u16.json")
            emit(DAY_BEFORE, [{"channel_id": CHANNEL_ID}], out16,
                 fetch_feed=net2.fetch_feed, fetch_transcript=net2.fetch_transcript)
            units16 = json.loads(Path(out16).read_text(encoding="utf-8"))
            out18 = str(Path(tmp) / "u18.json")
            emit("2026-11-18", [{"channel_id": CHANNEL_ID}], out18,
                 fetch_feed=net2.fetch_feed, fetch_transcript=net2.fetch_transcript)
            units18 = json.loads(Path(out18).read_text(encoding="utf-8"))
        self.assertEqual(len(units17), 1)
        self.assertIn("https://www.youtube.com/watch?v=VIDLATE", units17[0]["body"])
        self.assertNotIn("VIDUTC", units17[0]["body"])
        self.assertEqual(len(units16), 1)
        self.assertIn("https://www.youtube.com/watch?v=VIDUTC", units16[0]["body"])
        # A day with nothing collected still writes a valid empty list.
        self.assertEqual(units18, [])


class CapTests(unittest.TestCase):
    ENTRIES = [(f"VID{i}", f"Video {i}", f"2026-11-17T{10 + i:02d}:00:00+00:00")
               for i in range(4)]

    def test_default_cap_is_two(self):
        transcripts = {f"VID{i}": (LONG, "api") for i in range(4)}
        net = FakeNetwork(one_channel_feed(self.ENTRIES), transcripts)
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, [{"channel_id": CHANNEL_ID}], out,
                          fetch_feed=net.fetch_feed,
                          fetch_transcript=net.fetch_transcript)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        # Cap counts candidates: transcripts are fetched for the newest
        # two only (feed order), the rest are never touched.
        self.assertEqual(net.transcript_calls, ["VID0", "VID1"])
        self.assertEqual(report["channels"][0]["candidates"], 2)
        self.assertEqual(len(units), 1)
        self.assertIn("Video 0", units[0]["body"])
        self.assertIn("Video 1", units[0]["body"])
        self.assertNotIn("Video 2", units[0]["body"])

    def test_per_channel_cap_override(self):
        transcripts = {f"VID{i}": (LONG, "api") for i in range(4)}
        net = FakeNetwork(one_channel_feed(self.ENTRIES), transcripts)
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, [{"channel_id": CHANNEL_ID, "max_items": 3}], out,
                          fetch_feed=net.fetch_feed,
                          fetch_transcript=net.fetch_transcript)
        self.assertEqual(report["channels"][0]["candidates"], 3)
        self.assertEqual(net.transcript_calls, ["VID0", "VID1", "VID2"])

    def test_config_cap_when_channel_has_none(self):
        transcripts = {f"VID{i}": (LONG, "api") for i in range(4)}
        net = FakeNetwork(one_channel_feed(self.ENTRIES), transcripts)
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, [{"channel_id": CHANNEL_ID}], out,
                          config=AdapterConfig(max_per_channel=1),
                          fetch_feed=net.fetch_feed,
                          fetch_transcript=net.fetch_transcript)
        self.assertEqual(report["channels"][0]["candidates"], 1)


class PendingTests(unittest.TestCase):
    def test_missing_transcript_withheld_as_pending(self):
        entries = [("VIDOK", "Has transcript", "2026-11-17T15:00:00+00:00"),
                   ("VIDNO", "No transcript", "2026-11-17T16:00:00+00:00")]
        net = FakeNetwork(one_channel_feed(entries), {"VIDOK": (LONG, "api")})
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, [{"name": "Test Source", "channel_id": CHANNEL_ID}],
                          out, fetch_feed=net.fetch_feed,
                          fetch_transcript=net.fetch_transcript)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(len(units), 1)
        self.assertIn("Has transcript", units[0]["body"])
        self.assertNotIn("No transcript", units[0]["body"])
        self.assertEqual(len(report["pending_transcripts"]), 1)
        pending = report["pending_transcripts"][0]
        self.assertEqual(pending["video_id"], "VIDNO")
        self.assertEqual(pending["title"], "No transcript")
        self.assertEqual(pending["source"], "Test Source")

    def test_all_missing_emits_no_unit_but_reports_pending(self):
        entries = [("VID1", "One", "2026-11-17T15:00:00+00:00"),
                   ("VID2", "Two", "2026-11-17T16:00:00+00:00")]
        net = FakeNetwork(one_channel_feed(entries), {})
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, [{"channel_id": CHANNEL_ID}], out,
                          fetch_feed=net.fetch_feed,
                          fetch_transcript=net.fetch_transcript)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(units, [])
        self.assertEqual(report["units"], 0)
        self.assertEqual([p["video_id"] for p in report["pending_transcripts"]],
                         ["VID1", "VID2"])


class IdentityTests(unittest.TestCase):
    def test_per_day_url_identity_differs(self):
        entries = [("VID16", "Monday video", "2026-11-16T18:00:00+00:00"),
                   ("VID17", "Tuesday video", "2026-11-17T18:00:00+00:00")]
        transcripts = {"VID16": (LONG, "api"), "VID17": (LONG, "api")}
        units_by_day = {}
        with tempfile.TemporaryDirectory() as tmp:
            for day in (DAY_BEFORE, DAY):
                net = FakeNetwork(one_channel_feed(entries), transcripts)
                out = str(Path(tmp) / f"units-{day}.json")
                emit(day, [{"channel_id": CHANNEL_ID}], out,
                     fetch_feed=net.fetch_feed,
                     fetch_transcript=net.fetch_transcript)
                units_by_day[day] = json.loads(Path(out).read_text(encoding="utf-8"))[0]
        url16, url17 = units_by_day[DAY_BEFORE]["url"], units_by_day[DAY]["url"]
        self.assertNotEqual(url16, url17)
        self.assertTrue(url16.endswith(f"?day={DAY_BEFORE}"))
        self.assertTrue(url17.endswith(f"?day={DAY}"))
        # The pipeline's own identity function must keep the days apart:
        # canonicalization preserves ?day= on channel URLs, so the stable
        # content identities differ (the 2026-11-15 LinkedIn lesson).
        self.assertNotEqual(canonical_url(url16), canonical_url(url17))
        id16, _, _ = content_identity(units_by_day[DAY_BEFORE], "src_test")
        id17, _, _ = content_identity(units_by_day[DAY], "src_test")
        self.assertNotEqual(id16, id17)


class FailureIsolationTests(unittest.TestCase):
    def test_one_channel_failure_never_blocks_others(self):
        feeds = {"UCbroken": RuntimeError("boom"),
                 CHANNEL_ID: feed_xml("Test Channel", [
                     ("VID1", "First video", "2026-11-17T15:00:00+00:00")])}
        net = FakeNetwork(feeds, {"VID1": (LONG, "api")})
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "units.json")
            report = emit(DAY, [{"name": "Broken", "channel_id": "UCbroken"},
                                {"name": "Test Source", "channel_id": CHANNEL_ID}],
                          out, fetch_feed=net.fetch_feed,
                          fetch_transcript=net.fetch_transcript)
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["source"], "Test Source")
        self.assertEqual(len(report["failures"]), 1)
        self.assertEqual(report["failures"][0]["channel_id"], "UCbroken")
        self.assertEqual(report["failures"][0]["error"], "RuntimeError")


class LadderTests(unittest.TestCase):
    def test_api_hit_short_circuits(self):
        calls = []

        def api(video_id):
            calls.append("api")
            return LONG

        def ytdlp(video_id):
            calls.append("ytdlp")
            return LONG

        body, via = fetch_transcript("VID", via_api=api, via_ytdlp=ytdlp)
        self.assertEqual((body, via), (LONG, "api"))
        self.assertEqual(calls, ["api"])

    def test_short_api_body_falls_through_to_ytdlp(self):
        body, via = fetch_transcript(
            "VID", via_api=lambda vid: "too short",
            via_ytdlp=lambda vid: LONG)
        self.assertEqual((body, via), (LONG, "yt-dlp-android"))

    def test_api_exception_falls_through(self):
        def api(video_id):
            raise RuntimeError("IpBlocked")

        body, via = fetch_transcript("VID", via_api=api,
                                     via_ytdlp=lambda vid: LONG)
        self.assertEqual(via, "yt-dlp-android")

    def test_both_rungs_short_means_missing(self):
        body, via = fetch_transcript(
            "VID", via_api=lambda vid: "short", via_ytdlp=lambda vid: "")
        self.assertEqual((body, via), ("", ""))

    def test_vtt_to_text_dedupes_and_strips(self):
        vtt = ("WEBVTT\nKind: captions\nLanguage: en\n\n"
               "00:00:01.000 --> 00:00:02.000\n<c>Hello</c> world\n\n"
               "00:00:02.000 --> 00:00:03.000\nHello world\n\n"
               "00:00:03.000 --> 00:00:04.000\nNext line\n")
        self.assertEqual(vtt_to_text(vtt), "Hello world Next line")


GOOD_VTT = "WEBVTT\nKind: captions\nLanguage: en\n\n" + "\n\n".join(
    f"00:00:{i:02d}.000 --> 00:00:{i + 1:02d}.000\nSubtitle line {i} with enough words"
    for i in range(30))


class YtdlpRungTests(unittest.TestCase):
    """The yt-dlp rung's per-group invocations (P2-5 live finding,
    2026-11-18): yt-dlp aborts an invocation on the first track that
    hits HTTP 429, so one language group failing must not discard the
    next group's tracks. subprocess is faked; nothing here is live."""

    def run_rung(self, writer):
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            group = args[args.index("--sub-langs") + 1]
            template = args[args.index("-o") + 1]
            writer(group, Path(template).parent)

        fake_subprocess = mock.Mock()
        fake_subprocess.run = fake_run
        with mock.patch.object(youtube, "_ytdlp_binary", lambda: "/fake/yt-dlp"), \
                mock.patch.object(youtube, "subprocess", fake_subprocess):
            return youtube.transcript_via_ytdlp("VID"), calls

    def test_failed_first_group_falls_through_to_second(self):
        def writer(group, tmp):
            if group.startswith("en"):
                (tmp / "sub.en.vtt").write_text(GOOD_VTT, encoding="utf-8")
            # The zh group writes nothing: its first track hit a 429 and
            # yt-dlp aborted the invocation (the live 2026-11-18 shape).

        text, calls = self.run_rung(writer)
        self.assertGreaterEqual(len(text), 200)
        self.assertIn("Subtitle line 0", text)
        self.assertEqual(len(calls), 2)

    def test_first_group_hit_short_circuits(self):
        def writer(group, tmp):
            (tmp / "sub.zh-Hans.vtt").write_text(GOOD_VTT, encoding="utf-8")

        text, calls = self.run_rung(writer)
        self.assertGreaterEqual(len(text), 200)
        self.assertEqual(len(calls), 1)

    def test_all_groups_empty_means_missing(self):
        text, calls = self.run_rung(lambda group, tmp: None)
        self.assertEqual(text, "")
        self.assertEqual(len(calls), 2)

    def test_no_binary_means_missing_without_a_subprocess(self):
        fake_subprocess = mock.Mock()
        with mock.patch.object(youtube, "_ytdlp_binary", lambda: None), \
                mock.patch.object(youtube, "subprocess", fake_subprocess):
            self.assertEqual(youtube.transcript_via_ytdlp("VID"), "")
        fake_subprocess.run.assert_not_called()


class CliTests(unittest.TestCase):
    def test_cli_emit_with_registry_file(self):
        registry = {"sources": [{"name": "Test Source",
                                 "channel_id": CHANNEL_ID, "max_items": 2}]}
        net = FakeNetwork(
            one_channel_feed([("VID1", "First video", "2026-11-17T15:00:00+00:00")]),
            {"VID1": (LONG, "api")})
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "youtube_sources.json"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            out = str(Path(tmp) / "units.json")
            with mock.patch.object(youtube, "fetch_feed_bytes", net.fetch_feed), \
                    mock.patch.object(youtube, "fetch_transcript",
                                      lambda vid, **kw: net.fetch_transcript(vid)):
                code = youtube.main(["emit", "--day", DAY, "--channels",
                                     str(registry_path), "--out", out])
            units = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["source"], "Test Source")

    def test_cli_comma_ids_pending_out_and_cap_flag(self):
        entries = [("VID1", "One", "2026-11-17T15:00:00+00:00"),
                   ("VID2", "Two", "2026-11-17T16:00:00+00:00")]
        net = FakeNetwork(one_channel_feed(entries), {"VID1": (LONG, "api")})
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "units.json")
            pending_out = str(Path(tmp) / "pending.json")
            with mock.patch.object(youtube, "fetch_feed_bytes", net.fetch_feed), \
                    mock.patch.object(youtube, "fetch_transcript",
                                      lambda vid, **kw: net.fetch_transcript(vid)):
                code = youtube.main(["emit", "--day", DAY, "--channels", CHANNEL_ID,
                                     "--out", out, "--max-per-channel", "1",
                                     "--pending-out", pending_out])
            units = json.loads(Path(out).read_text(encoding="utf-8"))
            pending = json.loads(Path(pending_out).read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        # Cap flag = 1: only VID1 was a candidate, so nothing is pending
        # and the bare-ID source name comes from the feed's own title.
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["source"], "Test Channel")
        self.assertEqual(pending, [])
        self.assertEqual(net.transcript_calls, ["VID1"])


if __name__ == "__main__":
    unittest.main()
