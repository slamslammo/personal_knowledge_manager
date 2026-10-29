import datetime as dt
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from weeks import (  # noqa: E402
    Week, monthly_status, quarterly_status, report_week, weekly_report_path, weeks_in_month,
)

D = dt.date.fromisoformat


class WeekTest(unittest.TestCase):
    def test_report_week_is_previous_week(self):
        w = report_week(D("2026-11-02"))  # 周一
        self.assertEqual(w.label, "2026-W44")
        self.assertEqual((w.start, w.end), (D("2026-10-26"), D("2026-11-01")))
        self.assertEqual(w.range_label, "10/26–11/1")
        self.assertEqual(report_week(D("2026-11-01")).label, "2026-W43")  # 周日

    def test_iso_year_boundary(self):
        self.assertEqual(Week.of(D("2026-12-28")).label, "2026-W53")
        self.assertEqual(Week.of(D("2027-01-03")).label, "2026-W53")
        self.assertEqual(Week.of(D("2027-01-04")).label, "2027-W01")
        self.assertEqual(report_week(D("2027-01-04")).label, "2026-W53")

    def test_parse(self):
        self.assertEqual(Week.parse("2026-W53").start, D("2026-12-28"))
        with self.assertRaises(ValueError):
            Week.parse("2027-W53")  # 2027 年只有 52 周
        with self.assertRaises(ValueError):
            Week.parse("2026-44")

    def test_beijing_timestamps(self):
        w = Week.parse("2026-W44")
        utc = dt.datetime.fromtimestamp(w.start_ts, dt.timezone.utc)
        self.assertEqual(utc.isoformat(), "2026-10-25T16:00:00+00:00")
        self.assertEqual(w.end_ts - w.start_ts, 7 * 86400)

    def test_thursday_rule(self):
        w40 = Week.parse("2026-W40")  # 9/28–10/4，周四 10/1
        self.assertEqual(w40.month, (2026, 10))
        self.assertEqual(w40.quarter, (2026, 4))
        self.assertEqual([w.label for w in weeks_in_month(2026, 10)],
                         ["2026-W40", "2026-W41", "2026-W42", "2026-W43", "2026-W44"])
        self.assertEqual(Week.parse("2027-W01").month, (2027, 1))


class PeriodStatusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def touch_weeks(self, *labels):
        for label in labels:
            p = self.repo / weekly_report_path(Week.parse(label))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x", encoding="utf-8")

    def test_monthly_due_needs_earlier_weeks(self):
        w44 = Week.parse("2026-W44")
        st = monthly_status(w44, self.repo)
        self.assertTrue(st["due"])
        self.assertEqual(st["period"], "2026-10")
        self.assertEqual(st["missing_weeks"], ["2026-W40", "2026-W41", "2026-W42", "2026-W43"])
        self.assertFalse(st["generate"])
        self.touch_weeks("2026-W40", "2026-W41", "2026-W42", "2026-W43")
        self.assertTrue(monthly_status(w44, self.repo)["generate"])

    def test_monthly_catch_up(self):
        w45 = Week.parse("2026-W45")
        st = monthly_status(w45, self.repo)
        self.assertFalse(st["due"])
        self.assertEqual(st["period"], "2026-10")
        self.touch_weeks("2026-W40", "2026-W41", "2026-W42", "2026-W43", "2026-W44")
        self.assertTrue(monthly_status(w45, self.repo)["generate"])
        p = self.repo / "AI资讯/月报/2026/2026-10.md"
        p.parent.mkdir(parents=True)
        p.write_text("x", encoding="utf-8")
        self.assertFalse(monthly_status(w45, self.repo)["generate"])

    def test_quarterly_due_at_year_end(self):
        st = quarterly_status(Week.parse("2026-W53"), self.repo)
        self.assertTrue(st["due"])
        self.assertEqual(st["period"], "2026-Q4")
        self.assertEqual(st["weeks"][0], "2026-W40")
        self.assertEqual(st["weeks"][-1], "2026-W53")


if __name__ == "__main__":
    unittest.main()
