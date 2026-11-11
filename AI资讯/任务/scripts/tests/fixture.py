"""本次运行的产物夹具：`coord.py publish` 前的门槛（check_run.py）需要它们。

协调流程的测试要跑真门槛，就必须有「采集、判定、草稿、搜索、数据说明都做过」的产物。
这里按 check_run.py 的检查项造一套，不联网；周次固定 2026-W43，因为 test_validate 的
REPORT / DATA 是这一周的内容。
"""
import datetime as dt
import json
import os
import pathlib
import time

import finalize
from test_validate import DATA, REPORT

WEEK = "2026-W43"
REPORT_REL = f"AI资讯/周报/2026/{WEEK}.md"
DATA_REL = f"AI资讯/数据/github-weekly/{WEEK}.json"


def week_info(mode="normal"):
    return {"week": WEEK, "mode": mode, "iso_year": 2026, "report_path": REPORT_REL,
            "data_path": DATA_REL, "state_path": f"AI资讯/数据/运行记录/{WEEK}.json"}


def _write(path: pathlib.Path, obj, when: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    os.utime(path, (when, when))


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")


def report_text(searches: int = 24, degraded: bool = False, title_suffix: str = "") -> str:
    """带自动数据说明的周报正文；degraded 时元数据加 quality: degraded。"""
    lines = ["- Trendshift 周榜：成功，25 项。", f"- 联网搜索：{searches} 次（下限 20，上限 40）。"]
    text = finalize.apply(REPORT.replace("- 联网搜索：12 次（上限 40）。\n", ""), lines)
    if title_suffix:
        text = text.replace("（10/19–10/25）\n", f"（10/19–10/25）{title_suffix}\n", 1)
    if degraded:
        text = text.replace("---\nweek: 2026-W43\n", "---\nweek: 2026-W43\nquality: degraded\n", 1)
    return text


def build(work: pathlib.Path, info: dict, *, searches: int = 24, degraded: bool = False,
          start: float | None = None) -> str:
    """在 work 里写一整套「本次运行都做了」的产物，返回周报正文。

    week.json 的修改时间就是本次运行的开始时间（check_run.py 这么取），其余文件都晚于它。
    搜索次数低于下限（<20）或产物缺失时，真实门槛就会失败，用来测不通过的路径。
    """
    start = time.time() - 600 if start is None else start
    _write(work / "week.json", info, start)
    sources = {k: {"status": "ok"} for k in ("trendshift", "hn", "hf", "articles")}
    _write(work / "collect_report.json", {"week": info["week"], "sources": sources}, start + 30)
    _write(work / "materials.json", {"week": info["week"], "hn": {"stories": []}}, start + 30)
    _write(work / "judgments.json", {"non_ai": [], "exclude": {}, "hn_ai_repos": []}, start + 40)
    _write(work / "draft.json", {"degraded": degraded}, start + 50)
    _write(work / "searches.txt", "".join(f"发现\tq{i}\n" for i in range(searches)), start + 60)
    _write(work / "out" / info["data_path"], dict(DATA, generated_at=_iso(start + 120)), start + 130)
    text = report_text(searches, degraded)
    _write(work / "out" / info["report_path"], text, start + 300)
    return text
