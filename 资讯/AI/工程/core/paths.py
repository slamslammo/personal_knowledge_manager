"""仓库产出、运行时目录和共享文件名。

运行时目录通常由仓库检出位置推导。可用 workdir.py print 查看生效路径。
"""
from __future__ import annotations

import os
import pathlib
import re

# 板块根目录（相对仓库根）：资讯/{板块名}
BOARD_REL = "资讯/AI"

# 榜单数据与运行记录所在目录。
DATA_REL = f"{BOARD_REL}/数据"

# 周报 / 月报 / 季报同样收在 数据/ 下。
OUTPUT_REL = DATA_REL


def report(iso_year: int | str, week: str) -> str:
    return f"{OUTPUT_REL}/周报/{iso_year}/{week}.md"


def data(week: str) -> str:
    return f"{DATA_REL}/github-weekly/{week}.json"


def state(week: str) -> str:
    return f"{DATA_REL}/运行记录/{week}.json"


def monthly(year: int, month: int) -> str:
    return f"{OUTPUT_REL}/月报/{year}/{year}-{month:02d}.md"


def quarterly(year: int, quarter: int) -> str:
    return f"{OUTPUT_REL}/季报/{year}/{year}-Q{quarter}.md"


def period_report(period: str) -> str:
    if re.fullmatch(r"[0-9]{4}-Q[1-4]", period):
        return quarterly(int(period[:4]), int(period[-1]))
    if re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", period):
        return monthly(int(period[:4]), int(period[-2:]))
    raise ValueError(f"非法月季报期间：{period}")


# coord.py 的写入白名单正则；迁移时随 OUTPUT_REL 自动更新。
MONTHLY_RE = re.escape(OUTPUT_REL) + r"/月报/\d{4}/\d{4}-\d{2}\.md$"
QUARTERLY_RE = re.escape(OUTPUT_REL) + r"/季报/\d{4}/\d{4}-Q[1-4]\.md$"


# ---------------------------------------------------------------------------
# 运行时目录：由仓库检出位置推导，不依赖 OS 临时目录，也不由智能体命名。
# ---------------------------------------------------------------------------

RUNTIME_DIR_NAME = ".ai-weekly"      # 落在仓库检出目录的父级（仓库外）
WORK_DIR_NAME = "work"               # 单次运行的 scratch
ARCHIVE_DIR_NAME = "archive"         # 按周归档，一周一份，只读证据
STATE_DIR_NAME = "state"             # 跨运行状态，clean 不清
LOGS_DIR_NAME = "logs"               # 运行日志

WEEK_PATTERN = re.compile(r"^\d{4}-W\d{2}$")

# 固定文件名。脚本读写中间数据一律从这里取，不追加周后缀、不按次数编号。
FILES = {
    "week": "week.json",
    "coord": "coord.json",
    "deployment": "deployment.json",
    "materials": "materials.json",
    "digest": "digest.md",
    "collect_report": "collect_report.json",
    "articles": "articles.json",
    "hn": "hn.json",
    "hf": "hf.json",
    "draft": "draft.json",
    "judgments": "judgments.json",
    "rework": "rework.json",
    "checks": "checks.txt",
    "trace": "trace.jsonl",
    "searches": "searches.txt",
    "notification": "notification.txt",
    "notification_short": "notification-short.txt",
    "feishu_content": "feishu-content.md",
    "feishu": "feishu.json",
    "feishu_mode": "feishu-mode.json",
    "feishu_delivery_check": "feishu-delivery-check.json",
    "feishu_notify_receipt": "feishu-notify-receipt.json",
    "annual_index": "annual-index.json",
    "manifest": "MANIFEST.json",
}

# workdir.py 清理时保留这些文件，避免丢失防重状态或交付收据。
CLEAN_PRESERVE = frozenset({
    FILES["feishu"],
    FILES["feishu_delivery_check"],
    FILES["feishu_notify_receipt"],
    FILES["annual_index"],
    FILES["deployment"],
})

# clean 只移除本项目生成的内容。兼容路径即使配错，也保留目录里的其他文件。
CLEAN_SCRATCH = (set(FILES.values()) - CLEAN_PRESERVE) | {
    "out", "verify", "sandbox.git", "coord.index", "rank_report.json", "report.partial.md",
    "trendshift.json", "acceptance.json", "resume.json", "feishu-readback.md",
    "notification-failure.txt",
}

# 归档只留不可再生的关键证据；采集原文、素材、摘要等可再生数据不归档。
ARCHIVE_EVIDENCE = (
    FILES["checks"],
    FILES["trace"],
    FILES["searches"],
    FILES["notification"],
    FILES["notification_short"],
    FILES["feishu_content"],
    FILES["feishu"],
    FILES["feishu_delivery_check"],
    FILES["feishu_notify_receipt"],
)


