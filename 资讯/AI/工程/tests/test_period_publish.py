import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

CORE = pathlib.Path(__file__).resolve().parents[1] / "core"
sys.path.insert(0, str(CORE))
import annual_index
import coord
import paths
import period_report as pr


class PeriodPublication(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.work = self.root / "work"
        self.work.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "test")
        self.git("config", "user.email", "test@example.invalid")
        self.period = "2025-Q1"
        for n in range(1, 4):
            file = self.repo / paths.monthly(2025, n)
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(f"---\nmonth: 2025-{n:02}\nquality: full\ncoverage: {{正文: 4周}}\n---\n\n月报\n")
        self.git("add", ".")
        self.git("commit", "-qm", "种子报告")
        remote = coord.setup_sandbox(self.repo, self.work, "main")
        self.ctx = SimpleNamespace(repo=self.repo, remote=remote, branch="main", work=self.work, test=True)
        self.tip = coord.remote_tip(self.ctx)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args])

    def test_quarter_publishes_only_requested_path_then_reuses_blob(self):
        m = pr.prepare(self.ctx, self.period, self.tip)
        self.assertEqual(m["board_weeks"], 0)
        self.assertEqual(len(m["reports"]), 3)
        body = (f"<!-- source: {self.tip} -->\n## 季度主线\n- 第一条有证据的结论 [来源](https://example.org/a)\n"
                "- 第二条有证据的结论\n## 重点发布与技术方向\n有据可查。\n## 开源与产业趋势\n"
                "<!-- period-board -->\n## 回看上季判断\n首期。\n## 下一季度观察点\n跟踪进展。")
        (self.work / "body.md").write_text(body)
        sha = pr.publish(self.ctx, self.period, self.tip)
        self.assertEqual(self.git("diff", "--name-only", "-z", self.tip, sha).decode(),
                         paths.quarterly(2025, 1) + "\0")
        self.assertEqual(pr.publish(self.ctx, self.period, sha), sha)
        self.assertEqual(self.git("rev-parse", "HEAD").decode().strip(), self.tip)
        with mock.patch.object(subprocess, "run", wraps=subprocess.run) as sub:
            self.assertTrue(pr.deliver(self.ctx, self.period, sha))
            self.assertFalse(any("lark-cli" in str(c) for c in sub.call_args_list))

    def test_missing_month_blocks(self):
        with self.assertRaisesRegex(ValueError, "缺少已发布报告"):
            pr.prepare(self.ctx, "2025-Q2", self.tip)

    def test_week_context_rejects_cross_period(self):
        with self.assertRaises(ValueError):
            coord.weekly_paths(dict(week="2026-W46", report_path=paths.monthly(2026, 10),
                                    data_path=paths.data("2026-W46")))

    def test_index_preview_never_calls_feishu(self):
        with mock.patch.dict(os.environ, TEST_RUN="1"), mock.patch.object(annual_index, "sync") as sync, \
             mock.patch.object(sys, "argv", ["annual_index.py", "--period", self.period, "--sha", self.tip]):
            self.assertEqual(annual_index.main(), 0)
            sync.assert_not_called()

    def test_config_missing_clears_pending_for_later_retry(self):
        """发送前确定性失败（缺 CLI/接收人）不应留下 pending 阻塞补配置后的重试。"""
        sha = self.tip
        self.ctx.test = False  # 走正式分支才会尝试发通知
        pending = self.work / "notification-pending.json"
        seed = self.repo / paths.monthly(2025, 1)
        seed.write_text(seed.read_text(encoding="utf-8").replace("coverage: {正文: 4周}",
                        "coverage: {正文: 4周, 榜单: 0周}").replace("\n月报\n",
                        "\n## 月度主线\n- 第一条有证据的结论 [来源](https://example.org/a)\n- 第二条有证据的结论\n"), encoding="utf-8")
        (self.work / "notification.txt").write_text("通知", encoding="utf-8")
        def fake_run(argv, **kw):
            out = "NOTIFY=error CODE=FEISHU_CONFIG_MISSING\n"
            return subprocess.CompletedProcess(argv, 1, out, "")
        with mock.patch.object(pr.subprocess, "run", side_effect=fake_run), \
             mock.patch.object(pr.coord, "read_at", return_value=("---\nmouth: 2025-01\nmonth: 2025-01\ncoverage: {正文: 4周, 榜单: 0周}\nquality: full\nsource: abc\n---\n\n## 季度主线\n\n- 第一条有证据的结论 [来源](https://example.org/a)\n- 第二条有证据的结论\n").encode()), \
             mock.patch.object(pr, "read_json", side_effect=lambda p: json.loads(p.read_text())):
            self.assertFalse(pr.deliver(self.ctx, self.period, sha))
        self.assertFalse(pending.exists(), "配置缺失是发送前确定性失败，应清除 pending")
