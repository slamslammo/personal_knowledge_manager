#!/usr/bin/env python
"""Execute every P1 notebook in the shared pkm-quant kernel."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import nbformat
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
REPORT_JSON = ROOT / "notebook-validation.json"
REPORT_MD = ROOT / "notebook-validation.md"
NOTEBOOKS = sorted((ROOT / "notebooks").glob("*.ipynb")) + sorted(
    (ROOT / "labs").glob("*.ipynb")
)
EXPECTED_LESSONS = {*range(4, 25), *range(26, 30)}


def execute_notebook(path: Path) -> dict:
    notebook = nbformat.read(path, as_version=4)
    client = NotebookClient(
        notebook,
        timeout=180,
        kernel_name="pkm-quant",
        allow_errors=False,
        record_timing=True,
    )
    prior = Path.cwd()
    try:
        os.chdir(ROOT)
        client.execute()
    finally:
        os.chdir(prior)
    nbformat.write(notebook, path)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    return {
        "notebook": str(path.relative_to(ROOT)),
        "status": "pass",
        "code_cells": len(code_cells),
        "executed_code_cells": sum(
            cell.get("execution_count") is not None for cell in code_cells
        ),
    }


def main() -> None:
    lesson_numbers = {
        int(path.name.split("_", 1)[0]) for path in ROOT.joinpath("notebooks").glob("*.ipynb")
    }
    lab_ids = {path.name.split("_", 1)[0] for path in ROOT.joinpath("labs").glob("*.ipynb")}
    if lesson_numbers != EXPECTED_LESSONS:
        raise RuntimeError(
            f"P1 逐课 Notebook 不完整：expected={sorted(EXPECTED_LESSONS)}, "
            f"actual={sorted(lesson_numbers)}"
        )
    if lab_ids != {f"L{i}" for i in range(1, 7)}:
        raise RuntimeError(f"P1 综合实验不完整：{sorted(lab_ids)}")
    if len(NOTEBOOKS) != 31:
        raise RuntimeError(f"应有 31 个 Notebook，实际 {len(NOTEBOOKS)}")

    results = []
    for path in NOTEBOOKS:
        print(f"executing {path.relative_to(ROOT)}", flush=True)
        results.append(execute_notebook(path))
    report = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "environment": "pkm-quant",
        "status": "pass",
        "notebook_count": len(results),
        "results": results,
    }
    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# P1 Notebook 执行验收",
        "",
        f"- 状态：`{report['status']}`",
        f"- 环境：`{report['environment']}`",
        f"- Notebook：{report['notebook_count']}/31",
        f"- 时间：{report['validated_at']}",
        "",
        "| Notebook | 代码单元 | 已执行 | 结果 |",
        "|---|---:|---:|---|",
    ]
    for result in results:
        lines.append(
            f"| `{result['notebook']}` | {result['code_cells']} | "
            f"{result['executed_code_cells']} | {result['status']} |"
        )
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

