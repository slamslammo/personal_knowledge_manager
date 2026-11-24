"""段 A（三段式）：准备与采集。

把执行手册第 0 步的固定命令序列与第 1 步采集收进一个入口，模型只需跑一条命令：

    python3 资讯/AI/工程/weekly/prepare.py --platform workbuddy

成功后输出 `PREPARE=ok`，模型接手 AI 判定、排名、搜索与写作；
失败（含重试用尽）输出 `PREPARE=failed CODE=… STEP=…`，由调度方按入口规则告警。
本脚本不做任何判断性工作，也不写仓库工作区；恢复/协调语义仍由既有脚本给出。
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time

_CORE = pathlib.Path(__file__).resolve().parents[1] / "core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import paths  # noqa: E402
from common import REPO_DIR, read_json  # noqa: E402

CORE = _CORE
WEEKLY = pathlib.Path(__file__).resolve().parent
SIGNAL = re.compile(r"^([A-Z_]+)=(\S+)", re.MULTILINE)


def emit(signal: str, **fields) -> None:
    parts = [f"PREPARE={signal}"] + [f"{k.upper()}={v}" for k, v in fields.items()]
    print(" ".join(parts))


def signal(text: str, key: str) -> str | None:
    for k, v in SIGNAL.findall(text or ""):
        if k == key:
            return v
    return None


class Runner:
    def __init__(self, work: pathlib.Path, env: dict, timeout: int = 300):
        self.work = work
        self.env = env
        self.timeout = timeout

    def __call__(self, script: str, *args: str) -> subprocess.CompletedProcess:
        directory = CORE if (CORE / script).exists() else WEEKLY
        return subprocess.run([sys.executable, str(directory / script), *args],
                              env=self.env, capture_output=True, text=True,
                              timeout=self.timeout, cwd=str(REPO_DIR))

    def check(self, script: str, *args: str) -> subprocess.CompletedProcess:
        p = self(script, *args)
        if p.returncode != 0:
            raise RuntimeError(f"{script} 退出码 {p.returncode}: {(p.stderr or p.stdout or '').strip()[:200]}")
        return p


def prepare() -> int:
    ap = argparse.ArgumentParser(description="段 A：准备与采集")
    ap.add_argument("--platform", default="workbuddy", help="平台名（小写英文，写进运行记录）")
    target = ap.add_mutually_exclusive_group()
    target.add_argument("--week", help="回溯周 YYYY-Www")
    target.add_argument("--target-start", help="回溯周起止 YYYY-MM-DD（周一）")
    ap.add_argument("--test", action="store_true", help="TEST_RUN=1，传递给所有子进程")
    ap.add_argument("--collect-retries", type=int, default=3, help="周榜未就绪时的补采次数上限")
    ap.add_argument("--retry-wait", type=float, default=20.0, help="补采间隔秒数")
    ap.add_argument("--max-wait", type=int, default=None, help="可选轮询次数限制；默认使用 coord 的累计等待时限")
    args = ap.parse_args()

    if args.collect_retries < 0 or args.retry_wait < 0 or (args.max_wait is not None and args.max_wait < 0):
        ap.error("重试与等待参数须为非负数")
    env = dict(os.environ)
    if args.test:
        env["TEST_RUN"] = "1"
    work = paths.work_dir(REPO_DIR)
    try:
        paths.validate_work_dir(work, REPO_DIR)
    except ValueError as e:
        emit("failed", code="WORK_DIR_INVALID", step="workdir_check", detail=str(e))
        return 1
    run = Runner(work, env)

    week_args = []
    if args.week:
        week_args = ["--week", args.week]
    elif args.target_start:
        week_args = ["--target-start", args.target_start]
    meta = run.check("weeks.py", *week_args)
    info = json.loads(meta.stdout)
    week = info.get("week")
    if not isinstance(week, str) or not paths.WEEK_PATTERN.fullmatch(week):
        emit("failed", code="WEEK_UNKNOWN", step="weeks")
        return 1

    # 第 0 步：恢复分支（有本地协调记录时先尝试补交付）
    if (work / paths.FILES["coord"]).exists():
        previous_week = read_json(work / paths.FILES["coord"]).get("week")
        p = run("deployment.py", "resume")
        state = signal(p.stdout, "RESUME")
        if state == "completed" and p.returncode == 0:
            if previous_week == week:
                emit("resumed", detail="已用保存的沙箱提交补交付并核对结果，不重新采集")
                return 0
        elif state != "not_available" or p.returncode:
            emit("failed", code="RESUME_PENDING", step="resume",
                 detail="保留整个工作目录，按 env-bootstrap 补齐缺项后重试")
            return 1

    # 第 0 步：清理、凭据观察、环境自检、模式判定
    try:
        run.check("workdir.py", "clean")
        run.check("env_check.py", "ensure")
        plan = run.check("deployment.py", "plan")
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        emit("failed", code="PREPARE_ENV_FAILED", step="prepare", detail=str(e)[:200])
        return 1
    mode = signal(plan.stdout, "RUN_MODE")
    if mode not in ("production", "acceptance"):
        emit("failed", code="PLAN_INVALID", step="prepare")
        return 1

    (work / paths.FILES["week"]).write_text(meta.stdout, encoding="utf-8")

    # 第 0 步：飞书预检与协调启动
    run("feishu_sync.py", "preflight")
    try:
        started = run.check("deployment.py", "start", "--platform", args.platform)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        emit("failed", code="START_FAILED", step="deployment_start", detail=str(e)[:200])
        return 1
    action = signal(started.stdout, "ACTION")
    polls = 0
    while action == "wait":
        if args.max_wait is not None and polls >= args.max_wait:
            emit("deferred", code="ACTION_WAIT", step="wait", detail="本次等待次数已用完")
            return 0
        action = signal(run.check("coord.py", "wait").stdout, "ACTION")
        polls += 1
    if action == "verify":
        verified = run("verify.py", "--record")
        action = signal(verified.stdout, "ACTION")
        if verified.returncode or action not in ("done", "run", "exit"):
            emit("failed", code="VERIFY_FAILED", step="verify", detail=verified.stdout.strip()[-300:])
            return 1
        if action == "exit":
            emit("failed", code="VERIFY_NEEDS_HUMAN", step="verify", detail=verified.stdout.strip()[-300:])
            return 1
    if action in ("done", "exit"):
        emit("deferred", code=f"ACTION_{action.upper()}", step="coord")
        return 0
    if action != "run":
        emit("failed", code="ACTION_UNKNOWN", step="coord", detail=str(action))
        return 1

    for attempt in range(args.collect_retries + 1):
        if attempt:
            time.sleep(args.retry_wait)
        flags = ("--only", "trendshift") if attempt else ()
        collected = run("collect_all.py", *flags)
        state = signal(collected.stdout, "COLLECT")
        if collected.returncode == 0 and state in ("ok", "degraded"):
            break
        if collected.returncode != 3 or state != "trendshift_not_ready":
            emit("failed", code="COLLECT_FAILED", step="collect", detail=collected.stderr[:200])
            return 1
    else:
        emit("failed", code="COLLECT_TRENDSHIFT_NOT_READY", step="collect")
        return 1

    print(f"OUT_REPORT={work / 'out' / paths.report(week[:4], week)}")
    emit("ok", week=week, mode=mode, work=str(work),
         digest=str(work / paths.FILES["digest"]),
         detail="下一步：写 judgments.json → rank_github.py → 联网搜索与写稿 → deliver.py")
    return 0


def main() -> int:
    try:
        return prepare()
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        emit("failed", code="PREPARE_FAILED", step="prepare", detail=str(exc)[:200])
        return 1


if __name__ == "__main__":
    sys.exit(main())
