"""段 A（三段式）：准备与采集。

把执行手册第 0 步的固定命令序列与第 1 步采集收进一个入口，模型只需跑一条命令：

    python3 资讯/AI/工程/weekly/prepare.py --platform workbuddy

成功后输出 `PREPARE=ok`，模型接手 AI 判定、排名、搜索与写作；
失败（含重试用尽）输出 `PREPARE=failed CODE=… STEP=…`，由调度方按入口规则告警。
本脚本不做任何判断性工作，也不写仓库工作区；恢复/协调语义仍由既有脚本给出。
"""
from __future__ import annotations

import argparse
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
from common import REPO_DIR, load_config  # noqa: E402

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


def main() -> int:
    ap = argparse.ArgumentParser(description="段 A：准备与采集")
    ap.add_argument("--platform", default="workbuddy", help="平台名（小写英文，写进运行记录）")
    ap.add_argument("--week", help="回溯周 YYYY-Www")
    ap.add_argument("--target-start", help="回溯周起止 YYYY-MM-DD（周一）")
    ap.add_argument("--test", action="store_true", help="TEST_RUN=1，传递给所有子进程")
    ap.add_argument("--collect-retries", type=int, default=3, help="周榜未就绪时的补采次数上限")
    ap.add_argument("--retry-wait", type=float, default=20.0, help="补采间隔秒数")
    ap.add_argument("--max-wait", type=int, default=5, help="协调 wait 的最多轮询次数")
    args = ap.parse_args()

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

    # 第 0 步：恢复分支（有本地协调记录时先尝试补交付）
    if (work / paths.FILES["coord"]).exists():
        p = run("deployment.py", "resume")
        state = signal(p.stdout, "RESUME")
        if state == "completed":
            emit("resumed", detail="已用保存的沙箱提交补交付并核对结果，不重新采集")
            return 0
        if state == "pending":
            emit("failed", code="RESUME_PENDING", step="resume",
                 detail="保留整个工作目录，按 env-bootstrap 补齐缺项后重试")
            return 1
        # not_available / 错误 → 按手册进入新运行准备，保留现场

    # 第 0 步：清理、凭据观察、环境自检、模式判定
    try:
        run.check("workdir.py", "clean")
        run("credential_probe.py", "--resume")   # 缺历史观察只报 pending，不阻断
        run.check("env_check.py", "ensure")
        plan = run.check("deployment.py", "plan")
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        emit("failed", code="PREPARE_ENV_FAILED", step="prepare", detail=str(e)[:200])
        return 1
    mode = signal(plan.stdout, "RUN_MODE") or "unknown"

    # 第 0 步：周编号与本次产出路径
    week_args = []
    if args.week:
        week_args = ["--week", args.week]
    elif args.target_start:
        week_args = ["--target-start", args.target_start]
    try:
        meta = run.check("weeks.py", *week_args)
        (work / paths.FILES["week"]).write_text(meta.stdout, encoding="utf-8")
        env_out = run.check("weeks.py", *week_args, "--format", "env").stdout
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        emit("failed", code="WEEK_UNKNOWN", step="weeks", detail=str(e)[:200])
        return 1
    week = signal(env_out, "WEEK") or signal(meta.stdout, "week") or "unknown"

    # 第 0 步：飞书预检与协调启动
    run("feishu_sync.py", "preflight")
    try:
        started = run.check("deployment.py", "start", "--platform", args.platform)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        emit("failed", code="START_FAILED", step="deployment_start", detail=str(e)[:200])
        return 1
    action = signal(started.stdout, "ACTION")
    for _ in range(args.max_wait):
        if action != "wait":
            break
        waited = run("coord.py", "wait")
        action = signal(waited.stdout, "ACTION")
    if action == "run":
        pass
    elif action in ("verify", "exit", "blocked", "error"):
        emit("deferred", code=f"ACTION_{action.upper()}", step="deployment_start",
             detail="按入口/手册的对应分支处理，不进入采集")
        return 0
    else:
        emit("failed", code="ACTION_UNKNOWN", step="deployment_start",
             detail="无动作行或未知值，保留现场")
        return 1

    # 第 1 步：采集；周榜未就绪的穿插重试收进脚本内置等待
    for attempt in range(args.collect_retries + 1):
        try:
            p = run.check("collect_all.py")
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            emit("failed", code="COLLECT_FAILED", step="collect", detail=str(e)[:200])
            return 1
        state = signal(p.stdout, "COLLECT")
        if state != "trendshift_not_ready":
            break
        if attempt == args.collect_retries:
            emit("failed", code="COLLECT_TRENDSHIFT_NOT_READY", step="collect",
                 detail="补采次数用尽，按手册写『周榜未就绪』或转降级，不无限重试")
            return 1
        time.sleep(args.retry_wait)
        try:
            retry = run.check("collect_all.py", "--only", "trendshift")
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            emit("failed", code="COLLECT_FAILED", step="collect_retry", detail=str(e)[:200])
            return 1
        if signal(retry.stdout, "COLLECT") != "trendshift_not_ready":
            break

    emit("ok", week=week, mode=mode, work=str(work),
         digest=str(work / paths.FILES["digest"]),
         detail="下一步：写 judgments.json → rank_github.py → 联网搜索与写稿 → deliver.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
