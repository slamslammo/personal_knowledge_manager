import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from collect_hn import build_stories  # noqa: E402
from collect_trendshift import (  # noqa: E402
    describe_prior, list_matches_week, parse_daily, parse_weekly_list, prior_judgments, week_sums,
)
from common import github_repo_from_url, normalize_url  # noqa: E402
from weeks import Week  # noqa: E402


class TrendshiftParseTest(unittest.TestCase):
    def test_parse_weekly_list(self):
        item_list = {
            "@type": "ItemList",
            "name": "Weekly trending repositories for Sep 28 to Oct 4, 2026",
            "itemListElement": [{"position": 1, "url": "https://trendshift.io/repositories/1",
                                 "item": {"name": "a/b"}}],
        }
        html = ('<script type="application/ld+json">{"@type":"BreadcrumbList"}</script>'
                f'<script type="application/ld+json">{json.dumps(item_list)}</script>')
        self.assertEqual(parse_weekly_list(html)["itemListElement"][0]["item"]["name"], "a/b")
        self.assertIsNone(parse_weekly_list("<html></html>"))

    def test_list_matches_week(self):
        self.assertTrue(list_matches_week("Weekly trending repositories for Sep 28 to Oct 4, 2026",
                                          Week.parse("2026-W40")))
        self.assertTrue(list_matches_week("Weekly trending repositories for Oct 19 to 25, 2026",
                                          Week.parse("2026-W43")))
        self.assertTrue(list_matches_week("Dec 28, 2026 to Jan 3, 2027", Week.parse("2026-W53")))
        self.assertFalse(list_matches_week("Weekly trending repositories for Oct 12 to 18, 2026",
                                           Week.parse("2026-W43")))
        self.assertFalse(list_matches_week("", Week.parse("2026-W43")))

    def test_daily_sums(self):
        rows = [("2026-10-18", 99, 9)] + [(f"2026-10-{d}", d, 1) for d in range(19, 24)]
        html = "".join(
            f'{{\\"date\\":\\"{d}T00:00:00Z\\",\\"stars\\":{s},\\"forks\\":{f},\\"merged_prs\\":0}},'
            for d, s, f in rows
        )
        daily = parse_daily(html)
        self.assertEqual(daily["2026-10-18"], (99, 9))
        sums = week_sums(daily, Week.parse("2026-W43"))  # 10/19–10/25，只有 5 天数据
        self.assertEqual(sums["week_stars"], 19 + 20 + 21 + 22 + 23)
        self.assertEqual(sums["week_forks"], 5)
        self.assertEqual(sums["days_covered"], 5)
        self.assertIsNone(week_sums({}, Week.parse("2026-W43"))["week_stars"])


class PriorJudgmentTest(unittest.TestCase):
    def test_latest_earlier_week_wins(self):
        def repo(name, status, note=""):
            return {"full_name": name, "status": status, "note": note}

        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp)
            (d / "2026-W41.json").write_text(json.dumps({"repos": [
                repo("a/x", "non_ai"), repo("a/y", "candidate"), repo("a/z", "top5")]}), encoding="utf-8")
            (d / "2026-W42.json").write_text(json.dumps({"repos": [
                repo("a/x", "candidate"), repo("a/j", "excluded", "越狱提示词合集；HN 80 分")]}), encoding="utf-8")
            (d / "2026-W43.json").write_text(json.dumps({"repos": [repo("a/z", "non_ai")]}), encoding="utf-8")
            (d / "broken.json").write_text("{", encoding="utf-8")
            prior = prior_judgments(Week.parse("2026-W43"), d)
        self.assertEqual(prior["a/x"], {"week": "2026-W42", "verdict": "AI", "reason": ""})
        self.assertEqual(prior["a/y"]["verdict"], "AI")
        self.assertEqual(prior["a/z"]["week"], "2026-W41")  # 不看报告周本身和之后的文件
        self.assertEqual(describe_prior(prior["a/j"]), "往期：排除：越狱提示词合集（2026-W42）")
        self.assertEqual(describe_prior(None), "")


class LinkTest(unittest.TestCase):
    def test_normalize_url(self):
        self.assertEqual(normalize_url("https://www.Example.com/a/?utm_source=x&b=1#frag"), "example.com/a?b=1")
        self.assertEqual(normalize_url("http://example.com/a"), normalize_url("https://www.example.com/a/"))

    def test_github_repo_from_url(self):
        cases = {
            "https://github.com/deepseek-ai/DeepInfer": "deepseek-ai/DeepInfer",
            "https://github.com/a/b.git": "a/b",
            "https://github.com/a/b/tree/main/docs": "a/b",
            "https://github.com/a/b/issues/12": None,
            "https://github.com/a/b/pull/3": None,
            "https://github.com/orgs/foo/discussions": None,
            "https://github.com/a": None,
            "https://gist.github.com/a/b": None,
            None: None,
        }
        for url, want in cases.items():
            self.assertEqual(github_repo_from_url(url), want, url)


class HNTest(unittest.TestCase):
    def test_dedupe_and_order(self):
        hits = [
            {"objectID": 1, "title": "A", "url": "https://x.com/a?utm_source=hn", "points": 100,
             "num_comments": 5, "created_at_i": 0},
            {"objectID": 2, "title": "A again", "url": "http://www.x.com/a/", "points": 300,
             "num_comments": 1, "created_at_i": 0},
            {"objectID": 3, "title": "Ask HN", "url": None, "points": 300, "num_comments": 9, "created_at_i": 0},
            {"objectID": 4, "title": "Repo", "url": "https://github.com/o/r", "points": 60,
             "num_comments": 2, "created_at_i": 0},
        ]
        stories = build_stories(hits)
        self.assertEqual([s["id"] for s in stories], ["3", "2", "4"])
        self.assertEqual(stories[1]["dup_ids"], ["1"])
        self.assertEqual(stories[2]["github_repo"], "o/r")
        self.assertEqual(stories[0]["hn_url"], "https://news.ycombinator.com/item?id=3")


if __name__ == "__main__":
    unittest.main()
