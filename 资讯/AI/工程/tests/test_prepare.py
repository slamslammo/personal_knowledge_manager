"""段 A prepare.py 的离线用例：mock 子进程，不触网不跑真实脚本。"""
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

import prepare  # noqa: E402


def done(stdout="", rc=0):
    return subprocess.CompletedProcess([], rc, stdout=stdout, stderr="")


class PrepareTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = pathlib.Path(self.tmp.name)
        self.calls = []
        self.responses = {}

    def runner(self, *a, **kw):
        script = pathlib.Path(a[0][1]).name
        self.calls.append((script, a[0][2:]))
        if script in self.responses:
            value = self.responses[script]
            if isinstance(value, list):
                return value.pop(0) if len(value) > 1 else value[0]
            return value
        return done()

    def run_prepare(self, *extra):
        argv = ["prepare.py"] + list(extra)
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(prepare.paths, "work_dir", return_value=self.work), \
             mock.patch.object(prepare.subprocess, "run", side_effect=self.runner), \
             mock.patch.object(prepare.time, "sleep", lambda *_: None), \
             redirect_stdout(buf):
            rc = prepare.main()
        return rc, buf.getvalue().strip()

    def base_responses(self):
        return {
            "weeks.py": done("WEEK=2026-W43\nOUT_REPORT=out/report.md\n"),
            "deployment.py": [done("RUN_MODE=production\n"), done("ACTION=run\n")],
            "collect_all.py": done("COLLECT=ok\n"),
        }

    def test_ok_emits_prepare_ok_and_skips_manual_commands(self):
        self.responses = self.base_responses()
        rc, out = self.run_prepare()
        self.assertEqual(rc, 0)
        self.assertIn("PREPARE=ok", out)
        self.assertIn("WEEK=2026-W43", out)
        scripts = [s for s, _ in self.calls]
        self.assertIn("workdir.py", scripts)
        self.assertIn("env_check.py", scripts)
        self.assertIn("collect_all.py", scripts)
        self.assertNotIn("draft.py", scripts)   # 写作仍属智能段
        self.assertTrue((self.work / "week.json").exists())

    def test_action_exit_does_not_collect(self):
        self.responses = self.base_responses()
        self.responses["deployment.py"] = [done("RUN_MODE=production\n"), done("ACTION=exit\n")]
        rc, out = self.run_prepare()
        self.assertEqual(rc, 0)
        self.assertIn("PREPARE=deferred", out)
        self.assertIn("ACTION_EXIT", out)
        self.assertNotIn("collect_all.py", [s for s, _ in self.calls])

    def test_resume_completed_stops_early(self):
        (self.work / "coord.json").write_text(json.dumps({"week": "2026-W43"}), encoding="utf-8")
        self.responses = {"deployment.py": done("RESUME=completed\n")}
        rc, out = self.run_prepare()
        self.assertEqual(rc, 0)
        self.assertIn("PREPARE=resumed", out)
        self.assertEqual([s for s, _ in self.calls], ["deployment.py"])

    def test_trendshift_retry_then_ok(self):
        self.responses = self.base_responses()
        self.responses["collect_all.py"] = [
            done("COLLECT=trendshift_not_ready\n"), done("COLLECT=ok\n")]
        rc, out = self.run_prepare()
        self.assertEqual(rc, 0)
        self.assertIn("PREPARE=ok", out)
        self.assertEqual(len([s for s, _ in self.calls if s == "collect_all.py"]), 2)

    def test_retry_exhausted_fails(self):
        self.responses = self.base_responses()
        self.responses["collect_all.py"] = done("COLLECT=trendshift_not_ready\n")
        rc, out = self.run_prepare("--collect-retries", "1")
        self.assertEqual(rc, 1)
        self.assertIn("PREPARE=failed", out)
        self.assertIn("COLLECT_TRENDSHIFT_NOT_READY", out)

    def test_env_step_failure_reports_step(self):
        self.responses = {"workdir.py": done("boom", rc=1)}
        rc, out = self.run_prepare()
        self.assertEqual(rc, 1)
        self.assertIn("PREPARE=failed", out)
        self.assertIn("PREPARE_ENV_FAILED", out)


if __name__ == "__main__":
    unittest.main()
