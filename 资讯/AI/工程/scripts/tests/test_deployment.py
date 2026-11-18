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
        with mock.patch.dict(os.environ, self.agent.env()), mock.patch.object(d, "WORK_DIR", self.agent.work), \
                mock.patch.object(env_check, "cmd_check", return_value=0):
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
        with mock.patch.object(d, "_sync_published", return_value=0) as sync, \
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
        with mock.patch.object(d, "_sync_published", return_value=1), \
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
        with mock.patch.object(d.fs, "find_cli", return_value="/mock/lark-cli"), \
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


if __name__ == "__main__":
    unittest.main()
