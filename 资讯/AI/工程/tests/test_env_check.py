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

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent  # 工程根
for _d in ("core", "weekly"):
    if str(SCRIPTS / _d) not in sys.path:
        sys.path.insert(0, str(SCRIPTS / _d))

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

    def test_push_dry_run_has_explicit_destination(self):
        with mock.patch.object(env_check, "sh", side_effect=[(0, "git version"), (0, "")]) as run:
            env_check.check_git()
        self.assertEqual(run.call_args_list[1].args[0][-3:], ["--dry-run", "origin", "HEAD:main"])

    def test_git_error_does_not_expose_url_credentials(self):
        with mock.patch.object(env_check, "sh", side_effect=[
                (0, "git version"), (128, "remote: https://secret@github.com denied")]):
            result = env_check.check_git()
        self.assertNotIn("secret@", str(result))

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

    def test_inactive_app_occurrence_does_not_match(self):
        with mock.patch.object(env_check.feishu_sync, "run_cli", return_value={
                "appId": "cli_other", "profiles": [{"appId": env_check.APP_ID}]}):
            self.assertEqual(env_check.check_binding(True, "/bin/lark-cli")[0], "NEEDS_HUMAN")

    def test_actual_root_shape(self):
        with mock.patch.object(env_check.feishu_sync, "run_cli", return_value={
                "appId": env_check.APP_ID, "appSecret": "do-not-log"}):
            result = env_check.check_binding(True, "/bin/lark-cli")
        self.assertEqual(result[0], "PASS")
        self.assertNotIn("do-not-log", str(result))

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
    def verified(self):
        return {"verified": True, "identities": {
            name: {"available": True, "verified": True} for name in ("bot", "user")}}

    def call(self, response):
        with mock.patch.object(env_check.feishu_sync, "find_cli", return_value="/bin/lark-cli"), \
             mock.patch.object(env_check.feishu_sync, "run_cli", return_value=response) as run:
            result = env_check.check_outbound(True)
            run.assert_called_once_with("/bin/lark-cli", "auth", "status", "--verify")
            return result

    def test_cli_missing(self):
        self.assertEqual(env_check.check_outbound(False)[0], "MISSING")

    def test_verified_server_identities_pass(self):
        self.assertEqual(self.call(self.verified())[0], "PASS")

    def test_local_status_is_not_network_evidence(self):
        self.assertEqual(self.call({"identities": {"user": {"available": True}}})[0], "FAIL")

    def test_failed_identity_is_not_verified(self):
        response = self.verified()
        response["identities"]["user"]["verified"] = False
        self.assertEqual(self.call(response)[0], "FAIL")

    def test_error_detail_is_not_exposed(self):
        result = self.call({"error": {"detail": "secret-token-in-url"}})
        self.assertEqual(result[0], "FAIL")
        self.assertNotIn("secret-token-in-url", str(result))


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
        self.assertEqual(summary, "ENV=needs_human:git推送凭据")
        self.assertEqual(code, 1)

    def test_needs_human(self):
        results, summary, code = self.run_with(git=item("NEEDS_HUMAN", "git推送凭据"),
                                               user=item("NEEDS_HUMAN", "user身份"))
        self.assertEqual(summary, "ENV=needs_human:git推送凭据")
        self.assertEqual(code, 1)

    def test_fail(self):
        results, summary, code = self.run_with(outbound=item("FAIL", "飞书出站", "timeout"))
        self.assertEqual(summary, "ENV=ok")
        self.assertEqual(code, 0)
        self.assertIn("DELIVERY=degraded", env_check.delivery_summary(results))

    def test_only_user_missing_does_not_stop_git(self):
        results, summary, code = self.run_with(user=item("NEEDS_HUMAN", "user身份"))
        self.assertEqual((summary, code), ("ENV=ok", 0))
        self.assertEqual(env_check.delivery_summary(results), "DELIVERY=degraded:user身份")

    def test_missing_cli_does_not_stop_git(self):
        results, summary, code = self.run_with(cli=item("MISSING", "lark-cli"))
        self.assertEqual((summary, code), ("ENV=ok", 0))

    def test_core_python_failure_is_blocking(self):
        _, summary, code = self.run_with(python=item("FAIL", "python"))
        self.assertEqual((summary, code), ("ENV=fail:python", 1))

    def test_require_delivery_blocks_acceptance_only(self):
        rows, summary, code = self.run_with(user=item("NEEDS_HUMAN", "user身份"))
        with mock.patch.object(env_check, "run_checks", return_value=(rows, summary, code)):
            self.assertEqual(env_check.cmd_check(), 0)
            self.assertEqual(env_check.cmd_check(require_delivery=True), 1)


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

    def write_marker(self, version=env_check.ENV_VERSION, status="core_ready"):
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
        self.assertEqual(d["status"], "core_ready")
        self.assertEqual(d["acceptance"], "pending")

    def test_failed_checks_do_not_write_marker(self):
        results = [item("MISSING", "PyYAML")] + [item("PASS")] * 7 + env_check.MANUAL_ITEMS
        with mock.patch.object(env_check, "run_checks",
                               return_value=(results, "ENV=missing:PyYAML", 1)):
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

    def test_valid_marker_cannot_hide_deleted_python_dependency(self):
        self.write_marker()
        with mock.patch.object(env_check, "check_python", return_value=item("MISSING", "PyYAML")), \
             mock.patch.object(env_check, "check_git_binary", return_value=item("PASS", "git")):
            self.assertEqual(env_check.cmd_ensure(), 1)

    def test_valid_marker_cannot_hide_deleted_git(self):
        self.write_marker()
        with mock.patch.object(env_check, "check_git_binary", return_value=item("MISSING", "git")):
            self.assertEqual(env_check.cmd_ensure(), 1)

    def test_old_ok_marker_is_not_production_acceptance(self):
        self.write_marker(status="ok")
        with self.ok_checks() as checks:
            self.assertEqual(env_check.cmd_ensure(), 0)
            checks.assert_called_once()
        import json
        marker = json.loads(self.marker.read_text())
        self.assertEqual(marker["status"], "core_ready")
        self.assertEqual(marker["acceptance"], "pending")

    def test_manual_items_do_not_become_passed_in_marker(self):
        with self.ok_checks():
            env_check.cmd_ensure()
        import json
        marker = json.loads(self.marker.read_text())
        self.assertEqual(marker["acceptance"], "pending")
        self.assertNotIn("身份边界", marker["versions"])

    def test_reset_deletes_marker(self):
        self.write_marker()
        self.assertEqual(env_check.cmd_reset(), 0)
        self.assertFalse(self.marker.exists())

    def test_main_dispatch(self):
        self.assertEqual(env_check.main(["reset"]), 0)
        self.assertEqual(env_check.main(["bogus"]), 2)


if __name__ == "__main__":
    unittest.main()
