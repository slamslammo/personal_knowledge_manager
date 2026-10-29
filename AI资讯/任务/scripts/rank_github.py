"""按 ../方案.md 6.3 节计算 GitHub AI 项目热度榜，写入 数据/github-weekly/{WEEK}.json。

输入：
- collect_trendshift.py 的输出（周榜全部条目与本周新增 star、fork）；
- collect_hn.py 的输出（HN 分数，用于"HN 热议项目"）；
- 智能体写的判定文件 judgments.json：
    {
      "non_ai":      ["owner/repo", ...],                 # 周榜里与 AI 无关的仓库，拿不准的不要放进来
      "exclude":     {"owner/repo": "awesome 类链接合集"},  # 按名称和描述就能判断的排除项及原因
      "hn_ai_repos": ["owner/repo", ...]                  # HN 链接里与 AI 相关的仓库
    }

脚本负责：OSS Insight 补充总 star、归档、fork、open issue；归档、fork、疑似刷星的排除；
按本周新增 star 排名取 Top 5；新晋项目与 HN 热议项目（只写入数据文件，周报不展示）。
参数见 config/ranking.yaml 的 github 段。

退出码：0 成功；3 周榜未就绪（不写数据文件）；1 其他错误。

用法：
    python3 rank_github.py --week 2026-W43
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from common import REPO_DIR, WORK_DIR, fetch, load_config, read_json, write_json
from weeks import BJT, Week, weekly_data_path

EXIT_NOT_READY = 3
OSSINSIGHT = "https://api.ossinsight.io/gh/repos/{}"
OSS_FIELDS = ("stargazers_count", "forks_count", "open_issues_count", "topics", "archived", "fork", "created_at")


def ossinsight_lookup(full_name: str) -> dict:
    """返回 {"ok": True, ...字段} / {"ok": False, "not_found": bool, "error": str}。"""
    res = fetch(
        OSSINSIGHT.format(full_name), timeout=15, retries=3,
        give_up=lambda status, body: b"Not Found" in body,
    )
    if b"Not Found" in res.body:
        return {"ok": False, "not_found": True, "error": "仓库不存在"}
    if not res.ok:
        return {"ok": False, "not_found": False, "error": res.error or f"HTTP {res.status}"}
    try:
        data = json.loads(res.text())["data"]
    except (ValueError, KeyError, TypeError):
        return {"ok": False, "not_found": False, "error": "返回格式无法解析"}
    return {"ok": True, **{k: data.get(k) for k in OSS_FIELDS}}


def _date(value: str | None) -> dt.date | None:
    return dt.date.fromisoformat(value[:10]) if value else None


def rank(
    week: Week,
    trendshift: dict,
    hn: dict | None,
    judgments: dict,
    cfg: dict,
    lookup: Callable[[str], dict] = ossinsight_lookup,
    workers: int = 4,
) -> tuple[list[dict], dict]:
    """返回 (repos, info)。repos 是写入数据文件的条目，info 是打印摘要用的附加信息。"""
    non_ai = set(judgments.get("non_ai") or [])
    manual_exclude = dict(judgments.get("exclude") or {})
    hn_ai = list(dict.fromkeys(judgments.get("hn_ai_repos") or []))
    farming = cfg["star_farming"]
    new_cfg = cfg["new_entrants"]
    hn_cfg = cfg["hn_discussed"]

    # HN 上每个仓库的最高分帖子
    hn_best: dict[str, dict] = {}
    for s in (hn or {}).get("stories", []):
        repo = s.get("github_repo")
        if repo and (repo not in hn_best or s["points"] > hn_best[repo]["points"]):
            hn_best[repo] = s

    repos: dict[str, dict] = {}
    for it in trendshift["items"]:
        name = it["full_name"]
        notes = []
        if it.get("days_covered", 0) < 7:
            notes.append(f"部分天数（{it.get('days_covered', 0)}/7）")
        if it.get("error"):
            notes.append(it["error"])
        if name in hn_best:
            notes.append(f"HN {hn_best[name]['points']} 分")
        repos[name] = {
            "full_name": name,
            "trendshift_position": it["trendshift_position"],
            "rank": None,
            "week_stars": it.get("week_stars"),
            "week_forks": it.get("week_forks"),
            "days_covered": it.get("days_covered", 0),
            "total_stars": None,
            "created_at": it.get("created_at"),
            "status": "non_ai" if name in non_ai else "candidate",
            "note": "；".join(notes),
            "_notes": notes,
        }
    in_list = set(repos)

    hn_candidates = [
        r for r in hn_ai
        if r not in in_list and r in hn_best and hn_best[r]["points"] >= hn_cfg["min_points"]
    ]
    hn_candidates.sort(key=lambda r: -hn_best[r]["points"])

    oss: dict[str, dict] = {}

    def enrich(names):
        todo = [n for n in dict.fromkeys(names) if n not in oss]
        if todo:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for n, result in zip(todo, pool.map(lookup, todo)):
                    oss[n] = result

    week_end = week.end
    new_since = week_end - dt.timedelta(days=new_cfg["created_within_days"])

    def is_new(r):
        created = _date(r["created_at"])
        return created is not None and new_since <= created <= week_end

    def stars_key(r):
        return (-(r["week_stars"] if r["week_stars"] is not None else -1),
                -(r["week_forks"] or 0), r["trendshift_position"])

    def exclusion(r) -> str | None:
        name = r["full_name"]
        if name in manual_exclude:
            return manual_exclude[name]
        o = oss.get(name)
        if not o:
            return None
        if not o["ok"]:
            return "仓库已不存在" if o.get("not_found") else None
        if o.get("archived"):
            return "已归档"
        if o.get("fork"):
            return "fork 仓库"
        ws, wf, issues = r["week_stars"], r["week_forks"], o.get("open_issues_count")
        if ws and wf is not None and issues is not None:
            if wf < farming["max_fork_to_star_ratio"] * ws and issues <= farming["max_open_issues"]:
                return f"疑似刷星：本周 +{ws} star 仅 +{wf} fork，open issue {issues} 个"
        return None

    def select():
        pool = [r for r in repos.values() if r["status"] != "non_ai"]
        ok = [r for r in sorted(pool, key=stars_key) if exclusion(r) is None]
        top = ok[: cfg["top_n"]]
        new = [r for r in ok[cfg["top_n"]:] if is_new(r)][: new_cfg["max"]]
        return pool, top, new

    # 先补充增量前 N 名、新晋候选和 HN 项目；若排除后入选项目仍有未查询的，继续补查直到稳定
    pool, _, _ = select()
    ranked = sorted(pool, key=stars_key)
    enrich([r["full_name"] for r in ranked[: cfg["ossinsight_enrich"]["top"]]]
           + [r["full_name"] for r in ranked if is_new(r)]
           + hn_candidates)
    while True:
        pool, top, new = select()
        missing = [r["full_name"] for r in top + new if r["full_name"] not in oss]
        if not missing:
            break
        enrich(missing)

    for r in pool:
        reason = exclusion(r)
        if reason:
            r["status"] = "excluded"
            r["_notes"].insert(0, reason)
    for i, r in enumerate(top, 1):
        r["status"], r["rank"] = "top5", i
    for r in new:
        r["status"] = "new"

    hn_rows = []
    for name in hn_candidates:
        s = hn_best[name]
        row = {
            "full_name": name, "trendshift_position": None, "rank": None,
            "week_stars": None, "week_forks": None, "days_covered": 0,
            "total_stars": None, "created_at": None, "status": "hn",
            "note": "", "_notes": [f"HN {s['points']} 分：{s['hn_url']}"],
        }
        reason = exclusion(row)
        if reason:
            row["status"] = "excluded"
            row["_notes"].insert(0, reason)
        hn_rows.append(row)
    shown_hn = [r for r in hn_rows if r["status"] == "hn"][: hn_cfg["max"]]
    hn_rows = shown_hn + [r for r in hn_rows if r["status"] == "excluded"]

    failures = []
    for r in list(repos.values()) + hn_rows:
        o = oss.get(r["full_name"])
        if o and o["ok"]:
            r["total_stars"] = o.get("stargazers_count")
            r["created_at"] = o.get("created_at") or r["created_at"]
        elif o and not o.get("not_found"):
            failures.append(f"{r['full_name']}（{o['error']}）")
            r["_notes"].append("OSS Insight 获取失败，未核查归档与刷星")
        r["note"] = "；".join(r.pop("_notes"))

    order = {"top5": 0, "new": 1, "hn": 2, "candidate": 3, "excluded": 4, "non_ai": 5}
    rows = sorted(list(repos.values()) + hn_rows,
                  key=lambda r: (order[r["status"]], r["rank"] or 0, stars_key_safe(r)))
    info = {"ossinsight_requested": len(oss), "ossinsight_failed": failures}
    return rows, info


def stars_key_safe(r):
    return (-(r["week_stars"] if r["week_stars"] is not None else -1), r["trendshift_position"] or 999)


def print_summary(rows: list[dict], info: dict) -> None:
    def line(r):
        total = "?" if r["total_stars"] is None else r["total_stars"]
        ws = "?" if r["week_stars"] is None else f"+{r['week_stars']}"
        return f"{r['full_name']} | 本周 {ws} | 总 {total} | 创建 {(r['created_at'] or '')[:10]} | {r['note']}"

    for status, title in [("top5", "Top 5"), ("new", "新晋项目"), ("hn", "HN 热议项目"),
                          ("excluded", "排除"), ("candidate", "其他候选"), ("non_ai", "非 AI")]:
        group = [r for r in rows if r["status"] == status]
        if not group:
            continue
        print(f"# {title}")
        for r in group:
            prefix = f"{r['rank']}. " if r["rank"] else "- "
            print(prefix + line(r))
    print(f"# OSS Insight 请求 {info['ossinsight_requested']} 个，失败 {len(info['ossinsight_failed'])} 个"
          + ("：" + "、".join(info["ossinsight_failed"]) if info["ossinsight_failed"] else ""))
    meta = [r["full_name"] for r in sorted(rows, key=lambda r: r["rank"] or 99) if r["status"] == "top5"]
    print("# 周报元数据 repos：" + json.dumps(meta, ensure_ascii=False))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", required=True, help="报告周编号，YYYY-Www")
    ap.add_argument("--trendshift", default=str(WORK_DIR / "trendshift.json"))
    ap.add_argument("--hn", default=str(WORK_DIR / "hn.json"))
    ap.add_argument("--judgments", default=str(WORK_DIR / "judgments.json"))
    ap.add_argument("--out", help="默认写入仓库的 数据/github-weekly/{WEEK}.json")
    args = ap.parse_args(argv)

    week = Week.parse(args.week)
    trendshift = read_json(args.trendshift)
    if trendshift.get("week") != week.label:
        print(f"trendshift 文件是 {trendshift.get('week')}，与 {week.label} 不符", file=sys.stderr)
        return 1
    if trendshift["status"] != "ok":
        print(f"# 周榜未就绪：{trendshift['status_detail']}，不写数据文件")
        return EXIT_NOT_READY
    try:
        hn = read_json(args.hn)
    except FileNotFoundError:
        hn = None
    judgments = read_json(args.judgments)

    rows, info = rank(week, trendshift, hn, judgments, load_config("ranking")["github"])
    out = args.out or str(REPO_DIR / weekly_data_path(week))
    write_json(out, {
        "week": week.label,
        "range": f"{week.start}/{week.end}",
        "generated_at": dt.datetime.now(BJT).isoformat(timespec="seconds"),
        "repos": rows,
    })
    print_summary(rows, info)
    print(f"# 已写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
