"""feishu_sync.py 的测试：mock 子进程与 socket，不触网、不调真实 lark-cli。

覆盖：preflight 分级降级、代理自适应（只清回环死端口）、查重 0/1/N 分支、
create 超时不重试 / overwrite 幂等重试、标题双条件匹配（含间隔号）、
from-published 路径推导、notify 发送与 fallback。
"""
import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import feishu_sync  # noqa: E402

WEEK = "2026-W45"
H1 = f"AI 周报 · {WEEK}（11/2–11/8）"
REPORT = f"---\nweek: {WEEK}\n---\n\n# {H1}\n\n## ① 本周概览\n"


def auth_json(bot=True, user=True):
    return {"identities": {
        "bot": {"status": "ready" if bot else "expired", "available": bot},
        "user": {"status": "ready" if user else "expired", "available": user}}}


def search_json(titles):
    """titles: [(title, token, doc_types)]"""
    return {"data": {"results": [
        {"entity_type": "DOC",
         "result_meta": {"doc_types": dt, "token": tok, "url": f"https://x.feishu.cn/docx/{tok}"},
         "title_highlighted": t}
        for t, tok, dt in titles]}}


def cli_ok(payload):
    return {"ok": True, **payload}


def cli_err(type_="network", subtype="timeout"):
    return {"ok": False, "error": {"type": type_, "subtype": subtype, "detail": "mock"}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = pathlib.Path(self.tmp.name)
        patchers = [
            mock.patch.object(feishu_sync, "WORK_DIR", self.work),
            mock.patch.object(feishu_sync.tracelog, "log", lambda *a, **k: {}),
            # 此测试组默认模拟已经明确进入 production 的项目。
            mock.patch.object(feishu_sync, "_project_test_mode", return_value=False),
        ]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        (self.work / "week.json").write_text(json.dumps({"week": WEEK}), encoding="utf-8")
        # 默认环境：无代理变量、非测试模式
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        for v in feishu_sync.PROXY_VARS + ("TEST_RUN",):
            os.environ.pop(v, None)
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_sync(self, **kw):
        ns = {"sha": None, "week": None, "report": None}
        ns.update(kw)
        args = types.SimpleNamespace(**ns)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = feishu_sync.cmd_sync(args)
        return code, buf.getvalue()

    def run_preflight(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = feishu_sync.cmd_preflight(None)
        return code, buf.getvalue()


class PreflightTest(Base):
    def preflight_with(self, cfg, cli="/bin/lark-cli", auth=None, auth_seq=None):
        with mock.patch.object(feishu_sync, "cfg_load", return_value=cfg), \
             mock.patch.object(feishu_sync, "find_cli", return_value=cli), \
             mock.patch.object(feishu_sync, "_auth_status",
                               return_value=auth if auth is not None else None), \
             mock.patch.object(feishu_sync.time, "sleep", lambda *_: None):
            if auth_seq is not None:
                with mock.patch.object(feishu_sync, "run_cli", side_effect=auth_seq):
                    return self.run_preflight()
            return self.run_preflight()

    def test_config_missing(self):
        code, out = self.preflight_with(cfg=None)
        self.assertEqual(code, 0)
        self.assertIn("PREFLIGHT=degraded:off", out)
        self.assertIn("FEISHU_CONFIG_MISSING", out)
        self.assertEqual(feishu_sync.read_mode(), "off")

    def test_disabled(self):
        _, out = self.preflight_with(cfg={"enabled": False})
        self.assertIn("PREFLIGHT=disabled", out)

    def test_cli_not_found(self):
        _, out = self.preflight_with(cfg={"enabled": True}, cli=None)
        self.assertIn("FEISHU_CLI_NOT_FOUND", out)

    def test_full(self):
        _, out = self.preflight_with(cfg={"enabled": True}, auth=auth_json())
        self.assertIn("PREFLIGHT=ok", out)
        self.assertEqual(feishu_sync.read_mode(), "full")

    def test_user_invalid_gives_no_doc(self):
        _, out = self.preflight_with(cfg={"enabled": True}, auth=auth_json(user=False))
        self.assertIn("degraded:no_doc", out)
        self.assertIn("FEISHU_USER_INVALID", out)

    def test_bot_invalid_gives_no_notify(self):
        _, out = self.preflight_with(cfg={"enabled": True}, auth=auth_json(bot=False))
        self.assertIn("degraded:no_notify", out)
        self.assertIn("FEISHU_BOT_INVALID", out)

    def test_both_invalid_gives_off(self):
        _, out = self.preflight_with(cfg={"enabled": True}, auth=auth_json(bot=False, user=False))
        self.assertIn("degraded:off", out)
        self.assertIn("FEISHU_AUTH_INVALID", out)

    def test_unreachable_after_retries(self):
        calls = []
        def fake_status(cli):
            calls.append(1)
            return cli_err("network", "timeout")
        with mock.patch.object(feishu_sync, "cfg_load", return_value={"enabled": True}), \
             mock.patch.object(feishu_sync, "find_cli", return_value="/bin/lark-cli"), \
             mock.patch.object(feishu_sync, "_auth_status", side_effect=fake_status), \
             mock.patch.object(feishu_sync.time, "sleep", lambda *_: None):
            _, out = self.run_preflight()
        self.assertIn("FEISHU_UNREACHABLE", out)


class ProxyAdaptTest(unittest.TestCase):
    def adapt(self, env, listening):
        def fake_conn(addr, timeout=0):
            host = addr[0]
            if host in listening:
                return mock.MagicMock()
            raise OSError("refused")
        with mock.patch.object(feishu_sync.socket, "create_connection", side_effect=fake_conn):
            return feishu_sync.adapt_proxy_env(env)

    def test_dead_loopback_removed(self):
        env, removed = self.adapt({"HTTPS_PROXY": "http://127.0.0.1:49797"}, listening=set())
        self.assertEqual(removed, ["HTTPS_PROXY"])
        self.assertNotIn("HTTPS_PROXY", env)

    def test_alive_loopback_kept(self):
        env, removed = self.adapt({"HTTPS_PROXY": "http://127.0.0.1:7890"}, listening={"127.0.0.1"})
        self.assertEqual(removed, [])
        self.assertEqual(env["HTTPS_PROXY"], "http://127.0.0.1:7890")

    def test_non_loopback_kept_even_if_unreachable(self):
        # 云端真实代理是远端主机：一次探测失败不能作为清除依据（评审修正点 4）
        env, removed = self.adapt({"HTTPS_PROXY": "http://proxy.corp.internal:8080"}, listening=set())
        self.assertEqual(removed, [])
        self.assertIn("HTTPS_PROXY", env)

    def test_mixed_proxy_keeps_valid_one(self):
        # 评审 P2-7 混合代理负例：死回环 HTTP_PROXY 被移除后，
        # 仍有效的远端 HTTPS_PROXY 必须继续生效，且不设全局 NO_PROXY 开关
        env, removed = self.adapt({"HTTP_PROXY": "http://127.0.0.1:49797",
                                   "HTTPS_PROXY": "http://proxy.corp:8080"}, listening=set())
        self.assertEqual(removed, ["HTTP_PROXY"])
        self.assertNotIn("HTTP_PROXY", env)
        self.assertEqual(env.get("HTTPS_PROXY"), "http://proxy.corp:8080")
        self.assertNotIn("LARK_CLI_NO_PROXY", env)

    def test_no_proxy_vars(self):
        env, removed = self.adapt({}, listening=set())
        self.assertEqual(removed, [])
        self.assertNotIn("LARK_CLI_NO_PROXY", env)


class TitleMatchTest(unittest.TestCase):
    def test_h1_with_middle_dot_matches(self):
        # 真实 H1：「AI 周报 · 2026-W45（11/2–11/8）」，结构匹配不受间隔号与可变后缀影响
        self.assertTrue(feishu_sync.title_matches(H1, WEEK, test=False))
        self.assertTrue(feishu_sync.title_matches(f"AI 周报 · {WEEK}（11/2–11/8）（回溯版）", WEEK, test=False))

    def test_other_week_rejected(self):
        self.assertFalse(feishu_sync.title_matches(H1, "2026-W46", test=False))
        self.assertFalse(feishu_sync.title_matches("随便一个文档", WEEK, test=False))

    def test_unrelated_summary_doc_rejected(self):
        # 评审 P1-2 最小反例：「包含」匹配会把问题汇总类文档当成覆盖对象
        self.assertFalse(feishu_sync.title_matches(f"关于 AI 周报 · {WEEK} 的问题汇总", WEEK, test=False))
        self.assertFalse(feishu_sync.title_matches(f"关于 AI 周报 · {WEEK} 的问题汇总", WEEK, test=True))

    def test_week_boundary(self):
        # 周编号带边界：2026-W45 不能命中 2026-W455 或 12026-W45
        self.assertFalse(feishu_sync.title_matches("AI 周报 · 2026-W455", WEEK, test=False))
        self.assertFalse(feishu_sync.title_matches("AI 周报 · 12026-W45", WEEK, test=False))

    def test_test_mode_isolation(self):
        self.assertTrue(feishu_sync.title_matches(f"[测试] {H1}", WEEK, test=True))
        self.assertFalse(feishu_sync.title_matches(H1, WEEK, test=True))          # 正式文档不被测试覆盖
        self.assertFalse(feishu_sync.title_matches(f"[测试] {H1}", WEEK, test=False))  # 测试文档不进正式查重


class SyncTest(Base):
    def setUp(self):
        super().setUp()
        (self.work / feishu_sync.MODE_FILE).write_text(json.dumps({"mode": "full"}), encoding="utf-8")
        self.git = mock.patch.object(feishu_sync, "git_show", return_value=REPORT)
        self.git.start()
        self.addCleanup(self.git.stop)
        self.cli = mock.patch.object(feishu_sync, "find_cli", return_value="/bin/lark-cli")
        self.cli.start()
        self.addCleanup(self.cli.stop)
        self.cfg = mock.patch.object(feishu_sync, "cfg_load",
                                     return_value={"enabled": True, "folder_token": "fld1"})
        self.cfg.start()
        self.addCleanup(self.cfg.stop)
        # sync 每次现场刷新 preflight（评审 P2-5）：默认双身份可用
        self.auth = mock.patch.object(feishu_sync, "_auth_status", return_value=auth_json())
        self.auth.start()
        self.addCleanup(self.auth.stop)
        mock.patch.object(feishu_sync.time, "sleep", lambda *_: None).start()

    def candidates(self, value):
        return mock.patch.object(feishu_sync, "search_candidates", return_value=value)

    def test_zero_candidates_creates(self):
        created = []
        def fake_create(cli, title, content_file, folder):
            created.append((title, folder))
            return {"action": "created", "document_id": "doc1", "url": "https://x/docx/doc1"}
        with self.candidates([]), \
             mock.patch.object(feishu_sync, "_create", side_effect=fake_create):
            code, out = self.run_sync(sha="abc123")
        self.assertEqual(code, 0)
        self.assertIn("SYNC=created", out)
        self.assertEqual(created, [(H1, "fld1")])
        result = json.loads((self.work / feishu_sync.RESULT_FILE).read_text(encoding="utf-8"))
        self.assertEqual(result["action"], "created")
        self.assertEqual(result["document_id"], "doc1")

    def test_one_candidate_overwrites(self):
        calls = []
        def fake_overwrite(cli, token, content_file):
            calls.append(token)
            return {"action": "updated", "document_id": token}
        with self.candidates([{"token": "doc1", "title": H1, "url": "u"}]), \
             mock.patch.object(feishu_sync, "_overwrite", side_effect=fake_overwrite):
            code, out = self.run_sync()
        self.assertEqual(code, 0)
        self.assertIn("SYNC=updated", out)
        self.assertEqual(calls, ["doc1"])
        result = json.loads((self.work / feishu_sync.RESULT_FILE).read_text(encoding="utf-8"))
        self.assertEqual(result["url"], "u")  # overwrite 成功也要带回 url（通知链接用）

    def test_multi_candidates_refused(self):
        with self.candidates([{"token": "a", "title": H1, "url": "u"},
                              {"token": "b", "title": H1, "url": "u"}]), \
             mock.patch.object(feishu_sync, "_overwrite") as ow, \
             mock.patch.object(feishu_sync, "_create") as cr:
            code, out = self.run_sync()
        self.assertEqual(code, 1)
        self.assertIn("FEISHU_AMBIGUOUS_DOC", out)
        ow.assert_not_called()
        cr.assert_not_called()

    def test_create_network_failure_not_retried(self):
        # create 超时可能已创建，索引延迟下重搜为空也不能再 create（评审修正点 2）
        calls = []
        def fake_create(cli, title, content_file, folder):
            calls.append(1)
            return {"action": "failed", "error": {"type": "network", "subtype": "timeout"}}
        with self.candidates([]), \
             mock.patch.object(feishu_sync, "_create", side_effect=fake_create):
            code, out = self.run_sync()
        self.assertEqual(code, 1)
        self.assertIn("FEISHU_SYNC_FAILED", out)
        self.assertEqual(len(calls), 1)

    def test_overwrite_network_failure_retried(self):
        # overwrite 幂等：网络失败重试直到成功
        attempts = []
        def fake_overwrite(cli, token, content_file):
            attempts.append(1)
            if len(attempts) < 2:
                return {"action": "retry", "error": {"type": "network"}}
            return {"action": "updated", "document_id": token}
        with self.candidates([{"token": "doc1", "title": H1, "url": "u"}]), \
             mock.patch.object(feishu_sync, "_overwrite", side_effect=fake_overwrite):
            code, out = self.run_sync()
        self.assertEqual(code, 0)
        self.assertEqual(len(attempts), 2)

    def test_week_from_arg_and_path_derivation(self):
        seen = {}
        def fake_git(ref, path):
            seen["ref"], seen["path"] = ref, path
            return REPORT
        with mock.patch.object(feishu_sync, "git_show", side_effect=fake_git), \
             self.candidates([]), \
             mock.patch.object(feishu_sync, "_create", return_value={"action": "created", "document_id": "d"}):
            self.run_sync(week="2026-W40")
        self.assertEqual(seen, {"ref": "main", "path": "AI资讯/周报/2026/2026-W40.md"})

    def test_source_missing(self):
        with mock.patch.object(feishu_sync, "git_show", return_value=None):
            code, out = self.run_sync()
        self.assertEqual(code, 1)
        self.assertIn("FEISHU_SOURCE_MISSING", out)

    def test_skipped_in_no_doc_mode(self):
        # 现场 preflight 判定 user 不可用 → no_doc 跳过
        with mock.patch.object(feishu_sync, "_auth_status", return_value=auth_json(user=False)):
            code, out = self.run_sync()
        self.assertEqual(code, 0)
        self.assertIn("SYNC=skipped mode=no_doc", out)

    def test_stale_no_doc_cache_refreshed_by_sync(self):
        # 评审 P2-5 最小反例：授权已修复但缓存 mode=no_doc，补交付不得再被短路
        (self.work / feishu_sync.MODE_FILE).write_text(json.dumps({"mode": "no_doc"}), encoding="utf-8")
        with self.candidates([]), \
             mock.patch.object(feishu_sync, "_create",
                               return_value={"action": "created", "document_id": "d1", "url": "u"}) as cr:
            code, out = self.run_sync(week=WEEK)
        self.assertEqual(code, 0)
        self.assertIn("SYNC=created", out)
        cr.assert_called_once()
        self.assertEqual(feishu_sync.read_mode(), "full")  # 缓存已被现场状态刷新

    def test_search_failure_retried_then_error(self):
        calls = []
        def fake_search(cli, week, test):
            calls.append(1)
            return None
        with mock.patch.object(feishu_sync, "search_candidates", side_effect=fake_search):
            code, out = self.run_sync()
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), feishu_sync.MAX_ATTEMPTS)

    def test_coord_test_flag_enables_test_mode(self):
        # 评审 P1-1：coord.json test=true、环境未导出 TEST_RUN，sync 也按测试模式查重/建文档
        (self.work / "coord.json").write_text(json.dumps({"test": True}), encoding="utf-8")
        titles = []
        with self.candidates([]), \
             mock.patch.object(feishu_sync, "_create",
                               side_effect=lambda c, t, f, d: titles.append(t) or {"action": "created", "document_id": "d"}):
            self.run_sync()
        self.assertTrue(titles[0].startswith("[测试] "))
        content = (self.work / "feishu-content.md").read_text(encoding="utf-8")
        self.assertIn(f"\n# [测试] {H1}\n", "\n" + content)

    def test_test_mode_title_prefix(self):
        os.environ["TEST_RUN"] = "1"
        titles = []
        with self.candidates([]), \
             mock.patch.object(feishu_sync, "_create",
                               side_effect=lambda c, t, f, d: titles.append(t) or {"action": "created", "document_id": "d"}):
            self.run_sync()
        self.assertTrue(titles[0].startswith("[测试] "))

    def test_test_mode_content_h1_prefixed(self):
        # overwrite 会用内容 H1 重置文档标题：前缀必须写进内容，否则覆盖后漏出隔离
        os.environ["TEST_RUN"] = "1"
        with self.candidates([]), \
             mock.patch.object(feishu_sync, "_create", return_value={"action": "created", "document_id": "d"}):
            self.run_sync()
        content = (self.work / "feishu-content.md").read_text(encoding="utf-8")
        self.assertIn(f"\n# [测试] {H1}\n", "\n" + content)

    def test_prod_mode_content_untouched(self):
        with self.candidates([]), \
             mock.patch.object(feishu_sync, "_create", return_value={"action": "created", "document_id": "d"}):
            self.run_sync()
        content = (self.work / "feishu-content.md").read_text(encoding="utf-8")
        self.assertNotIn("[测试]", content)

    def write_cache(self, **kw):
        d = {"week": WEEK, "test": False, "document_id": "doc1",
             "url": "https://x/docx/doc1", "action": "created"}
        d.update(kw)
        (self.work / feishu_sync.RESULT_FILE).write_text(json.dumps(d), encoding="utf-8")

    def test_cached_document_short_circuits_search(self):
        # create 后立刻重跑：搜索索引延迟查不到新文档，用结果文件的 document_id 直接覆盖
        self.write_cache()
        calls = []
        with mock.patch.object(feishu_sync, "_doc_state", return_value="exists"), \
             mock.patch.object(feishu_sync, "search_candidates",
                               side_effect=AssertionError("不应经过搜索")) as search, \
             mock.patch.object(feishu_sync, "_overwrite",
                               side_effect=lambda c, t, f: calls.append(t) or {"action": "updated", "document_id": t}):
            code, out = self.run_sync()
        self.assertEqual(code, 0)
        self.assertIn("SYNC=updated", out)
        self.assertEqual(calls, ["doc1"])
        result = json.loads((self.work / feishu_sync.RESULT_FILE).read_text(encoding="utf-8"))
        self.assertEqual(result["url"], "https://x/docx/doc1")  # url 从缓存带回

    def test_cached_document_deleted_falls_back_to_search(self):
        # 缓存文档被人为删除：确定 missing，回退搜索路径
        self.write_cache()
        with mock.patch.object(feishu_sync, "_doc_state", return_value="missing"), \
             self.candidates([{"token": "doc9", "title": H1, "url": "u"}]), \
             mock.patch.object(feishu_sync, "_overwrite",
                               return_value={"action": "updated", "document_id": "doc9"}) as ow:
            code, out = self.run_sync()
        self.assertEqual(code, 0)
        self.assertIn("SYNC=updated", out)

    def test_cached_document_fetch_unknown_aborts(self):
        # 评审 P2-5：缓存文档临时读取失败（unknown）不能当不存在——
        # 宁可失败也不落到搜索 0 候选 create（索引延迟下会重复建）
        self.write_cache()
        with mock.patch.object(feishu_sync, "_doc_state", return_value="unknown"), \
             mock.patch.object(feishu_sync, "_create",
                               side_effect=AssertionError("unknown 状态不应 create")) as cr, \
             mock.patch.object(feishu_sync, "_overwrite",
                               side_effect=AssertionError("unknown 状态不应 overwrite")) as ow:
            code, out = self.run_sync()
        self.assertEqual(code, 1)
        self.assertIn("FEISHU_SYNC_FAILED", out)

    def test_create_unknown_then_backfill_refuses_blind_recreate(self):
        # 评审 P2-5 跨两次调用回归：
        # 第 1 次 create 网络超时（结果不明）→ 记 action=unknown；
        # 第 2 次补交付搜索仍 0 候选（索引未收录）→ 拒绝盲目重建
        with self.candidates([]), \
             mock.patch.object(feishu_sync, "_create",
                               return_value={"action": "unknown",
                                             "error": {"type": "network", "subtype": "timeout"}}):
            code, out = self.run_sync()
        self.assertEqual(code, 1)
        self.assertIn("FEISHU_SYNC_UNKNOWN", out)
        result = json.loads((self.work / feishu_sync.RESULT_FILE).read_text(encoding="utf-8"))
        self.assertEqual(result["action"], "unknown")
        with self.candidates([]), \
             mock.patch.object(feishu_sync, "_create",
                               side_effect=AssertionError("上次 create 结果不明，0 候选不得重建")) as cr:
            code, out = self.run_sync()
        self.assertEqual(code, 1)
        self.assertIn("FEISHU_SYNC_FAILED", out)
        cr.assert_not_called()

    def test_create_unknown_then_backfill_finds_doc_overwrites(self):
        # 接上：第 2 次补交付搜索到已建文档（索引已收录）→ 正常 overwrite 收敛
        self.write_cache(action="unknown", document_id=None, url=None)
        with self.candidates([{"token": "doc7", "title": H1, "url": "u7"}]), \
             mock.patch.object(feishu_sync, "_overwrite",
                               return_value={"action": "updated", "document_id": "doc7"}):
            code, out = self.run_sync()
        self.assertEqual(code, 0)
        self.assertIn("SYNC=updated", out)

    def test_cached_result_ignores_mismatch(self):
        self.write_cache(week="2026-W44")
        self.assertIsNone(feishu_sync._cached_result(WEEK, test=False))
        self.write_cache(test=True)
        self.assertIsNone(feishu_sync._cached_result(WEEK, test=False))
        self.assertIsNone(feishu_sync._cached_result("2026-W44", test=False))


