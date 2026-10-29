"""校验周报与榜单数据文件，提交前必须通过。

周报（结构见 ../templates/weekly.md）：
- 元数据：week、range、topics、orgs、repos 齐全；week 与 range 和报告周一致；
  topics 3–6 个且都在 config/topics.yaml 词表内；repos 都是 owner/repo。
- 标题：`# AI 周报 · {WEEK}（{M/D}–{M/D}）`，回溯模式下以"（回溯版）"结尾。
- 板块：七个二级标题齐全且顺序正确（洞察紧跟在 ① 之后）；各板块条目数在 config/ranking.yaml 规定的范围内。
- ④⑤ 是表格：④ 每行都有 HN 讨论链接，且不收 ②③ 已写的发布；⑤ 每行都有代表链接。
- 洞察：每条（### 洞察 N：）都写了依据和必读。
- 链接：Markdown 链接目标都是 http(s) 地址；没有残留的模板占位符。
- 与数据文件一致：③ 的 `### N. [owner/repo]` 依次对应数据文件 rank 1..N；
  元数据 repos 等于数据文件中 Top 5 的集合；③ 只有编号项目，不写新晋、HN 热议等附加小节。

数据文件（格式见 ../方案.md 6.3 节）：字段齐全、类型正确、status 合法、rank 只给 top5 且从 1 连续编号。

退出码：0 通过（可能有警告）；1 有错误。

用法：
    python3 validate.py --week 2026-W43 [--backfill]
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys

from common import REPO_DIR, load_config, normalize_url, read_json
from weeks import Week, weekly_data_path, weekly_report_path

OVERVIEW = "## ① 本周概览"
INSIGHTS = "## 洞察"
RELEASES = "## ② 新发布与技术 Top 5"
GITHUB = "## ③ GitHub AI 项目热度 Top 5"
ARTICLES = "## ④ 传播文章 Top 5"
TOPICS = "## ⑤ 热点话题 Top 5"
NOTES = "## 数据说明"
SECTIONS = [OVERVIEW, INSIGHTS, RELEASES, GITHUB, ARTICLES, TOPICS, NOTES]  # 周报中的出现顺序
STATUSES = {"top5", "new", "candidate", "hn", "excluded", "non_ai"}
REPO_RE = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
LINK_RE = re.compile(r"\]\(([^)]*)\)")
PLACEHOLDER_RE = re.compile(r"\{\{|\}\}|TODO|待填写")
NUMBERED_RE = re.compile(r"^### (\d+)\. \[([^\]]+)\]\(", re.M)


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


# ---------------------------------------------------------------- 数据文件


def validate_data(data: dict, week: Week, rep: Report) -> None:
    for key in ("week", "range", "generated_at", "repos"):
        if key not in data:
            rep.error(f"数据文件缺少字段 {key}")
    if data.get("week") != week.label:
        rep.error(f"数据文件 week 为 {data.get('week')}，应为 {week.label}")
    if data.get("range") != f"{week.start}/{week.end}":
        rep.error(f"数据文件 range 为 {data.get('range')}，应为 {week.start}/{week.end}")
    try:
        dt.datetime.fromisoformat(data.get("generated_at", ""))
    except ValueError:
        rep.error(f"数据文件 generated_at 不是 ISO 8601 时间：{data.get('generated_at')}")
    repos = data.get("repos")
    if not isinstance(repos, list):
        rep.error("数据文件 repos 应为列表")
        return
    fields = {
        "full_name": str, "trendshift_position": (int, type(None)), "rank": (int, type(None)),
        "week_stars": (int, type(None)), "week_forks": (int, type(None)), "days_covered": int,
        "total_stars": (int, type(None)), "created_at": (str, type(None)), "status": str, "note": str,
    }
    ranks = []
    seen = set()
    for i, r in enumerate(repos):
        where = f"数据文件 repos[{i}]"
        for key, typ in fields.items():
            if key not in r:
                rep.error(f"{where} 缺少字段 {key}")
            elif not isinstance(r[key], typ) or isinstance(r[key], bool):
                rep.error(f"{where}.{key} 类型不对：{r[key]!r}")
        name = r.get("full_name", "")
        if not REPO_RE.match(str(name)):
            rep.error(f"{where}.full_name 不是 owner/repo：{name}")
        if name in seen:
            rep.error(f"数据文件中 {name} 重复")
        seen.add(name)
        if r.get("status") not in STATUSES:
            rep.error(f"{where}.status 不合法：{r.get('status')}")
        if r.get("status") == "top5":
            ranks.append(r.get("rank"))
        elif r.get("rank") is not None:
            rep.error(f"{where} 不在 Top 5，rank 应为 null")
        if isinstance(r.get("days_covered"), int) and not 0 <= r["days_covered"] <= 7:
            rep.error(f"{where}.days_covered 应在 0–7")
    if sorted(ranks) != list(range(1, len(ranks) + 1)):
        rep.error(f"Top 5 的 rank 应从 1 连续编号，实际为 {sorted(ranks)}")
    if len(ranks) > 5:
        rep.error(f"Top 5 有 {len(ranks)} 项")
    for status, limit in (("new", 3), ("hn", 3)):
        n = sum(1 for r in repos if r.get("status") == status)
        if n > limit:
            rep.error(f"status 为 {status} 的有 {n} 项，上限 {limit}")


# ---------------------------------------------------------------- 周报


def split_front_matter(text: str) -> tuple[str | None, str]:
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return None, text
    return text[4:end], text[end + 5:]


def section_bodies(body: str) -> dict[str, str]:
    """按二级标题切分正文。"""
    parts: dict[str, str] = {}
    current = None
    for line in body.splitlines(keepends=True):
        if line.startswith("## "):
            current = line.rstrip()
            parts[current] = ""
        elif current:
            parts[current] += line
    return parts


def table_rows(text: str) -> list[list[str]]:
    """板块里第一张 Markdown 表格的数据行（去掉表头和分隔行），每行拆成单元格。"""
    rows = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("|"):
            in_table = True
            rows.append(line)
        elif in_table:
            break
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows[1:]]
    return [c for c in cells if not all(re.fullmatch(r":?-{3,}:?", x) for x in c)]


def section_limits() -> dict:
    """各板块条目数，取自 config/ranking.yaml。"""
    cfg = load_config("ranking")
    return {
        "overview": (cfg["overview"]["min"], cfg["overview"]["max"]),
        "releases": (1, cfg["releases"]["max_items"]),
        "articles": cfg["articles"]["top_n"],
        "topics": cfg["topics"]["target"],
        "insights": (cfg["insights"]["min"], cfg["insights"]["max"]),
        "reads": tuple(cfg["insights"]["reads_per_insight"]),
    }


def count_in_range(rep, name, n, low, high):
    if not low <= n <= high:
        rep.warn(f"{name} 有 {n} 项，规则为 {low}–{high} 项")


def validate_report(text: str, week: Week, backfill: bool, data: dict | None,
                    vocabulary: set[str], rep: Report, limits: dict | None = None) -> None:
    import yaml

    fm_text, body = split_front_matter(text)
    if fm_text is None:
        rep.error("周报开头缺少 --- 包围的元数据")
        return
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        rep.error(f"元数据不是合法 YAML：{e}")
        return
    for key in ("week", "range", "topics", "orgs", "repos"):
        if key not in fm:
            rep.error(f"元数据缺少 {key}")
    if fm.get("week") != week.label:
        rep.error(f"元数据 week 为 {fm.get('week')}，应为 {week.label}")
    if fm.get("range") != f"{week.start}/{week.end}":
        rep.error(f"元数据 range 为 {fm.get('range')}，应为 {week.start}/{week.end}")
    topics = fm.get("topics") or []
    if not isinstance(topics, list) or not 3 <= len(topics) <= 6:
        rep.error(f"元数据 topics 应为 3–6 个，实际为 {topics!r}")
    else:
        unknown = [t for t in topics if t not in vocabulary]
        if unknown:
            rep.error(f"topics 不在 config/topics.yaml 词表内：{unknown}")
    orgs = fm.get("orgs") or []
    if not isinstance(orgs, list) or not orgs or not all(isinstance(o, str) and o for o in orgs):
        rep.error(f"元数据 orgs 应为非空字符串列表：{orgs!r}")
    repos = fm.get("repos")
    if repos is None:
        repos = []
    if not isinstance(repos, list) or not all(isinstance(r, str) and REPO_RE.match(r) for r in repos):
        rep.error(f"元数据 repos 应为 owner/repo 列表：{repos!r}")
        repos = []

    title = next((ln for ln in body.splitlines() if ln.strip()), "")
    expected = f"# AI 周报 · {week.label}（{week.range_label}）" + ("（回溯版）" if backfill else "")
    if title != expected:
        rep.error(f"标题应为「{expected}」，实际为「{title}」")

    headings = [ln.rstrip() for ln in body.splitlines() if ln.startswith("## ")]
    present = [h for h in headings if h in SECTIONS]
    missing = [s for s in SECTIONS if s not in headings]
    if missing:
        rep.error(f"缺少板块：{missing}")
    if present != [s for s in SECTIONS if s in present]:
        rep.error(f"板块顺序不对：{present}")
    extra = [h for h in headings if h not in SECTIONS]
    if extra:
        rep.error(f"多出的二级标题：{extra}")

    for target in LINK_RE.findall(body):
        if not re.match(r"^https?://\S+$", target.strip()):
            rep.error(f"链接不是 http(s) 地址：({target})")
    for m in PLACEHOLDER_RE.finditer(text):
        line = text[: m.start()].count("\n") + 1
        rep.error(f"第 {line} 行残留占位符：{m.group(0)}")

    lim = limits or section_limits()
    sec = section_bodies(body)
    overview = re.findall(r"^- ", sec.get(OVERVIEW, ""), re.M)
    count_in_range(rep, "① 本周概览", len(overview), *lim["overview"])

    s2 = sec.get(RELEASES, "")
    releases = re.findall(r"^### ", s2, re.M)
    if len(releases) > lim["releases"][1]:
        rep.error(f"② 有 {len(releases)} 条，上限 {lim['releases'][1]}")
    else:
        count_in_range(rep, "② 新发布与技术", len(releases), *lim["releases"])

    s3 = sec.get(GITHUB, "")
    numbered = NUMBERED_RE.findall(s3)
    if [int(n) for n, _ in numbered] != list(range(1, len(numbered) + 1)):
        rep.error(f"③ 的项目编号应从 1 连续：{[n for n, _ in numbered]}")
    if len(numbered) > 5:
        rep.error(f"③ 有 {len(numbered)} 个编号项目，上限 5")
    extra_subsections = [h for h in re.findall(r"^### (.+)$", s3, re.M) if not re.match(r"\d+\. \[", h)]
    if extra_subsections:
        rep.error(f"③ 只写 Top 5，多出的小节：{extra_subsections}")

    covered = {normalize_url(u) for u in LINK_RE.findall(s2)}
    covered |= {normalize_url(f"https://github.com/{name}") for _, name in numbered}
    articles = table_rows(sec.get(ARTICLES, ""))
    if len(articles) > lim["articles"]:
        rep.error(f"④ 有 {len(articles)} 篇，上限 {lim['articles']}")
    else:
        count_in_range(rep, "④ 文章", len(articles), lim["articles"], lim["articles"])
    if [r[0] for r in articles] != [str(i) for i in range(1, len(articles) + 1)]:
        rep.error(f"④ 的排名应从 1 连续：{[r[0] for r in articles]}")
    for r in articles:
        row = " | ".join(r)
        if "news.ycombinator.com/item?id=" not in row:
            rep.error(f"④ 第 {r[0]} 行缺少 HN 讨论链接")
        first = LINK_RE.search(row)
        if first and normalize_url(first.group(1)) in covered:
            rep.error(f"④ 第 {r[0]} 行是 ②③ 已写的发布，④ 只收文章与讨论：{first.group(1)}")

    topics = table_rows(sec.get(TOPICS, ""))
    if len(topics) > lim["topics"]:
        rep.error(f"⑤ 有 {len(topics)} 个话题，上限 {lim['topics']}")
    else:
        count_in_range(rep, "⑤ 热点话题", len(topics), lim["topics"], lim["topics"])
    for r in topics:
        n_links = len(LINK_RE.findall(" | ".join(r)))
        if n_links == 0:
            rep.error(f"⑤「{r[0]}」没有代表链接")
        elif n_links < 2:
            rep.warn(f"⑤「{r[0]}」只有 {n_links} 个代表链接，规则为 2–3 个")

    insights = re.split(r"^### 洞察 \d+[：:]", sec.get(INSIGHTS, ""), flags=re.M)[1:]
    count_in_range(rep, "洞察", len(insights), *lim["insights"])
    for i, block in enumerate(insights, 1):
        if "**依据**" not in block:
            rep.error(f"洞察 {i} 没有写依据")
        if "**必读**" not in block:
            rep.error(f"洞察 {i} 没有写必读")
            continue
        reads = len(LINK_RE.findall(block[block.index("**必读**"):]))
        if reads == 0:
            rep.error(f"洞察 {i} 的必读没有链接")
        else:
            count_in_range(rep, f"洞察 {i} 的必读", reads, *lim["reads"])

    notes = sec.get(NOTES, "")
    if "搜索" not in notes:
        rep.error("数据说明里没有写联网搜索次数")

    if data is None:
        if numbered:
            rep.error("③ 有排名项目，但没有对应的数据文件")
        return
    top = sorted((r for r in data.get("repos", []) if r.get("status") == "top5"), key=lambda r: r["rank"])
    listed = [name for _, name in numbered]
    expected_top = [r["full_name"] for r in top]
    if listed != expected_top:
        rep.error(f"③ 的项目顺序 {listed} 与数据文件 Top 5 {expected_top} 不一致")
    meta = {r["full_name"] for r in data.get("repos", []) if r.get("status") == "top5"}
    if set(repos) != meta:
        rep.error(f"元数据 repos 应为数据文件中的 Top 5：缺 {sorted(meta - set(repos))}，"
                  f"多 {sorted(set(repos) - meta)}")


def load_vocabulary() -> set[str]:
    return {t["name"] for t in load_config("topics")["topics"]}


def run_checks(week: Week, backfill: bool = False, report_path=None, data_path=None,
               data_only: bool = False) -> Report:
    """校验仓库里（或指定路径）的周报与数据文件，返回 Report。check_run.py 也调用它。"""
    rep = Report()
    data_path = data_path or REPO_DIR / weekly_data_path(week)
    data = None
    try:
        data = read_json(data_path)
        validate_data(data, week, rep)
    except FileNotFoundError:
        (rep.error if data_only else rep.warn)(f"没有数据文件：{data_path}")
    except ValueError as e:
        rep.error(f"数据文件不是合法 JSON：{e}")

    if not data_only:
        report_path = report_path or REPO_DIR / weekly_report_path(week)
        try:
            with open(report_path, encoding="utf-8") as f:
                text = f.read()
            validate_report(text, week, backfill, data, load_vocabulary(), rep)
        except FileNotFoundError:
            rep.error(f"没有周报文件：{report_path}")
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", required=True, help="报告周编号，YYYY-Www")
    ap.add_argument("--backfill", action="store_true", help="回溯模式：标题须以（回溯版）结尾")
    ap.add_argument("--report", help="默认为仓库中的周报路径")
    ap.add_argument("--data", help="默认为仓库中的数据文件路径")
    ap.add_argument("--data-only", action="store_true", help="只校验数据文件")
    args = ap.parse_args(argv)

    rep = run_checks(Week.parse(args.week), args.backfill, args.report, args.data, args.data_only)
    for w in rep.warnings:
        print(f"警告：{w}")
    for e in rep.errors:
        print(f"错误：{e}")
    print("校验通过" if not rep.errors else f"校验失败：{len(rep.errors)} 个错误")
    return 0 if not rep.errors else 1


if __name__ == "__main__":
    sys.exit(main())
