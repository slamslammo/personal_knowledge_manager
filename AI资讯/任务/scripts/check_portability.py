"""可移植性检查：确认任务的执行文件不绑定某个智能体平台。

任务要能在 Claude Code、Codex 等任何能运行 shell、git、python3 并能联网搜索的智能体上运行。
平台相关的做法（定时、通知、GitHub 操作、分支命名）只允许写在部署指南里；
入口提示词、执行手册、模板、配置和脚本必须与平台无关。本脚本逐行检查这些文件：

- 不出现平台专属的工具名、标签或分支前缀（见 PLATFORM_TERMS）；
- 入口提示词只做引导：不引用执行手册的步骤编号，并指向执行手册与任务标记。

退出码：0 通过；1 有问题。开发时由单元测试自动运行。

用法：
    python3 check_portability.py
"""
from __future__ import annotations

import pathlib
import re
import sys

from common import SCRIPTS_DIR, TASK_DIR

# 平台专属写法：(正则, 说明)。内容层面的词（如主题"MCP 与工具调用"）不在此列。
PLATFORM_TERMS = [
    (r"PushNotification", "平台专属的通知工具名"),
    (r"routine_summary", "平台专属的通知标签"),
    (r"GitHub MCP|MCP 工具", "平台专属的 GitHub 工具"),
    (r"(?<![\w-])claude/", "平台专属的分支前缀"),
    (r"Claude Code|Claude 云端|云端会话|云端定时任务", "平台名称"),
    (r"(?i)\bcodex\b", "平台名称"),
    (r"已挂载", "平台专属的仓库挂载概念"),
]
MANUAL_MARKER = "<!-- task: ai-weekly -->"


def neutral_files(task_dir: pathlib.Path = TASK_DIR) -> list[pathlib.Path]:
    """必须与平台无关的文件。部署指南、方案、版本规划、README 可以描述具体平台，不在此列。"""
    files = []
    files += sorted((task_dir / "prompts").glob("*.md"))
    files += sorted((task_dir / "templates").glob("*.md"))
    files += sorted((task_dir / "config").glob("*.yaml"))
    files += sorted(p for p in (task_dir / "scripts").glob("*.py") if p.name != "check_portability.py")
    return files


def scan(files: list[pathlib.Path], base: pathlib.Path) -> list[str]:
    problems = []
    for path in files:
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for pattern, why in PLATFORM_TERMS:
                m = re.search(pattern, line)
                if m:
                    problems.append(f"{path.relative_to(base)}:{no}：{why}「{m.group(0)}」")
    return problems


def check_entry_prompt(path: pathlib.Path, base: pathlib.Path) -> list[str]:
    """入口提示词只做引导：指向执行手册与任务标记，不引用手册内部的步骤编号。"""
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(base)
    problems = []
    if "prompts/weekly.md" not in text:
        problems.append(f"{rel}：没有指向执行手册 prompts/weekly.md")
    if MANUAL_MARKER not in text:
        problems.append(f"{rel}：没有要求核对执行手册的任务标记 {MANUAL_MARKER}")
    for no, line in enumerate(text.splitlines(), 1):
        m = re.search(r"第\s*\d+\s*步", line)
        if m:
            problems.append(f"{rel}:{no}：引用了执行手册的步骤编号「{m.group(0)}」，改流程时会被迫重贴提示词")
    return problems


def run(task_dir: pathlib.Path = TASK_DIR) -> list[str]:
    base = task_dir.parent.parent
    return scan(neutral_files(task_dir), base) + check_entry_prompt(task_dir / "prompts" / "routine-prompt.md", base)


def main() -> int:
    problems = run()
    for p in problems:
        print(f"问题：{p}")
    print("可移植性检查通过" if not problems else f"可移植性检查失败：{len(problems)} 处")
    return 0 if not problems else 1


if __name__ == "__main__":
    assert SCRIPTS_DIR.exists()
    sys.exit(main())
