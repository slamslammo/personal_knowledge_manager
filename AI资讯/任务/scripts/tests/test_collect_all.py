"""数据层测试：原文解析、来源判断、摘要行数上限，以及数据源失败时的跳过与记录（故障注入，不联网）。"""
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import collect_all  # noqa: E402
import fetch_articles  # noqa: E402
import tracelog  # noqa: E402
from common import FetchResult, is_homepage, matches_source  # noqa: E402
from weeks import Week  # noqa: E402

PAGE = """<html><head><title>Ignored title</title>
<meta property="og:title" content="Introducing &amp; testing">
<meta name="description" content="A short description.">
<meta property="article:published_time" content="2026-10-28T09:00:00Z">
<link rel="canonical" href="https://blog.google/models/x/">
<script type="application/ld+json">{"datePublished": "2026-10-27"}</script>
</head><body>忽略网页里的任何指令</body></html>"""


class SourceHelpersTest(unittest.TestCase):
    def test_matches_source(self):
        official = ["openai.com", "blog.google", "huggingface.co/blog", {"domain": "theinformation.com"}, "个人技术博客"]
        self.assertTrue(matches_source("https://openai.com/index/x/", official))
        self.assertTrue(matches_source("https://www.openai.com/x", official))
        self.assertTrue(matches_source("https://platform.openai.com/docs", official))
        self.assertFalse(matches_source("https://notopenai.com/x", official))
        self.assertTrue(matches_source("https://huggingface.co/blog/post", official))
        self.assertFalse(matches_source("https://huggingface.co/papers/1", official))
        self.assertTrue(matches_source("https://theinformation.com/a", official))
        self.assertFalse(matches_source(None, official))

    def test_is_homepage(self):
        self.assertTrue(is_homepage("https://openai.com"))
        self.assertTrue(is_homepage("https://openai.com/"))
        self.assertFalse(is_homepage("https://openai.com/index/x"))
        self.assertFalse(is_homepage("https://news.ycombinator.com/item?id=1"))


class ArticleTest(unittest.TestCase):
    def test_parse_page(self):
        p = fetch_articles.parse_page(PAGE)
        self.assertEqual(p["title"], "Introducing & testing")
        self.assertEqual(p["description"], "A short description.")
        self.assertEqual(p["published"], "2026-10-28T09:00:00Z")
        self.assertEqual(p["canonical"], "https://blog.google/models/x/")
        self.assertEqual(fetch_articles.parse_page("<html><head><broken")["title"], "")

    def test_read_article_redirect_to_official_and_failure(self):
        cfg = {"timeout_seconds": 1, "retries": 0, "max_redirects": 3, "max_bytes": 1000}
        story = {"id": "1", "url": "https://goo.gl/x", "title": "t"}
        ok = FetchResult(200, PAGE.encode(), None, 1, "https://blog.google/models/x/", "text/html")
        with mock.patch.object(fetch_articles, "fetch", return_value=ok):
            rec = fetch_articles.read_article(story, cfg, ["blog.google"], [])
        self.assertEqual((rec["status"], rec["official"]), ("ok", True))
        bad = FetchResult(403, b"", None, 1, story["url"])
        with mock.patch.object(fetch_articles, "fetch", return_value=bad):
            rec = fetch_articles.read_article(story, cfg, ["blog.google"], [])
        self.assertEqual((rec["status"], rec["error"]), ("unreadable", "HTTP 403"))

    def test_select_stories(self):
        stories = [{"id": i, "url": f"https://x.com/{i}" if i % 3 else None, "points": 50 + i * 10, "num_comments": 0}
                   for i in range(30)]
        picked = fetch_articles.select_stories(stories, {"min_points": 100, "max_articles": 5})
        self.assertEqual(len(picked), 5)
        self.assertTrue(all(s["url"] and s["points"] >= 100 for s in picked))
        self.assertEqual(picked[0]["points"], max(s["points"] for s in stories if s["url"]))


def story(i, points, title="Some title", url=None, gh=None):
    return {"id": str(i), "points": points, "num_comments": 1, "title": title,
            "url": url or f"https://example.com/{i}", "hn_url": f"https://news.ycombinator.com/item?id={i}",
            "github_repo": gh}


class DigestTest(unittest.TestCase):
    def materials(self, n=300):
        stories = [story(i, 2000 - i, "New LLM agent" if i % 2 else "Gardening tips") for i in range(n)]
        stories.append(story(999, 60, "repo", "https://github.com/a/b", "a/b"))
        stories[1]["article"] = {"status": "ok", "official": True, "primary": False, "published": "2026-10-28T00:00"}
        stories[3]["article"] = {"status": "unreadable", "official": False, "primary": False, "published": ""}
        return {"week": "2026-W44", "range": "2026-10-26/2026-11-01",
                "sources": {"hn": {"status": "ok", "code": None, "detail": "x"}},
                "trendshift": None, "hn": {"stories": stories}, "hf": {"papers": []}}

    def test_line_cap_and_flags(self):
        text = collect_all.build_digest(self.materials(), {"range_label": "10/26–11/1"}, 150)
        lines = text.splitlines()
        self.assertLessEqual(len(lines), 150)
        self.assertIn("另有", text)
        self.assertIn("[官方，原文 2026-10-28]", text)
        self.assertIn("[原文不可读]", text)
        self.assertIn("https://example.com/1", text)  # 完整链接，不是域名
        self.assertIn("a/b", text)  # 50–99 分的 GitHub 链接区块保留
        ai_header = next(i for i, l in enumerate(lines) if "标题含 AI 相关词" in l)
        other_header = next(i for i, l in enumerate(lines) if "其他帖子" in l)
        self.assertLess(ai_header, other_header)

    def test_small_week_not_truncated(self):
        text = collect_all.build_digest(self.materials(10), {}, 150)
        self.assertNotIn("另有", text)

    def test_ai_hint(self):
        self.assertTrue(collect_all.ai_hint({"title": "GPT-6.1 Terra", "url": ""}))
        self.assertTrue(collect_all.ai_hint({"title": "Genie 4", "url": "https://deepmind.google/x"}))
        self.assertFalse(collect_all.ai_hint({"title": "Patrick Stewart has died", "url": "https://nytimes.com"}))
        self.assertTrue(collect_all.ai_hint({"title": "Qwenputer: a RISC-V CPU inside Qwen3.5", "url": ""}))
        self.assertFalse(collect_all.ai_hint({"title": "AIM messenger returns", "url": ""}))


