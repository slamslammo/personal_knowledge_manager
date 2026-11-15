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
        self.assertEqual(env.get("LARK_CLI_NO_PROXY"), "1")

    def test_alive_loopback_kept(self):
        env, removed = self.adapt({"HTTPS_PROXY": "http://127.0.0.1:7890"}, listening={"127.0.0.1"})
        self.assertEqual(removed, [])
        self.assertEqual(env["HTTPS_PROXY"], "http://127.0.0.1:7890")
        self.assertNotIn("LARK_CLI_NO_PROXY", env)

    def test_non_loopback_kept_even_if_unreachable(self):
        # 云端真实代理是远端主机：一次探测失败不能作为清除依据（评审修正点 4）
        env, removed = self.adapt({"HTTPS_PROXY": "http://proxy.corp.internal:8080"}, listening=set())
        self.assertEqual(removed, [])
        self.assertIn("HTTPS_PROXY", env)

    def test_no_proxy_vars(self):
        env, removed = self.adapt({}, listening=set())
        self.assertEqual(removed, [])
        self.assertNotIn("LARK_CLI_NO_PROXY", env)


class TitleMatchTest(unittest.TestCase):
    def test_h1_with_middle_dot_matches(self):
        # 真实 H1：「AI 周报 · 2026-W45（11/2–11/8）」，前缀匹配会漏（评审修正点 1）
        self.assertTrue(feishu_sync.title_matches(H1, WEEK, test=False))
        self.assertTrue(feishu_sync.title_matches(f"AI 周报 · {WEEK}（11/2–11/8）（回溯版）", WEEK, test=False))

    def test_other_week_rejected(self):
        self.assertFalse(feishu_sync.title_matches(H1, "2026-W46", test=False))
        self.assertFalse(feishu_sync.title_matches("随便一个文档", WEEK, test=False))

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
        (self.work / feishu_sync.MODE_FILE).write_text(json.dumps({"mode": "no_doc"}), encoding="utf-8")
        code, out = self.run_sync()
        self.assertEqual(code, 0)
        self.assertIn("SYNC=skipped", out)

    def test_search_failure_retried_then_error(self):
        calls = []
        def fake_search(cli, week, test):
            calls.append(1)
            return None
        with mock.patch.object(feishu_sync, "search_candidates", side_effect=fake_search):
            code, out = self.run_sync()
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), feishu_sync.MAX_ATTEMPTS)

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
        with mock.patch.object(feishu_sync, "_doc_exists", return_value=True), \
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
        # 缓存文档被人为删除：fetch 不到，回退搜索路径
        self.write_cache()
        with mock.patch.object(feishu_sync, "_doc_exists", return_value=False), \
             self.candidates([{"token": "doc9", "title": H1, "url": "u"}]), \
             mock.patch.object(feishu_sync, "_overwrite",
                               return_value={"action": "updated", "document_id": "doc9"}) as ow:
            code, out = self.run_sync()
        self.assertEqual(code, 0)
        self.assertIn("SYNC=updated", out)

    def test_cached_result_ignores_mismatch(self):
        self.write_cache(week="2026-W44")
        self.assertIsNone(feishu_sync._cached_result(WEEK, test=False))
        self.write_cache(test=True)
        self.assertIsNone(feishu_sync._cached_result(WEEK, test=False))
        self.assertIsNone(feishu_sync._cached_result("2026-W44", test=False))


class SearchCandidatesTest(unittest.TestCase):
    def test_filters_and_strips_highlight(self):
        payload = search_json([
            (f"AI 周报 · <h>{WEEK}</h>（11/2–11/8）", "docA", "DOCX"),
            (f"AI 周报 · {WEEK} 的多维表格", "baseB", "BITABLE"),   # 非 DOCX 排除
            ("无关文档", "docC", "DOCX"),                              # 无栏目+周编号排除
        ])
        with mock.patch.object(feishu_sync, "run_cli", return_value=cli_ok(payload)):
            cands = feishu_sync.search_candidates("/bin/lark-cli", WEEK, test=False)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["token"], "docA")
        self.assertNotIn("<h>", cands[0]["title"])

    def test_search_error_returns_none(self):
        with mock.patch.object(feishu_sync, "run_cli", return_value=cli_err()):
            self.assertIsNone(feishu_sync.search_candidates("/bin/lark-cli", WEEK, test=False))


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

    def test_fallback_on_failure(self):
        fb = self.work / "fallback.txt"
        fb.write_text("精简版", encoding="utf-8")
        calls = []
        def fake_run(cli, *a, **k):
            calls.append(a)
            return cli_err() if len(calls) == 1 else {"ok": True}
        with mock.patch.object(feishu_sync, "run_cli", side_effect=fake_run):
            code, out = self.run_notify(fallback=str(fb))
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 2)
        self.assertTrue(any(f"@{fb}" == a for a in calls[1]))

    def test_skipped_in_no_notify_mode(self):
        (self.work / feishu_sync.MODE_FILE).write_text(json.dumps({"mode": "no_notify"}), encoding="utf-8")
        code, out = self.run_notify()
        self.assertEqual(code, 0)
        self.assertIn("NOTIFY=skipped", out)

    def test_skipped_in_test_mode(self):
        # 脚本级隔离：TEST_RUN=1 不调 lark-cli，防止测试通知误发
        os.environ["TEST_RUN"] = "1"
        with mock.patch.object(feishu_sync, "run_cli",
                               side_effect=AssertionError("测试模式不应调 lark-cli")):
            code, out = self.run_notify()
        self.assertEqual(code, 0)
        self.assertIn("NOTIFY=skipped test=1", out)


if __name__ == "__main__":
    unittest.main()
