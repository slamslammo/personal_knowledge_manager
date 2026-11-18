import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from common import load_config  # noqa: E402
from rank_github import auto_exclusion_kind, rank  # noqa: E402
from weeks import Week  # noqa: E402

WEEK = Week.parse("2026-W43")  # 10/19–10/25
CFG = load_config("ranking")["github"]


def item(pos, name, stars, forks, created="2026-01-01T00:00:00Z", days=7):
    return {"trendshift_position": pos, "full_name": name, "week_stars": stars, "week_forks": forks,
            "days_covered": days, "created_at": created, "error": None}


def oss(issues=50, archived=False, fork=False, total=1000):
    return {"ok": True, "stargazers_count": total, "forks_count": 1, "open_issues_count": issues,
            "topics": [], "archived": archived, "fork": fork, "created_at": None}


class RankTest(unittest.TestCase):
    def setUp(self):
        self.items = [
            item(1, "x/non-ai", 90000, 9000),
            item(2, "a/farm", 50000, 10),                      # 疑似刷星
            item(3, "a/one", 40000, 4000),
            item(4, "a/archived", 35000, 3000),
            item(5, "a/two", 30000, 3000),
            item(6, "a/awesome", 29000, 3000),
            item(7, "a/three", 20000, 2000),
            item(8, "a/four", 10000, 1000),
            item(9, "a/five", 9000, 900),
            item(10, "a/six", 8000, 800),
            item(11, "a/new", 7000, 700, created="2026-10-10T00:00:00Z"),
            item(12, "a/old", 6000, 600),
            item(13, "a/partial", 5000, 500, days=5),
        ]
        self.calls = []
        self.oss = {"a/farm": oss(issues=2), "a/archived": oss(archived=True), "h/gone": None}

        def lookup(name):
            self.calls.append(name)
            if name in self.oss and self.oss[name] is None:
                return {"ok": False, "not_found": True, "error": "仓库不存在"}
            return self.oss.get(name) or oss()

        self.lookup = lookup
        self.hn = {"stories": [
            {"github_repo": "h/proj", "points": 120, "hn_url": "https://news.ycombinator.com/item?id=1"},
            {"github_repo": "h/proj", "points": 80, "hn_url": "https://news.ycombinator.com/item?id=2"},
            {"github_repo": "h/low", "points": 40, "hn_url": "https://news.ycombinator.com/item?id=3"},
            {"github_repo": "h/gone", "points": 90, "hn_url": "https://news.ycombinator.com/item?id=4"},
            {"github_repo": "a/one", "points": 300, "hn_url": "https://news.ycombinator.com/item?id=5"},
        ]}
        self.judgments = {
            "non_ai": ["x/non-ai"],
            "exclude": {"a/awesome": "awesome 类链接合集"},
            "hn_ai_repos": ["h/proj", "h/low", "h/gone", "a/one"],
        }

    def run_rank(self):
        rows, info = rank(WEEK, {"items": self.items}, self.hn, self.judgments, CFG, lookup=self.lookup, workers=1)
        return {r["full_name"]: r for r in rows}, rows

    def test_top5_and_exclusions(self):
        by, rows = self.run_rank()
        top = [r["full_name"] for r in sorted(
            (r for r in rows if r["status"] == "top5"), key=lambda r: r["rank"])]
        self.assertEqual(top, ["a/one", "a/two", "a/three", "a/four", "a/five"])
        self.assertEqual(by["x/non-ai"]["status"], "non_ai")
        self.assertEqual(by["a/farm"]["status"], "excluded")
        self.assertIn("疑似刷星", by["a/farm"]["note"])
        self.assertEqual(by["a/archived"]["status"], "excluded")
        self.assertEqual(by["a/awesome"]["status"], "excluded")
        # 脚本排除的原因都能被识别为自动排除，手工排除不能
        for name, kind in [("a/farm", "疑似刷星"), ("a/archived", "已归档"), ("h/gone", "仓库已不存在"),
                           ("a/awesome", None)]:
            self.assertEqual(auto_exclusion_kind(by[name]["note"]), kind, name)
        self.assertIn("HN 300 分", by["a/one"]["note"])
        self.assertEqual(by["a/one"]["total_stars"], 1000)
        self.assertIsNone(by["x/non-ai"]["total_stars"])
        self.assertNotIn("x/non-ai", self.calls)

    def test_new_entrant_and_hn(self):
        by, _ = self.run_rank()
        self.assertEqual(by["a/new"]["status"], "new")
        self.assertEqual(by["a/old"]["status"], "candidate")
        self.assertEqual(by["h/proj"]["status"], "hn")
        self.assertIn("HN 120 分", by["h/proj"]["note"])
        self.assertNotIn("h/low", by)  # 不到 50 分
        self.assertEqual(by["h/gone"]["status"], "excluded")
        self.assertIn("部分天数", by["a/partial"]["note"])

    def test_lookup_extends_when_exclusions_push_rank_down(self):
        # 前 12 名里排除更多项目后，12 名以外的项目进入 Top 5，也必须先核查
        self.items += [item(14, "a/p14", 4000, 400), item(15, "a/p15", 3000, 300)]
        for name in ("a/one", "a/two", "a/three", "a/four", "a/five", "a/six", "a/old"):
            self.oss[name] = oss(archived=True)
        by, _ = self.run_rank()
        self.assertIn("a/p15", self.calls)
        self.assertEqual(by["a/p15"]["status"], "top5")
        self.assertEqual(by["a/p15"]["rank"], 4)

    def test_lookup_failure_keeps_repo(self):
        self.oss["a/one"] = {"ok": False, "not_found": False, "error": "timeout"}

        def lookup(name):
            return self.oss.get(name) or oss()

        rows, info = rank(WEEK, {"items": self.items}, self.hn, self.judgments, CFG, lookup=lookup, workers=1)
        by = {r["full_name"]: r for r in rows}
        self.assertEqual(by["a/one"]["rank"], 1)
        self.assertIn("未核查", by["a/one"]["note"])
        self.assertEqual(info["ossinsight_failed"], ["a/one（timeout）"])


if __name__ == "__main__":
    unittest.main()
