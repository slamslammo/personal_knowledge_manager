# -*- coding: utf-8 -*-
"""把 365 课程入口页同步为量化板块内的本地页面。

源页面: ../pam-video-captures/365-days-quant-finance/knowledge-map.html(Codex 维护,只读)
产物:   365天量化课程.html(结构与内容同源页一致,仅改写相对链接)

改写规则:
- ../../personal_knowledge_manager/量化交易/... -> 去前缀(实验报告等回到本板块相对路径)
- #锚点 / http(s) / mailto -> 保持不变
- 其余相对链接(课次目录、大纲审计等) -> 加 ../../pam-video-captures/365-days-quant-finance/ 前缀

版式调整(2026-08-04 按用户要求):
- 顶部快捷跳转改为全部阶段列表(编号 + 标题 + 课次范围,从各阶段区块自动提取)
- 去掉「查看映射审计」「结构化大纲数据」按钮
- 去掉统计卡片区(数字跟不上课程变化)

课程更新后重新运行: python3 sync_course_map.py
"""
import re, pathlib

BASE = pathlib.Path(__file__).parent
SRC = BASE.parent.parent / "pam-video-captures" / "365-days-quant-finance" / "knowledge-map.html"
OUT = BASE / "365天量化课程.html"
PKM_PREFIX = "../../personal_knowledge_manager/量化交易/"
COURSE_PREFIX = "../../pam-video-captures/365-days-quant-finance/"

html = SRC.read_text(encoding="utf-8")

# --- 版式调整:先改结构,再改链接 ---
# 1) 从阶段区块提取 编号/标题/课次范围,生成完整跳转列表
phases = []
for m in re.finditer(
    r'<section class="phase[^"]*" id="(P\d+)"[\s\S]*?<span class="phase-name">(.*?)</span>\s*'
    r'<span class="phase-summary">([^<]*)</span>', html):
    code, name, summary = m.group(1), m.group(2), m.group(3)
    name = re.sub(r"<small>.*?</small>", "", name).strip()
    d = re.search(r"Day\s*(\d+)[–-](\d+)", summary)
    rng = f"{int(d.group(1))}–{int(d.group(2))}" if d else ""
    phases.append((code, name, rng))
nav = "".join(
    f'<a href="#{c}" style="align-self:flex-start">{c} {n}' + (f" · {r}" if r else "") + "</a>"
    for c, n, r in phases)
html, n_nav = re.subn(
    r'<nav class="hero-links">.*?</nav>',
    '<nav class="hero-links" style="display:flex;flex-direction:column;align-items:flex-start;gap:8px">%s</nav>' % nav,
    html, flags=re.S)
assert n_nav == 1 and len(phases) >= 11, f"hero 导航替换异常: nav={n_nav}, phases={len(phases)}"

# 2) 精简导语:去掉 P1/P2 组织方式的说明
html = html.replace("P1 以策略报告和能力矩阵反向组织量化基础，P2 以可运行 Notebook 组织 Python 工具链；逐课材料和模块综合实验均回到同一课程入口。",
                    "逐课材料和模块综合实验均回到同一课程入口。")

# 3) 去掉统计卡片区(<div class="stats">...到进度热力图之前)
i = html.find('<div class="stats">')
j = html.find('<div class="progre', i)
assert 0 < i < j, "stats 区块定位失败"
html = html[:i] + html[j:]

def rewrite(m):
    url = m.group(1)
    if url.startswith(PKM_PREFIX):
        return 'href="%s"' % url[len(PKM_PREFIX):]
    if url.startswith(("#", "http:", "https:", "mailto:")):
        return m.group(0)
    return 'href="%s%s"' % (COURSE_PREFIX, url)

html, n = re.subn(r'href="([^"]*)"', rewrite, html)
html = html.replace("<!doctype html>",
    "<!doctype html>\n<!-- 由 sync_course_map.py 从 pam-video-captures/365-days-quant-finance/knowledge-map.html 同步生成,不要手工编辑;课程更新后重新运行脚本 -->", 1)
OUT.write_text(html, encoding="utf-8")
print(f"生成 {OUT.name} ✓ ;改写链接: {n} 个")
