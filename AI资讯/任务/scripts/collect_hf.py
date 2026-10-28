"""采集 Hugging Face 报告周的高赞论文，作为 ② 关键发布与"值得细读"的候选。

接口 https://huggingface.co/api/daily_papers?week={WEEK}&limit=100，按 upvotes 降序取前 N 篇
（N 见 config/ranking.yaml 的 hf_papers.candidates_top）。结果写入 --out（默认 /tmp/ai-weekly/hf.json）。

用法：
    python3 collect_hf.py --week 2026-W43
"""
from __future__ import annotations

import argparse
import json
import sys

from common import WORK_DIR, fetch, load_config, truncate, write_json
from weeks import Week

API = "https://huggingface.co/api/daily_papers"


def build_papers(entries: list[dict], top: int) -> list[dict]:
    papers = []
    for e in entries:
        p = e.get("paper") or {}
        pid = p.get("id")
        if not pid:
            continue
        papers.append({
            "id": pid,
            "title": p.get("title") or e.get("title") or "",
            "upvotes": p.get("upvotes") or 0,
            "published_at": (p.get("publishedAt") or e.get("publishedAt") or "")[:10],
            "hf_url": f"https://huggingface.co/papers/{pid}",
            "arxiv_url": f"https://arxiv.org/abs/{pid}",
            "github_repo": p.get("githubRepo"),
            "project_page": p.get("projectPage"),
            "summary": truncate(p.get("ai_summary") or p.get("summary") or e.get("summary"), 300),
        })
    papers.sort(key=lambda x: -x["upvotes"])
    return papers[:top]


def collect(week: Week, top: int) -> dict:
    out = {"week": week.label, "status": "ok", "error": None, "papers": []}
    res = fetch(API, params={"week": week.label, "limit": 100}, timeout=40, retries=3)
    if not res.ok:
        out["status"], out["error"] = "failed", res.error or f"HTTP {res.status}"
        return out
    out["papers"] = build_papers(json.loads(res.text()), top)
    return out


def main(argv=None) -> int:
    ranking = load_config("ranking")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", required=True, help="报告周编号，YYYY-Www")
    ap.add_argument("--out", default=str(WORK_DIR / "hf.json"))
    args = ap.parse_args(argv)

    result = collect(Week.parse(args.week), ranking["hf_papers"]["candidates_top"])
    write_json(args.out, result)
    print(f"# Hugging Face {result['week']} {result['status']}" + (f" 错误：{result['error']}" if result["error"] else ""))
    print("# 赞 | 发布 | 链接 | 标题 | 摘要")
    for p in result["papers"]:
        print(f"{p['upvotes']} | {p['published_at']} | {p['hf_url']} | {truncate(p['title'], 100)} | {truncate(p['summary'], 160)}")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
