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

import tracelog
import paths  # noqa: E402
from common import REPO_DIR, load_config, read_json, write_json  # noqa: E402

CORE = _CORE
WEEKLY = pathlib.Path(__file__).resolve().parent



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
    path.write_text(f"【AI 周报 W{week[-2:]}｜失败】{code}。\n"
                    f"停在：{step}\n原因：{detail}\n已完成：见 {work / 'checks.txt'}\n",
                    encoding="utf-8")
    return path


def deliver() -> int:
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
                result = run("feishu_sync.py", "notify", "--file", str(path))
                if result.returncode or value(result.stdout, "NOTIFY") != "sent":
                    print(path.read_text(encoding="utf-8"))
            except (OSError, subprocess.TimeoutExpired):
                print(path.read_text(encoding="utf-8"))
        emit("failed", code=code, step=step, detail=detail[:200])
        return 1

    coord_file = work / paths.FILES["coord"]
    ctx = read_json(coord_file)
    if ctx.get("week") != args.week or not ctx.get("run_id"):
        return fail("RUN_CONTEXT_MISMATCH", "coord", "交付参数与本次运行不符", alert=False)
    test = ctx["test"]
    if not isinstance(test, bool):
        return fail("RUN_MODE_INVALID", "coord", "缺少有效的协调模式标记", alert=False)
    if not test and (env.get("TEST_RUN") == "1" or load_config("deployment")["mode"] != "production"):
        return fail("RUN_MODE_MISMATCH", "coord", "测试请求不可发布到正式运行上下文", alert=False)
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
    if check.returncode and not codes:
        return fail("CHECK_FAILED", "check_run", "检查器未返回门槛错误码")
    if codes:
        counter = work / paths.FILES["rework"]
        rounds = read_json(counter) if counter.exists() else {}
        n = rounds.get("rounds", 0) if rounds.get("run_id") == ctx["run_id"] else 0
        limit = load_config("runtime")["gates"]["max_rounds"]
        if n < limit:
            write_json(counter, {"run_id": ctx["run_id"], "rounds": n + 1})
            emit("rework", codes=codes, round=n + 1, limit=limit)
            return 1
        if {"GATE_STRUCTURE", "GATE_INCOMPLETE", "GATE_UNVERIFIED"} & set(codes.split(",")):
            return fail("REWORK_EXHAUSTED", "check_run", codes)
    # 第 5 步：发布（唯一写入口）
    try:
        pub = run("coord.py", "publish")
    except (OSError, subprocess.TimeoutExpired) as e:
        return fail("PUBLISH_FAILED", "publish", str(e)[:200])
    action = value(pub.stdout, "ACTION")
    if pub.returncode or action != "published":
        return fail(f"PUBLISH_{str(action or 'UNKNOWN').upper()}", "publish",
                    "未发布，不进入同步；不拿旧 SHA 或默认 main 冒充")
    published = read_json(coord_file)
    sha = published.get("published_commit", "")
    quality = published.get("published_quality")
    if (not re.fullmatch(r"[0-9a-f]{40}", sha) or published["run_id"] != ctx["run_id"]
            or quality not in ("full", "degraded", "check_failed")):
        return fail("PUBLISH_RECEIPT_INVALID", "publish", "发布收据缺少本次运行的提交号或质量")

    def stage(script, key, *argv):
        try:
            proc = run(script, *argv)
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"
        status = value(proc.stdout, key)
        if proc.returncode and status not in ("failed", "error", "pending", "unknown", "ambiguous"):
            return "error"
        return status or "unknown"

    # 全文仍只在 GitHub；通知不再附 GitHub 全文链接，改放年度表当期记录的直达链接。
    # 链接由 annual_index.py 在索引成功后写入运行时收据；取不到就不写这一行，不伪造。
    target = "本地沙箱" if test else "main"
    index = "skipped" if test else stage("annual_index.py", "INDEX", "--period", args.week, "--sha", sha)
    record_url = None
    if not test:
        receipt = work / paths.FILES["annual_index"]
        if receipt.is_file():
            data = read_json(receipt) or {}
            if data.get("period") == args.week and data.get("sha") == sha:
                url = data.get("url")
                if isinstance(url, str) and url.startswith("https://"):
                    record_url = url
    quality_text = {"full": "通过", "degraded": "降级", "check_failed": "检查未通过"}[quality]
    completeness = "通过" if check.returncode == 0 else codes
    footer = (f"校验：{quality_text}\n完整性：{completeness}，联网搜索 {tracelog.search_count(work)} 次"
              f"\n提交：已推送到{target}（{sha[:7]}）")
    if record_url:
        footer += f"\n年报：{record_url}"
    for path in (note, short):
        body = path.read_text(encoding="utf-8").rstrip()
        if quality != "full":
            body = re.sub(r"^(【AI\s*周报 W\d{2}[^】]*)】", rf"\1｜{quality_text}】", body, count=1)
        path.write_text(f"{body}\n\n{footer}\n", encoding="utf-8")
    notify = stage("feishu_sync.py", "NOTIFY", "notify", "--file", str(note), "--fallback-file", str(short))
    if notify != "sent":
        print(note.read_text(encoding="utf-8"))
    archive = stage("workdir.py", "ARCHIVE", "archive", "--week", args.week)
    ok = (index == ("skipped" if test else "updated") and archive == "ok" and notify == ("skipped" if test else "sent"))
    emit("ok" if ok else "partial", week=args.week, sha=sha, quality=quality,
         notify=notify, archive=archive, index=index, record_url=record_url or "none")
    return 0 if ok else 1


def main() -> int:
    try:
        return deliver()
    except (OSError, ValueError, KeyError) as exc:
        emit("failed", code="DELIVERY_STATE_INVALID", detail=str(exc)[:200])
        return 1


if __name__ == "__main__":
    sys.exit(main())
