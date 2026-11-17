import json
from pathlib import Path
import tempfile
import os
import shutil
import subprocess
from unittest.mock import patch
import unittest
from publish import build, sha256, episode_date
from editorial import editorial, blocks_from_markdown, compose_article_with_openai, clean
from cover_art import typographic_svg

class PublisherTests(unittest.TestCase):
    def test_build_and_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            deliveries = root / "deliveries"
            folder = deliveries / "frontier-20261102"
            folder.mkdir(parents=True)
            (folder / "podcast.mp3").write_bytes(b"real-existing-audio-fixture")
            (folder / "research.md").write_text("# A Research Briefing\n")
            template = Path(__file__).with_name("index.html")
            output = root / "artifact-v1"
            self.assertEqual(build(deliveries, output, template, 15), 1)
            data = json.loads((output / "assets/episodes.json").read_text())
            episode = data["episodes"][0]
            self.assertEqual(episode["title"], "A Research Briefing")
            self.assertEqual(sha256(output / episode["audio_url"]), sha256(folder / "podcast.mp3"))
            self.assertIn("A Research Briefing", (output / "index.html").read_text())
            with self.assertRaises(FileExistsError):
                build(deliveries, output, template, 15)

    def test_gfm_financial_table_preserves_figure_columns_and_exact_values(self):
        markdown = (
            "# Quarterly financial results\n\n"
            "| Item (Q3 2026) | Figure | Notes / comparatives |\n"
            "|:---|---:|:---|\n"
            "| Revenue | **$116k** ($116 thousand) | vs $55k Q3 2025 (+110% per table; Seeking Alpha calculates +140%) |\n"
            "| Net income (consolidated) | **+$11.66M** | vs −$15.79M Q3 2025; 9M: −$76.09M |\n"
            "| Net loss attributable | **−$20.8M** | −$19.527M in income statement; see discrepancy note |\n"
            "| Geography | N/A | Utah \| Nevada comparison |\n\n"
            "The report includes an important reconciliation note."
        )
        blocks = blocks_from_markdown(markdown)
        tables = [block for block in blocks if block["type"] == "table"]
        self.assertEqual(len(tables), 1)
        table = tables[0]
        self.assertEqual(table["headers"], ["Item (Q3 2026)", "Figure", "Notes / comparatives"])
        self.assertEqual(table["align"], ["left", "right", "left"])
        self.assertEqual(len(table["rows"]), 4)
        self.assertEqual(table["rows"][0][1], "**$116k** ($116 thousand)")
        self.assertIn("+140%", table["rows"][0][2])
        self.assertEqual(table["rows"][1][1], "**+$11.66M**")
        self.assertEqual(table["rows"][2][1], "**−$20.8M**")
        self.assertEqual(table["rows"][3][2], "Utah | Nevada comparison")
        self.assertTrue(any(b["type"] == "paragraph" and "reconciliation" in b["text"] for b in blocks))

    def test_table_is_published_as_structured_blocks_without_rewriting_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "financial-20261109"
            folder.mkdir(parents=True)
            markdown = (
                "# Financial original\n\n"
                "| Metric | Amount | Comparison |\n"
                "| --- | ---: | --- |\n"
                "| Revenue | **$116k** | Q3 2025: $55k |\n"
                "| Loss | **−$20.8M** | Consolidated reconciliation |\n"
            )
            (folder / "article.md").write_text(markdown, encoding="utf-8")
            (folder / "content.json").write_text(json.dumps({
                "content_id": "financial-2026-11-09",
                "origin": "user_initiated", "podcast_mode": "none"
            }), encoding="utf-8")
            bundle = root / "bundle"
            build(root / "deliveries", bundle, Path(__file__).with_name("index.html"), 15)
            data = json.loads((bundle / "assets/episodes.json").read_text())
            item = data["items"][0]
            tables = [x for x in item["article_blocks"] if x["type"] == "table"]
            self.assertEqual(len(tables), 1)
            self.assertEqual(tables[0]["rows"][1], ["Loss", "**−$20.8M**", "Consolidated reconciliation"])
            staged_md = bundle / item["formats"]["article"]["path"]
            self.assertEqual(staged_md.read_text(encoding="utf-8"), markdown)
            self.assertEqual(sha256(staged_md), sha256(folder / "article.md"))
            self.assertNotIn("audio", item["formats"])

    def test_markdown_lookalike_and_code_fences_are_not_recast_as_tables(self):
        markdown = (
            "A sentence with | pipes is not a table.\n\n"
            "```markdown\n"
            "| Item | Amount |\n| --- | --- |\n| Example | $42 |\n"
            "```\n\n"
            "| Not really | table |\n"
            "| Arbitrary text | not delimiter |\n"
        )
        blocks = blocks_from_markdown(markdown)
        self.assertFalse(any(x["type"] == "table" for x in blocks))
        self.assertTrue(any(x["type"] == "code" for x in blocks))

    def test_dates_and_chronological_limit(self):
        self.assertEqual(episode_date("frontier-20261102"), "2026-11-02")
        self.assertEqual(episode_date("voice-input_20261018"), "2026-10-18")
        self.assertEqual(episode_date("frontier-20261340"), "")
        self.assertEqual(episode_date("voice-input"), "")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            deliveries = root / "deliveries"
            for name in ("voice-input-20261018", "frontier-20261102", "frontier-20261031"):
                folder = deliveries / name
                folder.mkdir(parents=True)
                (folder / "podcast.mp3").write_bytes(name.encode())
            output = root / "bundle"
            build(deliveries, output, Path(__file__).with_name("index.html"), 2)
            episodes = json.loads((output / "assets/episodes.json").read_text())["episodes"]
            self.assertEqual([ep["date"] for ep in episodes], ["2026-11-02", "2026-10-31"])
            self.assertEqual([ep["id"] for ep in episodes], ["frontier-20261102", "frontier-20261031"])

    def test_content_json_published_at_is_honored(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            deliveries = root / "deliveries"
            # Folder name carries no date suffix: the explicit metadata date must win.
            folder = deliveries / "cleanslate-briefing"
            folder.mkdir(parents=True)
            (folder / "research.md").write_text("# Briefing\n\nBody.\n")
            (folder / "content.json").write_text(json.dumps(
                {"title": "Briefing", "published_at": "2026-11-04"}))
            # Folder suffix disagrees with the metadata: metadata still wins.
            folder2 = deliveries / "other-20260101"
            folder2.mkdir(parents=True)
            (folder2 / "research.md").write_text("# Other\n\nBody.\n")
            (folder2 / "content.json").write_text(json.dumps(
                {"title": "Other", "published_at": "2026-11-03"}))
            output = root / "bundle"
            build(deliveries, output, Path(__file__).with_name("index.html"), 15)
            items = json.loads((output / "assets/episodes.json").read_text())["items"]
            by_id = {it["content_id"]: it["published_at"] for it in items}
            self.assertEqual(by_id["cleanslate-briefing"], "2026-11-04")
            self.assertEqual(by_id["other-20260101"], "2026-11-03")

    def test_muse_loader_fallback_structure(self):
        html = Path(__file__).with_name("index.html").read_text()
        self.assertIn("const manifest=params.get('manifest')||'assets/episodes.json'", html)
        self.assertIn("try{const url=safeUrl(manifest);if(!url)throw Error('Invalid manifest URL');const response=", html)
        self.assertIn("catch(e){data=embedded;note='embedded snapshot (manifest unavailable)';if(!data.length)", html)
        self.assertIn("return v}", html)

    def test_unified_item_with_article_and_editorial_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "topic-20261103"
            folder.mkdir(parents=True)
            (folder / "podcast.mp3").write_bytes(b"unchanged-audio")
            (folder / "article.html").write_text("<h1>Readable article</h1>")
            (folder / "content.json").write_text(json.dumps({"title": "A Specific Topic", "summary": "A short explanation."}))
            output = root / "bundle"
            build(root / "deliveries", output, Path(__file__).with_name("index.html"), 15)
            payload = json.loads((output / "assets/episodes.json").read_text())
            item = payload["items"][0]
            self.assertEqual(item["content_id"], "topic-20261103")
            self.assertEqual(item["title"], "A Specific Topic")
            self.assertEqual(item["summary"], "A short explanation.")
            self.assertIn("article", item["formats"])
            self.assertEqual((output / item["formats"]["article"]["path"]).read_text(), "<h1>Readable article</h1>")
            self.assertEqual((output / item["audio_url"]).read_bytes(), b"unchanged-audio")
            self.assertEqual(payload["episodes"][0]["id"], item["content_id"])

    def test_article_first_generation_from_real_research_shape(self):
        research = (
            "# What is new from Focu's registered research sources between two dates?\n\n"
            "One source announced a new result in distributed inference.\n\n"
            "## Findings\n\n"
            "- Pando releases a memory architecture for long-running agents "
            "([s1](https://example.org/story)).\n"
            "  > Authors demonstrated persistent agent execution.\n\n"
            "## Sources\n\n- [s1](https://example.org/story)\n"
        )
        info = editorial(research)
        self.assertTrue(info["title"].startswith("Pando releases a memory architecture"))
        self.assertNotIn("What is new", info["title"])
        self.assertIn("distributed inference", info["summary"])
        self.assertTrue(any(block["type"] == "heading" for block in info["article_blocks"]))
        self.assertTrue(any(block["type"] == "bullet" for block in info["article_blocks"]))
        self.assertIn("https://example.org/story", str(info["article_blocks"]))
        self.assertGreaterEqual(info["reading_minutes"], 1)

    def test_gist_is_first_complete_sentence_when_it_fits(self):
        info = editorial("# Briefing\n\nBody.\n", {"summary": (
            "Jack Clark's Import AI covers the week's research. "
            "This issue leads with a long essay on mesa-optimization and then "
            "surveys robotaxis, chip export controls, and three new benchmarks.")})
        self.assertEqual(info["gist"],
                         "Jack Clark's Import AI covers the week's research.")
        self.assertLessEqual(len(info["gist"]), 90)
        # The scan layer is untouched by the glance extraction.
        self.assertIn("mesa-optimization", info["summary"])

    def test_gist_trims_at_word_boundary_and_stays_extractive(self):
        source = ("The study reports that experienced developers using AI coding "
                  "tools were measurably slower overall while believing that they "
                  "had been faster by roughly the same amount in the trial.")
        info = editorial("# Briefing\n\nBody.\n", {"summary": source})
        gist = info["gist"]
        self.assertTrue(gist.endswith("…"))
        self.assertLessEqual(len(gist), 91)  # 90 chars of source + ellipsis
        self.assertIn(gist.rstrip("…"), clean(source))
        self.assertNotIn("  ", gist)

    def test_gist_uses_whole_text_when_it_already_fits(self):
        info = editorial(
            "# Research\n\nOne source announced a new result in distributed inference.\n")
        self.assertEqual(info["gist"],
                         "One source announced a new result in distributed inference")

    def test_gist_cjk_sentence_boundary(self):
        lead = "蚂蚁灵光发布了新一代多模态模型，重点提升了长视频理解与生成能力。"
        rest = ("节目还邀请了团队负责人讨论它与主流闭源模型的差距、中文场景下的实际表现、"
                "定价策略，以及下一阶段的产品路线图和组织方式，整集信息量很大。")
        self.assertGreater(len(clean(lead + rest)), 90)
        info = editorial("# 硅谷101\n\n" + lead + rest + "\n")
        self.assertEqual(info["gist"], lead)

    def test_gist_ignores_abbreviation_fragments(self):
        source = ("U.S. officials outlined the new export framework for advanced "
                  "chips and the licensing process that now applies to three "
                  "categories of accelerators sold overseas this year.")
        gist = editorial("# Briefing\n\nBody.\n", {"summary": source})["gist"]
        self.assertNotEqual(gist, "U.")
        self.assertGreater(len(gist), 40)
        self.assertIn(gist.rstrip("…"), clean(source))

    def test_gist_omitted_when_nothing_honest_can_be_extracted(self):
        self.assertEqual(editorial("# Title only\n")["gist"], "")
        self.assertEqual(editorial("", {})["gist"], "")
        self.assertEqual(editorial("", {"summary": "Too short"})["gist"], "")

    def test_build_emits_gist_and_omits_it_when_unextractable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "story-20261110"
            folder.mkdir(parents=True)
            (folder / "article.md").write_text(
                "# A grounded result\n\n"
                "Pando releases a memory architecture for long-running agents. "
                "The design keeps working state across sessions, tools, and days, "
                "and the authors report large gains on multi-day tasks in their "
                "internal evaluation harness.\n")
            audio_only = root / "deliveries" / "audio-20261110"
            audio_only.mkdir()
            (audio_only / "podcast.mp3").write_bytes(b"audio-only")
            output = root / "bundle"
            build(root / "deliveries", output, Path(__file__).with_name("index.html"), 15)
            items = {x["content_id"]: x for x in
                     json.loads((output / "assets/episodes.json").read_text())["items"]}
            self.assertEqual(items["story-20261110"]["gist"],
                             "Pando releases a memory architecture for long-running agents.")
            self.assertLessEqual(len(items["story-20261110"]["gist"]), 90)
            self.assertNotIn("gist", items["audio-20261110"])

    def test_offline_covers_are_deterministic_and_distinct(self):
        first = typographic_svg("Pando memory architecture", "AI research")
        self.assertEqual(first, typographic_svg("Pando memory architecture", "AI research"))
        self.assertNotEqual(first, typographic_svg("Geothermal rock physics", "Energy"))
        self.assertTrue(first.startswith(b"<svg"))
        self.assertIn(b"Pando memory", first)
        self.assertIn(b"architecture", first)

    def test_build_stages_markdown_and_cover_without_network(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "frontier-20261103"
            folder.mkdir(parents=True)
            (folder / "podcast.mp3").write_bytes(b"original-bytes")
            (folder / "research.md").write_text(
                "# What is new from Focu's registered research sources?\n\n"
                "Research on energy use in AI infrastructure.\n\n"
                "## Findings\n- A new cooling design reduces data-center water use "
                "([src](https://example.org)).\n"
            )
            (folder / "content.json").write_text(json.dumps({"source_image_url": "https://example.org/cover.jpg"}))
            output = root / "bundle"
            build(root / "deliveries", output, Path(__file__).with_name("index.html"), 15)
            item = json.loads((output / "assets/episodes.json").read_text())["items"][0]
            self.assertIn("cooling design", item["title"])
            self.assertEqual(item["cover"]["origin"], "offline_art")
            self.assertTrue((output / item["cover"]["path"]).is_file())
            self.assertGreater(len(item["article_blocks"]), 1)
            self.assertEqual((output / item["audio_url"]).read_bytes(), b"original-bytes")
            embedded = (output / "index.html").read_text()
            self.assertIn("cooling design", embedded)
            self.assertIn("article_blocks", embedded)
            self.assertEqual(item["formats"]["article"]["mime_type"], "text/markdown")

    def test_original_cover_takes_priority(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "topic-20261103"
            folder.mkdir(parents=True)
            (folder / "podcast.mp3").write_bytes(b"audio")
            (folder / "cover.jpg").write_bytes(b"source-owned-cover-fixture")
            (folder / "research.md").write_text("# A specific research finding\n\nA summary.")
            output = root / "bundle"
            build(root / "deliveries", output, Path(__file__).with_name("index.html"), 15)
            item = json.loads((output / "assets/episodes.json").read_text())["items"][0]
            self.assertEqual(item["cover"]["origin"], "source")
            self.assertEqual((output / item["cover"]["path"]).read_bytes(), b"source-owned-cover-fixture")

    def test_manual_archive_reader_contract(self):
        html = Path(__file__).with_name("index.html").read_text()
        self.assertIn('id="readerarchive"', html)
        self.assertIn("manualArchive(id)", html)
        self.assertIn("markDone(id,'manual')", html)
        self.assertIn("'focu:content-consumption:v1'", html)
        self.assertIn("view==='archive'?'Restore':'Archive'", html)
        self.assertIn("markUnread(item.id)", html)

    def test_origin_policy_article_first_with_podcast_only_after_opt_in(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "idea-20261105"
            folder.mkdir(parents=True)
            intent = "int_" + "a"*32
            (folder / "article.md").write_text("# Research article\n\n## Mechanism\nA measured improvement.")
            metadata = {"content_id": intent, "origin": "user_initiated",
                        "title": "Research article", "podcast_mode": "none"}
            (folder / "content.json").write_text(json.dumps(metadata))
            output = root / "article-only"
            build(root / "deliveries", output, Path(__file__).with_name("index.html"), 15)
            item = json.loads((output / "assets/episodes.json").read_text())["items"][0]
            self.assertEqual(item["podcast_mode"], "none")
            self.assertNotIn("audio", item["formats"])
            self.assertEqual(item["content_id"], intent)
            (folder / "podcast.mp3").write_bytes(b"synthetic-mp3-fixture")
            with self.assertRaisesRegex(ValueError, "stray MP3"):
                build(root / "deliveries", root / "rejected", Path(__file__).with_name("index.html"), 15)
            metadata["podcast_mode"] = "single"
            (folder / "content.json").write_text(json.dumps(metadata))
            build(root / "deliveries", root / "podcast", Path(__file__).with_name("index.html"), 15)
            updated = json.loads((root / "podcast/assets/episodes.json").read_text())["items"][0]
            self.assertEqual(updated["content_id"], intent)
            self.assertEqual(updated["podcast_mode"], "single")
            self.assertIn("audio", updated["formats"])
            self.assertEqual(len(json.loads((root / "podcast/assets/episodes.json").read_text())["episodes"]), 1)

    def test_original_url_passes_through_from_content_json_source_url(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def delivery(name, content_id, metadata_extra):
                folder = root / "deliveries" / name
                folder.mkdir(parents=True)
                (folder / "article.md").write_text("# Piece\n\nBody.", encoding="utf-8")
                metadata = {"content_id": content_id, "origin": "registered_source",
                            "podcast_mode": "daily_compilation"}
                metadata.update(metadata_extra)
                (folder / "content.json").write_text(json.dumps(metadata), encoding="utf-8")
            delivery("with-url-20261110", "piece-with-url",
                     {"source_url": "https://example.org/the-original-post"})
            delivery("no-url-20261110", "piece-without-url", {})
            delivery("bad-url-20261110", "piece-with-bad-url",
                     {"source_url": "javascript:alert(1)"})
            research = root / "deliveries" / "research-url-20261110"
            research.mkdir(parents=True)
            (research / "article.md").write_text("# Investigation\n\nFindings.", encoding="utf-8")
            (research / "content.json").write_text(json.dumps({
                "content_id": "piece-research-url", "origin": "user_initiated",
                "podcast_mode": "none",
                "source_url": "https://example.org/source-thread"
            }), encoding="utf-8")
            # A research item whose delivery data carries an origin URL
            # gets the field too: the pass-through follows the data, not
            # the item class.
            build(root / "deliveries", root / "bundle", Path(__file__).with_name("index.html"), 15)
            data = json.loads((root / "bundle/assets/episodes.json").read_text())
            by_id = {item["content_id"]: item for item in data["items"]}
            self.assertEqual(by_id["piece-with-url"]["original_url"],
                             "https://example.org/the-original-post")
            self.assertEqual(by_id["piece-research-url"]["original_url"],
                             "https://example.org/source-thread")
            # Absent or non-HTTP(S) source_url emits nothing at all: the
            # item shape is exactly what pre-change bundles carried.
            self.assertNotIn("original_url", by_id["piece-without-url"])
            self.assertNotIn("original_url", by_id["piece-with-bad-url"])

    AGENDA_ARTICLE = (
        "# Daily Briefing — November 16, 2026\n\n"
        "Here's what came in.\n\n"
        "Two items today:\n\n"
        "- Pando releases a memory architecture for long-running agents — Pando Blog\n"
        "- A new cooling design reduces data-center water use — Energy Weekly\n\n"
        "## Pando releases a memory architecture for long-running agents\n\n"
        "Pando releases a memory architecture for long-running agents, with "
        "working state kept across sessions.\n\n"
        "## A new cooling design reduces data-center water use\n\n"
        "A new cooling design reduces data-center water use across existing "
        "facilities.\n"
    )

    def test_compilation_gist_comes_from_the_agenda_not_the_formula_lead(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, content_id, article in (
                ("source-a-20261116", "agenda-source-a",
                 "# Pando release\n\nPando releases a memory architecture for "
                 "long-running agents. The design keeps working state across "
                 "sessions, tools, and days.\n"),
                ("source-b-20261116", "agenda-source-b",
                 "# Cooling design\n\nA new cooling design reduces data-center "
                 "water use. The retrofit applies to existing facilities.\n"),
            ):
                folder = root / "deliveries" / name
                folder.mkdir(parents=True)
                (folder / "article.md").write_text(article, encoding="utf-8")
                (folder / "content.json").write_text(json.dumps({
                    "content_id": content_id, "origin": "registered_source",
                    "podcast_mode": "daily_compilation"
                }), encoding="utf-8")
            daily = root / "deliveries" / "daily-20261116"
            daily.mkdir()
            (daily / "article.md").write_text(self.AGENDA_ARTICLE, encoding="utf-8")
            (daily / "content.json").write_text(json.dumps({
                "content_id": "daily-2026-11-16", "origin": "daily_compilation",
                "podcast_mode": "daily_compilation", "published_at": "2026-11-16",
                "covered_content_ids": ["agenda-source-a", "agenda-source-b"]
            }), encoding="utf-8")
            build(root / "deliveries", root / "bundle",
                  Path(__file__).with_name("index.html"), 15)
            data = json.loads((root / "bundle/assets/episodes.json").read_text())
            by_id = {item["content_id"]: item for item in data["items"]}
            gist = by_id["daily-2026-11-16"]["gist"]
            # The glance line reflects the contents — the agenda's count
            # and a covered item's title — and is never the bare formula.
            self.assertNotEqual(gist, "Here's what came in")
            self.assertIn("Two items today", gist)
            self.assertIn("Pando releases a memory architecture", gist)
            self.assertLessEqual(len(gist), 91)
            # The scan layer is untouched: the summary still leads with
            # the article's own opening, exactly as before.
            self.assertEqual(by_id["daily-2026-11-16"]["summary"],
                             "Here's what came in")
            # Non-compilation gists are byte-identical to the old pipeline.
            self.assertEqual(by_id["agenda-source-a"]["gist"],
                             "Pando releases a memory architecture for long-running agents.")
            self.assertEqual(by_id["agenda-source-b"]["gist"],
                             "A new cooling design reduces data-center water use.")

    def test_agenda_gist_is_compilation_only(self):
        info = editorial(self.AGENDA_ARTICLE, {"origin": "daily_compilation"})
        self.assertIn("Two items today", info["gist"])
        self.assertIn("Pando releases a memory architecture", info["gist"])
        # The same article under any other origin keeps today's gist:
        # the formula lead, extracted exactly as before this fix.
        self.assertEqual(editorial(self.AGENDA_ARTICLE,
                                   {"origin": "registered_source"})["gist"],
                         "Here's what came in")
        self.assertEqual(editorial(self.AGENDA_ARTICLE)["gist"],
                         "Here's what came in")
        # A compilation whose lead is real prose keeps the prose gist.
        prose = ("# Daily Briefing\n\nA prose lead that honestly summarises "
                 "the day for the reader in plain words.\n\n## Item\n\nBody.\n")
        self.assertEqual(editorial(prose, {"origin": "daily_compilation"})["gist"],
                         "A prose lead that honestly summarises the day for the "
                         "reader in plain words")
        # An explicit synopsis supplied by the publisher still wins.
        info = editorial(self.AGENDA_ARTICLE,
                         {"origin": "daily_compilation",
                          "summary": "An explicit synopsis supplied by the "
                                     "publisher for this briefing."})
        self.assertEqual(info["gist"],
                         "An explicit synopsis supplied by the publisher for "
                         "this briefing")

    # Wave 28: a bullet-shaped digest unit (the LinkedIn feed shape) has
    # no synopsis, claim, or lead paragraph, so it used to publish with
    # gist and summary both empty — title + price and no text at all.
    LINKEDIN_DIGEST_ARTICLE = (
        "# LinkedIn Feed — Friday, November 14, 2026\n\n"
        "1. Jane Doe — shipped a mapping tool for geothermal surveys "
        "(https://www.linkedin.com/feed/update/urn:li:ugcPost:7526714905299763201/)\n"
        "2. John Roe — a new paper on reservoir simulation boundary "
        "conditions is out today "
        "(https://www.linkedin.com/feed/update/urn:li:ugcPost:7526714905299763202/)\n"
        "3. Ana Lee — hiring two ML engineers for exploration work "
        "(https://www.linkedin.com/feed/update/urn:li:ugcPost:7526714905299763203/)\n"
        "4. Tom Poe — notes from the GEMS workshop on fault mapping "
        "(https://www.linkedin.com/feed/update/urn:li:ugcPost:7526714905299763204/)\n"
    )

    def test_bullet_digest_gist_and_summary_come_from_the_first_bullet(self):
        info = editorial(self.LINKEDIN_DIGEST_ARTICLE,
                         {"title": "LinkedIn Feed — Friday, November 14, 2026"})
        expected = "Jane Doe — shipped a mapping tool for geothermal surveys"
        self.assertEqual(info["gist"], expected)
        self.assertEqual(info["summary"], expected)
        # Extractive only: both fields are the item's own words, and the
        # entry's permalink — a locator, not content — never leaks in.
        self.assertIn(info["gist"], self.LINKEDIN_DIGEST_ARTICLE)
        self.assertIn(info["summary"], self.LINKEDIN_DIGEST_ARTICLE)
        self.assertLessEqual(len(info["gist"]), 90)
        self.assertNotIn("http", info["gist"])
        self.assertNotIn("linkedin.com", info["gist"])
        self.assertNotIn("7526714905299763201", info["gist"])

    def test_build_bullet_digest_publishes_gist_and_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "linkedin-20261114"
            folder.mkdir(parents=True)
            (folder / "article.md").write_text(self.LINKEDIN_DIGEST_ARTICLE,
                                               encoding="utf-8")
            (folder / "content.json").write_text(json.dumps({
                "content_id": "linkedin-2026-11-14",
                "origin": "registered_source",
                "podcast_mode": "daily_compilation",
                "title": "LinkedIn Feed — Friday, November 14, 2026",
                "published_at": "2026-11-14",
            }), encoding="utf-8")
            build(root / "deliveries", root / "bundle",
                  Path(__file__).with_name("index.html"), 15)
            data = json.loads((root / "bundle/assets/episodes.json").read_text())
            by_id = {item["content_id"]: item for item in data["items"]}
            item = by_id["linkedin-2026-11-14"]
            self.assertTrue(item["gist"])
            self.assertTrue(item["summary"])
            self.assertIn(item["gist"], self.LINKEDIN_DIGEST_ARTICLE)
            self.assertIn(item["summary"], self.LINKEDIN_DIGEST_ARTICLE)
            self.assertLessEqual(len(item["gist"]), 90)
            self.assertNotIn("http", item["gist"])

    def test_bullet_fallback_never_overrides_a_prose_lead(self):
        # Shape gate is both-fields-empty: an item the prose paths serve
        # keeps its exact output even when its body also carries bullets,
        # and a short explicit synopsis is likewise left alone.
        prose = ("# Report\n\nA prose lead that honestly summarises the "
                 "work in plain words for the reader.\n\n"
                 "- First point\n- Second point\n- Third point\n")
        info = editorial(prose)
        self.assertEqual(info["gist"],
                         "A prose lead that honestly summarises the work "
                         "in plain words for the reader")
        self.assertEqual(info["summary"], info["gist"])
        info = editorial("# Report\n\nBody text here.\n\n"
                         "- Alpha point\n- Beta point\n- Gamma point\n",
                         {"summary": "Too short"})
        self.assertEqual(info["gist"], "")
        self.assertEqual(info["summary"], "Too short")

    def test_bullet_digest_with_unusable_first_bullet_stays_empty(self):
        # A bare-URL first bullet yields nothing, and the fallback never
        # manufactures a line from a later bullet instead.
        bare = ("# LinkedIn Feed — Saturday, November 15, 2026\n\n"
                "1. https://www.linkedin.com/feed/update/urn:li:ugcPost:7526714905299763201/\n"
                "2. John Roe — a new paper on reservoir simulation boundary "
                "conditions is out today "
                "(https://www.linkedin.com/feed/update/urn:li:ugcPost:7526714905299763202/)\n"
                "3. Ana Lee — hiring two ML engineers for exploration work "
                "(https://www.linkedin.com/feed/update/urn:li:ugcPost:7526714905299763203/)\n")
        info = editorial(bare, {"title": "LinkedIn Feed — Saturday, "
                                        "November 15, 2026"})
        self.assertEqual(info["gist"], "")
        self.assertEqual(info["summary"], "")
        # A fragment first bullet is likewise unusable for both fields.
        fragment = ("# Digest\n\n"
                    "1. Hi (https://example.com/x)\n"
                    "2. John Roe — a new paper on reservoir simulation "
                    "boundary conditions is out today (https://example.com/y)\n"
                    "3. Ana Lee — hiring two ML engineers for exploration "
                    "work (https://example.com/z)\n")
        info = editorial(fragment)
        self.assertEqual(info["gist"], "")
        self.assertEqual(info["summary"], "")
        # Two bullets are not the digest shape: no fallback either.
        info = editorial("# Digest\n\n- Alpha point worth reading\n"
                         "- Beta point worth reading\n")
        self.assertEqual(info["gist"], "")
        self.assertEqual(info["summary"], "")

    def test_build_bullet_digest_omits_gist_that_repeats_the_title(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "notes-20261114"
            folder.mkdir(parents=True)
            (folder / "article.md").write_text(
                "# Notes on reservoir simulation\n\n"
                "- Notes on reservoir simulation\n"
                "- Boundary conditions for the Cape field model\n"
                "- Grid refinement results from the October run\n",
                encoding="utf-8")
            (folder / "content.json").write_text(json.dumps({
                "content_id": "notes-2026-11-14",
                "origin": "registered_source",
                "podcast_mode": "daily_compilation",
            }), encoding="utf-8")
            build(root / "deliveries", root / "bundle",
                  Path(__file__).with_name("index.html"), 15)
            data = json.loads((root / "bundle/assets/episodes.json").read_text())
            by_id = {item["content_id"]: item for item in data["items"]}
            self.assertNotIn("gist", by_id["notes-2026-11-14"])

    def test_source_name_passes_through_from_content_json(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def delivery(name, content_id, metadata_extra):
                folder = root / "deliveries" / name
                folder.mkdir(parents=True)
                (folder / "article.md").write_text("# Piece\n\nBody.", encoding="utf-8")
                metadata = {"content_id": content_id}
                metadata.update(metadata_extra)
                (folder / "content.json").write_text(json.dumps(metadata),
                                                     encoding="utf-8")
            delivery("named-20261116", "piece-named",
                     {"origin": "registered_source",
                      "podcast_mode": "daily_compilation",
                      "source_name": "OpenAI Official"})
            delivery("unnamed-20261116", "piece-unnamed",
                     {"origin": "registered_source",
                      "podcast_mode": "daily_compilation"})
            delivery("url-named-20261116", "piece-url-named",
                     {"origin": "registered_source",
                      "podcast_mode": "daily_compilation",
                      "source_name": "https://spam.example/post"})
            delivery("research-plain-20261116", "piece-research-plain",
                     {"origin": "user_initiated", "podcast_mode": "none"})
            delivery("research-named-20261116", "piece-research-named",
                     {"origin": "user_initiated", "podcast_mode": "none",
                      "source_name": "Field notes"})
            build(root / "deliveries", root / "bundle",
                  Path(__file__).with_name("index.html"), 15)
            data = json.loads((root / "bundle/assets/episodes.json").read_text())
            by_id = {item["content_id"]: item for item in data["items"]}
            self.assertEqual(by_id["piece-named"]["source"], "OpenAI Official")
            # Absent ⇒ today's labels, byte-identical: registered items
            # are "Focu", commissioned research is "Your research".
            self.assertEqual(by_id["piece-unnamed"]["source"], "Focu")
            self.assertEqual(by_id["piece-research-plain"]["source"],
                             "Your research")
            # A URL is not a plain-text name and is never passed through.
            self.assertEqual(by_id["piece-url-named"]["source"], "Focu")
            # The pass-through follows the recorded data, not the origin.
            self.assertEqual(by_id["piece-research-named"]["source"],
                             "Field notes")

    def test_daily_article_rejects_missing_visual_even_without_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "deliveries" / "official-source"
            source.mkdir(parents=True)
            (source / "article.md").write_text("# Source\\n\\nOriginal source may cite Figure 1.")
            (source / "content.json").write_text(json.dumps({
                "content_id": "source-figure", "origin": "registered_source",
                "podcast_mode": "daily_compilation"
            }))
            daily = root / "deliveries" / "daily-20261109"
            daily.mkdir()
            article = daily / "article.md"
            article.write_text("# Briefing\\n\\nSee Figure 2 for the experiment.")
            (daily / "content.json").write_text(json.dumps({
                "content_id": "daily-2026-11-09", "origin": "daily_compilation",
                "podcast_mode": "daily_compilation", "published_at": "2026-11-09",
                "covered_content_ids": ["source-figure"]
            }))
            with self.assertRaisesRegex(ValueError, "dangling visual references"):
                build(root / "deliveries", root / "invalid", Path(__file__).with_name("index.html"), 15)
            self.assertFalse((root / "invalid").exists())
            # Referencing the visual's actual data in words is allowed, while
            # source articles keep their original citations untouched.
            article.write_text("# Briefing\\n\\nThe experiment reports 38% accuracy.")
            build(root / "deliveries", root / "valid", Path(__file__).with_name("index.html"), 15)
            self.assertIn("Figure 1", (source / "article.md").read_text())

    def test_daily_briefing_article_only_when_audio_fails_qc(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / "deliveries" / "registered-20261107"
            src.mkdir(parents=True)
            (src / "article.md").write_text("# Original source\n\nSource result.", encoding="utf-8")
            (src / "content.json").write_text(json.dumps({
                "content_id": "source-1", "origin": "registered_source",
                "podcast_mode": "daily_compilation"
            }))
            research = root / "deliveries" / "research-20261107"
            research.mkdir()
            (research / "article.md").write_text("# New investigation\n\nIndependent evidence.", encoding="utf-8")
            (research / "content.json").write_text(json.dumps({
                "content_id": "int_" + "b"*32, "origin": "user_initiated",
                "podcast_mode": "none"
            }))
            brief = root / "deliveries" / "daily-20261107"
            brief.mkdir()
            (brief / "article.md").write_text("# Daily Briefing\n\nThe source and new research.", encoding="utf-8")
            (brief / "content.json").write_text(json.dumps({
                "content_id": "daily-2026-11-07",
                "origin": "daily_compilation", "podcast_mode": "daily_compilation",
                "published_at": "2026-11-07",
                "covered_content_ids": ["source-1", "int_" + "b"*32]
            }))
            build(root / "deliveries", root / "bundle", Path(__file__).with_name("index.html"), 15)
            data = json.loads((root / "bundle/assets/episodes.json").read_text())
            by_id = {item["content_id"]: item for item in data["items"]}
            self.assertEqual(len(by_id), 3)
            self.assertEqual(by_id["daily-2026-11-07"]["covered_content_ids"],
                             ["source-1", "int_"+"b"*32])
            self.assertIn("article", by_id["daily-2026-11-07"]["formats"])
            self.assertNotIn("audio", by_id["daily-2026-11-07"]["formats"])
            self.assertNotIn("audio", by_id["int_"+"b"*32]["formats"])
            self.assertEqual(len(data["episodes"]), 0)

    def test_daily_source_articles_and_one_compilation_link(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index in range(3):
                folder = root / "deliveries" / ("source-" + str(index) + "-20261105")
                folder.mkdir(parents=True)
                (folder / "article.md").write_text("# Source " + str(index) + "\n\nFactual source report.")
                (folder / "content.json").write_text(json.dumps({
                    "content_id": "source-"+str(index), "origin": "registered_source",
                    "podcast_mode": "daily_compilation"
                }))
            compilation = root / "deliveries" / "daily-briefing-20261105"
            compilation.mkdir(parents=True)
            (compilation / "podcast.mp3").write_bytes(b"synthetic-single-daily-briefing")
            (compilation / "content.json").write_text(json.dumps({
                "content_id": "daily-2026-11-05", "origin": "daily_compilation",
                "podcast_mode": "daily_compilation", "published_at": "2026-11-05",
                "covered_content_ids": ["source-0", "source-1", "source-2"]
            }))
            output = root / "bundle"
            build(root / "deliveries", output, Path(__file__).with_name("index.html"), 15)
            data = json.loads((output / "assets/episodes.json").read_text())
            self.assertEqual(len(data["items"]), 4)
            self.assertEqual(len(data["episodes"]), 1)
            by_id = {item["content_id"]: item for item in data["items"]}
            self.assertEqual(by_id["daily-2026-11-05"]["covered_content_ids"],
                             ["source-0", "source-1", "source-2"])
            for n in range(3):
                self.assertNotIn("audio", by_id["source-"+str(n)]["formats"])
                self.assertEqual(by_id["source-"+str(n)]["podcast_mode"], "daily_compilation")

    def test_compilation_with_mp3_carries_audio_url_for_listen_button(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / "deliveries" / "source-20261108"
            src.mkdir(parents=True)
            (src / "article.md").write_text("# Source item\n\nFactual source report.")
            (src / "content.json").write_text(json.dumps({
                "content_id": "source-1", "origin": "registered_source",
                "podcast_mode": "daily_compilation"
            }))
            brief = root / "deliveries" / "daily-20261108"
            brief.mkdir()
            (brief / "article.md").write_text("# Daily Briefing\n\nCompiled briefing.")
            (brief / "podcast.mp3").write_bytes(b"compilation-audio-fixture")
            (brief / "content.json").write_text(json.dumps({
                "content_id": "daily-2026-11-08", "origin": "daily_compilation",
                "podcast_mode": "daily_compilation", "published_at": "2026-11-08",
                "covered_content_ids": ["source-1"]
            }))
            output = root / "bundle"
            build(root / "deliveries", output, Path(__file__).with_name("index.html"), 15)
            data = json.loads((output / "assets/episodes.json").read_text())
            by_id = {item["content_id"]: item for item in data["items"]}
            compilation = by_id["daily-2026-11-08"]
            self.assertIn("audio_url", compilation)
            self.assertEqual(compilation["formats"]["audio"]["path"],
                             compilation["audio_url"])
            self.assertEqual(compilation["formats"]["audio"]["mime_type"], "audio/mpeg")
            self.assertEqual((output / compilation["audio_url"]).read_bytes(),
                             b"compilation-audio-fixture")
            self.assertEqual([x["content_id"] for x in data["episodes"]],
                             ["daily-2026-11-08"])
            self.assertNotIn("audio", by_id["source-1"]["formats"])

    def test_compilation_can_cover_user_research_without_authorizing_standalone_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            user = root / "deliveries" / "idea-20261105"
            user.mkdir(parents=True)
            (user / "article.md").write_text("# User research\n\nA grounded article.")
            (user / "content.json").write_text(json.dumps({
                "content_id": "int_"+"a"*32, "origin": "user_initiated",
                "podcast_mode": "none"
            }))
            daily = root / "deliveries" / "daily-20261105"
            daily.mkdir()
            (daily / "podcast.mp3").write_bytes(b"daily-fixture")
            (daily / "content.json").write_text(json.dumps({
                "content_id": "daily-1", "origin": "daily_compilation",
                "covered_content_ids": ["int_"+"a"*32]
            }))
            build(root / "deliveries", root / "accepted", Path(__file__).with_name("index.html"), 15)
            bundled = json.loads((root / "accepted/assets/episodes.json").read_text())
            by_id = {item["content_id"]: item for item in bundled["items"]}
            self.assertEqual(by_id["daily-1"]["covered_content_ids"], ["int_"+"a"*32])
            self.assertEqual(by_id["int_"+"a"*32]["podcast_mode"], "none")
            self.assertNotIn("audio", by_id["int_"+"a"*32]["formats"])
            (daily / "content.json").write_text(json.dumps({
                "content_id": "daily-1", "origin": "daily_compilation",
                "covered_content_ids": ["missing-source"]
            }))
            with self.assertRaisesRegex(ValueError, "references missing"):
                build(root / "deliveries", root / "rejected-again", Path(__file__).with_name("index.html"), 15)

    def test_reader_automatic_completion_contract(self):
        html = Path(__file__).with_name("index.html").read_text()
        self.assertIn("focu:content-consumption:v1", html)
        self.assertIn("markDone(playingId,'audio')", html)
        self.assertIn("markDone(currentId,'article')", html)
        self.assertIn("bottomSeen&&readMs>=minMs", html)
        self.assertIn("reader.hidden=false", html)
        self.assertNotIn("Done reading", html)
        self.assertNotIn("Mark done", html)

    def test_article_only_and_audio_only_share_optional_format_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            deliveries = root / "deliveries"
            article = deliveries / "article-20261103"
            article.mkdir(parents=True)
            (article / "article.md").write_text("# A standalone research story\n\nAn evidence-backed article.")
            audio = deliveries / "podcast-20261102"
            audio.mkdir(parents=True)
            (audio / "podcast.mp3").write_bytes(b"audio-only")
            output = root / "bundle"
            self.assertEqual(build(deliveries, output, Path(__file__).with_name("index.html"), 15), 2)
            payload = json.loads((output / "assets/episodes.json").read_text())
            self.assertEqual(len(payload["items"]), 2)
            self.assertEqual(len(payload["episodes"]), 1)
            items = {x["content_id"]: x for x in payload["items"]}
            self.assertIn("article", items["article-20261103"]["formats"])
            self.assertNotIn("audio", items["article-20261103"]["formats"])
            self.assertGreater(len(items["article-20261103"]["article_blocks"]), 1)
            self.assertIn("audio", items["podcast-20261102"]["formats"])
            self.assertNotIn("article", items["podcast-20261102"]["formats"])
            self.assertEqual((output / items["podcast-20261102"]["audio_url"]).read_bytes(), b"audio-only")
            self.assertEqual(json.loads((output / "build-report.json").read_text())["item_count"], 2)

    def test_opt_in_editorial_writes_cached_article_without_touching_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "research-20261103"
            folder.mkdir(parents=True)
            (folder / "research.md").write_text(
                "# What is new?\n\nInitial evidence summary.\n\n"
                "## Findings\n- A factual observation ([s1](https://example.org/a)).\n"
            )
            article = ("# A precise article headline\n\n"
                       "A careful explanation with enough context to keep this test "
                       "faithful to the editorial output. " * 6 +
                       "\n\n## Sources\n- [s1](https://example.org/a)\n")
            response = {"title": "A precise article headline",
                        "summary": "A research-based explanation of the original observation.",
                        "article_markdown": article}
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}):
                with patch("publish.compose_article_with_openai", return_value=response) as mock:
                    for name in ("bundle-a", "bundle-b"):
                        build(root / "deliveries", root / name,
                              Path(__file__).with_name("index.html"), 15,
                              generate_editorial=True)
                    self.assertEqual(mock.call_count, 1)
            item = json.loads((root / "bundle-b/assets/episodes.json").read_text())["items"][0]
            self.assertEqual(item["title"], response["title"])
            self.assertEqual(item["summary"], response["summary"])
            self.assertTrue(item["article_blocks"])
            self.assertEqual((folder / "research.md").read_text().splitlines()[0], "# What is new?")

    def test_editorial_prompt_calibrates_expert_vs_novice_without_changing_facts(self):
        import io
        research = "# Evidence\n\nPublished results ([ref](https://example.org/a))."
        article = ("# Research Analysis\n\n" + "This evidence requires evaluation of its mechanism. " * 8 +
                   "\n\n## Sources\n- [ref](https://example.org/a)\n")
        response = {"choices": [{"message": {"content": json.dumps({
            "title": "Research Analysis", "summary": "The study reports a result needing verification.",
            "article_markdown": article
        })}}]}
        prompts = []
        for domain in ("machine_learning", "sociology"):
            with patch("urllib.request.urlopen",
                       return_value=io.BytesIO(json.dumps(response).encode())) as mocked:
                compose_article_with_openai(research, api_key="fixture-only",
                                            audience_domain=domain)
                payload = json.loads(mocked.call_args.args[0].data)
                prompts.append(payload["messages"][0]["content"])
        self.assertIn("Assume technical fluency", prompts[0])
        self.assertIn("Build foundational context", prompts[1])
        self.assertNotEqual(prompts[0], prompts[1])

    def test_editorial_provider_rejects_fabricated_citations(self):
        import io
        original = "# Research\n\nEvidence ([s1](https://example.org/a))."
        long_article = "# Valid headline\n\n" + "Technical details remain grounded. " * 12
        long_article += "\n\n## Sources\n- [fake](https://unverified.example/nope)"
        response = {"choices": [{"message": {"content": json.dumps({
            "title": "A valid research headline",
            "summary": "This summary only reflects the provided evidence.",
            "article_markdown": long_article,
        })}}]}
        with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
            with self.assertRaisesRegex(ValueError, "introduced citations"):
                compose_article_with_openai(original, api_key="test-only")

    def test_on_demand_research_queue_and_stable_content_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "idea-012345-20261103"
            folder.mkdir(parents=True)
            intent = "int_" + "a" * 32
            queued = "int_" + "b" * 32
            (folder / "research.md").write_text("# A technical article\n\nA factual summary.")
            (folder / "content.json").write_text(json.dumps({
                "content_id": intent, "title": "A technical article",
                "origin": "user_initiated", "summary": "Evidence-backed notes."
            }))
            requests = root / "requests.json"
            requests.write_text(json.dumps({"schema_version": 1, "requests": [
                {"intent_id": intent, "title": "A technical article",
                 "status": "completed", "created_at": "2026-11-03"},
                {"intent_id": queued, "title": "Could this work?",
                 "status": "queued", "created_at": "2026-11-03"}
            ]}))
            output = root / "bundle"
            build(root / "deliveries", output, Path(__file__).with_name("index.html"),
                  15, requests=requests)
            data = json.loads((output / "assets/episodes.json").read_text())
            self.assertEqual(data["items"][0]["content_id"], intent)
            self.assertEqual(data["items"][0]["source"], "Your research")
            self.assertEqual(len(data["research_requests"]), 1)
            self.assertEqual(data["research_requests"][0]["intent_id"], queued)
            self.assertIn(queued, (output / "index.html").read_text())
            self.assertNotIn('"intent_id": "' + intent + '"', json.dumps(data["research_requests"]))
            self.assertEqual(len(data["episodes"]), 0)

    def test_untrusted_research_status_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "article-20261103"
            folder.mkdir(parents=True)
            (folder / "article.md").write_text("# Topic\n\nSome content.")
            requests = root / "bad.json"
            requests.write_text(json.dumps({"requests": [
                {"intent_id": "bad", "status": "researching", "title": "untrusted"},
                {"intent_id": "int_" + "b"*32, "status": "hacked", "title": "untrusted"}
            ]}))
            output = root / "bundle"
            build(root / "deliveries", output, Path(__file__).with_name("index.html"),
                  15, requests=requests)
            data = json.loads((output / "assets/episodes.json").read_text())
            self.assertEqual(data["research_requests"], [])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires local audio tools")
    def test_strict_media_audit_rejects_truncated_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "article-20261103"
            folder.mkdir(parents=True)
            (folder / "article.md").write_text("# Important research result\\n\\nFull article.")
            audio = folder / "podcast.mp3"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                            "-y", "-f", "lavfi", "-i", "sine=frequency=400:duration=6",
                            "-codec:a", "libmp3lame", "-b:a", "64k", str(audio)],
                           check=True, timeout=30, capture_output=True)
            target = root / "good-bundle"
            build(root / "deliveries", target, Path(__file__).with_name("index.html"),
                  15, verify_audio=True)
            data = json.loads((target / "assets/episodes.json").read_text())
            self.assertGreater(data["items"][0]["formats"]["audio"]["duration_seconds"], 5)
            report = json.loads((target / "build-report.json").read_text())
            self.assertTrue(report["audio_audit"]["article-20261103"]["verified"])
            original = audio.read_bytes()
            audio.write_bytes(original[:len(original)//3])
            with self.assertRaisesRegex(ValueError, "Audio validation failed"):
                build(root / "deliveries", root / "rejected-bundle",
                      Path(__file__).with_name("index.html"), 15, verify_audio=True)
            self.assertFalse((root / "rejected-bundle").exists())

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "requires local audio tools")
    def test_ios_compat_publisher_cbr_is_opt_in_and_preserves_delivery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            delivery = root / "deliveries" / "daily-20261109"
            delivery.mkdir(parents=True)
            (delivery / "article.md").write_text(
                "# Daily Briefing\\n\\nOriginal research numbers retained.")
            (delivery / "content.json").write_text(json.dumps({
                "content_id": "daily-2026-11-09",
                "origin": "daily_compilation",
                "podcast_mode": "daily_compilation",
                "published_at": "2026-11-09",
                "covered_content_ids": ["source-1"]
            }))
            source = root / "deliveries" / "source-20261109"
            source.mkdir()
            (source / "article.md").write_text("# Source\\n\\nEvidence.")
            (source / "content.json").write_text(json.dumps({
                "content_id": "source-1", "origin": "registered_source",
                "podcast_mode": "daily_compilation"
            }))
            original_mp3 = delivery / "podcast.mp3"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-v", "error", "-y",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                "-c:a", "libmp3lame", "-q:a", "2", str(original_mp3)
            ], check=True, capture_output=True, timeout=60)
            original_hash = sha256(original_mp3)
            with self.assertRaisesRegex(ValueError, "requires strict audio audit"):
                build(root / "deliveries", root / "unsafe",
                      Path(__file__).with_name("index.html"), 15,
                      ios_compatible_audio=True, verify_audio=False)
            out = root / "bundle-ios"
            build(root / "deliveries", out,
                  Path(__file__).with_name("index.html"), 15,
                  ios_compatible_audio=True, verify_audio=True)
            self.assertEqual(sha256(original_mp3), original_hash,
                             "publisher must leave original deliveries unchanged")
            report = json.loads((out / "build-report.json").read_text())
            converted = report["audio_transforms"]["daily-20261109"]
            self.assertEqual(converted["profile"], "mp3_cbr_128k_mono_44100")
            self.assertEqual(converted["source_sha256"], original_hash)
            self.assertNotEqual(converted["published_sha256"], original_hash)
            self.assertAlmostEqual(converted["published_decoded_duration_seconds"],
                                   converted["source_decoded_duration_seconds"], delta=1.5)
            manifest = json.loads((out / "assets/episodes.json").read_text())
            episode = next(x for x in manifest["items"]
                           if x["content_id"] == "daily-2026-11-09")
            staged = out / episode["formats"]["audio"]["path"]
            self.assertEqual(sha256(staged), converted["published_sha256"])
            self.assertEqual(sha256(staged),
                             report["sha256"][episode["formats"]["audio"]["path"]])
            self.assertNotIn("audio", next(x for x in manifest["items"]
                                         if x["content_id"] == "source-1")["formats"])

    def test_legacy_html_article_is_safe_and_auto_readable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "deliveries" / "legacy-20261103"
            folder.mkdir(parents=True)
            (folder / "article.html").write_text(
                "<article><h1>Old research</h1><p>Important finding with "
                "<a href='https://example.org/first'>a source</a>.</p>"
                "<script>throw new Error('must not run')</script></article>")
            out = root / "bundle"
            build(root / "deliveries", out, Path(__file__).with_name("index.html"), 15)
            item = json.loads((out / "assets/episodes.json").read_text())["items"][0]
            blocks = item["article_blocks"]
            self.assertTrue(any("Important finding" in b["text"] for b in blocks))
            self.assertTrue(any("https://example.org/first" in b["text"] for b in blocks))
            self.assertNotIn("must not run", json.dumps(blocks))
            self.assertGreater(item["reading_minutes"], 0)

    def test_zero_cost_article_narration_and_consumption_contract(self):
        html = Path(__file__).with_name("index.html").read_text()
        self.assertIn("speechSynthesis.speak(utterance)", html)
        self.assertIn("markDone(completedId,'device_voice')", html)
        self.assertIn("stopNarration()", html)
        self.assertIn("bottomSeen&&readMs>=minMs", html)
        self.assertIn("Reading history cannot be saved", html)

    def test_daily_briefing_article_with_boilerplate_is_rejected(self):
        # Real text from the 2026-11-10 briefing article (Anthropic IPO
        # item): the publisher must fail closed on prospectus boilerplate in
        # a daily briefing article (style v2026-11-10.2).
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            deliveries = root / "deliveries"
            folder = deliveries / "briefing-2026-11-10"
            folder.mkdir(parents=True)
            (folder / "content.json").write_text(json.dumps(
                {"title": "Daily Briefing — November 10, 2026",
                 "origin": "daily_compilation", "podcast_mode": "daily_compilation",
                 "published_at": "2026-11-10", "covered_content_ids": ["x"]}))
            (folder / "article.md").write_text(
                "# Daily Briefing — November 10, 2026\n\n"
                "Copies of the preliminary prospectus may be obtained from Goldman Sachs "
                "& Co. LLC, Attention: Prospectus Department, 200 West Street, New York, "
                "NY 10282, by telephone at (866) 471-2526, or by email at "
                "prospectus-ny@ny.email.gs.com.\n")
            with self.assertRaises(ValueError) as ctx:
                build(deliveries, root / "bundle", Path(__file__).with_name("index.html"), 15)
            self.assertIn("Boilerplate contamination", str(ctx.exception))

    def test_reject_empty_and_unsafe_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            deliveries = root / "deliveries"
            deliveries.mkdir()
            template = Path(__file__).with_name("index.html")
            with self.assertRaises(ValueError):
                build(deliveries, root / "out", template, 15)
            with self.assertRaises(ValueError):
                build(deliveries, deliveries / "out", template, 15)
            with self.assertRaises(ValueError):
                build(deliveries, root / "out", template, 0)

if __name__ == "__main__":
    unittest.main()
