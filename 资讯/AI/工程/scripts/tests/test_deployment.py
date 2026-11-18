"""运行方式由项目管理；验证默认沙箱、真实提交验收及正文差异不误报成功。"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
import deployment as d
import credential_probe
import env_check
import fixture
from test_coord import Lab


class ModeTest(unittest.TestCase):
    def test_config_decides_mode_without_prompt_parameters(self):
        for mode in ("acceptance", "production"):
            with self.subTest(mode=mode), mock.patch.dict(os.environ, TEST_RUN=""), \
                    mock.patch.object(d, "load_config", return_value={"mode": mode}):
                self.assertEqual(d.run_mode(), mode)

    def test_missing_invalid_or_unreadable_config_cannot_start(self):
        for value in ({}, {"mode": "prod"}, None):
            with mock.patch.object(d, "load_config", return_value=value):
                with self.assertRaises(ValueError):
                    d.run_mode()
        with mock.patch.object(d, "load_config", side_effect=OSError):
            with self.assertRaises(ValueError):
                d.run_mode()

    def test_explicit_test_only_reduces_access(self):
        with mock.patch.dict(os.environ, TEST_RUN="1"), \
                mock.patch.object(d, "load_config", return_value={"mode": "production"}):
            self.assertEqual(d.run_mode(), "acceptance")

    def test_start_ignores_stale_production_plan(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(d, "WORK_DIR", pathlib.Path(td)), \
                mock.patch.object(d, "load_config", return_value={"mode": "acceptance"}), \
                mock.patch.object(env_check, "cmd_check", return_value=0), \
                mock.patch.object(d.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
            (pathlib.Path(td) / "deployment.json").write_text('{"mode":"production"}')
            self.assertEqual(d.start("codex"), 0)
            self.assertIn("--test", run.call_args.args[0])
            self.assertFalse(json.loads((pathlib.Path(td) / "deployment.json").read_text())["auto_activate"])

    def test_incomplete_first_acceptance_never_starts_coordination(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(d, "WORK_DIR", pathlib.Path(td)), \
                mock.patch.object(d, "load_config", return_value={"mode": "acceptance"}), \
                mock.patch.object(env_check, "cmd_check", return_value=1) as check, \
                mock.patch.object(d.subprocess, "run", side_effect=AssertionError("未就绪不能启动")):
            self.assertEqual(d.start("codex"), 1)
            check.assert_called_once_with(require_delivery=True)

    def test_production_keeps_feishu_degradation_policy(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(d, "WORK_DIR", pathlib.Path(td)), \
                mock.patch.object(d, "load_config", return_value={"mode": "production"}), \
                mock.patch.object(env_check, "cmd_check", side_effect=AssertionError("生产不设交付硬门槛")), \
                mock.patch.object(d.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
            self.assertEqual(d.start("codex"), 0)
            self.assertNotIn("--test", run.call_args.args[0])

    def test_no_prior_context_needs_no_config_or_api(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(d, "load_config", side_effect=AssertionError("首次尚未安装依赖")), \
                mock.patch.object(d, "_sync_published", side_effect=AssertionError("不应调API")):
            result, code = d.resume(pathlib.Path(tmp))
        self.assertEqual(result["resume"], "not_available")
        self.assertEqual(code, 0)


class SandboxAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lab = Lab(pathlib.Path(self.tmp.name), week=fixture.WEEK)
        self.agent = self.lab.agent("codex")
        # 用新的项目入口真实启动，确认不必靠提示词传 --test。
        self.origin_before = self.lab.log("%H")
        # 身份验证由 env_check 专测覆盖；这里使用已通过门槛的边界，协调与提交仍跑真 Git。
        # 模式必须钉在 acceptance：项目切 production 后（2026-11-18），若读真实配置，
        # start 会走 origin 而不是沙箱，用例会真的朝生产远端推送（CI 上直接失败）。
        with mock.patch.dict(os.environ, self.agent.env()), mock.patch.object(d, "WORK_DIR", self.agent.work), \
                mock.patch.object(env_check, "cmd_check", return_value=0), \
                mock.patch.object(d, "load_config", return_value={"mode": "acceptance"}):
            self.assertEqual(d.start("codex"), 0)
        self.work = self.agent.work
        self.ctx = json.loads((self.work / "coord.json").read_text())
        self.assertTrue(self.ctx["test"])
        self.assertNotEqual(self.ctx["remote"], str(self.lab.remote))
        self.text = self.agent.write_fixture()
        action, p = self.agent.coord("publish")
        self.assertEqual(action, "published", p.stdout + p.stderr)
        (self.work / "notification.txt").write_text("测试通知预览，不发送", encoding="utf-8")
        (self.work / "feishu.json").write_text(json.dumps({
            "test": True, "week": fixture.WEEK, "action": "created", "document_id": "doc-test",
            "url": "https://example.feishu.cn/docx/doc-test"}))
        self.assertEqual(self.lab.log("%H"), self.origin_before)

    def finish(self, actual=None, probe_code=0):
        actual = self.text.replace("# AI 周报", "# [测试] AI 周报", 1) if actual is None else actual
        with mock.patch.object(d.fs, "find_cli", return_value="/mock/lark-cli"), \
                mock.patch.object(d.fs, "run_cli", return_value={"ok": True, "data": {
                    "document": {"content": actual}}}), \
                mock.patch.object(credential_probe, "run_probe", return_value=({"c9": "pending"}, probe_code)):
            return d.finish(self.work)

    def test_real_sandbox_pass_is_separate_from_c9(self):
        result, code = self.finish()
        self.assertEqual(code, 0, result)
        self.assertEqual(result["acceptance"], "passed")
        self.assertEqual(result["c9"], "pending")
        self.assertEqual(result["notification"], "skipped")
        self.assertFalse(result["auto_activate"])
        self.assertEqual(self.lab.log("%H"), self.origin_before)

    def test_different_doc_content_stays_pending(self):
        result, code = self.finish("# [测试] 内容被改过")
        self.assertEqual(result["acceptance"], "pending")
        self.assertEqual(result["content_match"], "manual_review")
        self.assertFalse(result["title_match"])
        self.assertEqual(result["first_diff_line"], 1)
        self.assertEqual(result["body_lines"].split("/")[0], "0")
        self.assertNotEqual(code, 0)

    def test_unknown_readback_format_never_passes_acceptance(self):
        result, code = self.finish(
            "<title>[测试] AI 周报</title><script>unexpected</script>")
        self.assertEqual(result["acceptance"], "pending")
        self.assertEqual(result["comparison_error"], "unsupported_format")
        self.assertNotEqual(code, 0)

    def test_unsynced_doc_and_failed_read_do_not_pass(self):
        result, code = self.finish(probe_code=1)
        self.assertEqual(result["acceptance"], "failed")
        (self.work / "feishu.json").write_text('{"test":false}')
        result, code = self.finish()
        self.assertEqual(result["acceptance"], "failed")

    def test_no_published_commit_cannot_pass(self):
        ctx = json.loads((self.work / "coord.json").read_text())
        del ctx["published_commit"]
        (self.work / "coord.json").write_text(json.dumps(ctx))
        result, code = self.finish()
        self.assertEqual(result["acceptance"], "failed")

    def test_missing_notification_preview_cannot_pass(self):
        (self.work / "notification.txt").unlink()
        result, code = self.finish()
        self.assertEqual(result["acceptance"], "failed")

    def test_resume_only_delivers_existing_commit_and_preserves_materials(self):
        before = (self.work / "searches.txt").read_bytes()
        context = json.loads((self.work / "coord.json").read_text())
        with mock.patch.object(d, "load_config", return_value={"mode": "acceptance"}), \
                mock.patch.object(d, "_sync_published", return_value=0) as sync, \
                mock.patch.object(d.fs, "find_cli", return_value="/mock/lark-cli"), \
                mock.patch.object(env_check, "check_binding", return_value=("PASS", "应用绑定", "")), \
                mock.patch.object(credential_probe, "run_probe", return_value=({"c9": "pending"}, 0)), \
                mock.patch.object(d, "finish", return_value=({"acceptance": "passed", "c9": "pending"}, 0)):
            result, code = d.resume(self.work)
        self.assertEqual(code, 0, result)
        self.assertEqual(result["resume"], "completed")
        self.assertEqual(sync.call_args.args[1]["published_commit"], context["published_commit"])
        self.assertEqual((self.work / "searches.txt").read_bytes(), before)
        self.assertEqual(self.lab.log("%H"), self.origin_before)

    def test_resume_failure_preserves_existing_artifacts(self):
        saved = (self.work / "feishu.json").read_bytes()
        with mock.patch.object(d, "load_config", return_value={"mode": "acceptance"}), \
                mock.patch.object(d, "_sync_published", return_value=1), \
                mock.patch.object(d.fs, "find_cli", return_value="/mock/lark-cli"), \
                mock.patch.object(env_check, "check_binding", return_value=("PASS", "应用绑定", "")), \
                mock.patch.object(credential_probe, "run_probe", return_value=({"c9": "pending"}, 0)), \
                mock.patch.object(d, "finish", side_effect=AssertionError("同步失败不能假装完成")):
            result, code = d.resume(self.work)
        self.assertEqual(result["resume"], "pending")
        self.assertEqual(code, 1)
        self.assertEqual((self.work / "feishu.json").read_bytes(), saved)
        self.assertTrue((self.work / "out" / fixture.REPORT_REL).is_file())

    def test_wrong_app_from_scan_cannot_write_documents(self):
        with mock.patch.object(d, "load_config", return_value={"mode": "acceptance"}), \
                mock.patch.object(d.fs, "find_cli", return_value="/mock/lark-cli"), \
                mock.patch.object(env_check, "check_binding", return_value=("NEEDS_HUMAN", "应用绑定", "")), \
                mock.patch.object(d, "_sync_published", side_effect=AssertionError("错误应用不能写入")), \
                mock.patch.object(credential_probe, "run_probe", side_effect=AssertionError("不应继续")):
            result, code = d.resume(self.work)
        self.assertEqual(result["resume"], "pending")
        self.assertEqual(code, 1)
        self.assertIn("指定应用", result["reason"])

    def test_production_does_not_resume_old_sandbox(self):
        with mock.patch.object(d, "run_mode", return_value="production"), \
                mock.patch.object(d, "_sync_published", side_effect=AssertionError("不应调用")):
            result, code = d.resume(self.work)
        self.assertEqual(result["resume"], "not_available")
        self.assertEqual(code, 0)


class ReadbackMatchTest(unittest.TestCase):
    """飞书读回是 HTML 化单行表示，必须还原块结构后比对，但不能因此放过内容丢失。

    2026-11-18 验收：读回 12,201 字符 0 换行（`<title>`、`<h2>`、`<br/>`、`<table>`），
    发布稿 8,497 字符 144 行 Markdown，旧的逐行折叠必然不等，导致每次运行都以
    `ACCEPTANCE=pending` 收尾。此处的样本保留真实结构：标题被提到文档首位、YAML 头
    变成正文首块、列表与表格走 HTML 标签。
    """

    MARKDOWN = """---