def repo_root(start: pathlib.Path) -> pathlib.Path:
    """从脚本位置向上找含 .git 的目录；归档副本无 .git 时按板块结构匹配。"""
    for parent in (start, *start.parents):
        if (parent / ".git").exists():
            return parent
    for parent in (start, *start.parents):
        expected = parent.joinpath(*pathlib.PurePosixPath(BOARD_REL).parts, "工程", "core")
        if expected.resolve() == start.resolve():
            return parent
    raise RuntimeError("无法定位仓库根目录：需要 Git 检出或保留项目目录结构的归档")


def runtime_root(repo: pathlib.Path | None = None,
                 env: dict | None = None) -> pathlib.Path:
    """运行时根。

    优先级：AI_WEEKLY_HOME（部署级显式覆盖）> 由 REPO_DIR 推导的默认根。
    默认落在仓库检出目录的父级，因此不在仓库内、不入库、工作空间可见。
    """
    env = os.environ if env is None else env
    override = env.get("AI_WEEKLY_HOME")
    if override:
        return pathlib.Path(override).expanduser().resolve()
    if repo is None:
        repo = repo_root(pathlib.Path(__file__).resolve().parent)
    return (pathlib.Path(repo).resolve().parent / RUNTIME_DIR_NAME).resolve()


def work_dir(repo: pathlib.Path | None = None,
             env: dict | None = None) -> pathlib.Path:
    """本次运行的工作目录。

    AI_WEEKLY_TMP 是过渡期兼容入口（旧任务与测试仍在使用），优先级最高；
    PR 合并、旧任务停用后随测试一并删除。正常路径恒为 runtime_root()/work。
    """
    env = os.environ if env is None else env
    legacy = env.get("AI_WEEKLY_TMP")
    if legacy:
        return pathlib.Path(legacy).expanduser().resolve()
    return runtime_root(repo, env) / WORK_DIR_NAME


# 报告类型与期间的合法取值，供 period_work_dir 校验。
PERIOD_TYPES = ("weekly", "monthly", "quarterly")
PERIOD_PATTERN = {
    "weekly": re.compile(r"^\d{4}-W\d{2}$"),
    "monthly": re.compile(r"^\d{4}-\d{2}$"),
    "quarterly": re.compile(r"^\d{4}-Q[1-4]$"),
}


def period_work_dir(report_type: str, period: str,
                    repo: pathlib.Path | None = None,
                    env: dict | None = None) -> pathlib.Path:
    """按报告类型与期间隔离的工作子根；子根内部仍复用 FILES 固定文件名。

    AI_WEEKLY_TMP 覆盖父目录，期间子目录仍按类型和期间隔离。
    非法类型或期间格式显式失败，不静默落到别处。
    """
    if report_type not in PERIOD_TYPES:
        raise ValueError(f"非法报告类型：{report_type!r}，应为 {PERIOD_TYPES}")
    if not PERIOD_PATTERN[report_type].fullmatch(period or ""):
        raise ValueError(f"非法期间：{period!r}，类型 {report_type} 格式不符")
    env = os.environ if env is None else env
    legacy = env.get("AI_WEEKLY_TMP")
    if legacy:
        return pathlib.Path(legacy).expanduser().resolve() / report_type / period
    return runtime_root(repo, env) / WORK_DIR_NAME / report_type / period


def archive_dir(week: str, repo: pathlib.Path | None = None,
                env: dict | None = None) -> pathlib.Path:
    """按周归档目录，一周一份；周编号格式不合法时显式失败。"""
    if not WEEK_PATTERN.fullmatch(week or ""):
        raise ValueError(f"非法周编号：{week!r}，应为 YYYY-Www")
    return runtime_root(repo, env) / ARCHIVE_DIR_NAME / week


def state_dir(repo: pathlib.Path | None = None,
              env: dict | None = None) -> pathlib.Path:
    return runtime_root(repo, env) / STATE_DIR_NAME


def logs_dir(repo: pathlib.Path | None = None,
             env: dict | None = None) -> pathlib.Path:
    return runtime_root(repo, env) / LOGS_DIR_NAME


def validate_work_dir(work: pathlib.Path, repo: pathlib.Path) -> None:
    """校验工作目录，非法即报错停止，不静默回退 /tmp。"""
    work = pathlib.Path(work).resolve()
    repo = pathlib.Path(repo).resolve()
    if str(work) in ("", "/", "."):
        raise ValueError(f"工作目录非法：{work}")
    if work in repo.parents or work == pathlib.Path.home().resolve() or (work / ".git").exists():
        raise ValueError(f"工作目录不能是检出目录的上级、用户主目录或另一仓库：{work}")
    if work == repo or repo in work.parents:
        raise ValueError(f"工作目录不得落在仓库内：{work}（仓库 {repo}）")
    for parent in (work, *work.parents):
        if parent.exists() and parent.is_symlink() and repo in parent.resolve().parents:
            raise ValueError(f"工作目录不得通过符号链接指向仓库内：{work}")


def archive_report_path(week: str, iso_year: int | str) -> str:
    """归档目录内的周报副本相对路径，文件名与仓库内完全一致。"""
    if not WEEK_PATTERN.fullmatch(week or ""):
        raise ValueError(f"非法周编号：{week!r}")
    return f"{week}.md"
