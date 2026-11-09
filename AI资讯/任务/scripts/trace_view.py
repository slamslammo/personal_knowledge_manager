"""还原一周的执行时间线：哪个智能体、几点、做到哪一步、在哪里失败、为什么重跑。

数据来自状态文件 AI资讯/数据/运行记录/{WEEK}.json（随每次状态变更推送到 main），
或本机正在进行的运行的 /tmp/ai-weekly/trace.jsonl。规则见 ../方案.md 7.10 节。

用法：
    python3 trace_view.py --week 2026-W45            # 读远端 main 上的状态文件
    python3 trace_view.py --file 路径/2026-W45.json   # 读本地状态文件
    python3 trace_view.py --local                     # 读本机当前运行的事件日志
    加 --errors 只看警告和错误
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

import tracelog
from common import REPO_DIR, WORK_DIR

MARK = {"info": " ", "ok": "✓", "warn": "!", "error": "✗"}


def load_remote(week: str, repo: pathlib.Path = REPO_DIR) -> dict | None:
    path = f"AI资讯/数据/运行记录/{week}.json"
    subprocess.run(["git", "-C", str(repo), "fetch", "-q", "origin", "main"], capture_output=True)
    p = subprocess.run(["git", "-C", str(repo), "show", f"FETCH_HEAD:{path}"], capture_output=True)
    if p.returncode != 0:
        return None
    return json.loads(p.stdout)


def render_state(state: dict, errors_only: bool = False) -> list[str]:
    lines = [f"# {state['week']}：{state['phase']}，产出尝试 {state.get('attempts', 0)} 次"]
    lock = state.get("lock")
    if lock:
        lines.append(f"锁：{lock['purpose']}，{lock.get('platform')}（{lock['run_id']}），租约到 {lock['lease_until']}")
    prod, ver = state.get("produced"), state.get("verified")
    if prod:
        lines.append(f"产出：{prod.get('platform')} {prod.get('at')}，{prod.get('quality')}，{prod.get('mode')}")
    if ver:
        lines.append(f"校验：{ver.get('platform')} {ver.get('at')}，{ver.get('result')} {','.join(ver.get('codes', []))}")
    lines.append("")
    lines.append("## 运行")
    for r in state.get("runs", []):
        summ = r.get("summary") or {}
        extra = f"，搜索 {summ['searches']} 次" if summ.get("searches") else ""
        lines.append(f"- {r.get('started_at', '')} → {r.get('ended_at', '进行中')}  {r.get('platform')} "
                     f"{r.get('action')}/{r.get('mode', '')}：{r.get('outcome')} "
                     f"{','.join(r.get('codes', []))}{extra}")
        if r.get("reason"):
            lines.append(f"    原因：{r['reason']}")
        if r.get("detail"):
            lines.append(f"    说明：{r['detail']}")
    lines.append("")
    lines += render_events(state.get("events", []), errors_only)
    return lines


def render_events(events: list[dict], errors_only: bool = False) -> list[str]:
    lines = ["## 事件"]
    for e in events:
        if errors_only and e.get("status") not in ("warn", "error"):
            continue
        code = f" [{e['code']}]" if e.get("code") else ""
        who = (e.get("run_id") or "").split("-")[0]
        lines.append(f"{MARK.get(e.get('status'), ' ')} {e.get('ts', '')[11:19]} {who:>7} "
                     f"{e.get('step', '')}/{e.get('event', '')}{code} {e.get('detail', '')}".rstrip())
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--week")
    g.add_argument("--file")
    g.add_argument("--local", action="store_true")
    ap.add_argument("--errors", action="store_true", help="只看警告和错误")
    args = ap.parse_args(argv)
    if args.local:
        print("\n".join(render_events(tracelog.read_events(WORK_DIR), args.errors)))
        return 0
    state = json.loads(pathlib.Path(args.file).read_text(encoding="utf-8")) if args.file else load_remote(args.week)
    if state is None:
        print(f"{args.week} 还没有状态文件")
        return 1
    print("\n".join(render_state(state, args.errors)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