week: 2026-W45
range: 2026-11-02/2026-11-08
---
# [测试] AI 周报 · 2026-W45

## ① 本周概览

- **开放权重**：Kimi K3.1 Pro 放出完整权重。
- 争议见 [问题报告](https://example.com/report)。

## ② 传播文章 Top 5

| # | 文章 | 分数 |
| --- | --- | --- |
| 1 | [模型权重编程实验](https://example.com/astra) | 2971 |

## 数据说明

<!-- auto:data-notes -->
- 联网搜索：22 次（下限 20，上限 40）。
<!-- /auto -->

> 口径：每日数据按 UTC 日期累计。
"""

    READBACK = (
        "<title>[测试] AI 周报 · 2026-W45</title><hr/>"
        "<h2>week: 2026-W45<br/>range: 2026-11-02/2026-11-08</h2>"
        "<h2>① 本周概览</h2><ul>"
        "<li><b>开放权重</b>：Kimi K3.1 Pro 放出完整权重。</li>"
        '<li>争议见 <a href="https://example.com/report">问题报告</a>。</li></ul>'
        "<h2>② 传播文章 Top 5</h2><table><colgroup><col/><col/><col/></colgroup>"
        '<thead><tr><th><p>#</p></th><th><p>文章</p></th><th><p>分数</p></th></tr></thead>'
        '<tbody><tr><td><p>1</p></td><td><p><a href="https://example.com/astra">模型权重编程实验</a></p></td>'
        "<td><p>2971</p></td></tr></tbody></table>"
        "<h2>数据说明</h2><ul><li>联网搜索：22 次（下限 20，上限 40）。</li></ul>"
        "<blockquote><p>口径：每日数据按 UTC 日期累计。</p></blockquote>"
    )

    def test_html_readback_equals_markdown_source(self):
        self.assertEqual(d.document_parts(self.READBACK), d.document_parts(self.MARKDOWN))

    def test_title_is_compared_separately(self):
        broken = self.READBACK.replace("<title>[测试] AI 周报", "<title>AI 周报")
        self.assertNotEqual(d.document_parts(broken)[0], d.document_parts(self.MARKDOWN)[0])

    def test_missing_line_is_detected(self):
        broken = self.READBACK.replace("<li>联网搜索：22 次（下限 20，上限 40）。</li>", "")
        self.assertNotEqual(d.document_parts(broken), d.document_parts(self.MARKDOWN))

    def test_changed_number_is_detected(self):
        broken = self.READBACK.replace("<p>2971</p>", "<p>2900</p>")
        self.assertNotEqual(d.document_parts(broken), d.document_parts(self.MARKDOWN))

    def test_changed_link_target_is_detected(self):
        broken = self.READBACK.replace("https://example.com/astra", "https://example.com/other")
        self.assertNotEqual(d.document_parts(broken), d.document_parts(self.MARKDOWN))

    def test_dropped_table_column_is_detected(self):
        broken = self.READBACK.replace("<td><p>2971</p></td>", "")
        self.assertNotEqual(d.document_parts(broken), d.document_parts(self.MARKDOWN))

    def test_swapped_order_is_detected(self):
        first = "<li><b>开放权重</b>：Kimi K3.1 Pro 放出完整权重。</li>"
        second = '<li>争议见 <a href="https://example.com/report">问题报告</a>。</li>'
        broken = self.READBACK.replace(first + second, second + first)
        self.assertNotEqual(d.document_parts(broken), d.document_parts(self.MARKDOWN))

    def test_extra_section_is_detected(self):
        broken = self.READBACK + "<h2>补一段</h2>"
        self.assertNotEqual(d.document_parts(broken), d.document_parts(self.MARKDOWN))

    def test_html_comment_does_not_count(self):
        without_comment = self.MARKDOWN.replace("<!-- auto:data-notes -->\n", "")
        self.assertEqual(d.document_parts(without_comment), d.document_parts(self.MARKDOWN))

    def test_markdown_with_angle_bracket_text_is_not_treated_as_html(self):
        """发布稿里可能有 `URLError: <urlopen error …>`，不能当成标签剥掉。"""
        text = self.MARKDOWN.replace("联网搜索：22 次", "联网搜索：<urlopen error Tunnel failed> 22 次")
        self.assertIn("<urlopen error Tunnel failed>", "\n".join(d.document_parts(text)[1]))

    def test_link_destination_is_not_formatted_as_markdown(self):
        expected = "# T\n\n[源](https://example.com/a**b)"
        correct = '<title>T</title><p><a href="https://example.com/a**b">源</a></p>'
        changed = correct.replace("a**b", "ab")
        self.assertEqual(d.compare_documents(expected, correct)["content_match"], "normalized_equal")
        self.assertEqual(d.compare_documents(expected, changed)["content_match"], "manual_review")
        # Literal backticks and nested parentheses in destinations survive too.
        expected = "# T\n\n[源](https://example.com/a" + chr(96) + "(b))"
        actual = '<title>T</title><p><a href="https://example.com/a' + chr(96) + '(b)">源</a></p>'
        self.assertEqual(d.compare_documents(expected, actual)["content_match"], "normalized_equal")

    def test_inline_code_operators_spaces_and_literal_markup_survive(self):
        expected = "# T\n\n" + chr(96) + "2 ** 10 <x>  +  1" + chr(96)
        actual = "<title>T</title><p><code>2 ** 10 &lt;x&gt;  +  1</code></p>"
        self.assertEqual(d.compare_documents(expected, actual)["content_match"], "normalized_equal")
        for broken in (actual.replace("**", ""), actual.replace("  +  ", " + "),
                       actual.replace("&lt;x&gt;", "")):
            with self.subTest(broken=broken):
                self.assertEqual(d.compare_documents(expected, broken)["content_match"], "manual_review")

    def test_numbered_heading_keeps_its_number(self):
        expected = "# T\n\n### 1. 项目"
        correct = "<title>T</title><h3>1. 项目</h3>"
        self.assertEqual(d.compare_documents(expected, correct)["content_match"], "normalized_equal")
        self.assertEqual(d.compare_documents(expected, correct.replace("1.", "99."))["content_match"],
                         "manual_review")

    def test_table_cell_boundaries_and_empty_cells_are_preserved(self):
        expected = "# T\n\n| A | B |\n| --- | --- |\n| a\\|b | c |\n| | d |"
        correct = ("<title>T</title><table><tr><th>A</th><th>B</th></tr>"
                   "<tr><td>a|b</td><td>c</td></tr><tr><td></td><td>d</td></tr></table>")
        self.assertEqual(d.compare_documents(expected, correct)["content_match"], "normalized_equal")
        for broken in (correct.replace("<td>a|b</td><td>c</td>", "<td>a</td><td>b|c</td>"),
                       correct.replace("<td></td>", "")):
            with self.subTest(broken=broken):
                self.assertEqual(d.compare_documents(expected, broken)["content_match"], "manual_review")

    def test_html_table_entities_are_decoded_once(self):
        expected = "# T\n\n| 错误 |\n| --- |\n| <urlopen error 502> &amp;lt; |"
        actual = ("<title>T</title><table><tr><th>错误</th></tr>"
                  "<tr><td><p>&lt;urlopen error 502&gt; &amp;lt;</p></td></tr></table>")
        self.assertEqual(d.compare_documents(expected, actual)["content_match"], "normalized_equal")
        self.assertEqual(d.compare_documents(expected, actual.replace("&amp;lt;", "&lt;"))["content_match"],
                         "manual_review")

    def test_supported_inline_formatting_does_not_hide_literal_symbols(self):
        expected = "# T\n\n- **说明**：" + chr(96) + "**" + chr(96) + " [来源](https://example.com/?x=1&amp;y=2)"
        actual = ('<title>T</title><ul><li><strong>说明</strong>：<code>**</code> '
                  '<a href="https://example.com/?x=1&amp;y=2">来源</a></li></ul>')
        self.assertEqual(d.compare_documents(expected, actual)["content_match"], "normalized_equal")
        self.assertEqual(d.compare_documents(expected, actual.replace("<code>**</code>", ""))["content_match"],
                         "manual_review")

    def test_unsupported_or_malformed_conversion_requires_review(self):
        for actual in ("<title>T</title><iframe>正文</iframe>",
                       "<title>T</title><p>正文</div>",
                       "<title>T</title><p>正文",
                       "<title>T</title><table><tr><td colspan=\"2\">正文</td></tr></table>"):
            with self.subTest(actual=actual):
                result = d.compare_documents("# T\n\n正文", actual)
                self.assertEqual(result["content_match"], "manual_review")
                self.assertEqual(result["comparison_error"], "unsupported_format")
        # The weekly format does not currently use these Markdown constructs.
        for unsupported in ("![图](https://example.com/image.png)", chr(96) * 3 + "\n正文\n" + chr(96) * 3,
                            "1. 正文"):
            with self.subTest(unsupported=unsupported):
                result = d.compare_documents("# T\n\n" + unsupported, "# T\n\n" + unsupported)
                self.assertEqual(result["content_match"], "manual_review")


if __name__ == "__main__":
    unittest.main()