class IsTestTest(Base):
    def test_env_var(self):
        os.environ["TEST_RUN"] = "1"
        self.assertTrue(feishu_sync.is_test())

    def test_coord_json_flag(self):
        # 评审 P1-1：coord --test 只写 coord.json 不导出环境变量，脚本必须认运行状态
        (self.work / "coord.json").write_text(json.dumps({"test": True}), encoding="utf-8")
        self.assertTrue(feishu_sync.is_test())

    def test_neither_source(self):
        (self.work / "coord.json").write_text(json.dumps({"test": False}), encoding="utf-8")
        self.assertFalse(feishu_sync.is_test())


class ProjectIsolationTest(unittest.TestCase):
    """即使在启动协调前失败，项目验收模式也不能发送真实通知。"""

    def test_project_acceptance_skips_notify_before_coord_exists(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(feishu_sync, "WORK_DIR", pathlib.Path(tmp)), \
                mock.patch.dict(os.environ, TEST_RUN=""), \
                mock.patch.object(feishu_sync, "load_config", return_value={"mode": "acceptance"}), \
                mock.patch.object(feishu_sync, "run_cli", side_effect=AssertionError("不应发请求")), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            code = feishu_sync.cmd_notify(types.SimpleNamespace(file="unused", fallback_file=None))
            self.assertEqual(code, 0)
            self.assertIn("NOTIFY=skipped test=1", out.getvalue())

    def test_missing_or_invalid_mode_is_conservative(self):
        for config in (None, {}, {"mode": "typo"}, {"mode": "acceptance"}):
            with self.subTest(config=config), mock.patch.object(feishu_sync, "load_config", return_value=config):
                self.assertTrue(feishu_sync._project_test_mode())
        with mock.patch.object(feishu_sync, "load_config", side_effect=ValueError):
            self.assertTrue(feishu_sync._project_test_mode())
        with mock.patch.object(feishu_sync, "load_config", return_value={"mode": "production"}):
            self.assertFalse(feishu_sync._project_test_mode())


class RunCliEnvelopeTest(Base):
    """评审 P2-4：包装层必须解析 stderr 的结构化错误信封。"""

    def fake_proc(self, stdout="", stderr="", rc=0):
        return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=rc)

    def test_stderr_network_envelope_preserved(self):
        # stdout 空、stderr 是 network/timeout 信封：必须保留 network 类型（重试分支依赖它），
        # 不能错标成 cli/bad_output
        with mock.patch.object(feishu_sync.subprocess, "run",
                               return_value=self.fake_proc(
                                   stderr='{"ok": false, "error": {"type": "network", "subtype": "timeout"}}', rc=1)):
            out = feishu_sync.run_cli("/bin/lark-cli", "docs", "+fetch", "--doc", "x")
        self.assertEqual(out["error"]["type"], "network")
        self.assertEqual(out["error"]["subtype"], "timeout")
        self.assertFalse(out["ok"])

    def test_stderr_permission_envelope_keeps_detail(self):
        with mock.patch.object(feishu_sync.subprocess, "run",
                               return_value=self.fake_proc(
                                   stderr='{"ok": false, "error": {"type": "permission", "code": 99991672, "detail": "bot 无文档写权限"}}', rc=1)):
            out = feishu_sync.run_cli("/bin/lark-cli", "docs", "+create")
        self.assertEqual(out["error"]["type"], "permission")
        self.assertEqual(out["error"]["code"], 99991672)

    def test_unparseable_output_is_bad_output(self):
        with mock.patch.object(feishu_sync.subprocess, "run",
                               return_value=self.fake_proc(stdout="not json", stderr="also not json", rc=1)):
            out = feishu_sync.run_cli("/bin/lark-cli", "docs", "+search")
        self.assertEqual(out["error"]["type"], "cli")
        self.assertEqual(out["error"]["subtype"], "bad_output")

    def test_explicit_ok_false_becomes_error(self):
        # ok=false 但没有 error 字段：不能当成功
        with mock.patch.object(feishu_sync.subprocess, "run",
                               return_value=self.fake_proc(stdout='{"ok": false}', rc=0)):
            out = feishu_sync.run_cli("/bin/lark-cli", "docs", "+search")
        self.assertIn("error", out)
        self.assertFalse(out["ok"])

    def test_stdout_success_envelope(self):
        with mock.patch.object(feishu_sync.subprocess, "run",
                               return_value=self.fake_proc(stdout='{"ok": true, "data": {"x": 1}}', rc=0)):
            out = feishu_sync.run_cli("/bin/lark-cli", "docs", "+search")
        self.assertNotIn("error", out)
        self.assertTrue(out["ok"])
        self.assertEqual(out["data"], {"x": 1})


