"""执行记录：把每一步的事件追加到 /tmp/ai-weekly/trace.jsonl，事后可以还原整次运行。

规则见 ../方案.md 7.10 节。脚本通过 log() 自动记录；智能体用命令行记录关键动作：

    python3 tracelog.py search "② 核实" "Gemini 4 Carbon announcement"   # 记一次联网搜索
    python3 tracelog.py log --step 写作 --event 返工 --status warn --code GATE_LINK_HOMEPAGE --detail "..."

search 同时追加到 searches.txt（check_run.py 据此统计搜索次数）。coord.py 写状态文件时，
把本次运行尚未合并的事件并入状态文件，随状态一起推送。

每条事件：ts（北京时间）、seq、run_id、step、event、status（info/ok/warn/error）、
code（错误码，见 ERROR_CODES）、detail、data（可选的结构化字段）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys

from common import WORK_DIR

TRACE_FILE = "trace.jsonl"
SEARCH_FILE = "searches.txt"
BJT = dt.timezone(dt.timedelta(hours=8))

# 错误码：脚本与执行手册统一使用，状态文件和通知里只写代码，含义查这里。
ERROR_CODES = {
    # 数据源
    "SRC_TIMEOUT": "数据源超时或网络错误，重试后仍失败",
    "SRC_HTTP": "数据源返回错误状态码",
    "SRC_NOT_READY": "Trendshift 周榜未就绪",
    "SRC_PARSE": "数据源页面或接口结构变化，解析失败",
    "SRC_SKIPPED": "数据源失败后跳过，按降级处理",
    "ARTICLE_UNREADABLE": "文章原文读取失败",
    # 质量门槛
    "GATE_SEARCH_MIN": "联网搜索次数低于下限",
    "GATE_SEARCH_MAX": "联网搜索次数超过上限",
    "GATE_LINK_HOMEPAGE": "链接只指向网站首页",
    "GATE_NOT_OFFICIAL": "② 缺少官方或一手来源链接",
    "GATE_ARTICLE_LINK": "④ 文章链接与 HN 数据不一致",
    "GATE_NUMBERS": "HN 分数或评论数与采集数据不一致",
    "GATE_STRUCTURE": "周报结构或元数据不符合模板",
    "GATE_INCOMPLETE": "完整性检查发现有步骤没在本次运行中做",
    "GATE_LINK_DEAD": "校验时链接返回 404",
    "GATE_MISMATCH": "发布时声明的 quality 与门槛结果不一致，拒绝发布",
    "GATE_UNVERIFIED": "发布前无法运行门槛检查，按检查未通过处理",
    "GATE_OVERRIDE": "发布时显式覆盖了门槛结果（回溯或测试），质量以声明为准",
    "GATE_OVERRIDE_DENIED": "正式运行不允许覆盖门槛结果，只有回溯和测试模式可以",
    # 协调与提交
    "LOCK_LOST": "锁已被其他运行接管，放弃推送",
    "PUSH_REJECTED": "推送被拒（远端已有新提交），重试用尽",
    "PUSH_DENIED": "没有推送权限",
    "PUSH_NETWORK": "推送时网络错误，重试用尽",
    "STATE_INVALID": "状态文件格式不对",
    "MANUAL_EDIT": "周报被手工修改过，不覆盖",
    "WAIT_TIMEOUT": "等待超过上限",
    "ATTEMPTS_EXHAUSTED": "本周产出尝试次数已用完",
    # 写作与其他
    "WRITE_FAILED": "写作失败，提交降级版",
    "INTERNAL": "脚本内部错误",
}

STATUSES = ("info", "ok", "warn", "error")


def now_iso() -> str:
    return dt.datetime.now(BJT).isoformat(timespec="seconds")


def _run_id(work_dir: pathlib.Path) -> str:
    rid = os.environ.get("AI_WEEKLY_RUN_ID")
    if rid:
        return rid
    try:
        return json.loads((work_dir / "coord.json").read_text(encoding="utf-8")).get("run_id", "")
    except (OSError, ValueError):
        return ""


def read_events(work_dir: pathlib.Path = WORK_DIR) -> list[dict]:
    path = work_dir / TRACE_FILE
    events = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue  # 半行（进程被中断时）跳过
    except OSError:
        pass
    return events


def log(step: str, event: str, status: str = "info", code: str | None = None, detail: str = "",
        work_dir: pathlib.Path = WORK_DIR, **data) -> dict:
    """追加一条事件。写失败不影响调用方（记录是辅助，不能让主流程因此中断）。"""
    if status not in STATUSES:
        status = "info"
    if code and code not in ERROR_CODES:
        detail = f"[未登记的错误码 {code}] {detail}"
    ev = {
        "ts": now_iso(),
        "seq": len(read_events(work_dir)) + 1,
        "run_id": _run_id(work_dir),
        "step": step,
        "event": event,
        "status": status,
        "code": code,
        "detail": detail,
    }
    if data:
        ev["data"] = data
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        with open(work_dir / TRACE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return ev


def record_search(purpose: str, query: str, work_dir: pathlib.Path = WORK_DIR) -> int:
    """记录一次联网搜索，返回本次运行累计的搜索次数。"""
    purpose = " ".join(purpose.split())
    query = " ".join(query.split())
    work_dir.mkdir(parents=True, exist_ok=True)
    with open(work_dir / SEARCH_FILE, "a", encoding="utf-8") as f:
        f.write(f"{purpose}\t{query}\n")
    n = search_count(work_dir)
    log("搜索", "search", detail=f"{purpose}：{query}", work_dir=work_dir, n=n)
    return n


def search_count(work_dir: pathlib.Path = WORK_DIR) -> int:
    try:
        with open(work_dir / SEARCH_FILE, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def summarize(events: list[dict]) -> dict:
    """状态文件里每次运行的摘要：各状态的事件数、出现过的错误码、搜索次数。"""
    by_status = {s: 0 for s in STATUSES}
    codes: dict[str, int] = {}
    searches = 0
    for ev in events:
        by_status[ev.get("status", "info")] = by_status.get(ev.get("status", "info"), 0) + 1
        if ev.get("code"):
            codes[ev["code"]] = codes.get(ev["code"], 0) + 1
        if ev.get("event") == "search":
            searches += 1
    return {"events": len(events), "by_status": by_status, "codes": codes, "searches": searches}


def compact(ev: dict) -> dict:
    """并入状态文件的精简事件：去掉空字段，detail 截断。"""
    out = {k: v for k, v in ev.items() if v not in (None, "", {}, [])}
    if len(out.get("detail", "")) > 300:
        out["detail"] = out["detail"][:299] + "…"
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="记录一次联网搜索")
    s.add_argument("purpose", help="用途，如：发现、② 核实、③ 传播、④ 核实、⑤洞察、机动")
    s.add_argument("query", help="查询词")
    lg = sub.add_parser("log", help="记录一条事件")
    lg.add_argument("--step", required=True)
    lg.add_argument("--event", required=True)
    lg.add_argument("--status", default="info", choices=STATUSES)
    lg.add_argument("--code")
    lg.add_argument("--detail", default="")
    sub.add_parser("codes", help="列出错误码")
    args = ap.parse_args(argv)

    if args.cmd == "search":
        n = record_search(args.purpose, args.query)
        print(f"已记录，第 {n} 次联网搜索")
    elif args.cmd == "log":
        if args.code and args.code not in ERROR_CODES:
            print(f"未登记的错误码：{args.code}（可用 tracelog.py codes 查看）", file=sys.stderr)
        log(args.step, args.event, args.status, args.code, args.detail)
        print("已记录")
    else:
        for code, why in ERROR_CODES.items():
            print(f"{code}\t{why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
