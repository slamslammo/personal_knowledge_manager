import json
import os
import pathlib
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import finalize  # noqa: E402
from check_run import check  # noqa: E402
from test_validate import DATA, REPORT  # noqa: E402

START = time.time() - 600  # 本次运行开始于 10 分钟前
REPORT_REL = "AI资讯/周报/2026/2026-W43.md"
DATA_REL = "AI资讯/数据/github-weekly/2026-W43.json"


def write(path, obj, mtime=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    t = mtime if mtime is not None else START + 60
    os.utime(path, (t, t))


def with_auto(report, searches):
    lines = ["- Trendshift 周榜：成功，25 项。", f"- 联网搜索：{searches} 次（下限 20，上限 40）。"]
    return finalize.apply(report.replace("- 联网搜索：12 次（上限 40）。\n", ""), lines)


class CheckRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = pathlib.Path(self.tmp.name)
        self.out = self.work / "out"
        write(self.work / "week.json", {"week": "2026-W43", "mode": "normal", "report_path": REPORT_REL,
                                        "data_path": DATA_REL}, START)
        write(self.work / "coord.json", {"week": "2026-W43", "purpose": "run", "run_id": "claude-1"})
        sources = {k: {"status": "ok"} for k in ("trendshift", "hn", "hf", "articles")}
        write(self.work / "collect_report.json", {"week": "2026-W43", "sources": sources})
        write(self.work / "materials.json", {"week": "2026-W43", "hn": {"stories": []}})
        write(self.work / "judgments.json", {"non_ai": [], "exclude": {}, "hn_ai_repos": []})
        write(self.work / "draft.json", {"degraded": False})
        self.searches(24)
        write(self.out / DATA_REL, dict(DATA, generated_at=self.iso(START + 120)))
        write(self.out / REPORT_REL, with_auto(REPORT, 24), START + 300)

    def tearDown(self):
        self.tmp.cleanup()

    def searches(self, n):
        write(self.work / "searches.txt", "".join(f"发现\tq{i}\n" for i in range(n)))

    @staticmethod
    def iso(ts):
        import datetime as dt
        return dt.datetime.fromtimestamp(ts, dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")

    def failed(self):
        return {s.name: (s.detail, s.code) for s in check(self.work, self.out) if not s.ok}

    def test_complete_run_passes(self):
        self.assertEqual(self.failed(), {})

    def test_missing_week_json_stops(self):
        (self.work / "week.json").unlink()
        steps = check(self.work, self.out)
        self.assertEqual((len(steps), steps[0].ok), (1, False))

    def test_must_hold_run_lock(self):
        write(self.work / "coord.json", {"week": "2026-W43", "purpose": "verify"})
        self.assertIn("第 0 步 准备", self.failed())

    def test_stale_collection(self):
        write(self.work / "collect_report.json", {"week": "2026-W43", "sources": {}}, START - 3600)
        detail, code = self.failed()["第 1 步 采集"]
        self.assertIn("不是本次运行生成的", detail)
        self.assertEqual(code, "GATE_STALE")  # 只有「材料旧」可以豁免

    def test_missing_material_is_not_stale(self):
        (self.work / "materials.json").unlink()
        detail, code = self.failed()["第 1 步 采集"]
        self.assertIn("没有 materials.json", detail)
        self.assertEqual(code, "GATE_INCOMPLETE")  # 「这轮没产出」与「材料是旧的」要分开

    def test_every_source_must_have_a_result(self):
        sources = {"trendshift": {"status": "ok"}}  # 只运行了 --only trendshift
        write(self.work / "collect_report.json", {"week": "2026-W43", "sources": sources})
        detail, code = self.failed()["第 1 步 采集"]
        self.assertIn("hn", detail)
        self.assertEqual(code, "GATE_INCOMPLETE")

    def test_trendshift_not_ready_must_be_written(self):
        sources = {"trendshift": {"status": "not_ready"}, "hn": {"status": "ok"}, "hf": {"status": "ok"},
                   "articles": {"status": "ok"}}
        write(self.work / "collect_report.json", {"week": "2026-W43", "sources": sources})
        self.assertIn("周榜未就绪", self.failed()["第 1 步 采集"][0])

    def test_ranking_must_rerun(self):
        write(self.out / DATA_REL, dict(DATA, generated_at=self.iso(START - 86400)))
        self.assertIn("没有重新运行", self.failed()["第 1 步 AI 判定与排名"][0])
        (self.work / "judgments.json").unlink()
        self.assertIn("没有 judgments.json", self.failed()["第 1 步 AI 判定与排名"][0])

    def test_reused_data_skips_ranking(self):
        sources = {"trendshift": {"status": "reused"}, "hn": {"status": "ok"}, "hf": {"status": "ok"},
                   "articles": {"status": "ok"}}
        write(self.work / "collect_report.json", {"week": "2026-W43", "sources": sources})
        (self.work / "judgments.json").unlink()
        self.assertNotIn("第 1 步 AI 判定与排名", self.failed())

    def test_search_minimum_is_a_gate(self):
        self.searches(9)
        write(self.out / REPORT_REL, with_auto(REPORT, 9), START + 300)
        detail, code = self.failed()["第 1 步 联网搜索"]
        self.assertEqual(code, "GATE_SEARCH_MIN")
        # 降级版不要求搜索下限
        write(self.work / "draft.json", {"degraded": True})
        self.assertNotIn("第 1 步 联网搜索", self.failed())

    def test_search_maximum(self):
        self.searches(41)
        write(self.out / REPORT_REL, with_auto(REPORT, 41), START + 300)
        self.assertEqual(self.failed()["第 1 步 联网搜索"][1], "GATE_SEARCH_MAX")

    def test_finalize_must_run_after_last_search(self):
        self.searches(25)  # 搜索之后没有重新运行 finalize.py
        self.assertIn("finalize.py", self.failed()["第 4 步 数据说明"][0])
        write(self.out / REPORT_REL, REPORT, START + 300)  # 没有自动部分
        self.assertIn("没有自动部分", self.failed()["第 4 步 数据说明"][0])

    def test_draft_required(self):
        (self.work / "draft.json").unlink()
        self.assertIn("draft.py", self.failed()["第 2 步 草稿与写作"][0])

    def test_validate_errors_carry_codes(self):
        materials = {"hn": {"stories": [{"id": "1", "points": 899, "num_comments": 10, "title": "t",
                                         "url": "https://example.com/other", "hn_url": "https://news.ycombinator.com/item?id=1"}]}}
        write(self.work / "materials.json", materials)
        detail, code = self.failed()["第 4 步 校验与门槛"]
        self.assertEqual(code, "GATE_ARTICLE_LINK")


if __name__ == "__main__":
    unittest.main()