class BusinessResultTest(Base):
    """评审 P1-3：只有业务完整成功且拿到必需 ID 才记同步成功。"""

    def test_overwrite_partial_success_not_updated(self):
        payload = cli_ok({"data": {"result": "partial_success", "warnings": ["failed to write blocks"]}})
        with mock.patch.object(feishu_sync, "run_cli", return_value=payload):
            r = feishu_sync._overwrite("/bin/lark-cli", "doc1", self.work / "x.md")
        self.assertNotEqual(r["action"], "updated")
        self.assertEqual(r["action"], "retry")  # 写入不完整，幂等可重试

    def test_overwrite_business_failed_not_updated(self):
        payload = cli_ok({"data": {"result": "failed", "warnings": ["permission denied on block"]}})
        with mock.patch.object(feishu_sync, "run_cli", return_value=payload):
            r = feishu_sync._overwrite("/bin/lark-cli", "doc1", self.work / "x.md")
        self.assertNotEqual(r["action"], "updated")

    def test_overwrite_success(self):
        payload = cli_ok({"data": {"result": "success", "warnings": []}})
        with mock.patch.object(feishu_sync, "run_cli", return_value=payload):
            r = feishu_sync._overwrite("/bin/lark-cli", "doc1", self.work / "x.md")
        self.assertEqual(r, {"action": "updated", "document_id": "doc1"})

    def test_create_requires_document_id(self):
        payload = cli_ok({"data": {"document": {"url": "u"}}})  # 缺 document_id
        with mock.patch.object(feishu_sync, "run_cli", return_value=payload):
            r = feishu_sync._create("/bin/lark-cli", "t", self.work / "x.md", "")
        self.assertEqual(r["action"], "failed")
        self.assertEqual(r["error"]["subtype"], "no_document_id")

    def test_create_network_error_is_unknown(self):
        with mock.patch.object(feishu_sync, "run_cli", return_value=cli_err("network", "timeout")):
            r = feishu_sync._create("/bin/lark-cli", "t", self.work / "x.md", "")
        self.assertEqual(r["action"], "unknown")  # 结果不明，供下次补交付收敛

    def test_create_business_error_is_failed(self):
        with mock.patch.object(feishu_sync, "run_cli", return_value=cli_err("permission", "forbidden")):
            r = feishu_sync._create("/bin/lark-cli", "t", self.work / "x.md", "")
        self.assertEqual(r["action"], "failed")


