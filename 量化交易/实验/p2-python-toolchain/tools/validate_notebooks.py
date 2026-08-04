#!/usr/bin/env python
"""Execute every completed P2 notebook in a clean kernel and record the result."""

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
EXPECTED_NOTEBOOKS = {
    *(f"notebooks/{number}_" for number in range(31, 61)),
    *(f"labs/L{number}_" for number in range(1, 7)),
}


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
    executed = sum(cell.get("execution_count") is not None for cell in code_cells)
    return {
        "notebook": str(path.relative_to(ROOT)),
        "status": "pass",
        "code_cells": len(code_cells),
        "executed_code_cells": executed,
    }


def main():
    relative_names = [str(path.relative_to(ROOT)) for path in NOTEBOOKS]
    missing_prefixes = [
        prefix
        for prefix in sorted(EXPECTED_NOTEBOOKS)
        if not any(name.startswith(prefix) for name in relative_names)
    ]
    expected_count = 36
    if missing_prefixes or len(NOTEBOOKS) != expected_count:
        raise RuntimeError(
            "Expected lessons 31-60 plus L1-L6 "
            f"({expected_count} notebooks); found {len(NOTEBOOKS)}, "
            f"missing prefixes: {missing_prefixes}"
        )
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
        "# P2 Notebook 执行验收",
        "",
        f"- 状态：`{report['status']}`",
        f"- 环境：`{report['environment']}`",
        f"- Notebook：{report['notebook_count']}/{expected_count}",
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
