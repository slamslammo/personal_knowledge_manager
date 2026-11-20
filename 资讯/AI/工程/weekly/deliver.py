"""段 B（三段式）：检查、发布、交付与归档。

模型完成写稿后只需跑一条命令：

    python3 资讯/AI/工程/weekly/deliver.py --week 2026-W43

检查未通过时输出 `DELIVER=rework CODES=…`，模型按手册返工表只改未通过的部分后重跑；
重试用尽或任一环节失败时生成失败通知文件并尽力调用飞书通知（平台无 lark-cli 时输出文本），
定位与修复归开发流程。既有 CLI 全部保留兼容。
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys

_CORE = pathlib.Path(__file__).resolve().parents[1] / "core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import paths  # noqa: E402
from common import REPO_DIR  # noqa: E402

CORE = _CORE
WEEKLY = pathlib.Path(__file__).resolve().parent
SHA = re.compile(r"\b[0-9a-f]{40}\b")


def emit(signal: str, **fields) -> None:
    print(" ".join([f"DELIVER={signal}"] + [f"{k.upper()}={v}" for k, v in fields.items()]))


def value(text: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}=(\S+)", text or "", re.MULTILINE)
    return m.group(1) if m else None


class Runner:
    def __init__(self, work: pathlib.Path, env: dict, timeout: int = 300):
        self.work, self.env, self.timeout = work, env, timeout

    def __call__(self, script: str, *args: str) -> subprocess.CompletedProcess:
        directory = CORE if (CORE / script).exists() else WEEKLY
        return subprocess.run([sys.executable, str(directory / script), *args],
                              env=self.env, capture_output=True, text=True,
                              timeout=self.timeout, cwd=str(REPO_DIR))


def failure_notice(work: pathlib.Path, week: str, code: str, step: str, detail: str) -> pathlib.Path:
    path = work / "notification-failure.txt"
    path.write_text(f"【AI周报 W{week[-2:]}｜失败】{code}。\n"
                    f"停在：{step}\n原因：{detail}\n已完成：见 {work / 'checks.txt'}\n",
                    encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="段 B：检查、发布与交付")
    ap.add_argument("--week", required=True, help="ISO 周 YYYY-Www")
    ap.add_argument("--test", action="store_true", help="TEST_RUN=1，传递给所有子进程")
    ap.add_argument("--platform", default="workbuddy")
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
    note = work / paths.FILES["notification"]
    short = work / paths.FILES["notification_short"]

    def fail(code: str, step: str, detail: str, alert: bool = True) -> int:
        if alert:
            path = failure_notice(work, args.week, code, step, detail)
            try:
                run("feishu_sync.py", "notify", "--file", str(path))
            except (OSError, subprocess.TimeoutExpired):
                print(path.read_text(encoding="utf-8"))
        emit("failed", code=code, step=step, detail=detail[:200])
        return 1

    if not note.exists() or not short.exists():
        return fail("NOTIFY_FILE_MISSING", "prepare_notification",
                    "通知正文与精简版须由智能段写好（notification*.txt）", alert=False)

    # 第 4 步：整理数据说明 + 质量门槛
    try:
        finalize = run("finalize.py")
        if finalize.returncode != 0:
            return fail("FINALIZE_FAILED", "finalize", (finalize.stderr or finalize.stdout)[:200])
        check = run("check_run.py")
    except (OSError, subprocess.TimeoutExpired) as e:
        return fail("CHECK_FAILED", "check_run", str(e)[:200])
    codes = value(check.stdout, "CODES")
    (work / paths.FILES["checks"]).write_text(check.stdout, encoding="utf-8")
    if check.returncode != 0 or codes:
        emit("rework", codes=codes or "UNKNOWN",
             detail="按手册返工表只重做未通过的部分，最多 3 轮；改稿后重跑 deliver.py")
        return 1

    # 第 5 步：发布（唯一写入口）
    try:
        pub = run("coord.py", "publish")
    except (OSError, subprocess.TimeoutExpired) as e:
        return fail("PUBLISH_FAILED", "publish", str(e)[:200])
    action = value(pub.stdout, "ACTION")
    if action != "published":
        return fail(f"PUBLISH_{str(action or 'UNKNOWN').upper()}", "publish",
                    "未发布，不进入同步；不拿旧 SHA 或默认 main 冒充")
    sha = value(pub.stdout, "commit") or (SHA.search(pub.stdout).group(0) if SHA.search(pub.stdout) else None)
    if not sha:
        return fail("PUBLISH_SHA_MISSING", "publish", "发布输出缺少完整提交号")

    # 第 5.5 步：飞书同步与读回（失败不阻塞 Git 周报）
    warnings = []
    try:
        sync = run("feishu_sync.py", "sync", "--from-published", "--sha", sha, "--week", args.week)
        st = value(sync.stdout, "SYNC")
        if st not in ("created", "updated"):
            warnings.append(f"SYNC={st or 'unknown'}；通知链接应以 GitHub 为准")
        else:
            verify_args = ["verify", "--sha", sha, "--week", args.week]
            if args.test:
                # 测试模式的 feishu.json 是 test=true，cmd_verify 的 token 回退只认
                # test=false 记录；不带 --doc 会写出误导性的 FEISHU_READBACK_DOC_REQUIRED。
                # 验收的真正读回由 deployment.py finish 独立完成，这里补 doc 只为不留废料收据。
                doc = value(sync.stdout, "DOCUMENT_ID")
                if doc:
                    verify_args += ["--doc", doc]
            run("feishu_sync.py", *verify_args)
    except (OSError, subprocess.TimeoutExpired) as e:
        warnings.append(f"飞书交付异常 {str(e)[:80]}")

    # 第 6 步：通知 + 归档
    try:
        run("feishu_sync.py", "notify", "--file", str(note), "--fallback-file", str(short))
        run("workdir.py", "archive", "--week", args.week)
    except (OSError, subprocess.TimeoutExpired) as e:
        return fail("DELIVERY_FAILED", "notify_or_archive", str(e)[:200])

    emit("ok", week=args.week, sha=sha, work=str(work),
         detail="；".join(warnings) if warnings else "交付与归档完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
