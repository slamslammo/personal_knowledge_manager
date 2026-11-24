"""项目内的调度运行方式与沙箱验收，不改任务保存的提示词。

plan/start 每次读取项目 deployment.yaml，非法配置拒绝运行；TEST_RUN=1 只可
向验收降级，不能越过项目配置进入生产。finish 检查实际沙箱提交、质量门槛与
飞书读回，不把一次成功等同跨任务凭据或通知验收通过，也不自动启用生产。
"""
from __future__ import annotations

import pathlib as _pathlib
import sys as _sys
_CORE = _pathlib.Path(__file__).resolve().parents[1] / "core"  # weekly 依赖 core
if str(_CORE) not in _sys.path:
    _sys.path.insert(0, str(_CORE))


import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

from common import CORE_DIR, REPO_DIR, WORK_DIR, load_config, read_json, write_json
from document_compare import compare_documents, document_parts


def run_mode() -> str:
    try:
        config = load_config("deployment")
    except Exception as exc:
        raise ValueError("项目运行方式配置无法读取") from exc
    mode = config.get("mode") if isinstance(config, dict) else None
    if mode not in ("acceptance", "production"):
        raise ValueError("config/deployment.yaml 的 mode 必须为 acceptance 或 production")
    return "acceptance" if os.environ.get("TEST_RUN") == "1" else mode


def plan() -> dict:
    mode = run_mode()
    result = {"mode": mode, "test": mode == "acceptance", "auto_activate": False}
    write_json(WORK_DIR / "deployment.json", result)
    return result


def start(platform: str) -> int:
    # 不信任旧的 /tmp 计划；启动时再次读取项目配置。
    current = plan()
    if current["test"]:
        # 首次集成验收先完成依赖、现有应用绑定及服务端授权，再做昂贵的生成。
        # 这与 production 的飞书故障降级不同；C9 需要后续多次观察，暂不设门。
        import env_check
        if env_check.cmd_check(require_delivery=True):
            print("ACTION=blocked：首次验收环境或授权未就绪；先完成部署，不开始采集、搜索和写稿")
            return 1
    argv = [sys.executable, str(CORE_DIR / "coord.py"), "start", "--platform", platform]
    if current["test"]:
        argv.append("--test")
    return subprocess.run(argv).returncode


def _git(repo: pathlib.Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30)
    if p.returncode:
        raise ValueError("无法核对沙箱提交")
    return p.stdout


