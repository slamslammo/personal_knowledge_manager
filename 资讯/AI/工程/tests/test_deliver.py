"""段 B deliver.py 的离线用例：mock 子进程，不触网不碰飞书。"""
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
for sub in ("core", "weekly"):
    p = str(SCRIPTS / sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import deliver  # noqa: E402
import paths  # noqa: E402


def done(stdout="", rc=0):
    return subprocess.CompletedProcess([], rc, stdout=stdout, stderr="")


SHA = "a" * 40


class DeliverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = pathlib.Path(self.tmp.name)
        (self.work / paths.FILES["notification"]).write_text("通知", encoding="utf-8")
        (self.work / paths.FILES["notification_short"]).write_text("精简", encoding="utf-8")
        self.ctx = {"week": "2026-W43", "run_id": "r1", "test": False,
                    "report_path": paths.report(2026, "2026-W43")}
        self.calls = []
        self.responses = {}

    def runner(self, *a, **kw):
        cmd = a[0]
        script = pathlib.Path(cmd[1]).name
        if script == "coord.py" and cmd[2] == "publish":
            self.ctx.update(published_commit=SHA, published_quality="full")
            (self.work / "coord.json").write_text(json.dumps(self.ctx))
        self.calls.append((script, cmd[2:]))
        val = self.responses.get(script)
        if isinstance(val, list):
            return val.pop(0) if len(val) > 1 else val[0]
        return val if val is not None else done()

    def run_deliver(self, *extra):
        if "--test" in extra:
            self.ctx["test"] = True
        (self.work / "coord.json").write_text(json.dumps(self.ctx))
        (self.work / "feishu.json").write_text(json.dumps({
            **self.ctx, "action": "updated", "document_id": "doc1", "url": "https://example.com/doc1"
        }))
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["deliver.py", "--week", "2026-W43", *extra]), \
             mock.patch.object(deliver.paths, "work_dir", return_value=self.work), \
             mock.patch.object(deliver.subprocess, "run", side_effect=self.runner), \
             redirect_stdout(buf):
            rc = deliver.main()
        return rc, buf.getvalue().strip()

    def ok_chain(self):
        return {
            "finalize.py": done(),
            "check_run.py": done("检查通过\n"),
            "coord.py": done(f"ACTION=published\ncommit={SHA}\n"),
            "feishu_sync.py": [done("SYNC=updated\n"), done("READBACK=passed\n"), done("NOTIFY=sent\n")],
            "workdir.py": done("ARCHIVE=ok\n"),
        }

    def test_ok_runs_full_chain(self):
        self.responses = self.ok_chain()
        rc, out = self.run_deliver()
        self.assertEqual(rc, 0, out)
        self.assertIn("DELIVER=ok", out)
        self.assertIn(SHA, out)
        scripts = [s for s, _ in self.calls]
        for s in ("finalize.py", "check_run.py", "coord.py", "feishu_sync.py", "workdir.py"):
            self.assertIn(s, scripts)
        self.assertTrue((self.work / paths.FILES["checks"]).exists())

    def test_codes_triggers_rework_without_publish(self):
        self.responses = self.ok_chain()
        self.responses["check_run.py"] = done("CODES=GATE_LINK_HOMEPAGE,GATE_SEARCH_MIN\n", rc=1)
        rc, out = self.run_deliver()
        self.assertEqual(rc, 1)
        self.assertIn("DELIVER=rework", out)
        self.assertIn("GATE_LINK_HOMEPAGE", out)
        self.assertNotIn("coord.py", [s for s, _ in self.calls])

    def test_publish_lost_generates_failure_notice(self):
        self.responses = self.ok_chain()
        self.responses["coord.py"] = done("ACTION=lost\n")
        rc, out = self.run_deliver()
        self.assertEqual(rc, 1)
        self.assertIn("PUBLISH_LOST", out)
        notice = self.work / "notification-failure.txt"
        self.assertTrue(notice.exists())
        self.assertIn("｜失败】", notice.read_text(encoding="utf-8"))

    def test_test_mode_verify_passes_doc(self):
        self.responses = self.ok_chain()
        self.responses["feishu_sync.py"] = [
            done("SYNC=updated document_id=doc1\n"), done("READBACK=passed\n"), done("NOTIFY=skipped\n")]
        rc, out = self.run_deliver("--test")
        self.assertEqual(rc, 0, out)
        verify = [a for s, a in self.calls if s == "feishu_sync.py" and "verify" in a]
        self.assertEqual(len(verify), 1)
        self.assertIn("--doc", verify[0])
        self.assertIn("doc1", verify[0])
        self.assertIn("--test-document", verify[0])

    def test_sync_error_does_not_block_delivery(self):
        self.responses = self.ok_chain()
        self.responses["feishu_sync.py"] = [done("SYNC=error\n"), done("NOTIFY=sent\n")]
        rc, out = self.run_deliver()
        self.assertEqual(rc, 1, out)
        self.assertIn("DELIVER=partial", out)
        self.assertIn("SYNC=error", out)
        self.assertIn("workdir.py", [s for s, _ in self.calls])

    def test_readback_notify_and_archive_failure_reported_separately(self):
        self.responses = self.ok_chain()
        self.responses["feishu_sync.py"] = [
            done("SYNC=updated document_id=doc1"), done("READBACK=pending", rc=1),
            done("NOTIFY=unknown", rc=1)]
        self.responses["workdir.py"] = done("disk full", rc=1)
        rc, out = self.run_deliver()
        self.assertNotEqual(rc, 0)
        self.assertIn("DELIVER=partial", out)
        self.assertIn("READBACK=pending NOTIFY=unknown ARCHIVE=error", out)
        self.assertIn("/blob/" + SHA, out)

    def test_sandbox_context_without_flag_uses_test_h1(self):
        self.ctx["test"] = True
        self.responses = self.ok_chain()
        self.responses["feishu_sync.py"][-1] = done("NOTIFY=skipped test=1")
        self.assertEqual(self.run_deliver()[0], 0)
        verify = next(args for _, args in self.calls if args and args[0] == "verify")
        self.assertIn("--test-document", verify)

    def test_rework_budget_and_structural_stop(self):
        for code, terminal in [("GATE_SEARCH_MIN", "DELIVER=ok"), ("GATE_STRUCTURE", "REWORK_EXHAUSTED")]:
            self.ctx["run_id"] = "run-" + code
            self.responses = self.ok_chain()
            self.responses["check_run.py"] = done("CODES=" + code, rc=1)
            for _ in range(3):
                self.assertIn("DELIVER=rework", self.run_deliver()[1])
            self.assertIn(terminal, self.run_deliver()[1])

    def test_manual_edit_publish_uses_receipt_sha(self):
        self.responses = self.ok_chain()
        self.responses["coord.py"] = done(f"ACTION=published\ncommit={SHA}；周报被手工修改过，未覆盖")
        self.assertEqual(self.run_deliver()[0], 0)
        sync = next(args for _, args in self.calls if args and args[0] == "sync")
        self.assertEqual(sync[sync.index("--sha") + 1], SHA)

    def test_missing_notification_files_fails_early(self):
        (self.work / paths.FILES["notification"]).unlink()
        self.responses = self.ok_chain()
        rc, out = self.run_deliver()
        self.assertEqual(rc, 1)
        self.assertIn("NOTIFY_FILE_MISSING", out)
        self.assertNotIn("finalize.py", [s for s, _ in self.calls])