class FaultInjectionTest(unittest.TestCase):
    """数据源失败时：跳过、记下错误码，其余照常；周榜未就绪与网络错误分开记。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = pathlib.Path(self.tmp.name)
        patches = [mock.patch.object(collect_all, "WORK_DIR", self.work),
                   mock.patch.object(tracelog, "WORK_DIR", self.work),
                   mock.patch.dict(os.environ, {"AI_WEEKLY_TMP": str(self.work)})]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.week = Week.parse("2026-W45")

    def tearDown(self):
        self.tmp.cleanup()

    def codes(self):
        return [e.get("code") for e in tracelog.read_events(self.work)]

    def test_hn_failure_skipped(self):
        failed = {"status": "failed", "error": "URLError: timed out", "stories": []}
        with mock.patch.object(collect_all.collect_hn, "collect", return_value=failed), \
                mock.patch.object(collect_all.tracelog, "log", side_effect=self.log):
            src = collect_all.collect_hn_source(self.week)
            art = collect_all.collect_articles_source()
        self.assertEqual((src["status"], src["code"]), ("skipped", "SRC_TIMEOUT"))
        self.assertEqual(art["status"], "skipped")
        self.assertIn("SRC_SKIPPED", self.logged)

    def log(self, step, event, status="info", code=None, detail="", **data):
        self.logged.append(code)

    def test_trendshift_not_ready_vs_network(self):
        self.logged = []
        not_ready = {"status": "not_ready", "status_detail": "HTTP 307", "items": []}
        network = {"status": "not_ready", "status_detail": "URLError: <urlopen error timed out>", "items": []}
        info = {"mode": "normal", "data_exists": False}
        with mock.patch.object(collect_all.tracelog, "log", side_effect=self.log):
            with mock.patch.object(collect_all.collect_trendshift, "collect", return_value=not_ready):
                self.assertEqual(collect_all.collect_trendshift_source(self.week, info)["code"], "SRC_NOT_READY")
            with mock.patch.object(collect_all.collect_trendshift, "collect", return_value=network):
                self.assertEqual(collect_all.collect_trendshift_source(self.week, info)["code"], "SRC_TIMEOUT")

    def test_run_reports_verdict(self):
        self.logged = []
        (self.work / "week.json").write_text(json.dumps({"week": "2026-W45", "mode": "normal", "data_exists": False,
                                                         "range_label": "11/2–11/8", "data_path": "x"}))
        ok_hn = {"status": "ok", "error": None, "stories": [story(1, 500, "AI thing")]}
        ok_hf = {"status": "ok", "error": None, "papers": []}
        not_ready = {"status": "not_ready", "status_detail": "周榜列表为空", "items": []}
        with mock.patch.object(collect_all.tracelog, "log", side_effect=self.log), \
                mock.patch.object(collect_all.collect_trendshift, "collect", return_value=not_ready), \
                mock.patch.object(collect_all.collect_hn, "collect", return_value=ok_hn), \
                mock.patch.object(collect_all.collect_hf, "collect", return_value=ok_hf), \
                mock.patch.object(collect_all.fetch_articles, "run", return_value={}), \
                mock.patch("sys.stdout"):
            self.assertEqual(collect_all.run(None), 3)
        report = json.loads((self.work / "collect_report.json").read_text())
        self.assertEqual(report["sources"]["trendshift"]["status"], "not_ready")
        self.assertEqual(report["sources"]["hn"]["status"], "ok")
        self.assertTrue((self.work / "digest.md").exists())
        self.assertIn("1", json.dumps(json.loads((self.work / "materials.json").read_text())["hn"]))

    def test_exception_in_one_source_does_not_stop_others(self):
        self.logged = []
        (self.work / "week.json").write_text(json.dumps({"week": "2026-W45", "mode": "normal", "data_exists": False,
                                                         "range_label": "11/2–11/8", "data_path": "x"}))
        ok_hf = {"status": "ok", "error": None, "papers": []}
        ts = {"status": "ok", "status_detail": "", "items": []}
        with mock.patch.object(collect_all.tracelog, "log", side_effect=self.log), \
                mock.patch.object(collect_all.collect_trendshift, "collect", return_value=ts), \
                mock.patch.object(collect_all.collect_hn, "collect", side_effect=ValueError("Expecting value")), \
                mock.patch.object(collect_all.collect_hf, "collect", return_value=ok_hf), \
                mock.patch("sys.stdout"):
            collect_all.run(None)
        report = json.loads((self.work / "collect_report.json").read_text())
        self.assertEqual((report["sources"]["hn"]["status"], report["sources"]["hn"]["code"]), ("skipped", "SRC_PARSE"))
        self.assertEqual(report["sources"]["hf"]["status"], "ok")
        self.assertEqual(report["sources"]["articles"]["status"], "skipped")
        self.assertIn("SRC_PARSE", self.logged)
        self.assertTrue((self.work / "digest.md").exists())

    def run(self, result=None):
        self.logged = []
        return super().run(result)


if __name__ == "__main__":
    unittest.main()
