"""生成周报草稿：脚本能确定的部分由脚本填好，智能体只写判断和文字。规则见 ../方案.md 3、7.1 节。

脚本填写：元数据（week、range、repos）、标题、③ 的名次、链接、总 star 与本周增量、④ 的候选行
（原文链接、分数、评论数、HN 讨论链接）、数据说明的事实部分（由 finalize.py 生成）。
① 洞察 ② ⑤ 沿用 ../templates/weekly.md 的写法，占位符 {{...}} 留给智能体填写。
写作提示以 <!-- 草稿：... --> 注释给出，finalize.py 会删掉它们。

--degraded 生成降级版：文字部分写"本期降级，未生成"，元数据加 quality: degraded。智能体写作失败、
或质量门槛改了 3 轮仍有结构性错误时使用（../方案.md 3.10 节）；原稿先另存为 report.partial.md。

用法（collect_all.py 和 rank_github.py 之后）：
    python3 draft.py
    python3 draft.py --degraded --reason "写作中断"
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import shutil
import sys

import collect_all
import finalize
import tracelog
from common import OUT_DIR, TASK_DIR, WORK_DIR, load_config, read_json, truncate, write_json

TEMPLATE = TASK_DIR / "templates" / "weekly.md"
DEGRADED = "本期降级，未生成。"
CANDIDATES = 15


def template_sections() -> dict[str, str]:
    """模板正文按二级标题切分：{标题行: 内容}。"""
    text = TEMPLATE.read_text(encoding="utf-8")
    body = text.split("\n---\n", 1)[1] if text.startswith("---\n") else text
    parts, current = {}, None
    for line in body.splitlines(keepends=True):
        if line.startswith("## "):
            current = line.rstrip()
            parts[current] = ""
        elif current:
            parts[current] += line
    return parts


def md_text(s: str) -> str:
    """放进链接文字或表格的外部标题：去掉会破坏 Markdown 结构的字符。"""
    return truncate(s, 120).replace("|", "/").replace("[", "(").replace("]", ")")


def front_matter(info: dict, repos: list[str], degraded: bool) -> str:
    lines = ["---", f"week: {info['week']}", f"range: {info['start']}/{info['end']}"]
    if degraded:
        lines += ["topics: []", "orgs: []"]
    else:
        lines += ["topics: [{{3–6 个，取自 config/topics.yaml}}]",
                  "orgs: [{{本周涉及的主要公司和机构，写法见 config/topics.yaml 的 org_names}}]"]
    lines.append(f"repos: [{', '.join(repos)}]")
    if degraded:
        lines.append("quality: degraded")
    lines.append("---")
    return "\n".join(lines)


def github_section(info: dict, data: dict | None, materials: dict, degraded: bool) -> str:
    out = [f"> 口径：Trendshift {info['week']} 周榜中的 AI 项目，按报告周 7 天每日新增 star 之和排序。"
           "每日数据按 UTC 日期累计，比北京时间的报告周晚 8 小时。", ""]
    if data is None:
        detail = ((materials.get("sources") or {}).get("trendshift") or {}).get("detail") or "未采集"
        return "\n".join(out + [f"周榜未就绪：{detail}。", ""])
    descriptions = {i["full_name"]: i.get("description") for i in (materials.get("trendshift") or {}).get("items", [])}
    top = sorted((r for r in data["repos"] if r["status"] == "top5"), key=lambda r: r["rank"])
    if not degraded:
        out += ["<!-- 草稿：已在 ② 详细写过的项目，删掉下面三条要点，在一句话介绍后加\"，详见 ②\"。"
                "数字和链接由脚本填写，不要改。 -->", ""]
    for r in top:
        name = r["full_name"]
        total = "未获取" if r["total_stars"] is None else f"{r['total_stars']:,}"
        partial = f"，仅 {r['days_covered']} 天数据" if r["days_covered"] < 7 else ""
        out.append(f"### {r['rank']}. [{name}](https://github.com/{name})")
        out.append("")
        if degraded:
            desc = md_text(descriptions.get(name) or "") or "（无描述）"
            out += [f"总 star {total}（本周 +{r['week_stars']:,}{partial}）｜{desc}", ""]
            continue
        out.append(f"总 star {total}（本周 +{r['week_stars']:,}{partial}）｜{{{{一句话介绍}}}}")
        out.append("")
        hn = re.search(r"HN (\d+) 分：(\S+)", r.get("note") or "")
        if hn:
            out.append(f"<!-- 草稿：本项目上了 HN，{hn.group(1)} 分，{hn.group(2)} -->")
        out += ["- **本周为什么火**：{{触发事件：发版、上了 HN、爆款推文……}}",
                "- **传播分析**：{{相关文章与视频在讨论什么，附链接；找不到就如实写}}",
                "- **我们的判断**：{{适合谁用、成熟度、风险}}", ""]
    return "\n".join(out)


def article_candidates(materials: dict) -> list[dict]:
    min_points = load_config("ranking")["articles"]["min_points"]
    stories = [s for s in (materials.get("hn") or {}).get("stories", [])
               if s["points"] >= min_points and collect_all.ai_hint(s)]
    return stories[:CANDIDATES]


def articles_section(materials: dict, degraded: bool) -> str:
    if degraded:
        return DEGRADED + "\n"
    out = ["| # | 文章 | 摘要 | 传播原因 | 分数 | 评论 | 讨论 |", "| --- | --- | --- | --- | --- | --- | --- |", "",
           "<!-- 草稿：候选（HN 不低于 100 分、标题含 AI 相关词，按分数）。选 5 篇文章或讨论：不收发布帖，不收 ②③ 已写的，"
           "与 AI 无关的跳过。把整行复制到上面的表格，按顺序改编号，标题可以译成中文，填写摘要和传播原因；"
           "链接和数字不要改。原文不可读的，摘要据 HN 讨论和搜索结果写，并注明\"原文未能读取\"。"]
    for s in article_candidates(materials):
        a = s.get("article") or {}
        note = "原文不可读" if a and a.get("status") != "ok" else (f"原文 {a['published'][:10]}" if a.get("published") else "")
        hint = f"摘要｜{note}" if note else "摘要"
        link = s.get("url") or s["hn_url"]
        out.append(f"| {{{{n}}}} | [{md_text(s['title'])}]({link}) | {{{{{hint}}}}} | {{{{传播原因}}}} | "
                   f"{s['points']} | {s['num_comments']} | [HN]({s['hn_url']}) |")
    out.append("-->")
    return "\n".join(out) + "\n"


def releases_hint(materials: dict) -> str:
    """② 的线索：HN 上原文是官方或一手来源的高分帖，多数是发布本身。"""
    min_points = load_config("ranking")["articles"]["min_points"]
    rows = []
    for s in (materials.get("hn") or {}).get("stories", []):
        a = s.get("article") or {}
        if s["points"] >= min_points and (a.get("official") or a.get("primary")) and not s.get("github_repo"):
            date = f"，原文 {a['published'][:10]}" if a.get("published") else ""
            rows.append(f"{s['points']} 分 | {md_text(s['title'])} | 原文 {s['url']}{date} | HN {s['hn_url']}")
    if not rows:
        return ""
    return ("<!-- 草稿：② 的线索——HN 上原文为官方或一手来源的高分帖（多数是发布本身，原文链接可以直接用）。"
            "引用了这些 HN 帖子的条目，必须写对应的官方原文链接：\n" + "\n".join(rows[:20]) + "\n-->\n\n")


def build(info: dict, data: dict | None, materials: dict, degraded: bool, reason: str = "") -> str:
    sections = template_sections()
    repos = [r["full_name"] for r in sorted((r for r in (data or {}).get("repos", []) if r["status"] == "top5"),
                                            key=lambda r: r["rank"])]
    title = f"# AI 周报 · {info['week']}（{info['range_label']}）" + ("（回溯版）" if info["mode"] == "backfill" else "")
    parts = [front_matter(info, repos, degraded), "", title, ""]
    for heading, content in sections.items():
        parts.append(heading)
        parts.append("")
        if heading.startswith("## ③"):
            parts.append(github_section(info, data, materials, degraded))
        elif heading.startswith("## ④"):
            parts.append(articles_section(materials, degraded))
        elif heading.startswith("## 数据说明"):
            parts.append(finalize.AUTO_BEGIN)
            parts.append(finalize.AUTO_END)
            if degraded:
                parts += [f"- 降级与缺失：本期为降级版，文字分析未生成（{reason or '写作失败'}）。", "- 可疑内容：无", ""]
            else:
                parts += ["- 降级与缺失：{{无，或具体说明}}", "- 可疑内容：{{无，或\"可疑内容：<来源 URL>\"}}", ""]
        elif degraded:
            if heading.startswith("## ①"):
                parts.append("- **降级**：本期文字分析未能生成，以下只有脚本采集的数据。\n")
            else:
                parts.append(DEGRADED + "\n")
        else:
            body = content.strip("\n")
            if heading.startswith("## ②"):
                body = releases_hint(materials) + body
            parts.append(body + "\n")
    return finalize.apply("\n".join(parts), finalize.render_auto(WORK_DIR, data), strip_notes=degraded)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--degraded", action="store_true", help="生成降级版")
    ap.add_argument("--reason", default="", help="降级原因，写进数据说明")
    args = ap.parse_args(argv)
    info = read_json(WORK_DIR / "week.json")
    out = OUT_DIR / info["report_path"]
    data_path = OUT_DIR / info["data_path"]
    data = read_json(data_path) if data_path.exists() else None
    try:
        materials = read_json(WORK_DIR / "materials.json")
    except OSError:
        materials = {}
    if args.degraded and out.exists():
        shutil.copyfile(out, WORK_DIR / "report.partial.md")
    text = build(info, data, materials, args.degraded, args.reason)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    write_json(WORK_DIR / "draft.json", {"generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                                         "degraded": args.degraded, "report": str(out)})
    if args.degraded:
        tracelog.log("写作", "降级版", "warn", "WRITE_FAILED", args.reason or "写作失败，提交降级版")
    else:
        tracelog.log("写作", "草稿", "ok", detail=str(out))
    print(f"{'降级版' if args.degraded else '草稿'}已写入：{out}")
    if not args.degraded:
        n = text.count("{{")
        print(f"待填写的占位符 {n} 处；③ 的数字和链接、④ 的候选行已由脚本填好。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
