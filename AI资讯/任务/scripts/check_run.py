"""运行完整性检查：确认执行手册第 0–4 步都在本次运行中实际做完，提交前必须通过。

validate.py 检查周报和数据文件的内容是否合规；本脚本检查这些内容是不是本次运行产生的，
防止跳过采集、排名、搜索或重写，只改几处就提交。

本次运行的开始时间取 /tmp/ai-weekly/week.json 的修改时间（第 0 步先清空中间目录，再生成它）。逐项检查：

| 步骤 | 检查 |
| --- | --- |
| 0 准备 | week.json 存在，周编号一致 |
| 1.1 Trendshift | trendshift.json 本次生成、周编号一致；状态为 ok，或为 not_ready 且周报 ③ 写了"周榜未就绪" |
| 1.2 HN | hn.json 本次生成、周编号一致；采集失败时数据说明写了"失败" |
| 1.3 Hugging Face | hf.json 同上 |
| 1.4 AI 判定与排名 | judgments.json 本次生成、字段齐全；数据文件的 generated_at 晚于运行开始 |
| 1.5 联网搜索 | searches.txt 记录了 1–40 次搜索；数据说明写的次数与记录一致 |
| 2 写周报 | 周报文件在本次运行中写过 |
| 4 校验 | validate.py 的全部检查通过 |

回溯模式复用已有数据文件时（--reuse-data），1.1 和 1.4 不要求本次生成，改为检查数据说明注明了"复用"。

退出码：0 通过；1 有步骤未完成。

用法：
    python3 check_run.py --week 2026-W43 [--backfill] [--reuse-data]
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sys
from typing import NamedTuple

from common import REPO_DIR, WORK_DIR, load_config, read_json
from validate import GITHUB, NOTES, run_checks, section_bodies, split_front_matter
from weeks import BJT, Week, weekly_data_path, weekly_report_path

SEARCH_COUNT_RE = re.compile(r"联网搜索[：:][^\d\n]*(\d+)\s*次")
JUDGMENT_KEYS = ("non_ai", "exclude", "hn_ai_repos")
TOLERANCE = 1.0  # 秒；文件修改时间的精度


class Step(NamedTuple):
    name: str
    ok: bool
    detail: str


def _mtime(path: pathlib.Path) -> float | None:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None


def _fresh(path: pathlib.Path, start: float) -> str | None:
    """文件不存在或早于运行开始时返回原因，否则返回 None。"""
    m = _mtime(path)
    if m is None:
        return f"没有 {path.name}"
    if m < start - TOLERANCE:
        return f"{path.name} 不是本次运行生成的（{_fmt(m)}）"
    return None


def _fmt(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, BJT).strftime("%Y-%m-%d %H:%M:%S")


def _read(path: pathlib.Path):
    try:
        return read_json(path)
    except (FileNotFoundError, ValueError):
        return None


def search_count(work_dir: pathlib.Path) -> int | None:
    """searches.txt 每行一次搜索，# 开头的行和空行不计；没有文件返回 None。"""
    try:
        with open(work_dir / "searches.txt", encoding="utf-8") as f:
            return sum(1 for ln in f if ln.strip() and not ln.lstrip().startswith("#"))
    except FileNotFoundError:
        return None


def check_collector(name: str, path: pathlib.Path, week: Week, start: float, notes: str) -> Step:
    why = _fresh(path, start)
    if why:
        return Step(name, False, why)
    out = _read(path)
    if out is None:
        return Step(name, False, f"{path.name} 不是合法 JSON")
    if out.get("week") != week.label:
        return Step(name, False, f"{path.name} 是 {out.get('week')}，应为 {week.label}")
    if out.get("status") != "ok":
        if "失败" not in notes:
            return Step(name, False, f"采集失败（{out.get('error')}），但数据说明没有写明")
        return Step(name, True, f"采集失败，已在数据说明中写明（{out.get('error')}）")
    return Step(name, True, "本次采集成功")


