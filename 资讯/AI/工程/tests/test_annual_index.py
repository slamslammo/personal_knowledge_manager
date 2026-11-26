"""年度表索引：报告链接的写入形态与读回归一化。

背景：飞书「报告链接」是 type=text + style.type=url 字段。写入按 lark-cli 的
CellValue 约定传裸 URL，但 +record-list --format json 读回时会渲染成
"[显示文本](链接)"。此处锁定「写裸 URL、读回归一比较」这一约定，避免
把 CLI 的表现层差异误判成索引未更新，也避免错误链接被悄悄放过。
"""
import pathlib
import sys
import unittest
from unittest import mock

CORE = pathlib.Path(__file__).resolve().parents[1] / "core"
sys.path.insert(0, str(CORE))
import annual_index

SHA = "8fb48768c28fa614e2e8af56de3228257ec8c080"
TEXT = """---
quality: full
coverage: {正文: 5周, 榜单: 5周}
source: abc
---

## 月度主线

- 第一条有证据的结论 [来源](https://example.org/a)
- 第二条有证据的结论
"""


class LinkNormalization(unittest.TestCase):
    def test_bare_url_is_unchanged(self):
        url = "https://github.com/slamslammo/personal_knowledge_manager/blob/main/a.md"
        self.assertEqual(annual_index.normalize_link(url), url)

    def test_cli_rendered_link_is_normalized(self):
        url = "https://github.com/slamslammo/personal_knowledge_manager/blob/main/a.md"
        self.assertEqual(annual_index.normalize_link(f"[{url}]({url})"), url)
        self.assertEqual(annual_index.normalize_link(f"[报告正文]({url})"), url)

    def test_non_link_values_pass_through(self):
        self.assertIsNone(annual_index.normalize_link(None))
        self.assertEqual(annual_index.normalize_link("普通文本"), "普通文本")


class RecordLink(unittest.TestCase):
    def test_link_comes_from_the_requested_record(self):
        def call(cmd, *args):
            self.assertEqual(cmd, "+record-share-link-create")
            self.assertEqual(args, ("--record-id", "rec1"))
            return {"record_share_links": {"rec1": "https://example.feishu.cn/record/abc"}}

        self.assertEqual(annual_index.record_link(call, "rec1"),
                         "https://example.feishu.cn/record/abc")

    def test_missing_or_failed_link_returns_none(self):
        self.assertIsNone(annual_index.record_link(lambda *a: {}, "rec1"))

        def failed(*a):
            raise ValueError("share link unavailable")

        self.assertIsNone(annual_index.record_link(failed, "rec1"))


class RowMatching(unittest.TestCase):
    def setUp(self):
        self.fields = annual_index.published_row("2026-10", SHA, TEXT, False)

    def test_published_row_writes_bare_url(self):
        link = self.fields["报告链接"]
        self.assertTrue(link.startswith("https://github.com/"))
        self.assertFalse(link.startswith("["), "写入必须是裸 URL，不能是 markdown 链接")

    def test_cli_rendered_link_counts_as_match(self):
        link = self.fields["报告链接"]
        row = dict(self.fields, **{"报告链接": f"[{link}]({link})"})
        self.assertTrue(annual_index.row_matches(row, self.fields))

    def test_wrong_link_does_not_match(self):
        link = self.fields["报告链接"]
        row = dict(self.fields, **{"报告链接": f"[{link}](https://example.org/other)"})
        self.assertFalse(annual_index.row_matches(row, self.fields),
                         "链接目标不同必须判为不一致，触发重新写入")

    def test_other_field_mismatch_still_detected(self):
        row = dict(self.fields, **{"标题": "改过的标题"})
        self.assertFalse(annual_index.row_matches(row, self.fields))


QUARTER_TEXT = """---
quality: full
coverage: {正文: 13周, 榜单: 13周}
source: abc
---

## 季度主线

- 第一条有证据的结论 [来源](https://example.org/a)
- 第二条有证据的结论
- 第三条有证据的结论
"""


class QuarterRow(unittest.TestCase):
    def test_quarter_period_is_indexed_as_quarter_summary(self):
        """季报也能生成年度表行，通知链路才能共用同一份记录链接收据。"""
        fields = annual_index.published_row("2026-Q4", SHA, QUARTER_TEXT, False)
        self.assertEqual(fields["层级"], ["季"])
        self.assertEqual(fields["期间编号"], "Q4")
        self.assertEqual(fields["归属月"], "00 · 季度汇总")
        self.assertEqual(fields["归属季"], ["Q4"])
        lines = fields["关键信息"].splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(all(line[0] in "①②③" for line in lines))


class RecordReceipt(unittest.TestCase):
    def test_path_uses_fixed_filename_under_runtime_work(self):
        import paths
        p = annual_index.record_receipt_path()
        self.assertEqual(p.name, paths.FILES["annual_index"])
        self.assertEqual(p.parent.name, paths.WORK_DIR_NAME)

    def test_write_receipt_records_period_sha_and_url(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "annual-index.json"
            with mock.patch.object(annual_index, "record_receipt_path", return_value=target):
                self.assertTrue(annual_index.write_receipt(
                    "2026-Q4", SHA, "rec1", "https://example.feishu.cn/record/abc"))
            data = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(data["period"], "2026-Q4")
            self.assertEqual(data["sha"], SHA)
            self.assertEqual(data["record_id"], "rec1")
            self.assertEqual(data["url"], "https://example.feishu.cn/record/abc")

    def test_invalid_link_is_not_written(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "annual-index.json"
            with mock.patch.object(annual_index, "record_receipt_path", return_value=target):
                self.assertFalse(annual_index.write_receipt("2026-Q4", SHA, "rec1", "not-a-url"))
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
