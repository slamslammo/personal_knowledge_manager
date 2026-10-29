"""计算报告周、ISO 周编号、月季归属与到期判定，并给出各产出的仓库路径。

规则见 ../方案.md 第 2 节：
- 报告周是运行日所在周的上一周（周一至周日，北京时间），周编号用 ISO 周；
- 一周归属于它的周四所在的月份和季度；
- 报告周与下一周的周四跨月（跨季）时，月报（季报）到期；
- 最近一个已结束的月份（季度）没有月报（季报），而它包含的周报都已存在时，补生成。

用法：
    python3 weeks.py                          # 按北京时间今天推算报告周，输出 JSON
    python3 weeks.py --target-start 2026-10-19 # 回溯：指定报告周的周一
    python3 weeks.py --week 2026-W43           # 回溯：直接指定周编号
    python3 weeks.py --format env              # 输出 KEY=VALUE，可 eval 到 shell
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import shlex
import sys
from dataclasses import dataclass

BJT = dt.timezone(dt.timedelta(hours=8), "Asia/Shanghai")
TRENDSHIFT_DAILY_WINDOW_DAYS = 61  # Trendshift 仓库页内嵌的每日数据天数（含当天）

BOARD = "AI资讯"


@dataclass(frozen=True)
class Week:
    iso_year: int
    number: int

    @classmethod
    def of(cls, day: dt.date) -> "Week":
        y, w, _ = day.isocalendar()
        return cls(y, w)

    @classmethod
    def parse(cls, label: str) -> "Week":
        m = re.fullmatch(r"(\d{4})-W(\d{2})", label)
        if not m:
            raise ValueError(f"周编号格式应为 YYYY-Www：{label}")
        week = cls(int(m.group(1)), int(m.group(2)))
        if Week.of(week.start) != week:
            raise ValueError(f"不存在的 ISO 周：{label}")
        return week

    @property
    def label(self) -> str:
        return f"{self.iso_year}-W{self.number:02d}"

    @property
    def start(self) -> dt.date:
        return dt.date.fromisocalendar(self.iso_year, self.number, 1)

    @property
    def end(self) -> dt.date:
        return self.start + dt.timedelta(days=6)

    @property
    def thursday(self) -> dt.date:
        return self.start + dt.timedelta(days=3)

    def shift(self, weeks: int) -> "Week":
        return Week.of(self.start + dt.timedelta(weeks=weeks))

    @property
    def month(self) -> tuple[int, int]:
        return self.thursday.year, self.thursday.month

    @property
    def quarter(self) -> tuple[int, int]:
        return self.thursday.year, (self.thursday.month - 1) // 3 + 1

    @property
    def range_label(self) -> str:
        """周报标题里的日期范围，如 10/26–11/1。"""
        s, e = self.start, self.end
        return f"{s.month}/{s.day}–{e.month}/{e.day}"

    @property
    def start_ts(self) -> int:
        """报告周起点（北京时间周一 00:00）的 Unix 时间戳。"""
        return int(dt.datetime.combine(self.start, dt.time(), BJT).timestamp())

    @property
    def end_ts(self) -> int:
        """报告周终点（不含），即下周一 00:00 北京时间。"""
        return self.start_ts + 7 * 86400


def report_week(today: dt.date) -> Week:
    """运行日所在周的上一周。"""
    return Week.of(today).shift(-1)


def weeks_in_month(year: int, month: int) -> list[Week]:
    """周四落在该月的所有 ISO 周。"""
    day = dt.date(year, month, 1)
    day += dt.timedelta(days=(3 - day.weekday()) % 7)  # 当月第一个周四
    weeks = []
    while day.month == month:
        weeks.append(Week.of(day))
        day += dt.timedelta(weeks=1)
    return weeks


def weeks_in_quarter(year: int, quarter: int) -> list[Week]:
    weeks = []
    for month in range(3 * quarter - 2, 3 * quarter + 1):
        weeks.extend(weeks_in_month(year, month))
    return weeks


def prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def prev_quarter(year: int, quarter: int) -> tuple[int, int]:
    return (year - 1, 4) if quarter == 1 else (year, quarter - 1)


# ---------------------------------------------------------------- 路径


def weekly_report_path(week: Week) -> str:
    return f"{BOARD}/周报/{week.iso_year}/{week.label}.md"


def weekly_data_path(week: Week) -> str:
    return f"{BOARD}/数据/github-weekly/{week.label}.json"


def monthly_report_path(year: int, month: int) -> str:
    return f"{BOARD}/月报/{year}/{year}-{month:02d}.md"


def quarterly_report_path(year: int, quarter: int) -> str:
    return f"{BOARD}/季报/{year}/{year}-Q{quarter}.md"


# ---------------------------------------------------------------- 月报、季报判定


def _period_status(label, path, weeks, due, current, repo_dir: pathlib.Path) -> dict:
    """月报或季报在本次运行中是否需要生成。

    due：本次报告周正好是该周期的最后一周；
    generate：报告文件不存在，且包含的周报除本次报告周外都已存在（本次报告周的周报在同一次运行中生成）。
    """
    exists = (repo_dir / path).exists()
    missing = [
        w.label for w in weeks if w != current and not (repo_dir / weekly_report_path(w)).exists()
    ]
    return {
        "period": label,
        "path": path,
        "due": due,
        "exists": exists,
        "weeks": [w.label for w in weeks],
        "missing_weeks": missing,
        "generate": not exists and not missing,
    }


def monthly_status(week: Week, repo_dir: pathlib.Path) -> dict:
    """本次运行要检查的月份：到期时为报告周所在月，否则为上一个月（补生成）。"""
    due = week.month != week.shift(1).month
    year, month = week.month if due else prev_month(*week.month)
    return _period_status(
        f"{year}-{month:02d}", monthly_report_path(year, month),
        weeks_in_month(year, month), due, week, repo_dir,
    )


def quarterly_status(week: Week, repo_dir: pathlib.Path) -> dict:
    due = week.quarter != week.shift(1).quarter
    year, quarter = week.quarter if due else prev_quarter(*week.quarter)
    return _period_status(
        f"{year}-Q{quarter}", quarterly_report_path(year, quarter),
        weeks_in_quarter(year, quarter), due, week, repo_dir,
    )


# ---------------------------------------------------------------- 输出


def describe(week: Week, today: dt.date, mode: str, repo_dir: pathlib.Path) -> dict:
    oldest_daily = today - dt.timedelta(days=TRENDSHIFT_DAILY_WINDOW_DAYS - 1)
    return {
        "mode": mode,
        "today": today.isoformat(),
        "week": week.label,
        "iso_year": week.iso_year,
        "wnum": f"{week.number:02d}",
        "start": week.start.isoformat(),
        "end": week.end.isoformat(),
        "range": f"{week.start.isoformat()}/{week.end.isoformat()}",
        "range_label": week.range_label,
        "start_ts": week.start_ts,
        "end_ts": week.end_ts,
        "thursday": week.thursday.isoformat(),
        "month": "%d-%02d" % week.month,
        "quarter": "%d-Q%d" % week.quarter,
        "report_path": weekly_report_path(week),
        "data_path": weekly_data_path(week),
        "report_exists": (repo_dir / weekly_report_path(week)).exists(),
        "data_exists": (repo_dir / weekly_data_path(week)).exists(),
        "trendshift_weekly_url": f"https://trendshift.io/weekly/{week.iso_year}/{week.number}",
        "trendshift_daily_available": week.start >= oldest_daily,
        "monthly": monthly_status(week, repo_dir),
        "quarterly": quarterly_status(week, repo_dir),
    }


ENV_KEYS = {
    "MODE": "mode", "WEEK": "week", "YEAR": "iso_year", "WNUM": "wnum",
    "START": "start", "END": "end", "RANGE": "range_label",
    "START_TS": "start_ts", "END_TS": "end_ts",
    "REPORT_PATH": "report_path", "DATA_PATH": "data_path",
}


def main(argv=None) -> int:
    from common import REPO_DIR

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--target-start", help="回溯：报告周的周一，YYYY-MM-DD")
    g.add_argument("--week", help="回溯：报告周编号，YYYY-Www")
    ap.add_argument("--today", help="假定的运行日（北京时间），默认今天，YYYY-MM-DD")
    ap.add_argument("--format", choices=["json", "env"], default="json")
    args = ap.parse_args(argv)

    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(BJT).date()
    if args.target_start:
        start = dt.date.fromisoformat(args.target_start)
        if start.weekday() != 0:
            ap.error(f"TARGET_START 必须是周一：{start}")
        week, mode = Week.of(start), "backfill"
    elif args.week:
        week, mode = Week.parse(args.week), "backfill"
    else:
        week, mode = report_week(today), "normal"
    if week.end >= today:
        ap.error(f"{week.label} 尚未结束（{week.end} 是周日），不能生成周报")

    info = describe(week, today, mode, REPO_DIR)
    if args.format == "env":
        for key, field in ENV_KEYS.items():
            print(f"{key}={shlex.quote(str(info[field]))}")
    else:
        json.dump(info, sys.stdout, ensure_ascii=False, indent=2)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
