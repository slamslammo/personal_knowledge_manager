"""验证 P1 课程产物、Notebook 输出与课程总入口中的本地链接。"""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COURSE_ROOT = (
    PROJECT_ROOT.parents[3]
    / "pam-video-captures"
    / "365-days-quant-finance"
)
ENTRY_HTML = COURSE_ROOT / "knowledge-map.html"
MANIFEST_PATH = PROJECT_ROOT / "artifact-manifest.json"
EXPECTED_TITLE = "365 天量化金融课程学习整理"


class LinkCollector(HTMLParser):
    """收集静态页面中的链接，不执行任何脚本。"""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


def check_notebook(path: Path) -> list[str]:
    """检查 Notebook 是否已经执行，并拒绝异常输出和未解释警告。"""

    notebook = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    code_cells = [
        cell for cell in notebook.get("cells", []) if cell.get("cell_type") == "code"
    ]
    if not code_cells:
        problems.append("没有代码单元")

    for position, cell in enumerate(code_cells, start=1):
        if cell.get("execution_count") is None:
            problems.append(f"代码单元 {position} 未执行")
        for output in cell.get("outputs", []):
            if output.get("output_type") == "error":
                problems.append(
                    f"代码单元 {position} 报错：{output.get('ename', 'unknown')}"
                )
            text = output.get("text", [])
            if isinstance(text, str):
                text = [text]
            joined = "".join(text)
            if "Warning:" in joined or "Traceback (most recent call last)" in joined:
                problems.append(f"代码单元 {position} 含未清理的警告或回溯")
    return problems


def resolve_local_href(href: str) -> Path | None:
    """将课程入口中的相对文件链接解析为本地路径。"""

    if href.startswith(("#", "http://", "https://", "mailto:", "javascript:")):
        return None
    parsed = urlsplit(href)
    if parsed.scheme and parsed.scheme != "file":
        return None
    raw_path = unquote(parsed.path)
    if parsed.scheme == "file":
        return Path(raw_path)
    return (ENTRY_HTML.parent / raw_path).resolve()


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    failures: list[str] = []

    lessons = manifest["lessons"]
    labs = manifest["labs"]
    lesson_reports = [PROJECT_ROOT / lesson["report"] for lesson in lessons]
    lesson_notebooks = [
        PROJECT_ROOT / lesson["notebook"]
        for lesson in lessons
        if lesson["notebook"]
    ]
    lab_reports = [PROJECT_ROOT / lab["report"] for lab in labs]
    lab_notebooks = [PROJECT_ROOT / lab["notebook"] for lab in labs]

    expected_counts = {
        "knowledgeReports": 30,
        "lessonNotebooks": 25,
        "labs": 6,
    }
    if manifest.get("counts") != expected_counts:
        failures.append(
            f"manifest 数量不符：{manifest.get('counts')} != {expected_counts}"
        )

    artifact_groups = {
        "课程知识讲解": lesson_reports,
        "课程 Notebook": lesson_notebooks,
        "实验讲解": lab_reports,
        "实验 Notebook": lab_notebooks,
    }
    for label, paths in artifact_groups.items():
        for path in paths:
            if not path.is_file():
                failures.append(f"{label}缺失：{path}")

    notebook_problems: dict[str, list[str]] = {}
    for notebook_path in lesson_notebooks + lab_notebooks:
        problems = check_notebook(notebook_path)
        if problems:
            notebook_problems[str(notebook_path)] = problems
            failures.extend(f"{notebook_path.name}：{problem}" for problem in problems)

    entry_source = ENTRY_HTML.read_text(encoding="utf-8")
    if f"<title>{EXPECTED_TITLE}</title>" not in entry_source:
        failures.append("页面 <title> 未使用新标题")
    if f"<h1>{EXPECTED_TITLE}</h1>" not in entry_source:
        failures.append("页面主标题未使用新标题")

    for module_number in range(1, 7):
        if f'id="p1-m{module_number}"' not in entry_source:
            failures.append(f"课程入口缺少 P1 M{module_number} 区块")

    parser = LinkCollector()
    parser.feed(entry_source)
    local_targets = {
        target
        for href in parser.links
        if (target := resolve_local_href(href)) is not None
    }
    broken_links = sorted(
        str(path) for path in local_targets if not path.exists()
    )
    failures.extend(f"入口本地链接失效：{path}" for path in broken_links)

    result = {
        "status": "passed" if not failures else "failed",
        "title": EXPECTED_TITLE,
        "entry": str(ENTRY_HTML),
        "counts": {
            "knowledgeReports": len(lesson_reports),
            "lessonNotebooks": len(lesson_notebooks),
            "labReports": len(lab_reports),
            "labNotebooks": len(lab_notebooks),
            "executedNotebooks": len(lesson_notebooks) + len(lab_notebooks),
            "localLinksChecked": len(local_targets),
            "brokenLocalLinks": len(broken_links),
        },
        "notebookProblems": notebook_problems,
        "failures": failures,
    }
    (PROJECT_ROOT / "artifact-validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# P1 课程产物验证",
        "",
        f"- 状态：**{result['status']}**",
        f"- 页面标题：{EXPECTED_TITLE}",
        f"- 知识讲解：{len(lesson_reports)}/30",
        f"- 课程 Notebook：{len(lesson_notebooks)}/25",
        f"- 综合实验：{len(lab_reports)}/6",
        f"- 已执行 Notebook：{len(lesson_notebooks) + len(lab_notebooks)}/31",
        f"- 已检查本地链接：{len(local_targets)}",
        f"- 失效本地链接：{len(broken_links)}",
        "",
    ]
    if failures:
        lines.extend(["## 问题", "", *[f"- {failure}" for failure in failures]])
    else:
        lines.extend(
            [
                "## 结论",
                "",
                "P1 课程产物、Notebook 执行状态、页面标题和课程入口本地链接均通过检查。",
            ]
        )
    (PROJECT_ROOT / "artifact-validation.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
