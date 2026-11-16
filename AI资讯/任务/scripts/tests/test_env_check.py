"""env_check.py 的测试：mock 命令与 lark-cli，不触网、不真的推送。

覆盖：C0–C8 各项的 PASS/MISSING/NEEDS_HUMAN/FAIL 判定，与总结行
ENV=ok / missing / needs_human / fail 的分流和退出码。
"""
import pathlib
import subprocess
import sys
import types
import unittest
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import env_check  # noqa: E402


def item(status, name="x", detail=""):
    return (status, name, detail)


def proc(stdout="", stderr="", rc=0):
    return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=rc)


class PythonCheckTest(unittest.TestCase):
    def test_pass(self):
        status, name, detail = env_check.check_python()
        self.assertEqual(status, "PASS")
        self.assertIn("3.", detail)

    def test_missing_yaml(self):
        with mock.patch.dict(sys.modules, {"yaml": None}):
            status, name, detail = env_check.check_python()
        self.assertEqual(status, "MISSING")
        self.assertEqual(name, "PyYAML")


class GitCheckTest(unittest.TestCase):
    def sh_side(self, outputs):
        return lambda *a, **k: outputs.pop(0)

    def test_git_missing(self):
        with mock.patch.object(env_check, "sh", side_effect=[(127, "")]):
            self.assertEqual(env_check.check_git()[0], "MISSING")

    def test_pass(self):
        with mock.patch.object(env_check, "sh", side_effect=[(0, "git version 2.45"), (0, "")]):
            status, name, _ = env_check.check_git()
        self.assertEqual(status, "PASS")

    def test_no_credential_needs_human(self):
        with mock.patch.object(env_check, "sh", side_effect=[
                (0, "git version 2.45"),
                (128, "fatal: could not read Username for 'https://github.com'")]):
            status, name, _ = env_check.check_git()
        self.assertEqual(status, "NEEDS_HUMAN")
        self.assertEqual(name, "git推送凭据")

    def test_network_fail(self):
        with mock.patch.object(env_check, "sh", side_effect=[
                (0, "git version 2.45"), (128, "fatal: unable to access: connection timed out")]):
            status, name, _ = env_check.check_git()
        self.assertEqual(status, "FAIL")


class NodeCliCheckTest(unittest.TestCase):
    def test_node_missing(self):
        with mock.patch.object(env_check, "sh", return_value=(127, "")):
            status, name, _ = env_check.check_node()
        self.assertEqual((status, name), ("MISSING", "Node.js"))

    def test_node_too_old(self):
        with mock.patch.object(env_check, "sh", return_value=(0, "v16.20.0")):
            status, name, _ = env_check.check_node()
        self.assertEqual((status, name), ("MISSING", "Node.js"))

    def test_node_pass(self):
        with mock.patch.object(env_check, "sh", return_value=(0, "v22.22.2")):
            status, name, _ = env_check.check_node()
        self.assertEqual(status, "PASS")

    def test_cli_not_found(self):
        with mock.patch.object(env_check.feishu_sync, "cfg_load", return_value={}), \
             mock.patch.object(env_check.feishu_sync, "find_cli", return_value=None):
            status, name, _ = env_check.check_cli()
        self.assertEqual((status, name), ("MISSING", "lark-cli"))

    def test_cli_pass_ignores_node_warning(self):
        with mock.patch.object(env_check.feishu_sync, "cfg_load", return_value={}), \
             mock.patch.object(env_check.feishu_sync, "find_cli", return_value="/bin/lark-cli"), \
             mock.patch.object(env_check, "sh", return_value=(0, "lark-cli version 1.0.100\nwarning noise")):
            status, name, detail = env_check.check_cli()
        self.assertEqual(status, "PASS")
        self.assertNotIn("warning", detail)


class BindingIdentityCheckTest(unittest.TestCase):
    def test_binding_pass(self):
        with mock.patch.object(env_check.feishu_sync, "run_cli",
                               return_value={"ok": True, "data": {"app_id": env_check.APP_ID}}):
            status, name, _ = env_check.check_binding(True, "/bin/lark-cli")
        self.assertEqual(status, "PASS")

    def test_binding_wrong_app(self):
        with mock.patch.object(env_check.feishu_sync, "run_cli",
                               return_value={"ok": True, "data": {"app_id": "cli_other"}}):
            status, name, _ = env_check.check_binding(True, "/bin/lark-cli")
        self.assertEqual(status, "NEEDS_HUMAN")

    def test_binding_cli_missing(self):
        status, name, _ = env_check.check_binding(False, None)
        self.assertEqual(status, "MISSING")

    def identities(self, bot, user, err=None):
        st = {"error": err} if err else {"identities": {
            "bot": {"available": bot}, "user": {"available": user}}}
        return mock.patch.object(env_check.feishu_sync, "_auth_status", return_value=st)

    def test_identities_pass(self):
        with self.identities(True, True):
            bot, user = env_check.check_identities(True, "/bin/lark-cli")
        self.assertEqual((bot[0], user[0]), ("PASS", "PASS"))

    def test_user_needs_device_flow(self):
        with self.identities(True, False):
            bot, user = env_check.check_identities(True, "/bin/lark-cli")
        self.assertEqual((bot[0], user[0]), ("PASS", "NEEDS_HUMAN"))
        self.assertIn("auth login", user[2])

    def test_identities_cli_missing(self):
        bot, user = env_check.check_identities(False, None)
        self.assertEqual((bot[0], user[0]), ("MISSING", "MISSING"))

    def test_identities_auth_error(self):
        with self.identities(None, None, err={"type": "network", "detail": "x"}):
            bot, user = env_check.check_identities(True, "/bin/lark-cli")
        self.assertEqual((bot[0], user[0]), ("FAIL", "FAIL"))


