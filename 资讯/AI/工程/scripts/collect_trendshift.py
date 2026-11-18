"""采集 Trendshift 报告周周榜，以及每个上榜仓库在报告周 7 天内的每日新增 star 与 fork。

- 周榜：https://trendshift.io/weekly/{年}/{周数}，解析页面 JSON-LD 中 @type 为 ItemList 的对象。
  进行中的周返回 307，未来的周返回空列表，日期与报告周不符也视为未就绪。
- 每日数据：仓库页内嵌约 61 天的 dailyActivities，按报告周 START..END 的日期求和。
  Trendshift 的日期按 UTC 划分，与北京时间的报告周相差 8 小时，不做换算。

周榜全部条目都会采集（AI 判定由智能体在之后完成）。结果写入 --out（默认 /tmp/ai-weekly/trendshift.json），
并在标准输出打印每项一行的摘要。仓库在往期数据文件里出现过时，附上最近一次的判定（AI / 非 AI / 排除），
帮助智能体保持各周判定一致。

退出码：0 成功；3 周榜未就绪；1 其他错误。

用法：
    python3 collect_trendshift.py --week 2026-W43
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from common import BOARD_DIR, WORK_DIR, fetch, read_json, truncate, write_json
from rank_github import auto_exclusion_kind
from weeks import Week

EXIT_NOT_READY = 3
DATA_DIR = BOARD_DIR / "数据" / "github-weekly"

_LD_JSON = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
# 仓库页里 dailyActivities 以转义 JSON 字符串内嵌在 Next.js 数据中
_DAILY = re.compile(
    r'\\"date\\":\\"(\d{4}-\d\d-\d\d)T00:00:00Z\\",\\"stars\\":(-?\d+),\\"forks\\":(-?\d+)'
)
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
# "Sep 28 to Oct 4, 2026"；同月时省略后一个月份："Oct 19 to 25, 2026"；跨年时起始日期可能带年份
_RANGE = re.compile(
    r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})(?:,?\s*\d{4})?\s*(?:to|–|-)\s*"
    r"(?:([A-Za-z]{3})[a-z]*\.?\s+)?(\d{1,2})\b"
)


def parse_weekly_list(html: str) -> dict | None:
    """返回 ItemList 对象；找不到时返回 None。"""
    for m in _LD_JSON.finditer(html):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "ItemList":
            return data
    return None


def list_matches_week(name: str, week: Week) -> bool:
    """ItemList 的 name 形如 'Weekly trending repositories for Sep 28 to Oct 4, 2026'。

    年份写法不统一，只比对起止的月和日。
    """
    m = _RANGE.search(name or "")
    if not m:
        return False
    try:
        start_month = _MONTHS[m.group(1).lower()]
        end_month = _MONTHS[m.group(3).lower()] if m.group(3) else start_month
    except KeyError:
        return False
    got = ((start_month, int(m.group(2))), (end_month, int(m.group(4))))
    return got == ((week.start.month, week.start.day), (week.end.month, week.end.day))


def parse_daily(html: str) -> dict[str, tuple[int, int]]:
    """仓库页的每日新增：{日期: (stars, forks)}。"""
    return {d: (int(s), int(f)) for d, s, f in _DAILY.findall(html)}


def week_sums(daily: dict[str, tuple[int, int]], week: Week) -> dict:
    days = [(week.start + dt.timedelta(days=i)).isoformat() for i in range(7)]
    covered = [d for d in days if d in daily]
    return {
        "week_stars": sum(daily[d][0] for d in covered) if covered else None,
        "week_forks": sum(daily[d][1] for d in covered) if covered else None,
        "days_covered": len(covered),
        "daily": [{"date": d, "stars": daily[d][0], "forks": daily[d][1]} for d in covered],
    }


def collect_repo(entry: dict, week: Week) -> dict:
    item = entry.get("item") or {}
    rec = {
        "trendshift_position": entry.get("position"),
        "full_name": item.get("name"),
        "description": item.get("description") or "",
        "language": item.get("programmingLanguage"),
        "created_at": item.get("dateCreated"),
        "github_url": item.get("url") or item.get("codeRepository"),
        "trendshift_url": entry.get("url"),
        "error": None,
    }
    if not entry.get("url"):
        rec.update(week_stars=None, week_forks=None, days_covered=0, daily=[], error="周榜条目缺少仓库页链接")
        return rec
    res = fetch(entry["url"], timeout=40, retries=3)
    if not res.ok:
        rec.update(week_stars=None, week_forks=None, days_covered=0, daily=[])
        rec["error"] = "仓库页获取失败：" + (res.error or f"HTTP {res.status}")
        return rec
    daily = parse_daily(res.text())
    rec.update(week_sums(daily, week))
    if not daily:
        rec["error"] = "仓库页里没有解析到每日数据"
    return rec


def prior_judgments(week: Week, data_dir=DATA_DIR) -> dict[str, dict]:
    """往期数据文件里每个仓库最近一次的判定：{full_name: {"week", "verdict", "reason"}}。

    verdict 取值：AI（top5/new/candidate/hn）、非 AI（non_ai）、排除（excluded，reason 为排除原因）。
    脚本按当周数据做的排除（归档、fork、疑似刷星等）记为 AI：它们由 rank_github.py 每周重算，不能沿用。
    只看早于报告周的数据文件；ISO 周编号按字符串排序即为时间顺序。
    """
    prior: dict[str, dict] = {}
    for path in sorted(pathlib.Path(data_dir).glob("*.json")):
        if path.stem >= week.label:
            continue
        try:
            repos = read_json(path).get("repos", [])
        except (ValueError, OSError, AttributeError):
            continue
        for r in repos:
            status = r.get("status")
            if status == "non_ai":
                verdict, reason = "非 AI", ""
            elif status == "excluded":
                verdict, reason = "排除", (r.get("note") or "").split("；")[0]
                kind = auto_exclusion_kind(reason)
                if kind:
                    verdict, reason = "AI", f"脚本曾自动排除（{kind}），本周重新计算"
            else:
                verdict, reason = "AI", ""
            prior[r.get("full_name")] = {"week": path.stem, "verdict": verdict, "reason": reason}
    return prior


def describe_prior(p: dict | None) -> str:
    if not p:
        return ""
    reason = f"：{p['reason']}" if p["reason"] else ""
    return f"往期：{p['verdict']}{reason}（{p['week']}）"


def collect(week: Week, workers: int = 5) -> dict:
    url = f"https://trendshift.io/weekly/{week.iso_year}/{week.number}"
    out = {
        "week": week.label,
        "range": f"{week.start}/{week.end}",
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "weekly_url": url,
        "status": "ok",
        "status_detail": "",
        "list_name": None,
        "items": [],
    }
    res = fetch(url, timeout=40, retries=3)
    if res.status != 200:
        out["status"] = "not_ready"
        out["status_detail"] = res.error or f"HTTP {res.status}"
        return out
    data = parse_weekly_list(res.text())
    entries = (data or {}).get("itemListElement") or []
    out["list_name"] = (data or {}).get("name")
    if not entries:
        out["status"], out["status_detail"] = "not_ready", "周榜列表为空"
        return out
    if not list_matches_week(out["list_name"], week):
        out["status"], out["status_detail"] = "not_ready", f"周榜日期与报告周不符：{out['list_name']}"
        return out
    with ThreadPoolExecutor(max_workers=workers) as pool:
        out["items"] = list(pool.map(lambda e: collect_repo(e, week), entries))
    prior = prior_judgments(week)
    for item in out["items"]:
        item["prior"] = prior.get(item["full_name"])
    return out


def print_summary(result: dict) -> None:
    print(f"# Trendshift {result['week']} {result['status']} {result['status_detail']}".rstrip())
    if result["list_name"]:
        print(f"# {result['list_name']}")
    print("# 名次 | 仓库 | 本周 +star / +fork（天数）| 创建 | 语言 | 描述 | 往期判定")
    for r in result["items"]:
        stars = "?" if r["week_stars"] is None else f"+{r['week_stars']}"
        forks = "?" if r["week_forks"] is None else f"+{r['week_forks']}"
        print(
            f"{r['trendshift_position']} | {r['full_name']} | {stars} / {forks} ({r['days_covered']}d)"
            f" | {(r['created_at'] or '')[:10]} | {r['language'] or '-'} | {truncate(r['description'], 90)}"
            + (f" | {describe_prior(r.get('prior'))}" if r.get("prior") else "")
            + (f" | 错误：{r['error']}" if r["error"] else "")
        )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", required=True, help="报告周编号，YYYY-Www")
    ap.add_argument("--out", default=str(WORK_DIR / "trendshift.json"))
    args = ap.parse_args(argv)

    result = collect(Week.parse(args.week))
    write_json(args.out, result)
    print_summary(result)
    return EXIT_NOT_READY if result["status"] == "not_ready" else 0


if __name__ == "__main__":
    sys.exit(main())
