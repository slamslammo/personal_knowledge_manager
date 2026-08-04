# -*- coding: utf-8 -*-
"""把 365 课程入口页同步为量化板块内的本地页面。

源页面: ../pam-video-captures/365-days-quant-finance/knowledge-map.html(Codex 维护,只读)
产物:   365天量化课程.html(结构与内容同源页一致,仅改写相对链接)

改写规则:
- ../../personal_knowledge_manager/量化交易/... -> 去前缀(实验报告等回到本板块相对路径)
- #锚点 / http(s) / mailto -> 保持不变
- 其余相对链接(课次目录、大纲审计等) -> 加 ../../pam-video-captures/365-days-quant-finance/ 前缀

课程更新后重新运行: python3 sync_course_map.py
"""
import re, pathlib

BASE = pathlib.Path(__file__).parent
SRC = BASE.parent.parent / "pam-video-captures" / "365-days-quant-finance" / "knowledge-map.html"
OUT = BASE / "365天量化课程.html"
PKM_PREFIX = "../../personal_knowledge_manager/量化交易/"
COURSE_PREFIX = "../../pam-video-captures/365-days-quant-finance/"

html = SRC.read_text(encoding="utf-8")

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