def check(week: Week, work_dir: pathlib.Path = WORK_DIR, report_path=None, data_path=None,
          backfill: bool = False, reuse_data: bool = False) -> list[Step]:
    report_path = pathlib.Path(report_path or REPO_DIR / weekly_report_path(week))
    data_path = pathlib.Path(data_path or REPO_DIR / weekly_data_path(week))
    steps: list[Step] = []

    # 第 0 步
    week_json = work_dir / "week.json"
    start = _mtime(week_json)
    meta = _read(week_json)
    if start is None or meta is None:
        return [Step("第 0 步 准备", False, f"没有 {week_json}，无法确定本次运行的开始时间")]
    if meta.get("week") != week.label:
        return [Step("第 0 步 准备", False, f"week.json 是 {meta.get('week')}，应为 {week.label}")]
    steps.append(Step("第 0 步 准备", True, f"运行开始于 {_fmt(start)}（北京时间）"))

    try:
        text = report_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    sections = section_bodies(split_front_matter(text)[1])
    notes, github = sections.get(NOTES, ""), sections.get(GITHUB, "")

    # 第 1 步：采集
    trendshift_ready = True
    if reuse_data:
        ok = "复用" in notes
        steps.append(Step("第 1 步 Trendshift 周榜", ok,
                          "回溯复用已有数据文件，数据说明已注明" if ok else "回溯复用数据文件，但数据说明没有注明\"复用\""))
    else:
        path = work_dir / "trendshift.json"
        why = _fresh(path, start)
        out = _read(path) if not why else None
        if why:
            steps.append(Step("第 1 步 Trendshift 周榜", False, why))
        elif out is None or out.get("week") != week.label:
            steps.append(Step("第 1 步 Trendshift 周榜", False, f"{path.name} 无效或周编号不符"))
        elif out.get("status") == "ok":
            steps.append(Step("第 1 步 Trendshift 周榜", True, f"本次采集成功，{len(out.get('items', []))} 项"))
        else:
            trendshift_ready = False
            ok = "周榜未就绪" in github
            steps.append(Step("第 1 步 Trendshift 周榜", ok,
                              "周榜未就绪，③ 已写明" if ok else "周榜未就绪，但 ③ 没有写\"周榜未就绪\""))

    steps.append(check_collector("第 1 步 HN", work_dir / "hn.json", week, start, notes))
    steps.append(check_collector("第 1 步 Hugging Face", work_dir / "hf.json", week, start, notes))

    # 第 1 步：AI 判定与排名
    name = "第 1 步 AI 判定与排名"
    if reuse_data:
        steps.append(Step(name, data_path.exists(), "复用已有数据文件" if data_path.exists() else f"没有 {data_path}"))
    elif not trendshift_ready:
        steps.append(Step(name, True, "周榜未就绪，不排名"))
    else:
        jpath = work_dir / "judgments.json"
        why = _fresh(jpath, start)
        judgments = _read(jpath) if not why else None
        data = _read(data_path)
        if why:
            steps.append(Step(name, False, why))
        elif not isinstance(judgments, dict) or any(k not in judgments for k in JUDGMENT_KEYS):
            steps.append(Step(name, False, f"judgments.json 应包含 {', '.join(JUDGMENT_KEYS)}"))
        elif data is None:
            steps.append(Step(name, False, f"没有数据文件 {data_path}，rank_github.py 没有运行"))
        else:
            try:
                generated = dt.datetime.fromisoformat(data.get("generated_at", "")).timestamp()
            except ValueError:
                generated = 0.0
            if generated < start - TOLERANCE:
                steps.append(Step(name, False, f"数据文件生成于 {data.get('generated_at')}，早于本次运行，"
                                               "rank_github.py 没有重新运行"))
            else:
                steps.append(Step(name, True, f"数据文件生成于 {data['generated_at']}"))

    # 第 1 步：联网搜索
    name = "第 1 步 联网搜索"
    limit = load_config("task")["agent"]["web_search_budget"]
    n = search_count(work_dir)
    m = SEARCH_COUNT_RE.search(notes)
    if n is None:
        steps.append(Step(name, False, "没有 searches.txt，本次没有记录联网搜索"))
    elif n == 0:
        steps.append(Step(name, False, "searches.txt 里没有搜索记录"))
    elif n > limit:
        steps.append(Step(name, False, f"搜索 {n} 次，超出上限 {limit}"))
    elif not m:
        steps.append(Step(name, False, f"记录了 {n} 次搜索，但数据说明没有写\"联网搜索：N 次\""))
    elif int(m.group(1)) != n:
        steps.append(Step(name, False, f"数据说明写的是 {m.group(1)} 次，searches.txt 记录了 {n} 次"))
    else:
        steps.append(Step(name, True, f"{n} 次（上限 {limit}）"))

    # 第 2 步
    why = _fresh(report_path, start) if text else f"没有周报文件 {report_path}"
    steps.append(Step("第 2 步 写周报", not why, why or "周报在本次运行中写过"))

    # 第 4 步
    rep = run_checks(week, backfill, report_path, data_path)
    if rep.errors:
        steps.append(Step("第 4 步 validate.py", False, f"{len(rep.errors)} 个错误：" + "；".join(rep.errors)))
    else:
        detail = "通过" + (f"，{len(rep.warnings)} 个警告" if rep.warnings else "")
        steps.append(Step("第 4 步 validate.py", True, detail))
    return steps


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", required=True, help="报告周编号，YYYY-Www")
    ap.add_argument("--backfill", action="store_true", help="回溯模式")
    ap.add_argument("--reuse-data", action="store_true", help="回溯模式复用了已有数据文件")
    ap.add_argument("--work-dir", default=str(WORK_DIR))
    ap.add_argument("--report", help="默认为仓库中的周报路径")
    ap.add_argument("--data", help="默认为仓库中的数据文件路径")
    args = ap.parse_args(argv)

    week = Week.parse(args.week)
    steps = check(week, pathlib.Path(args.work_dir), args.report, args.data, args.backfill, args.reuse_data)
    print(f"# 运行完整性检查 {week.label}")
    for s in steps:
        print(f"[{'完成' if s.ok else '未完成'}] {s.name}：{s.detail}")
    failed = [s for s in steps if not s.ok]
    print("完整性检查通过" if not failed else f"完整性检查失败：{len(failed)} 项未完成")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