class SearchCandidatesTest(unittest.TestCase):
    def test_filters_and_strips_highlight(self):
        payload = search_json([
            (f"AI 周报 · <h>{WEEK}</h>（11/2–11/8）", "docA", "DOCX"),
            (f"AI 周报 · {WEEK} 的多维表格", "baseB", "BITABLE"),   # 非 DOCX 排除
            ("无关文档", "docC", "DOCX"),                              # 无栏目排除
            (f"关于 AI 周报 · {WEEK} 的问题汇总", "docD", "DOCX"),     # 评审 P1-2：非周报正文排除
        ])
        with mock.patch.object(feishu_sync, "run_cli", return_value=cli_ok(payload)):
            cands = feishu_sync.search_candidates("/bin/lark-cli", WEEK, test=False)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["token"], "docA")
        self.assertNotIn("<h>", cands[0]["title"])

    def test_search_error_returns_none(self):
        with mock.patch.object(feishu_sync, "run_cli", return_value=cli_err()):
            self.assertIsNone(feishu_sync.search_candidates("/bin/lark-cli", WEEK, test=False))

    def paged(self, pages):
        """pages: {page_token(首页为 None): payload}"""
        def fake_run(cli, *args, **kw):
            tok = args[args.index("--page-token") + 1] if "--page-token" in args else None
            return cli_ok(pages[tok])
        return fake_run

    def test_target_on_second_page_found(self):
        # 评审 P1-2：首页无候选但第二页有目标——不翻页会重复 create
        p1 = {"data": {"results": [], "has_more": True, "page_token": "t2"}}
        p2 = search_json([(f"AI 周报 · {WEEK}", "docP2", "DOCX")])
        with mock.patch.object(feishu_sync, "run_cli", side_effect=self.paged({None: p1, "t2": p2})):
            cands = feishu_sync.search_candidates("/bin/lark-cli", WEEK, test=False)
        self.assertEqual([c["token"] for c in cands], ["docP2"])

    def test_cross_page_two_candidates_collected(self):
        # 评审 P1-2：跨页两篇同周文档——不翻页不会报歧义
        p1 = search_json([(f"AI 周报 · {WEEK}", "docA", "DOCX")])
        p1["data"]["has_more"] = True
        p1["data"]["page_token"] = "t2"
        p2 = search_json([(f"AI 周报 · {WEEK}（回溯版）", "docB", "DOCX")])
        with mock.patch.object(feishu_sync, "run_cli", side_effect=self.paged({None: p1, "t2": p2})):
            cands = feishu_sync.search_candidates("/bin/lark-cli", WEEK, test=False)
        self.assertEqual(len(cands), 2)


