"""段 B deliver.py 的离线用例：mock 子进程，不触网不碰飞书。"""
import io
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
        self.calls = []
        self.responses = {}

    def runner(self, *a, **kw):
        cmd = a[0]
        script = pathlib.Path(cmd[1]).name
        self.calls.append((script, cmd[2:]))
        val = self.responses.get(script)
        if isinstance(val, list):
            return val.pop(0) if len(val) > 1 else val[0]
        return val if val is not None else done()

    def run_deliver(self, *extra):
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

    def test_sync_error_does_not_block_delivery(self):
        self.responses = self.ok_chain()
        self.responses["feishu_sync.py"] = [done("SYNC=error\n"), done("NOTIFY=sent\n")]
        rc, out = self.run_deliver()
        self.assertEqual(rc, 0, out)
        self.assertIn("DELIVER=ok", out)
        self.assertIn("SYNC=error", out)
        self.assertIn("workdir.py", [s for s, _ in self.calls])

    def test_missing_notification_files_fails_early(self):
        (self.work / paths.FILES["notification"]).unlink()
        self.responses = self.ok_chain()
        rc, out = self.run_deliver()
        self.assertEqual(rc, 1)
        self.assertIn("NOTIFY_FILE_MISSING", out)
        self.assertNotIn("finalize.py", [s for s, _ in self.calls])


if __name__ == "__main__":
    unittest.main()
