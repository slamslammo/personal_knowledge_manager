"""可移植性检查：确认任务的执行文件不绑定某个智能体平台。

任务要能在 Claude Code、Codex 等任何能运行 shell、git、python3 并能联网搜索的智能体上运行。
平台相关的做法（定时、通知、GitHub 操作、分支命名）只允许写在部署指南里；
入口提示词、执行手册、模板、配置和脚本必须与平台无关。本脚本逐行检查这些文件：

- 不出现平台专属的工具名、标签或分支前缀（见 PLATFORM_TERMS）；
- 执行手册不让智能体直接用 git 提交、推送、变基或改分支（见 GIT_TERMS）：这些操作只能经 coord.py 完成，
  否则会绕过协调锁（见 coord.py）；
- 入口提示词只做引导：不引用执行手册的步骤编号，并指向执行手册与任务标记。

退出码：0 通过；1 有问题。开发时由单元测试自动运行。

用法：
    python3 check_portability.py
"""
from __future__ import annotations

import pathlib
import re
import sys

from common import CORE_DIR, REPO_DIR, TASK_DIR, WEEKLY_DIR

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
# 执行手册里不能出现的 git 写操作：提交与推送一律经 coord.py
GIT_TERMS = re.compile(r"git\s+(add|commit|push|pull|rebase|merge|reset|checkout|switch|branch|restore|stash)\b")
MANUAL_MARKER = "<!-- task: ai-weekly -->"
# 三套入口各自的手册任务标记；安全规则段必须逐字节一致。
ENTRY_MARKERS = {"routine-weekly.md": MANUAL_MARKER,
                 "routine-monthly.md": "<!-- task: ai-weekly-monthly -->",
                 "routine-quarterly.md": "<!-- task: ai-weekly-quarterly -->"}


def neutral_files(task_dir: pathlib.Path = TASK_DIR) -> list[pathlib.Path]:
    """必须与平台无关的文件。部署指南、方案、版本规划、README 可以描述具体平台，不在此列。"""
    files = []
    files += sorted((task_dir / "prompts").glob("*.md"))
    files += sorted((task_dir / "templates").glob("*.md"))
    files += sorted((task_dir / "config").glob("*.yaml"))
    for sub in ("core", "weekly"):
        files += sorted(p for p in (task_dir / sub).glob("*.py")
                        if p.name != "check_portability.py")
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
    manual = {"routine-weekly.md": "prompts/weekly.md",
              "routine-monthly.md": "prompts/monthly.md",
              "routine-quarterly.md": "prompts/quarterly.md"}.get(path.name, "prompts/weekly.md")
    if manual not in text:
        problems.append(f"{rel}：没有指向执行手册 {manual}")
    marker = ENTRY_MARKERS.get(path.name, MANUAL_MARKER)
    if marker not in text:
        problems.append(f"{rel}：没有要求核对执行手册的任务标记 {marker}")
    for no, line in enumerate(text.splitlines(), 1):
        m = re.search(r"第\s*\d+\s*步", line)
        if m:
            problems.append(f"{rel}:{no}：引用了执行手册的步骤编号「{m.group(0)}」，改流程时会被迫重贴提示词")
    return problems


def check_entry_safety_consistency(task_dir: pathlib.Path, base: pathlib.Path) -> list[str]:
    """三套入口的安全规则段必须逐字节一致，不能因改一处而放宽另一处。"""
    section = re.compile(r"(## 安全规则[^\n]*\n.*?)(?=\n## )", re.S)
    seen: dict[str, str] = {}
    problems = []
    for name in ENTRY_MARKERS:
        path = task_dir / "prompts" / name
        if not path.is_file():
            continue
        m = section.search(path.read_text(encoding="utf-8"))
        if not m:
            continue  # 测试构造的简化入口可没有安全规则段，只检查真实入口的一致性
        seen[name] = m.group(1)
    if len(seen) > 1 and len(set(seen.values())) != 1:
        problems.append("三套入口的安全规则段不一致：" + ", ".join(
            f"{n}={hash(s) & 0xffff:04x}" for n, s in seen.items()))
    return problems


def check_git_discipline(task_dir: pathlib.Path, base: pathlib.Path) -> list[str]:
    """执行手册（入口提示词以外的 prompts/*.md）不能让智能体直接做 git 写操作。"""
    problems = []
    for path in sorted((task_dir / "prompts").glob("*.md")):
        if path.name.startswith("routine-"):
            continue  # 入口提示词里的是禁止项（如禁止 git reset --hard），不是操作指引；三套入口一并跳过
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = GIT_TERMS.search(line)
            if m:
                problems.append(f"{path.relative_to(base)}:{no}：直接的 git 写操作「{m.group(0)}」，应改用 coord.py")
    return problems


# 分层守卫：core 不得依赖 weekly，只允许 weekly → core 单向引用。
WEEKLY_MODULES = re.compile(
    r"^\s*(?:from|import)\s+(collect_all|collect_trendshift|collect_hn|collect_hf|"
    r"fetch_articles|rank_github|draft|finalize|check_run|verify|deployment)\b",
    re.MULTILINE)


def check_layering(task_dir: pathlib.Path, base: pathlib.Path) -> list[str]:
    problems = []
    for path in sorted((task_dir / "core").glob("*.py")):
        for name in WEEKLY_MODULES.findall(path.read_text(encoding="utf-8")):
            problems.append(f"{path.relative_to(base)}：core 反向依赖 weekly 模块「{name}」")
    return problems


def run(task_dir: pathlib.Path = TASK_DIR) -> list[str]:
    # 检查真实仓库时用仓库根；测试的临时目录沿用其父级，避免 relative_to 失败
    base = REPO_DIR if task_dir == TASK_DIR else task_dir.parent.parent
    entries = [task_dir / "prompts" / name for name in ENTRY_MARKERS
               if (task_dir / "prompts" / name).is_file()]
    return (scan(neutral_files(task_dir), base) + check_git_discipline(task_dir, base)
            + sum((check_entry_prompt(e, base) for e in entries), [])
            + check_entry_safety_consistency(task_dir, base)
            + check_layering(task_dir, base))


def main() -> int:
    problems = run()
    for p in problems:
        print(f"问题：{p}")
    print("可移植性检查通过" if not problems else f"可移植性检查失败：{len(problems)} 处")
    return 0 if not problems else 1


if __name__ == "__main__":
    assert CORE_DIR.exists() and WEEKLY_DIR.exists()
    sys.exit(main())