class DeliveryGitIntegration(unittest.TestCase):
    def test_sync_outage_preserves_real_git_publication_and_archive(self):
        import os
        import fixture
        from test_coord import Lab

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            agent = Lab(root, week=fixture.WEEK).agent("review")
            action, started = agent.start()
            self.assertEqual(action, "run", started.stdout)
            agent.write_fixture()
            for name in ("notification", "notification_short"):
                (agent.work / paths.FILES[name]).write_text("周报摘要", encoding="utf-8")
            original = deliver.Runner.__call__

            def run(runner, script, *args):
                if script != "feishu_sync.py":
                    return original(runner, script, *args)
                if args[0] == "sync":
                    return done("SYNC=error", rc=1)
                self.assertEqual(args[0], "notify")
                return done("NOTIFY=skipped test=1")

            env = dict(agent.env(), AI_WEEKLY_HOME=str(root / "runtime"))
            buf = io.StringIO()
            with mock.patch.dict(os.environ, env), mock.patch.object(
                    sys, "argv", ["deliver.py", "--week", fixture.WEEK, "--test"]), mock.patch.object(
                    deliver.Runner, "__call__", run), redirect_stdout(buf):
                self.assertEqual(deliver.main(), 1)
            ctx = json.loads((agent.work / "coord.json").read_text())
            self.assertEqual(ctx["published_quality"], "full")
            self.assertEqual(ctx["published_commit"], agent.lab.log("%H")[0])
            archive = root / "runtime" / "archive" / fixture.WEEK / "MANIFEST.json"
            self.assertEqual(json.loads(archive.read_text())["runs"][0]["git_sha"], ctx["published_commit"])
            self.assertIn("DELIVER=partial", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
