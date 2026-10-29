import json
import os
import pathlib
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from check_run import check  # noqa: E402
from test_validate import DATA, REPORT  # noqa: E402
from weeks import Week  # noqa: E402

WEEK = Week.parse("2026-W43")
START = time.time() - 600  # 本次运行开始于 10 分钟前


def write(path, obj, mtime=None):
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    t = mtime if mtime is not None else START + 60
    os.utime(path, (t, t))


class CheckRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.work = self.dir / "work"
        self.work.mkdir()
        self.report = self.dir / "report.md"
        self.data = self.dir / "data.json"
        write(self.work / "week.json", {"week": "2026-W43"}, START)
        write(self.work / "trendshift.json", {"week": "2026-W43", "status": "ok", "items": [{}] * 25})
        write(self.work / "hn.json", {"week": "2026-W43", "status": "ok", "error": None})
        write(self.work / "hf.json", {"week": "2026-W43", "status": "ok", "error": None})
        write(self.work / "judgments.json", {"non_ai": [], "exclude": {}, "hn_ai_repos": []})
        write(self.work / "searches.txt", "# 用途\t查询\n" + "".join(f"发现\tq{i}\n" for i in range(12)))
        data = dict(DATA, generated_at=self._iso(START + 120))
        write(self.data, data)
        write(self.report, REPORT)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _iso(ts):
        import datetime as dt
        return dt.datetime.fromtimestamp(ts, dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")

    def run_check(self, **kw):
        return check(WEEK, self.work, self.report, self.data, **kw)

    def failed(self, **kw):
        return {s.name: s.detail for s in self.run_check(**kw) if not s.ok}

    def test_complete_run_passes(self):
        self.assertEqual(self.failed(), {})

    def test_missing_week_json_stops(self):
        (self.work / "week.json").unlink()
        steps = self.run_check()
        self.assertEqual(len(steps), 1)
        self.assertFalse(steps[0].ok)

    def test_stale_collector_output(self):
        write(self.work / "hn.json", {"week": "2026-W43", "status": "ok"}, START - 3600)
        self.assertIn("不是本次运行生成的", self.failed()["第 1 步 HN"])

    def test_failed_collector_must_be_noted(self):
        write(self.work / "hf.json", {"week": "2026-W43", "status": "failed", "error": "HTTP 500"})
        self.assertIn("数据说明没有写明", self.failed()["第 1 步 Hugging Face"])
        write(self.report, REPORT.replace("- 联网搜索", "- Hugging Face 论文：失败（HTTP 500）。\n- 联网搜索"))
        self.assertNotIn("第 1 步 Hugging Face", self.failed())

    def test_ranking_must_rerun(self):
        write(self.data, dict(DATA, generated_at=self._iso(START - 86400)))
        self.assertIn("没有重新运行", self.failed()["第 1 步 AI 判定与排名"])
        (self.work / "judgments.json").unlink()
        self.assertIn("没有 judgments.json", self.failed()["第 1 步 AI 判定与排名"])

    def test_searches_required_and_counted(self):
        (self.work / "searches.txt").unlink()
        self.assertIn("没有 searches.txt", self.failed()["第 1 步 联网搜索"])
        write(self.work / "searches.txt", "".join(f"q{i}\n" for i in range(10)))
        self.assertIn("记录了 10 次", self.failed()["第 1 步 联网搜索"])
        write(self.work / "searches.txt", "".join(f"q{i}\n" for i in range(41)))
        self.assertIn("超出上限", self.failed()["第 1 步 联网搜索"])

    def test_report_must_be_rewritten(self):
        write(self.report, REPORT, START - 3600)
        self.assertIn("第 2 步 写周报", self.failed())

    def test_validate_errors_fail(self):
        write(self.report, REPORT.replace("## ⑤ 热点话题", "## 热点"))
        self.assertIn("缺少板块", self.failed()["第 4 步 validate.py"])

    def test_trendshift_not_ready(self):
        write(self.work / "trendshift.json", {"week": "2026-W43", "status": "not_ready"})
        self.assertIn("第 1 步 Trendshift 周榜", self.failed())
        report = REPORT.replace("## ③ GitHub AI 项目热度 Top 5\n", "## ③ GitHub AI 项目热度 Top 5\n\n周榜未就绪。\n")
        write(self.report, report)
        failed = self.failed()
        self.assertNotIn("第 1 步 Trendshift 周榜", failed)
        self.assertNotIn("第 1 步 AI 判定与排名", failed)

    def test_backfill_reuse_data(self):
        for name in ("trendshift.json", "judgments.json"):
            (self.work / name).unlink()
        write(self.data, dict(DATA, generated_at=self._iso(START - 86400)))
        report = REPORT.replace("# AI 周报 · 2026-W43（10/19–10/25）", "# AI 周报 · 2026-W43（10/19–10/25）（回溯版）")
        write(self.report, report)
        self.assertIn("第 1 步 Trendshift 周榜", self.failed(backfill=True, reuse_data=True))
        write(self.report, report.replace("- 联网搜索", "- 复用已有数据文件。\n- 联网搜索"))
        self.assertEqual(self.failed(backfill=True, reuse_data=True), {})


if __name__ == "__main__":
    unittest.main()