class OutboundCheckTest(unittest.TestCase):
    def preflight(self, out="PREFLIGHT=ok"):
        return mock.patch.object(env_check.subprocess, "run",
                                 return_value=proc(stdout=out))

    def test_cli_missing(self):
        status, name, _ = env_check.check_outbound(False)
        self.assertEqual(status, "MISSING")

    def test_preflight_ok(self):
        with self.preflight():
            status, name, _ = env_check.check_outbound(True)
        self.assertEqual(status, "PASS")

    def test_preflight_degraded(self):
        with self.preflight(out="PREFLIGHT=degraded:off CODE=FEISHU_UNREACHABLE"):
            status, name, _ = env_check.check_outbound(True)
        self.assertEqual(status, "FAIL")


class RunChecksTest(unittest.TestCase):
    def patch_all(self, **kw):
        defaults = {"python": item("PASS"), "git": item("PASS"), "node": item("PASS"),
                    "cli": item("PASS"), "binding": item("PASS"),
                    "bot": item("PASS"), "user": item("PASS"), "outbound": item("PASS")}
        defaults.update(kw)
        return [mock.patch.object(env_check, "check_python", return_value=defaults["python"]),
                mock.patch.object(env_check, "check_git", return_value=defaults["git"]),
                mock.patch.object(env_check, "check_node", return_value=defaults["node"]),
                mock.patch.object(env_check, "check_cli", return_value=defaults["cli"]),
                mock.patch.object(env_check, "check_binding", return_value=defaults["binding"]),
                mock.patch.object(env_check, "check_identities",
                                  return_value=(defaults["bot"], defaults["user"])),
                mock.patch.object(env_check, "check_outbound", return_value=defaults["outbound"]),
                mock.patch.object(env_check.feishu_sync, "cfg_load", return_value={}),
                mock.patch.object(env_check.feishu_sync, "find_cli", return_value=None)]

    def run_with(self, **kw):
        patches = self.patch_all(**kw)
        for p in patches:
            p.start()
        try:
            return env_check.run_checks()
        finally:
            for p in patches:
                p.stop()

    def test_all_pass(self):
        results, summary, code = self.run_with()
        self.assertEqual(summary, "ENV=ok")
        self.assertEqual(code, 0)
        self.assertEqual(len(results), 10)  # 8 项检查 + 2 个 MANUAL

    def test_missing_first_in_summary(self):
        results, summary, code = self.run_with(
            cli=item("MISSING", "lark-cli"), git=item("NEEDS_HUMAN", "git推送凭据"))
        self.assertEqual(summary, "ENV=missing:lark-cli")
        self.assertEqual(code, 1)

    def test_needs_human(self):
        results, summary, code = self.run_with(git=item("NEEDS_HUMAN", "git推送凭据"),
                                               user=item("NEEDS_HUMAN", "user身份"))
        self.assertEqual(summary, "ENV=needs_human:git推送凭据,user身份")
        self.assertEqual(code, 1)

    def test_fail(self):
        results, summary, code = self.run_with(outbound=item("FAIL", "飞书出站", "timeout"))
        self.assertEqual(summary, "ENV=fail:飞书出站")
        self.assertEqual(code, 1)


class EnsureMarkerTest(unittest.TestCase):
    """就绪标记：fast path、全量检查写标记、不通过不写、版本落后触发重验。"""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.marker = pathlib.Path(self.tmp.name) / "env.json"
        patcher = mock.patch.object(env_check, "MARKER", self.marker)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_marker(self, version=env_check.ENV_VERSION, status="ok"):
        import json
        self.marker.write_text(json.dumps({"env_version": version, "status": status,
                                           "checked_at": "t"}), encoding="utf-8")

    def ok_checks(self, **kw):
        results = [item("PASS")] * 8 + env_check.MANUAL_ITEMS
        return mock.patch.object(env_check, "run_checks",
                                 return_value=(results, "ENV=ok", 0))

    def test_valid_marker_short_circuits(self):
        self.write_marker()
        with mock.patch.object(env_check, "run_checks",
                              side_effect=AssertionError("标记有效不应重查")):
            code = env_check.cmd_ensure()
        self.assertEqual(code, 0)

    def test_missing_marker_runs_checks_and_writes(self):
        with self.ok_checks():
            code = env_check.cmd_ensure()
        self.assertEqual(code, 0)
        import json
        d = json.loads(self.marker.read_text(encoding="utf-8"))
        self.assertEqual(d["env_version"], env_check.ENV_VERSION)
        self.assertEqual(d["status"], "ok")

    def test_failed_checks_do_not_write_marker(self):
        results = [item("MISSING", "lark-cli")] + [item("PASS")] * 7 + env_check.MANUAL_ITEMS
        with mock.patch.object(env_check, "run_checks",
                               return_value=(results, "ENV=missing:lark-cli", 1)):
            code = env_check.cmd_ensure()
        self.assertEqual(code, 1)
        self.assertFalse(self.marker.exists())

    def test_version_mismatch_triggers_recheck(self):
        self.write_marker(version=env_check.ENV_VERSION - 1)
        with self.ok_checks():
            code = env_check.cmd_ensure()
        self.assertEqual(code, 0)
        import json
        self.assertEqual(json.loads(self.marker.read_text(encoding="utf-8"))["env_version"],
                         env_check.ENV_VERSION)

    def test_reset_deletes_marker(self):
        self.write_marker()
        self.assertEqual(env_check.cmd_reset(), 0)
        self.assertFalse(self.marker.exists())

    def test_main_dispatch(self):
        self.assertEqual(env_check.main(["reset"]), 0)
        self.assertEqual(env_check.main(["bogus"]), 2)


if __name__ == "__main__":
    unittest.main()
