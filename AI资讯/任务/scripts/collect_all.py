"""采集总调度：一条命令完成全部数据采集，统一重试、跳过与记录。规则见 ../方案.md 7.1、7.7 节。

依次运行 Trendshift 周榜、HN、Hugging Face 和原文读取（fetch_articles.py）。每个请求在 common.fetch
里重试 3 次；某个数据源仍失败就跳过并记录错误码，继续采集其他数据源。产出（都在 /tmp/ai-weekly/）：

- materials.json       全量素材：周榜（含往期判定）、HN 全部 story（含原文读取结果）、论文
- digest.md            精简摘要，不超过 digest.max_lines 行，链接都是完整链接；智能体只读这一份
- collect_report.json  各数据源的状态、错误码、条数、耗时，finalize.py 据此填写数据说明

回溯且榜单数据已存档时，直接复用仓库里的数据文件（复制到 OUT_DIR），不再采集 Trendshift。

用法（先运行 weeks.py 生成 week.json）：
    python3 collect_all.py                      全部采集
    python3 collect_all.py --only trendshift    周榜未就绪时稍后单独重试
    python3 collect_all.py show hn --offset 60  查看摘要之外的 HN 帖子
    python3 collect_all.py show article 50289418

输出第一行：COLLECT=ok（全部成功）/ degraded（有数据源跳过）/ trendshift_not_ready（周榜未就绪）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
import time

import collect_hf
import collect_hn
import collect_trendshift
import fetch_articles
import tracelog
from common import OUT_DIR, REPO_DIR, WORK_DIR, load_config, read_json, truncate, write_json
from weeks import BJT, Week

SOURCES = ("trendshift", "hn", "hf", "articles")

# 只用于决定摘要里先列哪些 HN 帖子，不用于过滤：是否与 AI 相关由智能体判断
AI_HINT = re.compile(
    r"\b(AI|A\.I\.|AGI|LLMs?|GPT[-\w.]*|ChatGPT|Claude|Gemini|Gemma|Llama|Mistral|DeepSeek|Qwen|Kimi|Grok|"
    r"OpenAI|Anthropic|DeepMind|Hugging ?Face|transformers?|neural|machine learning|deep learning|"
    r"agents?|agentic|MCP|RAG|inference|fine-?tun\w*|diffusion|models?|Copilot|Cursor|vibe[- ]cod\w*|"
    r"prompts?|tokens?|embeddings?|chatbots?|Sora|Veo|Midjourney|NVIDIA|GPUs?|CUDA|TPUs?|benchmarks?)\b",
    re.IGNORECASE,
)
AI_HINT_DOMAINS = ("openai.com", "anthropic.com", "deepmind", "huggingface.co", "arxiv.org", "mistral.ai")


def ai_hint(story: dict) -> bool:
    url = story.get("url") or ""
    return bool(AI_HINT.search(story.get("title", ""))) or any(d in url for d in AI_HINT_DOMAINS)


# ---------------------------------------------------------------- 采集


def _timed(fn):
    t0 = time.monotonic()
    result = fn()
    return result, round(time.monotonic() - t0, 1)


def collect_trendshift_source(week: Week, info: dict) -> dict:
    if info.get("mode") == "backfill" and info.get("data_exists"):
        src = REPO_DIR / info["data_path"]
        dst = OUT_DIR / info["data_path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        tracelog.log("采集", "Trendshift", "ok", detail="回溯：复用已存档的榜单数据文件")
        return {"status": "reused", "code": None, "detail": "复用已存档的榜单数据文件", "count": None}
    result, secs = _timed(lambda: collect_trendshift.collect(week))
    write_json(WORK_DIR / "trendshift.json", result)
    if result["status"] == "ok":
        partial = sum(1 for i in result["items"] if i["days_covered"] < 7)
        errors = sum(1 for i in result["items"] if i["error"])
        detail = f"{len(result['items'])} 项" + (f"，{partial} 项每日数据不足 7 天" if partial else "") + (
            f"，{errors} 项仓库页读取失败" if errors else "")
        tracelog.log("采集", "Trendshift", "ok" if not errors else "warn", detail=detail, seconds=secs)
        return {"status": "ok", "code": None, "detail": detail, "count": len(result["items"]), "seconds": secs}
    network = result["status_detail"].split(":")[0].endswith("Error") or "timed out" in result["status_detail"]
    code = "SRC_TIMEOUT" if network else "SRC_NOT_READY"
    tracelog.log("采集", "Trendshift", "warn", code, result["status_detail"], seconds=secs)
    return {"status": "not_ready", "code": code, "detail": result["status_detail"], "count": 0, "seconds": secs}


def collect_hn_source(week: Week) -> dict:
    ranking = load_config("ranking")
    result, secs = _timed(lambda: collect_hn.collect(week, ranking["hn_query"]["min_points"]))
    write_json(WORK_DIR / "hn.json", result)
    if result["status"] != "ok":
        tracelog.log("采集", "HN", "error", "SRC_SKIPPED", result["error"], seconds=secs)
        return {"status": "skipped", "code": "SRC_TIMEOUT", "detail": result["error"], "count": 0, "seconds": secs}
    n100 = sum(1 for s in result["stories"] if s["points"] >= ranking["articles"]["min_points"])
    detail = f"{len(result['stories'])} 条（不低于 {ranking['articles']['min_points']} 分的 {n100} 条）"
    tracelog.log("采集", "HN", "ok", detail=detail, seconds=secs)
    return {"status": "ok", "code": None, "detail": detail, "count": len(result["stories"]), "seconds": secs}


def collect_hf_source(week: Week) -> dict:
    top = load_config("ranking")["hf_papers"]["candidates_top"]
    result, secs = _timed(lambda: collect_hf.collect(week, top))
    write_json(WORK_DIR / "hf.json", result)
    if result["status"] != "ok":
        tracelog.log("采集", "Hugging Face", "error", "SRC_SKIPPED", result["error"], seconds=secs)
        return {"status": "skipped", "code": "SRC_TIMEOUT", "detail": result["error"], "count": 0, "seconds": secs}
    tracelog.log("采集", "Hugging Face", "ok", detail=f"{len(result['papers'])} 篇", seconds=secs)
    return {"status": "ok", "code": None, "detail": f"{len(result['papers'])} 篇", "count": len(result["papers"]),
            "seconds": secs}


def collect_articles_source() -> dict:
    try:
        hn = read_json(WORK_DIR / "hn.json")
    except OSError:
        hn = {"status": "failed", "stories": []}
    if hn.get("status") != "ok":
        write_json(WORK_DIR / "articles.json", {})
        return {"status": "skipped", "code": "SRC_SKIPPED", "detail": "HN 采集失败，未读取原文", "count": 0}
    result, secs = _timed(lambda: fetch_articles.run(hn))
    write_json(WORK_DIR / "articles.json", result)
    ok = [r for r in result.values() if r["status"] == "ok"]
    bad = [r["id"] for r in result.values() if r["status"] != "ok"]
    official = sum(1 for r in result.values() if r["official"])
    detail = f"{len(ok)}/{len(result)} 篇成功，官方来源 {official} 篇" + (f"，不可读 {len(bad)} 篇" if bad else "")
    tracelog.log("采集", "原文读取", "ok" if not bad else "warn", detail=detail, seconds=secs)
    return {"status": "ok", "code": "ARTICLE_UNREADABLE" if bad else None, "detail": detail,
            "count": len(result), "unreadable": bad, "seconds": secs}


# ---------------------------------------------------------------- 素材与摘要


def build_materials(week: Week, info: dict, report: dict) -> dict:
    def load(name, default):
        try:
            return read_json(WORK_DIR / name)
        except OSError:
            return default

    hn = load("hn.json", {"stories": []})
    articles = load("articles.json", {})
    for s in hn.get("stories", []):
        s["article"] = articles.get(str(s["id"]))
    return {
        "week": week.label,
        "range": f"{week.start}/{week.end}",
        "generated_at": dt.datetime.now(BJT).isoformat(timespec="seconds"),
        "sources": report["sources"],
        "data_reused": report["sources"].get("trendshift", {}).get("status") == "reused",
        "trendshift": load("trendshift.json", None),
        "hn": hn,
        "hf": load("hf.json", {"papers": []}),
    }


def hn_line(s: dict) -> str:
    a = s.get("article") or {}
    flags = []
    if a.get("official"):
        flags.append("官方")
    elif a.get("primary"):
        flags.append("一手")
    if a.get("published"):
        flags.append(f"原文 {a['published'][:10]}")
    if a and a.get("status") != "ok":
        flags.append("原文不可读")
    link = s.get("url") or s["hn_url"]
    gh = f" gh:{s['github_repo']}" if s.get("github_repo") else ""
    return (f"{s['points']} | {s['num_comments']} | {s['id']} | {truncate(s['title'], 90)} | {link}"
            + (f" [{'，'.join(flags)}]" if flags else "") + gh)


def build_digest(m: dict, info: dict, max_lines: int) -> str:
    ranking = load_config("ranking")
    article_min = ranking["articles"]["min_points"]
    head = [f"# 素材摘要 {m['week']}（{info.get('range_label', m['range'])}）",
            "> 完整数据在 /tmp/ai-weekly/materials.json。摘要之外的帖子：python3 collect_all.py show hn --offset N；"
            "单篇原文信息：python3 collect_all.py show article <HN id>。", "", "## 采集状态"]
    names = {"trendshift": "Trendshift 周榜", "hn": "HN", "hf": "Hugging Face", "articles": "原文读取"}
    for key, label in names.items():
        src = m["sources"].get(key)
        if src:
            code = f"（{src['code']}）" if src.get("code") else ""
            head.append(f"- {label}：{src['status']}{code}，{src.get('detail') or ''}")
    blocks = []
    ts = m.get("trendshift")
    if ts and ts.get("status") == "ok":
        lines = ["## GitHub 周榜（供 AI 判定）", "名次 | 仓库 | 本周 +star / +fork（天数）| 创建 | 描述 | 往期判定"]
        for r in ts["items"]:
            stars = "?" if r["week_stars"] is None else f"+{r['week_stars']}"
            forks = "?" if r["week_forks"] is None else f"+{r['week_forks']}"
            lines.append(f"{r['trendshift_position']} | {r['full_name']} | {stars} / {forks} ({r['days_covered']}d) | "
                         f"{(r['created_at'] or '')[:10]} | {truncate(r['description'], 70)}"
                         + (f" | {collect_trendshift.describe_prior(r.get('prior'))}" if r.get("prior") else ""))
        blocks.append(("trendshift", lines))
    stories = m["hn"].get("stories", [])
    high = [s for s in stories if s["points"] >= article_min]
    hinted = [s for s in high if ai_hint(s)]
    others = [s for s in high if not ai_hint(s)]
    blocks.append(("hn_ai", [f"## HN 不低于 {article_min} 分、标题含 AI 相关词（按分数；是否与 AI 相关仍需判断）",
                             "分数 | 评论 | id | 标题 | 原文链接 [官方/一手、原文日期、原文不可读]"]
                   + [hn_line(s) for s in hinted]))
    blocks.append(("hn_other", [f"## HN 不低于 {article_min} 分的其他帖子（按分数）"] + [hn_line(s) for s in others]))
    gh = [s for s in stories if s["points"] < article_min and s.get("github_repo")]
    if gh:
        blocks.append(("hn_gh", [f"## HN 50–{article_min - 1} 分的 GitHub 仓库链接"]
                       + [f"{s['points']} | {s['num_comments']} | {s['id']} | {s['github_repo']} | "
                          f"{truncate(s['title'], 70)}" for s in gh]))
    papers = (m.get("hf") or {}).get("papers", [])
    if papers:
        blocks.append(("hf", ["## Hugging Face 本周论文", "赞 | 链接 | 标题"]
                       + [f"{p['upvotes']} | {p['hf_url']} | {truncate(p['title'], 90)}" for p in papers]))
    # 超出行数上限时，依次截短"其他帖子"、AI 相关帖子、GitHub 链接，并注明省略了多少
    budget = max_lines - len(head) - sum(1 for _ in blocks)  # 每个区块前空一行
    total = sum(len(b) for _, b in blocks)
    for key in ("hn_other", "hn_ai", "hn_gh"):
        if total <= budget:
            break
        for i, (k, lines) in enumerate(blocks):
            if k != key:
                continue
            keep = max(2, len(lines) - (total - budget) - 1)
            if keep < len(lines):
                omitted = len(lines) - keep
                blocks[i] = (k, lines[:keep] + [f"……另有 {omitted} 条，用 collect_all.py show hn 查看"])
                total = sum(len(b) for _, b in blocks)
    out = head[:]
    for _, lines in blocks:
        out += [""] + lines
    return "\n".join(out[:max_lines]) + "\n"


def write_outputs(week: Week, info: dict, report: dict) -> None:
    m = build_materials(week, info, report)
    write_json(WORK_DIR / "materials.json", m)
    max_lines = load_config("runtime")["digest"]["max_lines"]
    (WORK_DIR / "digest.md").write_text(build_digest(m, info, max_lines), encoding="utf-8")
    write_json(WORK_DIR / "collect_report.json", report)


# ---------------------------------------------------------------- 命令


def run(only: str | None) -> int:
    info = read_json(WORK_DIR / "week.json")
    week = Week.parse(info["week"])
    try:
        report = read_json(WORK_DIR / "collect_report.json") if only else None
    except OSError:
        report = None
    report = report or {"week": week.label, "sources": {}}
    targets = [only] if only else list(SOURCES)
    for name in targets:
        if name == "trendshift":
            report["sources"]["trendshift"] = collect_trendshift_source(week, info)
        elif name == "hn":
            report["sources"]["hn"] = collect_hn_source(week)
        elif name == "hf":
            report["sources"]["hf"] = collect_hf_source(week)
        elif name == "articles":
            report["sources"]["articles"] = collect_articles_source()
    report["generated_at"] = dt.datetime.now(BJT).isoformat(timespec="seconds")
    write_outputs(week, info, report)

    statuses = {k: v["status"] for k, v in report["sources"].items()}
    if statuses.get("trendshift") == "not_ready":
        verdict = "trendshift_not_ready"
    elif any(s == "skipped" for s in statuses.values()):
        verdict = "degraded"
    else:
        verdict = "ok"
    print(f"COLLECT={verdict}")
    for k, v in report["sources"].items():
        print(f"- {k}：{v['status']}{'（' + v['code'] + '）' if v.get('code') else ''} {v.get('detail') or ''}")
    print(f"摘要：{WORK_DIR / 'digest.md'}（只读这一份即可）")
    return 3 if verdict == "trendshift_not_ready" else 0


def show(kind: str, args) -> int:
    m = read_json(WORK_DIR / "materials.json")
    if kind == "article":
        for s in m["hn"].get("stories", []):
            if str(s["id"]) == str(args.target):
                print(f"{s['points']} 分 {s['num_comments']} 评论 | {s['title']}\nHN：{s['hn_url']}\n原文：{s.get('url')}")
                for k, v in (s.get("article") or {}).items():
                    print(f"  {k}: {v}")
                return 0
        print(f"materials.json 里没有 HN id {args.target}")
        return 1
    stories = [s for s in m["hn"].get("stories", []) if s["points"] >= args.min]
    if args.grep:
        pat = re.compile(args.grep, re.IGNORECASE)
        stories = [s for s in stories if pat.search(s["title"]) or pat.search(s.get("url") or "")]
    for s in stories[args.offset: args.offset + args.limit]:
        print(hn_line(s))
    print(f"# 共 {len(stories)} 条，显示第 {args.offset + 1}–{min(len(stories), args.offset + args.limit)} 条")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=SOURCES, help="只重新采集一个数据源")
    sub = ap.add_subparsers(dest="cmd")
    sh = sub.add_parser("show", help="查看素材")
    sh.add_argument("kind", choices=["hn", "article"])
    sh.add_argument("target", nargs="?", help="show article 时为 HN id")
    sh.add_argument("--min", type=int, default=100, help="最低分数")
    sh.add_argument("--offset", type=int, default=0)
    sh.add_argument("--limit", type=int, default=40)
    sh.add_argument("--grep", help="按标题或链接过滤（正则）")
    args = ap.parse_args(argv)
    if args.cmd == "show":
        return show(args.kind, args)
    return run(args.only)


if __name__ == "__main__":
    sys.exit(main())
