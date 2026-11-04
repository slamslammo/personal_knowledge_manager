"""运行完整性检查：确认各步都在本次运行中实际做完、质量门槛都通过，提交前必须通过。

validate.py 检查周报内容；本脚本检查内容是不是本次运行产生的、门槛是否达标（../方案.md 7.8 节），
防止跳过采集、排名、搜索或重写，只改几处就提交。本次运行的开始时间取 /tmp/ai-weekly/week.json
的修改时间（第 0 步先清空中间目录，再生成它）。

| 步骤 | 检查 |
| --- | --- |
| 0 准备 | week.json 存在；coord.json 表明本次运行持有运行锁 |
| 1 采集 | collect_report.json 与 materials.json 本次生成；周榜未就绪时 ③ 写了"周榜未就绪" |
| 1 AI 判定与排名 | judgments.json 本次生成；产出目录里的数据文件本次生成（回溯复用存档时只要求存在） |
| 1 联网搜索 | searches.txt 的次数在 runtime.yaml 的 search.min–max 之间（降级版不要求下限） |
| 2 草稿与写作 | draft.py 本次运行过；周报在草稿之后写过 |
| 4 数据说明 | finalize.py 在最后一次搜索之后运行过（自动部分的搜索次数与记录一致） |
| 4 校验 | validate.py 全部通过，含对照素材的质量门槛 |

未完成的步骤带错误码，最后一行输出 CODES=...，供 coord.py publish --codes 使用。

退出码：0 通过；1 有步骤未完成。

用法：
    python3 check_run.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sys
from typing import NamedTuple

import tracelog
from common import OUT_DIR, WORK_DIR, load_config, read_json
from finalize import AUTO_BEGIN, AUTO_END
from validate import GITHUB, run_checks, section_bodies, split_front_matter
from weeks import BJT, Week

SEARCH_COUNT_RE = re.compile(r"联网搜索[：:][^\d\n]*(\d+)\s*次")
JUDGMENT_KEYS = ("non_ai", "exclude", "hn_ai_repos")
TOLERANCE = 1.0  # 秒；文件修改时间的精度


class Step(NamedTuple):
    name: str
    ok: bool
    detail: str
    code: str | None = None


def _mtime(path: pathlib.Path) -> float | None:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None


def _fresh(path: pathlib.Path, start: float) -> str | None:
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


def check(work_dir: pathlib.Path = WORK_DIR, out_dir: pathlib.Path = OUT_DIR) -> list[Step]:
    steps: list[Step] = []
    week_json = work_dir / "week.json"
    start, info = _mtime(week_json), _read(week_json)
    if start is None or info is None:
        return [Step("第 0 步 准备", False, f"没有 {week_json}，无法确定本次运行的开始时间", "GATE_INCOMPLETE")]
    week = Week.parse(info["week"])
    report_path, data_path = out_dir / info["report_path"], out_dir / info["data_path"]
    coord = _read(work_dir / "coord.json") or {}
    if coord.get("week") == week.label and coord.get("purpose") == "run":
        steps.append(Step("第 0 步 准备", True, f"运行开始于 {_fmt(start)}，持有运行锁（{coord.get('run_id')}）"))
    else:
        steps.append(Step("第 0 步 准备", False, "coord.json 显示本次运行没有持有运行锁，先运行 coord.py start",
                          "GATE_INCOMPLETE"))

    try:
        text = report_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    draft = _read(work_dir / "draft.json") or {}
    degraded = bool(draft.get("degraded"))

    # 第 1 步：采集
    report = _read(work_dir / "collect_report.json")
    why = _fresh(work_dir / "collect_report.json", start) or _fresh(work_dir / "materials.json", start)
    trendshift = ((report or {}).get("sources") or {}).get("trendshift", {}).get("status")
    if why or not report:
        steps.append(Step("第 1 步 采集", False, why or "collect_report.json 无效，先运行 collect_all.py",
                          "GATE_INCOMPLETE"))
    else:
        skipped = [k for k, v in report["sources"].items() if v.get("status") in ("skipped", "not_ready")]
        detail = "本次采集完成" + (f"，跳过或未就绪：{'、'.join(skipped)}（已写入数据说明）" if skipped else "")
        if trendshift == "not_ready" and "周榜未就绪" not in section_bodies(split_front_matter(text)[1]).get(GITHUB, ""):
            steps.append(Step("第 1 步 采集", False, "周榜未就绪，但 ③ 没有写\"周榜未就绪\"", "GATE_INCOMPLETE"))
        else:
            steps.append(Step("第 1 步 采集", True, detail))

    # 第 1 步：AI 判定与排名
    name = "第 1 步 AI 判定与排名"
    if trendshift == "reused":
        ok = data_path.exists()
        steps.append(Step(name, ok, "回溯，复用已存档的数据文件" if ok else f"没有 {data_path}", None if ok else "GATE_INCOMPLETE"))
    elif trendshift != "ok":
        steps.append(Step(name, True, "周榜未就绪，不排名"))
    else:
        jwhy = _fresh(work_dir / "judgments.json", start)
        judgments = _read(work_dir / "judgments.json") if not jwhy else None
        data = _read(data_path)
        if jwhy:
            steps.append(Step(name, False, jwhy, "GATE_INCOMPLETE"))
        elif not isinstance(judgments, dict) or any(k not in judgments for k in JUDGMENT_KEYS):
            steps.append(Step(name, False, f"judgments.json 应包含 {', '.join(JUDGMENT_KEYS)}", "GATE_INCOMPLETE"))
        elif data is None:
            steps.append(Step(name, False, f"没有 {data_path}，rank_github.py 没有运行", "GATE_INCOMPLETE"))
        else:
            try:
                generated = dt.datetime.fromisoformat(data.get("generated_at", "")).timestamp()
            except ValueError:
                generated = 0.0
            ok = generated >= start - TOLERANCE
            steps.append(Step(name, ok, f"数据文件生成于 {data.get('generated_at')}"
                              + ("" if ok else "，早于本次运行，rank_github.py 没有重新运行"),
                              None if ok else "GATE_INCOMPLETE"))

    # 第 1 步：联网搜索
    cfg = load_config("runtime")["search"]
    n = tracelog.search_count(work_dir)
    if n > cfg["max"]:
        steps.append(Step("第 1 步 联网搜索", False, f"搜索 {n} 次，超出上限 {cfg['max']}", "GATE_SEARCH_MAX"))
    elif n < cfg["min"] and not degraded:
        steps.append(Step("第 1 步 联网搜索", False, f"只搜索了 {n} 次，下限 {cfg['min']} 次：补做 ②③④⑤ 的核实与传播分析",
                          "GATE_SEARCH_MIN"))
    else:
        steps.append(Step("第 1 步 联网搜索", True, f"{n} 次（{cfg['min']}–{cfg['max']}）" + ("，降级版" if degraded else "")))

    # 第 2 步：草稿与写作
    dwhy = _fresh(work_dir / "draft.json", start)
    if dwhy:
        steps.append(Step("第 2 步 草稿与写作", False, f"{dwhy}：先运行 draft.py 生成草稿", "GATE_INCOMPLETE"))
    elif not text:
        steps.append(Step("第 2 步 草稿与写作", False, f"没有周报 {report_path}", "GATE_INCOMPLETE"))
    else:
        steps.append(Step("第 2 步 草稿与写作", True, "降级版" if degraded else "草稿已生成，周报在本次运行中写过"))

    # 第 4 步：数据说明（finalize.py）
    block = text[text.find(AUTO_BEGIN): text.find(AUTO_END)] if AUTO_BEGIN in text and AUTO_END in text else ""
    m = SEARCH_COUNT_RE.search(block)
    if not block:
        steps.append(Step("第 4 步 数据说明", False, "数据说明没有自动部分：运行 finalize.py", "GATE_INCOMPLETE"))
    elif not m or int(m.group(1)) != n:
        steps.append(Step("第 4 步 数据说明", False, f"自动部分写的搜索次数与记录（{n} 次）不一致：重新运行 finalize.py",
                          "GATE_INCOMPLETE"))
    else:
        steps.append(Step("第 4 步 数据说明", True, "finalize.py 已在最后一次搜索之后运行"))

    # 第 4 步：校验与质量门槛
    materials = _read(work_dir / "materials.json")
    rep = run_checks(week, info.get("mode") == "backfill", report_path, data_path, materials=materials)
    if rep.errors:
        steps.append(Step("第 4 步 校验与门槛", False, f"{len(rep.errors)} 个错误：" + "；".join(rep.errors),
                          (rep.codes or ["GATE_STRUCTURE"])[0]))
        for code in rep.codes[1:]:
            steps.append(Step("第 4 步 校验与门槛", False, "（同上）", code))
    else:
        steps.append(Step("第 4 步 校验与门槛", True, "通过" + (f"，{len(rep.warnings)} 个警告" if rep.warnings else "")))
    return steps


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work-dir", default=str(WORK_DIR))
    args = ap.parse_args(argv)
    work = pathlib.Path(args.work_dir)
    steps = check(work, work / "out")
    print("# 运行完整性检查")
    for s in steps:
        if s.detail != "（同上）":
            print(f"[{'完成' if s.ok else '未完成'}] {s.name}：{s.detail}")
    failed = [s for s in steps if not s.ok]
    codes = list(dict.fromkeys(s.code for s in failed if s.code))
    for code in codes:
        tracelog.log("检查", "门槛", "warn", code, tracelog.ERROR_CODES.get(code, ""), work_dir=work)
    print("完整性检查通过" if not failed else f"完整性检查失败：{len({s.name for s in failed})} 项未完成")
    if codes:
        print("CODES=" + ",".join(codes))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
