"""提交前整理周报：刷新数据说明的事实部分，删除草稿提示。规则见 ../方案.md 3.9 节。

- 数据说明里 <!-- auto:data-notes --> 与 <!-- /auto --> 之间的内容由本脚本根据采集报告、
  榜单数据文件和搜索记录生成：各数据源状态、每日数据覆盖、OSS Insight、原文读取、联网搜索次数。
  智能体不手写这部分；没有这对标记时插到数据说明开头。
- 删除 draft.py 留下的 <!-- 草稿：... --> 提示（包括 ④ 的候选清单）。

默认处理本次运行的产出 /tmp/ai-weekly/out/<周报路径>。在 validate.py 和 check_run.py 之前运行；
改了周报之后要重新运行。

用法：
    python3 finalize.py
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

import tracelog
from common import OUT_DIR, WORK_DIR, load_config, read_json

AUTO_BEGIN, AUTO_END = "<!-- auto:data-notes -->", "<!-- /auto -->"
DRAFT_NOTE_RE = re.compile(r"\n?<!-- 草稿：.*?-->\n?", re.S)
NOTES_HEADING = "## 数据说明"


def _load(path, default=None):
    try:
        return read_json(path)
    except (OSError, ValueError):
        return default


def render_auto(work_dir: pathlib.Path, data: dict | None) -> list[str]:
    report = _load(work_dir / "collect_report.json", {"sources": {}})
    src = report.get("sources", {})
    search_cfg = load_config("runtime")["search"]
    lines = []

    ts = src.get("trendshift") or {}
    if ts.get("status") == "reused":
        lines.append("- Trendshift 周榜：回溯，复用已存档的榜单数据文件；周榜和每日数据按 UTC 划分，与北京时间的报告周相差 8 小时。")
    elif ts.get("status") == "ok":
        lines.append(f"- Trendshift 周榜：成功，{ts.get('detail')}；周榜和每日数据按 UTC 划分，与北京时间的报告周相差 8 小时。")
    else:
        lines.append(f"- Trendshift 周榜：未就绪或失败（{ts.get('code') or '未采集'}：{ts.get('detail') or '无'}），③ 无法排名。")

    if data:
        top = sorted((r for r in data.get("repos", []) if r.get("status") == "top5"), key=lambda r: r["rank"])
        short = [f"{r['full_name']}（{r['days_covered']} 天）" for r in top if r.get("days_covered", 0) < 7]
        lines.append("- 每日 star 数据：Top 5 均覆盖 7 天。" if not short else f"- 每日 star 数据：不足 7 天的有 {'、'.join(short)}。")
        failed = [r["full_name"] for r in data.get("repos", []) if "OSS Insight 获取失败" in (r.get("note") or "")]
        asked = sum(1 for r in data.get("repos", []) if r.get("total_stars") is not None) + len(failed)
        lines.append(f"- OSS Insight：请求 {asked} 个，失败 {len(failed)} 个" + (f"（{'、'.join(failed)}）。" if failed else "。"))

    for key, label in (("hn", "HN"), ("hf", "Hugging Face 论文"), ("articles", "原文读取")):
        s = src.get(key)
        if not s:
            lines.append(f"- {label}：未采集。")
        elif s.get("status") == "ok":
            lines.append(f"- {label}：{s.get('detail')}。")
        else:
            lines.append(f"- {label}：失败，已跳过（{s.get('code')}：{s.get('detail')}）。")

    n = tracelog.search_count(work_dir)
    lines.append(f"- 联网搜索：{n} 次（下限 {search_cfg['min']}，上限 {search_cfg['max']}）。")
    return lines


def apply(text: str, auto_lines: list[str], strip_notes: bool = True) -> str:
    if strip_notes:
        text = DRAFT_NOTE_RE.sub("\n", text)
    block = "\n".join([AUTO_BEGIN, *auto_lines, AUTO_END])
    if AUTO_BEGIN in text and AUTO_END in text:
        start = text.index(AUTO_BEGIN)
        end = text.index(AUTO_END, start) + len(AUTO_END)
        text = text[:start] + block + text[end:]
    elif NOTES_HEADING in text:
        i = text.index(NOTES_HEADING) + len(NOTES_HEADING)
        text = text[:i] + "\n\n" + block + text[i:]
    else:
        text = text.rstrip("\n") + f"\n\n{NOTES_HEADING}\n\n{block}\n"
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.rstrip("\n") + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", help="默认为本次运行的周报产出")
    args = ap.parse_args(argv)
    info = read_json(WORK_DIR / "week.json")
    path = pathlib.Path(args.report) if args.report else OUT_DIR / info["report_path"]
    data = _load(OUT_DIR / info["data_path"])
    text = path.read_text(encoding="utf-8")
    auto = render_auto(WORK_DIR, data)
    path.write_text(apply(text, auto), encoding="utf-8")
    tracelog.log("写作", "finalize", "ok", detail=f"数据说明已刷新，联网搜索 {tracelog.search_count(WORK_DIR)} 次")
    print("已刷新数据说明并删除草稿提示：")
    print("\n".join(auto))
    return 0


if __name__ == "__main__":
    sys.exit(main())
