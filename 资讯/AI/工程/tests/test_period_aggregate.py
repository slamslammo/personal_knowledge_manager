"""期间聚合单测：口径正确性、跨周去重、缺测不当零、隔离路径。"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

CORE = pathlib.Path(__file__).resolve().parents[1] / "core"
sys.path.insert(0, str(CORE))
import period_aggregate as pa  # noqa: E402
import paths  # noqa: E402


class PeriodAggregateTest(unittest.TestCase):
    def test_weeks_for_month_and_quarter(self):
        self.assertEqual(pa.weeks_for("2026-10"),
                         ["2026-W40", "2026-W41", "2026-W42", "2026-W43", "2026-W44"])
        q4 = pa.weeks_for("2026-Q4")
        self.assertIn("2026-W40", q4)
        self.assertIn("2026-W53", q4)
        self.assertEqual(len(q4), 14)
        with self.assertRaises(ValueError):
            pa.weeks_for("bad")

    def test_real_october_aggregate(self):
        """W40–W44 五份真实榜单：star 累加、贡献周数、缺测不当零。"""
        result = pa.aggregate("2026-10")
        self.assertEqual(result["coverage"], {"weeks_total": 5, "weeks_with_board": 5})
        self.assertEqual(result["missing_weeks"], [])
        self.assertGreater(len(result["ranked"]), 10)
        self.assertNotIn("storytold/photocraft", {r["full_name"] for r in result["ranked"]})
        top = result["ranked"][0]
        self.assertEqual(top["full_name"], "morluto/rea")
        self.assertEqual(top["total"], 416739)
        self.assertEqual(len(top["contributing_weeks"]), 4)
        self.assertEqual(top["days_covered"], 28)
        self.assertTrue(all(r["total"] > 0 and r["contributing_weeks"]
                            for r in result["ranked"]))

    def test_no_board_period_not_count_zero(self):
        """历史期间无周榜存档：ranked 为空，missing_weeks 列全，不造零值。"""
        result = pa.aggregate("2026-01")
        self.assertEqual(result["coverage"]["weeks_with_board"], 0)
        self.assertEqual(len(result["missing_weeks"]), 5)
        self.assertEqual(result["ranked"], [])
        self.assertIn("无存档期间不计零", pa.markdown(result))

    def test_missing_week_not_zero(self):
        """部分周有榜、部分缺：缺周列入 missing，不当零参与排序。"""
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td)
            (d / "2026-W40.json").write_text(json.dumps({
                "week": "2026-W40",
                "repos": [{"status": "candidate", "full_name": "a/b", "week_stars": 10, "days_covered": 7}],
            }), encoding="utf-8")
            (d / "2026-W41.json").write_text(json.dumps({
                "week": "2026-W41",
                "repos": [{"status": "candidate", "full_name": "a/b", "week_stars": None, "days_covered": 0},
                          {"status": "candidate", "full_name": "c/d", "week_stars": 3, "days_covered": 2}],
            }), encoding="utf-8")
            r = pa.aggregate("2026-10", weeks=["2026-W40", "2026-W41", "2026-W42"],
                             weekly_dir=d)
        self.assertEqual(r["missing_weeks"], ["2026-W42"])
        by = {x["full_name"]: x for x in r["ranked"]}
        self.assertEqual(by["a/b"]["total"], 10)
        self.assertEqual(by["a/b"]["contributing_weeks"], ["2026-W40"])
        self.assertEqual(by["a/b"]["no_star_weeks"], ["2026-W41"])
        self.assertEqual(by["c/d"]["days_covered"], 2)

    def test_period_work_dir_isolation(self):
        """同期间不同报告类型、不同类型同期间均落在独立子根。"""
        root = pathlib.Path(tempfile.mkdtemp())
        env = {"AI_WEEKLY_HOME": str(root)}
        a = paths.period_work_dir("weekly", "2026-W40", env=env)
        b = paths.period_work_dir("monthly", "2026-10", env=env)
        c = paths.period_work_dir("monthly", "2026-11", env=env)
        self.assertNotEqual(a, b)
        self.assertNotEqual(b, c)
        self.assertTrue(str(b).endswith("work/monthly/2026-10"))
        with self.assertRaises(ValueError):
            paths.period_work_dir("daily", "2026-10", env=env)
        with self.assertRaises(ValueError):
            paths.period_work_dir("monthly", "bad", env=env)


if __name__ == "__main__":
    unittest.main()
