#!/usr/bin/env python
"""Export every executed P2 notebook to a browser-readable HTML report."""

from __future__ import annotations

from pathlib import Path
import re

import nbformat
from nbconvert import HTMLExporter


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)


def remove_unavailable_icon_fonts(body: str) -> str:
    """Remove nbconvert font declarations whose relative assets are not exported.

    The classic template inlines Bootstrap and Font Awesome CSS but does not copy
    their old ``../components/.../fonts`` directories.  These reports do not use
    either icon class, so keeping those declarations only creates broken local
    resource requests in the browser.
    """

    for font_family in ("Glyphicons Halflings", "FontAwesome"):
        pattern = (
            r"@font-face\s*\{\s*font-family:\s*'"
            + re.escape(font_family)
            + r"';.*?\}"
        )
        body = re.sub(pattern, "", body, flags=re.DOTALL)
    return body


def main():
    notebook_paths = sorted((ROOT / "notebooks").glob("*.ipynb"))
    notebook_paths += sorted((ROOT / "labs").glob("*.ipynb"))
    exporter = HTMLExporter(template_name="classic")
    exporter.exclude_input_prompt = False
    exporter.exclude_output_prompt = False

    for notebook_path in notebook_paths:
        notebook = nbformat.read(notebook_path, as_version=4)
        body, _ = exporter.from_notebook_node(notebook)
        body = remove_unavailable_icon_fonts(body)
        output_path = REPORTS / f"{notebook_path.stem}.html"
        output_path.write_text(body, encoding="utf-8")
        print(f"wrote {output_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
