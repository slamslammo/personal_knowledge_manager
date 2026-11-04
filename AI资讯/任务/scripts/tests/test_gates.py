"""质量门槛、草稿与数据说明的测试。门槛用例取自 W44 的真实问题（../../版本规划.md 2026-11-02）。"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import draft  # noqa: E402
import finalize  # noqa: E402
from test_validate import DATA, REPORT, VOCAB, WEEK  # noqa: E402
from validate import Report, validate_report, validate_sources  # noqa: E402

SOURCES = {"official": ["blog.google", "openai.com"], "primary": ["sec.gov", "github.com"],
           "media": ["techcrunch.com", "theverge.com"]}


def story(i, url, points=1000, comments=500, official=None):
    s = {"id": str(i), "points": points, "num_comments": comments, "title": f"t{i}", "url": url,
         "hn_url": f"https://news.ycombinator.com/item?id={i}", "github_repo": None}
    if official is not None:
        s["article"] = {"status": "ok", "official": official, "primary": False}
    return s


MATERIALS = {"hn": {"stories": [
    story(11, "https://blog.google/models/gemini-4-carbon/", 1018, 803),
    story(12, "https://openai.com/index/introducing-gpt-6-1-terra/", 637, 427),
    story(13, "https://www.sec.gov/Archives/edgar/data/1/s1.htm", 1710, 1682),
    story(1, "https://example.com/a1", 899, 10), story(2, "https://example.com/a2", 898, 10),
    story(3, "https://example.com/a3", 897, 10), story(4, "https://example.com/a4", 896, 10),
    story(5, "https://example.com/a5", 895, 10),
]}}


def report_with_releases(items: str) -> str:
    start = REPORT.index("## ② 新发布与技术 Top 5")
    end = REPORT.index("## ③")
    return REPORT[:start] + "## ② 新发布与技术 Top 5\n\n" + items + "\n" + REPORT[end:]


def gate(report, tolerance=0.0):
    rep = Report()
    validate_sources(report, MATERIALS, rep, tolerance, SOURCES)
    return rep


class SourceGateTest(unittest.TestCase):
    def test_w44_style_media_only_release_is_caught(self):
        items = ("### Google 预告 Gemini 4 Carbon\n\n- **原文**：[Khaleej Times 报道](https://khaleejtimes.com/x)；"
                 "HN 讨论 [1017 分](https://news.ycombinator.com/item?id=11)\n")
        rep = gate(report_with_releases(items))
        self.assertIn("GATE_NOT_OFFICIAL", rep.codes)
        self.assertIn("blog.google", "\n".join(rep.errors))  # 报错里给出应写的官方链接

    def test_homepage_link_is_caught(self):
        items = "### OpenAI 科研\n\n- **原文**：[OpenAI 公告](https://openai.com)；[HN](https://news.ycombinator.com/item?id=12)\n"
        rep = gate(report_with_releases(items))
        self.assertIn("GATE_LINK_HOMEPAGE", rep.codes)
        self.assertIn("GATE_NOT_OFFICIAL", rep.codes)  # 首页不算官方原文

    def test_official_link_passes_and_scores_checked(self):
        items = ("### GPT-6.1 Terra\n\n- **原文**：[OpenAI 公告](https://openai.com/index/introducing-gpt-6-1-terra/)；"
                 "[HN 讨论 637 分](https://news.ycombinator.com/item?id=12)\n\n"
                 "### Anthropic S-1\n\n- **原文**：[SEC 文件](https://www.sec.gov/Archives/edgar/data/1/s1.htm)；"
                 "[HN 讨论 1,710 分](https://news.ycombinator.com/item?id=13)\n")
        self.assertEqual(gate(report_with_releases(items)).errors, [])
        wrong = items.replace("637 分", "700 分")
        self.assertIn("GATE_NUMBERS", gate(report_with_releases(wrong)).codes)
        self.assertEqual(gate(report_with_releases(wrong), tolerance=0.15).errors, [])  # 校验时允许自然增长

    def test_media_only_needs_marker(self):
        items = "### 某传闻\n\n- **原文**：[TechCrunch](https://techcrunch.com/2026/x)\n"
        self.assertIn("GATE_NOT_OFFICIAL", gate(report_with_releases(items)).codes)
        marked = items.replace("[TechCrunch]", "「仅媒体报道」[TechCrunch]")
        self.assertEqual(gate(report_with_releases(marked)).errors, [])

    def test_article_link_must_match_hn_data(self):
        self.assertEqual(gate(REPORT).errors, [])
        hn_as_article = REPORT.replace("[文章1](https://example.com/a1)", "[文章1](https://news.ycombinator.com/item?id=1)")
        rep = gate(hn_as_article)
        self.assertIn("GATE_ARTICLE_LINK", rep.codes)
        self.assertIn("https://example.com/a1", "\n".join(rep.errors))
        wrong_score = REPORT.replace("| 899 | 10 |", "| 950 | 10 |")
        self.assertIn("GATE_NUMBERS", gate(wrong_score).codes)

    def test_no_materials_no_gates(self):
        rep = Report()
        validate_sources(REPORT, {"hn": {"stories": []}}, rep, 0.0, SOURCES)
        self.assertEqual(rep.errors, [])


class FinalizeTest(unittest.TestCase):
    def test_apply_replaces_block_and_strips_notes(self):
        text = "## ②\n\n<!-- 草稿：提示\n多行 -->\n内容\n\n## 数据说明\n\n- 可疑内容：无\n"
        once = finalize.apply(text, ["- 联网搜索：3 次。"])
        self.assertNotIn("草稿", once)
        self.assertIn(finalize.AUTO_BEGIN + "\n- 联网搜索：3 次。\n" + finalize.AUTO_END, once)
        twice = finalize.apply(once, ["- 联网搜索：5 次。"])
        self.assertEqual(twice.count(finalize.AUTO_BEGIN), 1)
        self.assertIn("5 次", twice)
        self.assertNotIn("3 次", twice)


class FinalizeAutoTest(unittest.TestCase):
    def test_render_auto_uses_rank_report_and_search_count(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            sources = {"trendshift": {"status": "ok", "detail": "25 项"}, "hn": {"status": "skipped", "code": "SRC_TIMEOUT",
                                                                              "detail": "超时"}}
            (work / "collect_report.json").write_text(json.dumps({"sources": sources}), encoding="utf-8")
            (work / "rank_report.json").write_text(json.dumps({"week": "2026-W43", "ossinsight_requested": 23,
                                                               "ossinsight_failed": ["a/x"]}), encoding="utf-8")
            (work / "searches.txt").write_text("发现\tq1\n发现\tq2\n", encoding="utf-8")
            lines = "\n".join(finalize.render_auto(work, DATA))
        self.assertIn("Trendshift 周榜：成功，25 项", lines)
        self.assertIn("OSS Insight：请求 23 个，失败 1 个（a/x）", lines)
        self.assertIn("HN：失败，已跳过（SRC_TIMEOUT：超时）", lines)
        self.assertIn("联网搜索：2 次", lines)


class DraftTest(unittest.TestCase):
    INFO = {"week": "2026-W43", "start": "2026-10-19", "end": "2026-10-25", "range_label": "10/19–10/25",
            "mode": "normal"}

    def test_draft_fills_numbers_and_candidates(self):
        materials = {"hn": {"stories": [story(1, "https://example.com/llm", 900, 50)]},
                     "trendshift": {"items": []}, "sources": {}}
        materials["hn"]["stories"][0]["title"] = "New LLM [beta] | release"
        text = draft.build(self.INFO, DATA, materials, degraded=False)
        self.assertIn("repos: [a/one, a/two]", text)
        self.assertIn("### 1. [a/one](https://github.com/a/one)", text)
        self.assertIn("总 star 1,000（本周 +100）｜{{一句话介绍}}", text)
        self.assertIn("| 900 | 50 | [HN](https://news.ycombinator.com/item?id=1) |", text)
        self.assertIn("[New LLM (beta) / release](https://example.com/llm)", text)
        self.assertIn(finalize.AUTO_BEGIN, text)
        # 草稿本身不能通过校验（占位符未填），定稿后的提示会被 finalize 删除
        rep = Report()
        validate_report(text, WEEK, False, DATA, VOCAB, rep)
        self.assertTrue(any("占位符" in e for e in rep.errors))

    def test_degraded_passes_structure_checks(self):
        text = draft.build(self.INFO, DATA, {"hn": {"stories": []}, "sources": {}}, degraded=True, reason="测试")
        self.assertIn("quality: degraded", text)
        self.assertNotIn("{{", text)
        self.assertNotIn("<!-- 草稿", text)
        rep = Report()
        validate_report(text, WEEK, False, DATA, VOCAB, rep)
        self.assertEqual(rep.errors, [])

    def test_trendshift_not_ready(self):
        text = draft.build(self.INFO, None, {"hn": {"stories": []},
                                             "sources": {"trendshift": {"detail": "HTTP 307"}}}, degraded=False)
        self.assertIn("周榜未就绪：HTTP 307", text)
        self.assertIn("repos: []", text)


if __name__ == "__main__":
    unittest.main()
