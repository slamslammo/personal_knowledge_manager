#!/usr/bin/env python
"""Export executed P1 lesson and lab notebooks to browser-readable HTML."""

from __future__ import annotations

from pathlib import Path
import re

import nbformat
from nbconvert import HTMLExporter


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)


def remove_unavailable_icon_fonts(body: str) -> str:
    for font_family in ("Glyphicons Halflings", "FontAwesome"):
        pattern = (
            r"@font-face\s*\{\s*font-family:\s*'"
            + re.escape(font_family)
            + r"';.*?\}"
        )
        body = re.sub(pattern, "", body, flags=re.DOTALL)
    return body


def add_report_identity(body: str) -> str:
    marker = """
<style>
.p1-report-banner{margin:12px auto 22px;max-width:1140px;padding:12px 16px;
border-left:4px solid #c98a12;background:#fff8e8;color:#4c3a13}
.p1-report-banner strong{display:block}
</style>
<div class="p1-report-banner"><strong>P1 量化基础 · 课程知识讲解</strong>
数据、公式、代码、结果含义和方法边界共同构成课程产物；模拟数据不代表真实证券收益。</div>
"""
    return body.replace("<body>", "<body>" + marker, 1)


def main() -> None:
    notebook_paths = sorted((ROOT / "notebooks").glob("*.ipynb"))
    notebook_paths += sorted((ROOT / "labs").glob("*.ipynb"))
    exporter = HTMLExporter(template_name="classic")
    exporter.exclude_input_prompt = False
    exporter.exclude_output_prompt = False
    for notebook_path in notebook_paths:
        notebook = nbformat.read(notebook_path, as_version=4)
        body, _ = exporter.from_notebook_node(notebook)
        body = add_report_identity(remove_unavailable_icon_fonts(body))
        output_path = REPORTS / f"{notebook_path.stem}.html"
        output_path.write_text(body, encoding="utf-8")
        print(f"wrote {output_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