def sandbox_evidence(work: pathlib.Path) -> dict:
    """从真实提交和真实质量门槛验证沙箱，不信任单独的 passed 标记。"""
    import check_run

    ctx, week = read_json(work / "coord.json"), read_json(work / "week.json")
    if ctx.get("test") is not True or ctx.get("week") != week.get("week"):
        raise ValueError("缺少本次沙箱协调记录")
    remote = pathlib.Path(str(ctx.get("remote", "")))
    if not remote.is_absolute() or not remote.is_dir():
        raise ValueError("验收远端必须为本地沙箱仓库")
    sha = ctx.get("published_commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("没有实际发布的沙箱提交")
    branch = ctx.get("branch", "main")
    if not re.fullmatch(r"[A-Za-z0-9/_-]+", branch):
        raise ValueError("沙箱分支无效")
    repo = pathlib.Path(ctx.get("repo", str(REPO_DIR)))
    tip = _git(remote, "rev-parse", f"refs/heads/{branch}").strip()
    if tip != sha:
        raise ValueError("沙箱远端没有本次发布提交")
    steps = check_run.check(work, work / "out")
    if not steps or not all(s.ok for s in steps):
        raise ValueError("本次完整性或质量门槛未通过")
    state = json.loads(_git(repo, "show", f"{sha}:{ctx['state_path']}"))
    produced = state.get("produced") or {}
    if produced.get("quality") != "full" or produced.get("run_id") != ctx.get("run_id"):
        raise ValueError("实际发布结果不是本次 full 周报")
    content = subprocess.check_output(["git", "-C", str(remote), "cat-file", "blob",
                                       f"{sha}:{ctx['report_path']}"], timeout=30)
    return {"week": week["week"], "commit": sha, "content": content}


def finish(work: pathlib.Path = WORK_DIR) -> tuple[dict, int]:
    result = {"acceptance": "failed", "auto_activate": False,
              "sandbox": "pending", "github_production": "not_run_acceptance_mode",
              "document_delivery": "pending", "c9": "pending", "notification_delivery": "pending"}
    try:
        evidence = sandbox_evidence(work)
        result.update(week=evidence["week"], sandbox_commit=evidence["commit"], quality="full", sandbox="passed")
        # 交付源收敛：全文只在 Git。验收读回改为「沙箱提交正文 vs 工作目录候选稿」，
        # 不再创建/更新/读回飞书 docx。C9 凭据探测降级为观测字段，不作为通过条件。
        ctx = read_json(work / "coord.json")
        report_rel = ctx["report_path"]
        actual = (work / "out" / report_rel).read_bytes()
        if not actual.strip():
            raise ValueError("工作目录候选稿为空")
        (work / "local-readback.md").write_bytes(evidence["content"])
        result.update(notification="skipped", api_read="not_applicable_no_docx",
                      document_delivery="local_commit_readback")
        if actual == evidence["content"]:
            result.update(content_match="byte_equal", acceptance="passed", document_delivery="passed")
        else:
            result.update(content_match="different", acceptance="pending",
                          reason="Git 正文字节与候选稿不同，请对照 local-readback.md")
        if not (work / "notification.txt").is_file():
            raise ValueError("缺少本次通知预览")
        # 再实际调用一次通知入口，验证其脚本级隔离，绝不借验收发真实消息。
        notify_env = dict(os.environ, AI_WEEKLY_TMP=str(work), TEST_RUN="1")
        notice = subprocess.run([sys.executable, str(CORE_DIR / "feishu_sync.py"), "notify",
                                 "--file", str(work / "notification.txt")],
                                capture_output=True, text=True, env=notify_env, timeout=30)
        if notice.returncode or "NOTIFY=skipped test=1" not in notice.stdout:
            raise ValueError("通知隔离未通过")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        # 不输出子进程 stderr、CLI 错误或配置原文。
        result["reason"] = "沙箱提交、质量门槛或候选稿正文未完成验收；查看本次非敏感运行产物定位"
        result["acceptance"] = "failed"
    write_json(work / "acceptance.json", result)
    return result, 0 if result["acceptance"] == "passed" else 1


def resume(work: pathlib.Path = WORK_DIR) -> tuple[dict, int]:
    """在清理临时目录之前恢复已有验收，不丢弃本轮产物和创建结果记录。"""
    result = {"resume": "not_available", "auto_activate": False}
    context_file = work / "coord.json"
    if not context_file.is_file():
        return result, 0
    try:
        context = read_json(context_file)
        if run_mode() != "acceptance" or context.get("test") is not True or not context.get("published_commit"):
            return result, 0
        evidence = sandbox_evidence(work)
        result.update(resume="pending", sandbox_commit=evidence["commit"], week=evidence["week"])
        # 交付源收敛：没有 docx 补交付，恢复路径直接用本地沙箱提交重做验收。
        accepted, code = finish(work)
        result.update(resume="completed" if code == 0 else "pending", acceptance=accepted)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        result.update(resume="pending", reason="已有沙箱验收恢复未完成；保留临时产物，核对配置和本地提交后再恢复")
    write_json(work / "resume.json", result)
    return result, 0 if result["resume"] == "completed" else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("plan")
    s = commands.add_parser("start")
    s.add_argument("--platform", required=True)
    commands.add_parser("finish")
    commands.add_parser("resume")
    args = p.parse_args(argv)
    try:
        if args.command == "start":
            return start(args.platform)
        if args.command == "finish":
            result, code = finish()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print(f"ACCEPTANCE={result['acceptance']} C9={result['c9']} AUTO_ACTIVATE=no")
            return code
        if args.command == "resume":
            result, code = resume()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print(f"RESUME={result['resume']} AUTO_ACTIVATE=no")
            return code
        result = plan()
        print(f"RUN_MODE={result['mode']} COORD_TEST={int(result['test'])} AUTO_ACTIVATE=no")
        return 0
    except (OSError, ValueError, TypeError):
        print("DEPLOYMENT=error：项目运行方式配置无效，未启动任务", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