class NotifyTest(Base):
    def setUp(self):
        super().setUp()
        (self.work / feishu_sync.MODE_FILE).write_text(json.dumps({"mode": "full"}), encoding="utf-8")
        self.note = self.work / "notification.txt"
        self.note.write_text("【AI周报 W45】测试。", encoding="utf-8")
        self.cfg = mock.patch.object(feishu_sync, "cfg_load",
                                     return_value={"enabled": True, "notify": {"user_open_id": "ou_x"}})
        self.cfg.start()
        self.addCleanup(self.cfg.stop)
        self.cli = mock.patch.object(feishu_sync, "find_cli", return_value="/bin/lark-cli")
        self.cli.start()
        self.addCleanup(self.cli.stop)
        # notify 每次现场刷新 preflight：默认双身份可用
        self.auth = mock.patch.object(feishu_sync, "_auth_status", return_value=auth_json())
        self.auth.start()
        self.addCleanup(self.auth.stop)

    def run_notify(self, fallback=None):
        args = types.SimpleNamespace(file=str(self.note), fallback_file=fallback)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = feishu_sync.cmd_notify(args)
        return code, buf.getvalue()

    def test_send_ok(self):
        sent = []
        def fake_run(cli, *a, **k):
            sent.append(a)
            return {"ok": True}
        with mock.patch.object(feishu_sync, "run_cli", side_effect=fake_run):
            code, out = self.run_notify()
        self.assertEqual(code, 0)
        self.assertIn("NOTIFY=sent", out)
        args = sent[0]
        self.assertIn("--as", args)
        self.assertIn("bot", args)
        self.assertIn("ou_x", args)
        key = args[args.index("--idempotency-key") + 1]
        self.assertTrue(key.startswith(f"ai-weekly-{WEEK}-"))

    def test_fallback_on_business_failure(self):
        # 确定拒绝（业务/权限类）：首条未发出，可安全换键发精简版
        fb = self.work / "fallback.txt"
        fb.write_text("精简版", encoding="utf-8")
        calls = []
        def fake_run(cli, *a, **k):
            calls.append(a)
            return cli_err("permission", "forbidden") if len(calls) == 1 else {"ok": True}
        with mock.patch.object(feishu_sync, "run_cli", side_effect=fake_run):
            code, out = self.run_notify(fallback=str(fb))
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 2)
        self.assertTrue(any(f"@{fb}" == a for a in calls[1]))

    def test_network_unknown_retries_same_key(self):
        # 评审 P2-6：网络超时结果不明（首条可能已送达），必须用同一幂等键重试，
        # 不得换键 fallback（会双发）
        fb = self.work / "fallback.txt"
        fb.write_text("精简版", encoding="utf-8")
        keys = []
        def fake_run(cli, *a, **k):
            keys.append(a[a.index("--idempotency-key") + 1])
            return cli_err("network", "timeout") if len(keys) == 1 else {"ok": True}
        with mock.patch.object(feishu_sync, "run_cli", side_effect=fake_run):
            code, out = self.run_notify(fallback=str(fb))
        self.assertEqual(code, 0)
        self.assertIn("NOTIFY=sent", out)
        self.assertEqual(len(keys), 2)
        self.assertEqual(keys[0], keys[1])  # 同键重试，服务端按幂等键去重

    def test_network_unknown_twice_reports_unknown(self):
        keys = []
        def fake_run(cli, *a, **k):
            keys.append(a[a.index("--idempotency-key") + 1])
            return cli_err("network", "timeout")
        with mock.patch.object(feishu_sync, "run_cli", side_effect=fake_run):
            code, out = self.run_notify()
        self.assertEqual(code, 1)
        self.assertIn("NOTIFY=unknown", out)
        self.assertIn("FEISHU_NOTIFY_UNKNOWN", out)
        self.assertEqual(len(keys), 2)
        self.assertEqual(keys[0], keys[1])

    def test_skipped_in_no_notify_mode(self):
        # 现场 preflight 判定 bot 不可用 → no_notify 跳过
        with mock.patch.object(feishu_sync, "_auth_status", return_value=auth_json(bot=False)):
            code, out = self.run_notify()
        self.assertEqual(code, 0)
        self.assertIn("NOTIFY=skipped mode=no_notify", out)

    def test_skipped_in_test_mode(self):
        # 脚本级隔离：TEST_RUN=1 不调 lark-cli，防止测试通知误发
        os.environ["TEST_RUN"] = "1"
        with mock.patch.object(feishu_sync, "run_cli",
                               side_effect=AssertionError("测试模式不应调 lark-cli")):
            code, out = self.run_notify()
        self.assertEqual(code, 0)
        self.assertIn("NOTIFY=skipped test=1", out)

    def test_skipped_by_coord_test_flag(self):
        # 评审 P1-1 最小反例：coord.json test=true、环境未导出 TEST_RUN，notify 不得发送
        (self.work / "coord.json").write_text(json.dumps({"test": True}), encoding="utf-8")
        with mock.patch.object(feishu_sync, "run_cli",
                               side_effect=AssertionError("coord 测试标记下不应调 lark-cli")):
            code, out = self.run_notify()
        self.assertEqual(code, 0)
        self.assertIn("NOTIFY=skipped test=1", out)


if __name__ == "__main__":
    unittest.main()
