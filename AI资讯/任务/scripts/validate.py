"""校验周报与榜单数据文件，提交前必须通过。

周报（结构见 ../templates/weekly.md）：
- 元数据：week、range、topics、orgs、repos 齐全；week 与 range 和报告周一致；
  topics 3–6 个且都在 config/topics.yaml 词表内；repos 都是 owner/repo。
- 标题：`# AI 周报 · {WEEK}（{M/D}–{M/D}）`，回溯模式下以"（回溯版）"结尾。
- 板块：七个二级标题齐全且顺序正确（洞察紧跟在 ① 之后）；各板块条目数在 config/ranking.yaml 规定的范围内。
- ④⑤ 是表格：④ 每行都有 HN 讨论链接，且不收 ②③ 已写的发布；⑤ 每行都有代表链接；单元格超长时给出警告。
- 洞察：每条（### 洞察 N：）都写了依据和必读。
- 链接：Markdown 链接目标都是 http(s) 地址；没有残留的模板占位符。
- 与数据文件一致：③ 的 `### N. [owner/repo]` 依次对应数据文件 rank 1..N；
  元数据 repos 等于数据文件中 Top 5 的集合；③ 只有编号项目，不写新晋、HN 热议等附加小节。

数据文件（格式见 ../方案.md 6.3 节）：字段齐全、类型正确、status 合法、rank 只给 top5 且从 1 连续编号。

质量门槛（对照采集素材 materials.json，见 ../方案.md 7.8 节；没有素材时跳过）：
- GATE_LINK_HOMEPAGE：② ④ 的链接不能只指向网站首页；
- GATE_NOT_OFFICIAL：② 条目引用的 HN 帖子链接的是官方或一手来源时，条目里必须有这篇原文的链接
  （规范化后相同，或同站点上互为路径前缀，也接受原文跳转后的地址和规范链接）；
  链接全部来自媒体（sources.yaml 的 media）的条目必须标注「仅媒体报道」；
- GATE_ARTICLE_LINK：④ 的文章链接与 HN 数据中该帖的原文链接一致，没有原文的帖子才用 HN 讨论链接；
- GATE_NUMBERS：② ④ 中的 HN 分数、评论数与采集数据一致（--tolerance 允许校验时的自然增长）。
错误信息以 [错误码] 开头。

降级版（元数据 quality: degraded）只检查结构、元数据、③ 与数据文件的一致性，不检查各板块条目数。

默认校验本次运行的产出（/tmp/ai-weekly/out 下）；没有时校验仓库中的文件。

退出码：0 通过（可能有警告）；1 有错误。

用法：
    python3 validate.py --week 2026-W43 [--backfill] [--materials 路径 | --no-materials]
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys

from common import OUT_DIR, REPO_DIR, WORK_DIR, is_homepage, load_config, matches_source, normalize_url, read_json
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
        self.codes: list[str] = []  # 质量门槛的错误码，按出现顺序去重

    def error(self, msg, code: str | None = None):
        self.errors.append(f"[{code}] {msg}" if code else msg)
        if code and code not in self.codes:
            self.codes.append(code)

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


def cell_text_len(cell: str) -> int:
    """单元格的可见字数：Markdown 链接只计链接文字，不计地址。"""
    return len(re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cell).strip())


def warn_long_cells(rep: Report, section: str, header: list[str], rows: list[list[str]], limit: int) -> None:
    for row in rows:
        for i, cell in enumerate(row):
            n = cell_text_len(cell)
            if n > limit:
                col = header[i] if i < len(header) else f"第 {i + 1} 列"
                where = f" 第 {row[0]} 行" if row[0].isdigit() else f"「{row[0]}」"
                rep.warn(f"{section}{where}的{col}有 {n} 字，建议不超过 {limit} 字")


def table_header(text: str) -> list[str]:
    """板块里第一张 Markdown 表格的表头。"""
    for line in text.splitlines():
        if line.startswith("|"):
            return [c.strip() for c in line.strip().strip("|").split("|")]
    return []


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
        "cell_chars": cfg["tables"]["cell_max_chars"],
    }


def count_in_range(rep, name, n, low, high):
    if not low <= n <= high:
        rep.warn(f"{name} 有 {n} 项，规则为 {low}–{high} 项")


def validate_report(text: str, week: Week, backfill: bool, data: dict | None,
                    vocabulary: set[str], rep: Report, limits: dict | None = None,
                    require_full: bool = False) -> None:
    import yaml

    for m in PLACEHOLDER_RE.finditer(text):  # 先查占位符：草稿里元数据的占位符也会让 YAML 解析失败
        line = text[: m.start()].count("\n") + 1
        rep.error(f"第 {line} 行残留占位符：{m.group(0)}")
    fm_text, body = split_front_matter(text)
    if fm_text is None:
        rep.error("周报开头缺少 --- 包围的元数据")
        return
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        rep.error(f"元数据不是合法 YAML：{e}")
        return
    # require_full：发布时声明了 full 就按完整周报校验，元数据自称降级也不能少内容
    degraded = fm.get("quality") == "degraded" and not require_full
    if fm.get("quality") not in (None, "degraded"):
        rep.error(f"元数据 quality 只能是 degraded（降级版）或不写：{fm.get('quality')!r}")
    for key in ("week", "range", "topics", "orgs", "repos"):
        if key not in fm:
            rep.error(f"元数据缺少 {key}")
    if fm.get("week") != week.label:
        rep.error(f"元数据 week 为 {fm.get('week')}，应为 {week.label}")
    if fm.get("range") != f"{week.start}/{week.end}":
        rep.error(f"元数据 range 为 {fm.get('range')}，应为 {week.start}/{week.end}")
    topics = fm.get("topics") or []
    if degraded and topics == []:
        pass  # 降级版没有做内容判断，主题可以为空
    elif not isinstance(topics, list) or not 3 <= len(topics) <= 6:
        rep.error(f"元数据 topics 应为 3–6 个，实际为 {topics!r}")
    else:
        unknown = [t for t in topics if t not in vocabulary]
        if unknown:
            rep.error(f"topics 不在 config/topics.yaml 词表内：{unknown}")
    orgs = fm.get("orgs") or []
    if degraded and orgs == []:
        pass
    elif not isinstance(orgs, list) or not orgs or not all(isinstance(o, str) and o for o in orgs):
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
    lim = limits or section_limits()
    sec = section_bodies(body)
    if degraded:
        validate_github_consistency(sec, repos, data, rep)
        return
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
    warn_long_cells(rep, "④", table_header(sec.get(ARTICLES, "")), articles, lim["cell_chars"])
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
    warn_long_cells(rep, "⑤", table_header(sec.get(TOPICS, "")), topics, lim["cell_chars"])
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
    validate_github_consistency(sec, repos, data, rep)


def validate_github_consistency(sec: dict, repos: list, data: dict | None, rep: Report) -> None:
    numbered = NUMBERED_RE.findall(sec.get(GITHUB, ""))
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


# ---------------------------------------------------------------- 质量门槛（对照采集素材）

HN_ID_RE = re.compile(r"news\.ycombinator\.com/item\?id=(\d+)")
HN_SCORE_RE = re.compile(r"\[[^\]]*?HN[^\]]*?([\d,]+)\s*分\]\(https?://news\.ycombinator\.com/item\?id=(\d+)\)")


def release_items(text: str) -> list[tuple[str, str]]:
    """② 的条目：(三级标题, 正文)。"""
    parts = re.split(r"^### (.+)$", text, flags=re.M)
    return [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]


def number_ok(written: int, actual: int, tolerance: float) -> bool:
    if tolerance <= 0:
        return written == actual
    return abs(actual - written) <= max(10, tolerance * actual)


def validate_sources(text: str, materials: dict, rep: Report, tolerance: float = 0.0,
                     sources: dict | None = None) -> None:
    """对照 materials.json 检查 ②④ 的链接与数字。tolerance 为校验时允许的分数自然变化比例。"""
    sources = sources or load_config("sources")
    official = (sources.get("official") or []) + (sources.get("primary") or [])
    media = sources.get("media") or []
    stories = {str(s["id"]): s for s in (materials.get("hn") or {}).get("stories", [])}
    if not stories:
        return
    # 同一链接的多次提交去重后只保留一条；校验时重新采集，保留的那条可能换了，被引用的 id 落在 dup_ids 里
    dups = {str(d): s for s in stories.values() for d in s.get("dup_ids", [])}
    _, body = split_front_matter(text)
    sec = section_bodies(body)

    def story_official(s):
        a = s.get("article") or {}
        return bool(s.get("url")) and (a.get("official") or a.get("primary") or matches_source(s["url"], official))

    for title, block in release_items(sec.get(RELEASES, "")):
        links = [u.strip() for u in LINK_RE.findall(block)]
        for u in links:
            if is_homepage(u):
                rep.error(f"② 「{title}」的链接只指向网站首页：{u}", "GATE_LINK_HOMEPAGE")
        non_hn = [u for u in links if "news.ycombinator.com" not in u]
        for hn_id in dict.fromkeys(HN_ID_RE.findall(block)):
            s = stories.get(hn_id) or dups.get(hn_id)
            if s and story_official(s) and not any(refers_to(u, s) for u in non_hn):
                rep.error(f"② 「{title}」引用的 HN 帖子原文是官方或一手来源，条目里没有这篇原文的链接：{s['url']}",
                          "GATE_NOT_OFFICIAL")
        if non_hn and all(matches_source(u, media) for u in non_hn) and "仅媒体报道" not in block:
            rep.error(f"② 「{title}」的链接都来自媒体，须标注「仅媒体报道」", "GATE_NOT_OFFICIAL")
        check_scores(block, f"② 「{title}」", stories, rep, tolerance)  # 只核对仍是保留条目的 id

    for row in table_rows(sec.get(ARTICLES, "")):
        cells = " | ".join(row)
        ids = HN_ID_RE.findall(cells)
        first = LINK_RE.search(cells)
        if first and is_homepage(first.group(1)):
            rep.error(f"④ 第 {row[0]} 行的文章链接只指向网站首页：{first.group(1)}", "GATE_LINK_HOMEPAGE")
        if not ids or not first:
            continue
        s, is_dup = stories.get(ids[-1]), False
        if s is None and ids[-1] in dups:
            s, is_dup = dups[ids[-1]], True  # 链接相同，但这次提交的分数和评论没有单独保存，不核对数字
        if s is None:
            rep.error(f"④ 第 {row[0]} 行的 HN 帖子 {ids[-1]} 不在本周采集数据里", "GATE_ARTICLE_LINK")
            continue
        expected = s.get("url") or s["hn_url"]
        if normalize_url(first.group(1)) != normalize_url(expected):
            rep.error(f"④ 第 {row[0]} 行的文章链接应为 HN 数据中的原文 {expected}，实际为 {first.group(1)}",
                      "GATE_ARTICLE_LINK")
        nums = [c.replace(",", "") for c in row if re.fullmatch(r"[\d,]+", c)]
        if len(nums) >= 2 and not is_dup:
            points, comments = int(nums[-2]), int(nums[-1])
            if not number_ok(points, s["points"], tolerance) or not number_ok(comments, s["num_comments"], tolerance):
                rep.error(f"④ 第 {row[0]} 行写的是 {points} 分、{comments} 评论，采集数据为 "
                          f"{s['points']} 分、{s['num_comments']} 评论", "GATE_NUMBERS")


def refers_to(link: str, story: dict) -> bool:
    """条目链接是否指向该帖子的原文：规范化后相同，或同站点上互为路径前缀（不含首页）。"""
    if is_homepage(link):
        return False
    a = story.get("article") or {}
    targets = {normalize_url(u) for u in (story.get("url"), a.get("final_url"), a.get("canonical")) if u}
    mine = normalize_url(link)
    for t in targets:
        if mine == t:
            return True
        short, long_ = sorted((mine, t), key=len)
        if long_.startswith(short + "/"):
            return True
    return False


def check_scores(block: str, where: str, stories: dict, rep: Report, tolerance: float) -> None:
    for written, hn_id in HN_SCORE_RE.findall(block):
        s = stories.get(hn_id)
        if s and not number_ok(int(written.replace(",", "")), s["points"], tolerance):
            rep.error(f"{where} 写的 HN 分数 {written} 与采集数据 {s['points']} 不一致", "GATE_NUMBERS")


def load_vocabulary() -> set[str]:
    return {t["name"] for t in load_config("topics")["topics"]}


def default_path(rel: str):
    """本次运行的产出优先（OUT_DIR 下），没有时用仓库里的文件。"""
    out = OUT_DIR / rel
    return out if out.exists() else REPO_DIR / rel


def run_checks(week: Week, backfill: bool = False, report_path=None, data_path=None,
               data_only: bool = False, materials: dict | None = None, tolerance: float = 0.0,
               require_full: bool = False) -> Report:
    """校验周报与数据文件，返回 Report。check_run.py、verify.py 也调用它。

    require_full：按完整周报校验，不被元数据里的 quality: degraded 放宽（校验声明为 full 的产出）。
    """
    rep = Report()
    data_path = data_path or default_path(weekly_data_path(week))
    data = None
    try:
        data = read_json(data_path)
        validate_data(data, week, rep)
    except FileNotFoundError:
        (rep.error if data_only else rep.warn)(f"没有数据文件：{data_path}")
    except ValueError as e:
        rep.error(f"数据文件不是合法 JSON：{e}")

    if not data_only:
        report_path = report_path or default_path(weekly_report_path(week))
        try:
            with open(report_path, encoding="utf-8") as f:
                text = f.read()
            validate_report(text, week, backfill, data, load_vocabulary(), rep, require_full=require_full)
            if materials:
                validate_sources(text, materials, rep, tolerance)
        except FileNotFoundError:
            rep.error(f"没有周报文件：{report_path}")
    return rep


def load_materials(path=None) -> dict | None:
    try:
        return read_json(path or WORK_DIR / "materials.json")
    except (OSError, ValueError):
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", required=True, help="报告周编号，YYYY-Www")
    ap.add_argument("--backfill", action="store_true", help="回溯模式：标题须以（回溯版）结尾")
    ap.add_argument("--report", help="默认为本次运行的产出，没有时为仓库中的周报")
    ap.add_argument("--data", help="默认为本次运行的产出，没有时为仓库中的数据文件")
    ap.add_argument("--data-only", action="store_true", help="只校验数据文件")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--materials", help="采集素材，默认 /tmp/ai-weekly/materials.json（存在时）")
    g.add_argument("--no-materials", action="store_true", help="不做对照素材的门槛检查")
    ap.add_argument("--tolerance", type=float, default=0.0, help="HN 数字允许的变化比例（校验时用）")
    args = ap.parse_args(argv)

    materials = None if args.no_materials else load_materials(args.materials)
    rep = run_checks(Week.parse(args.week), args.backfill, args.report, args.data, args.data_only,
                     materials, args.tolerance)
    for w in rep.warnings:
        print(f"警告：{w}")
    for e in rep.errors:
        print(f"错误：{e}")
    print("校验通过" if not rep.errors else f"校验失败：{len(rep.errors)} 个错误")
    if rep.codes:
        print("CODES=" + ",".join(rep.codes))
    return 0 if not rep.errors else 1


if __name__ == "__main__":
    sys.exit(main())
