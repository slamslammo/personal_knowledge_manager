"""一次取回报告周内 HN 分数不低于 50 的 story，去重、排序，并提取 GitHub 仓库链接。

- 时间窗口：报告周北京时间周一 00:00 至下周一 00:00。
- 链接去重：按 common.normalize_url 规范化后，同一链接只保留分数最高的一条。
- 排序：points 降序，同分按评论数降序（文章榜规则，见 ../方案.md 3.6）。
- AI 相关性由智能体逐条判断，本脚本不做过滤。

结果写入 --out（默认 /tmp/ai-weekly/hn.json）。标准输出打印两组：
分数不低于 100 的全部 story（④ 传播文章与 ⑤ 热点话题的候选），以及 50–99 分里的 GitHub 仓库链接（③ HN 热议项目的候选）。

用法：
    python3 collect_hn.py --week 2026-W43
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse

from common import WORK_DIR, fetch, github_repo_from_url, load_config, normalize_url, truncate, write_json
from weeks import BJT, Week

API = "https://hn.algolia.com/api/v1/search"


def build_stories(hits: list[dict]) -> list[dict]:
    stories = []
    for h in hits:
        url = h.get("url") or None
        stories.append({
            "id": str(h["objectID"]),
            "title": h.get("title") or "",
            "url": url,
            "norm_url": normalize_url(url) if url else None,
            "points": h.get("points") or 0,
            "num_comments": h.get("num_comments") or 0,
            "created_at": dt.datetime.fromtimestamp(h.get("created_at_i", 0), BJT).isoformat(timespec="minutes"),
            "hn_url": f"https://news.ycombinator.com/item?id={h['objectID']}",
            "github_repo": github_repo_from_url(url),
            "dup_ids": [],
        })
    stories.sort(key=lambda s: (-s["points"], -s["num_comments"]))
    kept, seen = [], {}
    for s in stories:
        key = s["norm_url"]
        if key and key in seen:
            seen[key]["dup_ids"].append(s["id"])
            continue
        if key:
            seen[key] = s
        kept.append(s)
    return kept


def collect(week: Week, min_points: int) -> dict:
    params = {
        "tags": "story",
        "numericFilters": f"created_at_i>={week.start_ts},created_at_i<{week.end_ts},points>={min_points}",
        "hitsPerPage": 1000,
        "attributesToRetrieve": "objectID,title,url,points,num_comments,created_at_i",
        "attributesToHighlight": "",
    }
    out = {
        "week": week.label,
        "range": f"{week.start}/{week.end}",
        "query_url": API + "?" + urllib.parse.urlencode(params),
        "status": "ok",
        "error": None,
        "total_hits": 0,
        "stories": [],
    }
    res = fetch(API, params=params, timeout=40, retries=3)
    if not res.ok:
        out["status"], out["error"] = "failed", res.error or f"HTTP {res.status}"
        return out
    data = json.loads(res.text())
    out["total_hits"] = data.get("nbHits", 0)
    out["stories"] = build_stories(data.get("hits", []))
    return out


def domain(url: str | None) -> str:
    if not url:
        return "(HN 帖)"
    host = urllib.parse.urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def print_summary(result: dict, article_min: int) -> None:
    print(f"# HN {result['week']} {result['status']} 共 {len(result['stories'])} 条（去重后）"
          + (f" 错误：{result['error']}" if result["error"] else ""))
    print(f"# 分数 >= {article_min}：分数 | 评论 | id | 标题 | 域名 | GitHub")
    for s in result["stories"]:
        if s["points"] >= article_min:
            gh = f" | gh:{s['github_repo']}" if s["github_repo"] else ""
            print(f"{s['points']} | {s['num_comments']} | {s['id']} | {truncate(s['title'], 100)} | {domain(s['url'])}{gh}")
    print(f"# 分数 < {article_min} 的 GitHub 仓库链接：分数 | 评论 | id | 仓库 | 标题")
    for s in result["stories"]:
        if s["points"] < article_min and s["github_repo"]:
            print(f"{s['points']} | {s['num_comments']} | {s['id']} | {s['github_repo']} | {truncate(s['title'], 80)}")


def main(argv=None) -> int:
    ranking = load_config("ranking")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", required=True, help="报告周编号，YYYY-Www")
    ap.add_argument("--out", default=str(WORK_DIR / "hn.json"))
    args = ap.parse_args(argv)

    result = collect(Week.parse(args.week), ranking["hn_query"]["min_points"])
    write_json(args.out, result)
    print_summary(result, ranking["articles"]["min_points"])
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
