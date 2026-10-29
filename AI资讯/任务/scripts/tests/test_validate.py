import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from validate import Report, load_vocabulary, table_rows, validate_data, validate_report  # noqa: E402
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

ARTICLE_ROWS = "\n".join(
    f"| {i} | [文章{i}](https://example.com/a{i}) | 摘要。 | 原因。 | {900 - i} | 10 | "
    f"[HN](https://news.ycombinator.com/item?id={i}) |"
    for i in range(1, 6)
)
TOPIC_ROWS = "\n".join(
    f"| 话题{i} | 起因。 | 争议。 | [链接](https://example.com/t{i})、[链接](https://example.com/u{i}) |"
    for i in range(1, 6)
)

REPORT = f"""---
week: 2026-W43
range: 2026-10-19/2026-10-25
topics: [智能体, 开源模型, 推理部署]
orgs: [DeepSeek]
repos: [a/one, a/two]
---

# AI 周报 · 2026-W43（10/19–10/25）

## ① 本周概览

- **一**：第一条。
- **二**：第二条。
- **三**：第三条。

## 洞察

### 洞察 1：结论一

- **依据**：② 某发布；⑤ 话题1。
- **必读**：[论文一](https://arxiv.org/abs/1)：收获。

### 洞察 2：结论二

- **依据**：③ a/one。
- **必读**：[论文二](https://arxiv.org/abs/2)：收获；[论文三](https://arxiv.org/abs/3)：收获。

## ② 新发布与技术 Top 5

### 某发布

- **原文**：[官方](https://example.com/post)

## ③ GitHub AI 项目热度 Top 5

### 1. [a/one](https://github.com/a/one)

总 star 1,000（本周 +100）

### 2. [a/two](https://github.com/a/two)

总 star 1,000（本周 +100），详见 ②。

## ④ 传播文章 Top 5

| # | 文章 | 摘要 | 传播原因 | 分数 | 评论 | 讨论 |
| --- | --- | --- | --- | --- | --- | --- |
{ARTICLE_ROWS}

## ⑤ 热点话题 Top 5

| 话题 | 起因 | 发展与争议 | 代表链接 |
| --- | --- | --- | --- |
{TOPIC_ROWS}

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
        report = REPORT.replace("## ⑤ 热点话题", "## 热点").replace("(https://example.com/a1)", "(/relative)")
        errors = "\n".join(check(report).errors)
        self.assertIn("缺少板块", errors)
        self.assertIn("/relative", errors)

    def test_placeholder_left(self):
        rep = check(REPORT.replace("第一条。", "{{一句话}}"))
        self.assertTrue(any("占位符" in e for e in rep.errors))

    def test_order_mismatch_with_data(self):
        report = REPORT.replace("[a/one](https://github.com/a/one)", "[a/c](https://github.com/a/c)")
        self.assertTrue(any("不一致" in e for e in check(report).errors))

    def test_front_matter_repos_must_match(self):
        report = REPORT.replace("repos: [a/one, a/two]", "repos: [a/one, a/new]")
        errors = "\n".join(check(report).errors)
        self.assertIn("元数据 repos 应为数据文件中的 Top 5", errors)

    def test_section3_only_top5(self):
        report = REPORT.replace("总 star 1,000（本周 +100），详见 ②。\n",
                                "总 star 1,000（本周 +100），详见 ②。\n\n### 新晋项目\n\n- [a/new](https://github.com/a/new)：介绍。\n")
        self.assertTrue(any("③ 只写 Top 5" in e for e in check(report).errors))

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

    def test_count_limits(self):
        extra = "\n".join(f"### 发布{i}\n" for i in range(5))
        errors = "\n".join(check(REPORT.replace("### 某发布\n", "### 某发布\n" + extra)).errors)
        self.assertIn("② 有 6 条", errors)
        rep = check(REPORT.replace(TOPIC_ROWS.splitlines()[-1] + "\n", ""))
        self.assertTrue(any("⑤ 热点话题 有 4 项" in w for w in rep.warnings))
        rep = check(REPORT.replace("- **三**：第三条。\n", "").replace("- **二**：第二条。\n", ""))
        self.assertTrue(any("① 本周概览" in w for w in rep.warnings))

    def test_articles_must_not_repeat_releases(self):
        report = REPORT.replace("[文章1](https://example.com/a1)", "[发布](https://example.com/post/)")
        report = report.replace("[文章2](https://example.com/a2)", "[项目](https://github.com/a/one)")
        errors = "\n".join(check(report).errors)
        self.assertIn("第 1 行是 ②③ 已写的发布", errors)
        self.assertIn("第 2 行是 ②③ 已写的发布", errors)

    def test_article_row_needs_hn_link(self):
        report = REPORT.replace("[HN](https://news.ycombinator.com/item?id=3)", "无")
        self.assertTrue(any("第 3 行缺少 HN 讨论链接" in e for e in check(report).errors))

    def test_insight_needs_basis_and_reads(self):
        report = REPORT.replace("- **依据**：③ a/one。\n", "")
        report = report.replace("- **必读**：[论文一](https://arxiv.org/abs/1)：收获。", "- 没有必读。")
        errors = "\n".join(check(report).errors)
        self.assertIn("洞察 2 没有写依据", errors)
        self.assertIn("洞察 1 没有写必读", errors)

    def test_insights_must_follow_overview(self):
        i0 = REPORT.index("## 洞察\n")
        i1 = REPORT.index("## ② ")
        block = REPORT[i0:i1]
        moved = REPORT[:i0] + REPORT[i1:]
        moved = moved.replace("## 数据说明", block + "## 数据说明")
        self.assertTrue(any("顺序不对" in e for e in check(moved).errors))

    def test_long_table_cells_warn(self):
        long_text = "很长的说明" * 20  # 100 字
        report = REPORT.replace("| 话题1 | 起因。 |", f"| 话题1 | {long_text} |")
        report = report.replace("[文章2](https://example.com/a2) | 摘要。", f"[文章2](https://example.com/a2) | {long_text}")
        rep = check(report)
        self.assertEqual(rep.errors, [])
        warnings = "\n".join(rep.warnings)
        self.assertIn("⑤「话题1」的起因有 100 字", warnings)
        self.assertIn("④ 第 2 行的摘要有 100 字", warnings)

    def test_link_urls_do_not_count_toward_cell_length(self):
        link = "[短](https://example.com/" + "x" * 200 + ")"
        rep = check(REPORT.replace("[链接](https://example.com/t1)", link))
        self.assertEqual(rep.warnings, [])

    def test_table_rows(self):
        rows = table_rows("说明\n| a | b |\n| --- | :---: |\n| 1 | x |\n| 2 | y |\n\n| z |\n")
        self.assertEqual(rows, [["1", "x"], ["2", "y"]])


if __name__ == "__main__":
    unittest.main()
