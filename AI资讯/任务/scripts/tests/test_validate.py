import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from validate import Report, load_vocabulary, validate_data, validate_report  # noqa: E402
from weeks import Week  # noqa: E402

WEEK = Week.parse("2026-W43")
VOCAB = load_vocabulary()


def repo(name, status, rank=None, pos=1):
    return {"full_name": name, "trendshift_position": pos, "rank": rank, "week_stars": 100,
            "week_forks": 10, "days_covered": 7, "total_stars": 1000,
            "created_at": "2026-01-01T00:00:00Z", "status": status, "note": ""}


DATA = {
    "week": "2026-W43",
    "range": "2026-10-19/2026-10-25",
    "generated_at": "2026-10-28T18:00:00+08:00",
    "repos": [repo("a/one", "top5", 1), repo("a/two", "top5", 2, 2), repo("a/new", "new", pos=3),
              repo("a/c", "candidate", pos=4), repo("x/y", "non_ai", pos=5)],
}

REPORT = """---
week: 2026-W43
range: 2026-10-19/2026-10-25
topics: [智能体, 开源模型, 推理部署]
orgs: [DeepSeek]
repos: [a/one, a/two, a/new]
---

# AI 周报 · 2026-W43（10/19–10/25）

## ① 本周概览

概览。

## ② 关键发布与新技术

### 某发布

- **原文**：[官方](https://example.com/post)

## ③ GitHub AI 项目热度 Top 5

### 1. [a/one](https://github.com/a/one)

总 star 1,000（本周 +100）

### 2. [a/two](https://github.com/a/two)

总 star 1,000（本周 +100），详见 ②。

### 新晋项目

- [a/new](https://github.com/a/new)：介绍。

## ④ 传播最广的文章 Top 5

### 1. [文章](https://example.com/a)

HN 300 分 · 10 条评论 · [HN 讨论](https://news.ycombinator.com/item?id=1)

## ⑤ 热点话题

### 话题一

### 话题二

### 话题三

## 值得细读

- [论文一](https://arxiv.org/abs/1)：收获。
- [论文二](https://arxiv.org/abs/2)：收获。
- [论文三](https://arxiv.org/abs/3)：收获。

## 数据说明

- 联网搜索：12 次（上限 40）。
"""


def check(report=REPORT, data=DATA, backfill=False):
    rep = Report()
    validate_data(data, WEEK, rep)
    validate_report(report, WEEK, backfill, data, VOCAB, rep)
    return rep


class ValidateTest(unittest.TestCase):
    def test_valid(self):
        rep = check()
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.warnings, [])

    def test_backfill_title(self):
        self.assertTrue(check(backfill=True).errors)
        report = REPORT.replace("（10/19–10/25）", "（10/19–10/25）（回溯版）")
        self.assertEqual(check(report, backfill=True).errors, [])

    def test_unknown_topic(self):
        rep = check(REPORT.replace("推理部署", "随便写的词"))
        self.assertTrue(any("词表" in e for e in rep.errors))

    def test_missing_section_and_bad_link(self):
        report = REPORT.replace("## ⑤ 热点话题", "## 热点").replace("(https://example.com/a)", "(/relative)")
        errors = "\n".join(check(report).errors)
        self.assertIn("缺少板块", errors)
        self.assertIn("/relative", errors)

    def test_placeholder_left(self):
        rep = check(REPORT.replace("概览。", "{{3–5 句话}}"))
        self.assertTrue(any("占位符" in e for e in rep.errors))

    def test_order_mismatch_with_data(self):
        report = REPORT.replace("[a/one](https://github.com/a/one)", "[a/c](https://github.com/a/c)")
        self.assertTrue(any("不一致" in e for e in check(report).errors))

    def test_front_matter_repos_must_match(self):
        report = REPORT.replace("repos: [a/one, a/two, a/new]", "repos: [a/one, a/two]")
        self.assertTrue(any("元数据 repos" in e for e in check(report).errors))

    def test_data_rank_rules(self):
        data = copy.deepcopy(DATA)
        data["repos"][1]["rank"] = 3
        data["repos"][3]["rank"] = 4
        errors = "\n".join(check(data=data).errors)
        self.assertIn("连续编号", errors)
        self.assertIn("rank 应为 null", errors)

    def test_data_types(self):
        data = copy.deepcopy(DATA)
        data["repos"][0]["week_stars"] = "100"
        data["repos"][0]["status"] = "hot"
        errors = "\n".join(check(data=data).errors)
        self.assertIn("week_stars 类型不对", errors)
        self.assertIn("status 不合法", errors)

    def test_count_warnings(self):
        rep = check(REPORT.replace("### 话题三\n", ""))
        self.assertTrue(any("⑤" in w for w in rep.warnings))


if __name__ == "__main__":
    unittest.main()
