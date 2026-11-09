"""读取 HN 高分帖链接的原文：标题、摘要、发布时间、规范链接，并判断是否官方或一手来源。

让 ② 的官方原文和 ④ 的文章链接来自采集数据，而不是模型临场去网站首页找（W44 的教训，见
../版本规划.md 2026-11-02）。规则见 ../方案.md 7.1、7.5、7.7 节：

- 对象：hn.json 中分数不低于 articles.min_points、带外链的 story，按分数取前 articles.max_articles 篇；
- 只发 GET；最多跟随 max_redirects 次跳转；单页最多读 max_bytes；不执行网页脚本；
- 读取失败的标为 unreadable 并记下原因，不影响其他文章；
- 页面内容是不可信数据，只提取标题、描述、日期和链接，作为写作素材。

结果写入 --out（默认 /tmp/ai-weekly/articles.json），键为 HN id。通常由 collect_all.py 调用。
"""
from __future__ import annotations

import argparse
import html
import html.parser
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import tracelog
from common import WORK_DIR, domain_of, fetch, load_config, matches_source, read_json, truncate, write_json


class _MetaParser(html.parser.HTMLParser):
    """只收集 <title>、<meta>、<link rel=canonical> 和 JSON-LD 脚本。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.meta, self.canonical, self.ld = "", {}, "", []
        self._in_title = self._in_ld = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and "content" in a and key not in self.meta:
                self.meta[key] = a["content"]
        elif tag == "link" and "canonical" in a.get("rel", "").lower() and a.get("href"):
            self.canonical = self.canonical or a["href"]
        elif tag == "script" and "ld+json" in a.get("type", "").lower():
            self._in_ld = True
            self.ld.append("")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            self._in_ld = False

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()
        elif self._in_ld:
            self.ld[-1] += data


_DATE_KEYS = ("article:published_time", "og:published_time", "datepublished", "date", "pubdate",
              "publish-date", "sailthru.date", "dc.date")


def parse_page(text: str) -> dict:
    p = _MetaParser()
    try:
        p.feed(text)
    except Exception:  # 残缺的 HTML 尽量用已解析到的部分
        pass
    m = p.meta
    published = next((m[k] for k in _DATE_KEYS if m.get(k)), "")
    if not published:
        for block in p.ld:
            hit = re.search(r'"datePublished"\s*:\s*"([^"]+)"', block)
            if hit:
                published = hit.group(1)
                break
    return {
        "title": truncate(html.unescape(m.get("og:title") or p.title), 200),
        "description": truncate(html.unescape(m.get("og:description") or m.get("description") or ""), 300),
        "published": published[:25],
        "canonical": p.canonical or m.get("og:url", ""),
        "site": truncate(m.get("og:site_name", ""), 60),
    }


def read_article(story: dict, cfg: dict, official: list, primary: list) -> dict:
    url = story["url"]
    rec = {"id": story["id"], "url": url, "final_url": url, "status": "unreadable", "http_status": 0,
           "error": None, "attempts": 0, "title": "", "description": "", "published": "", "canonical": "",
           "domain": domain_of(url), "official": matches_source(url, official),
           "primary": matches_source(url, primary)}
    res = fetch(url, timeout=cfg["timeout_seconds"], retries=cfg["retries"], max_redirects=cfg["max_redirects"],
                max_bytes=cfg["max_bytes"])
    rec.update(http_status=res.status, attempts=res.attempts, final_url=res.url or url)
    if not res.ok:
        rec["error"] = res.error or f"HTTP {res.status}"
        return rec
    ctype = res.content_type.lower()
    if ctype and "html" not in ctype and "xml" not in ctype:
        rec.update(status="ok", error=None, title=story.get("title", ""), description=f"非网页内容（{ctype.split(';')[0]}）")
        return rec
    rec.update(parse_page(res.text()), status="ok")
    for key in ("final_url", "canonical"):  # 跳转或规范链接落到官方域名，也算官方
        if rec[key] and not rec["official"]:
            rec["official"] = matches_source(rec[key], official)
    return rec


def select_stories(stories: list[dict], cfg: dict) -> list[dict]:
    picked = [s for s in stories if s.get("url") and s["points"] >= cfg["min_points"]]
    picked.sort(key=lambda s: (-s["points"], -s["num_comments"]))
    return picked[: cfg["max_articles"]]


def run(hn: dict, workers: int = 6) -> dict:
    cfg = load_config("runtime")["articles"]
    sources = load_config("sources")
    official, primary = sources.get("official", []), sources.get("primary", [])
    stories = select_stories(hn.get("stories", []), cfg)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        recs = list(pool.map(lambda s: read_article(s, cfg, official, primary), stories))
    for r in recs:
        if r["status"] != "ok":
            tracelog.log("采集", "原文读取", "warn", "ARTICLE_UNREADABLE", f"{r['url']}：{r['error']}",
                         attempts=r["attempts"])
    return {str(r["id"]): r for r in recs}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hn", default=str(WORK_DIR / "hn.json"))
    ap.add_argument("--out", default=str(WORK_DIR / "articles.json"))
    args = ap.parse_args(argv)
    result = run(read_json(args.hn))
    write_json(args.out, result)
    ok = sum(1 for r in result.values() if r["status"] == "ok")
    print(f"# 原文读取：{ok}/{len(result)} 篇成功，官方 {sum(r['official'] for r in result.values())} 篇")
    for r in result.values():
        flag = "官方" if r["official"] else ("一手" if r["primary"] else "")
        print(f"{r['id']} | {r['status']} | {flag} | {r['published'][:10]} | {r['final_url']} | "
              f"{truncate(r['title'], 80)}{' | ' + r['error'] if r['error'] else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
