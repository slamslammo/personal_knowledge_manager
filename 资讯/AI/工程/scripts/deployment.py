"""项目内的调度运行方式与沙箱验收，不改任务保存的提示词。

plan/start 每次读取项目 deployment.yaml，非法配置拒绝运行；TEST_RUN=1 只可
向验收降级，不能越过项目配置进入生产。finish 检查实际沙箱提交、质量门槛与
飞书读回，不把一次成功等同跨任务凭据或通知验收通过，也不自动启用生产。
"""
from __future__ import annotations

import argparse
import html
import json
import os
import pathlib
import re
import subprocess
import sys

from common import REPO_DIR, SCRIPTS_DIR, WORK_DIR, load_config, read_json, write_json
import feishu_sync as fs


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
    argv = [sys.executable, str(SCRIPTS_DIR / "coord.py"), "start", "--platform", platform]
    if current["test"]:
        argv.append("--test")
    return subprocess.run(argv).returncode


_TAG = re.compile(r"(?is)<[^>]+>")
# 只认块级标签，避免把正文里的 `<urlopen error …>` 这类文本误判成 HTML。
_HTML_HINT = re.compile(r"(?is)<(?:title|h[1-6]|p|br|table|ul|ol|li|div|blockquote|hr|tr|td|th)\b")
_SEPARATOR = re.compile(r"\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*")
_COMMENT = re.compile(r"(?s)<!--.*?-->")


def _inline_text(fragment: str) -> str:
    """行内标签还原成纯文本：链接还原成 `文本 地址`，与 Markdown 侧折叠规则对齐。"""
    def link(match: re.Match) -> str:
        text = _inline_text(match.group(2))
        href = html.unescape(match.group(1))
        return f"{text} {href}" if text else href

    fragment = re.sub(r'(?is)<a\s[^>]*href="([^"]*)"[^>]*>(.*?)</a>', link, fragment)
    fragment = re.sub(r"(?is)</p>\s*<p[^>]*>", " ", fragment)
    return html.unescape(_TAG.sub("", fragment))


def _table_rows(block: str) -> str:
    rows = []
    for row in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", block):
        cells = re.findall(r"(?is)<t[hd][^>]*>(.*?)</t[hd]>", row)
        values = [re.sub(r"\s+", " ", _inline_text(cell)).strip() for cell in cells]
        if values:
            rows.append("| " + " | ".join(values) + " |")
    return "\n".join(rows)


def _quote_block(inner: str) -> str:
    lines = [line.strip() for line in html_to_markdown(inner).splitlines() if line.strip()]
    return "\n" + "\n".join("> " + line for line in lines) + "\n"


def html_to_markdown(text: str) -> str:
    """把飞书读回的 HTML 化正文还原成块结构；输入已是 Markdown 时原样返回。

    `docs +fetch` 返回的正文是单行 HTML 表示：文档标题变 `<title>`（飞书把它放在
    全文最前，而发布稿里 H1 在 YAML 头之后）、段落变 `<p>`、换行变 `<br/>`、列表变
    `<li>`、表格变 `<table>`。不先还原块结构，任何跨行比对都必然不等。
    """
    if not _HTML_HINT.search(text):
        return text
    text = re.sub(r"(?is)<table[^>]*>.*?</table>", lambda m: "\n" + _table_rows(m.group(0)) + "\n", text)
    text = re.sub(r"(?is)<title[^>]*>(.*?)</title>", lambda m: "\n# " + _inline_text(m.group(1)) + "\n", text)
    text = re.sub(r"(?is)<blockquote[^>]*>(.*?)</blockquote>", lambda m: _quote_block(m.group(1)), text)
    text = re.sub(r"(?i)<h([1-6])[^>]*>", lambda m: "\n" + "#" * int(m.group(1)) + " ", text)
    text = re.sub(r"(?i)</h[1-6]>|<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "\n- ", text)
    text = re.sub(r"(?i)</?(?:p|div|ul|ol|li|tr|table|hr)[^>]*>", "\n", text)
    return _inline_text(text)


def _fold_line(line: str) -> str:
    """折叠单行的排版差异，文字、数字与链接地址都保留。"""
    line = re.sub(r"^\s*#{1,6}\s+", "", line)
    line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 \2", line)
    line = line.replace("**", "").replace("`", "")
    line = re.sub(r"\s*\|\s*", "|", line).strip().strip("|")
    line = re.sub(r"^(?:[-*+]\s+|\d+[.)]\s+|>\s?)", "", line)
    return re.sub(r"\s+", " ", line).strip()


def document_parts(text: str) -> tuple[str, list[str]]:
    """拆成（文档标题，正文行）。标题单独核对、正文按原顺序比对。

    飞书把 H1 提到文档标题位、把 YAML 头转成正文首块，标题与正文的相对位置和发布稿
    不同；顺序差异只允许发生在标题这一处，正文顺序仍严格比对。
    HTML 注释（如 `<!-- auto:data-notes -->`）不进入渲染结果，两侧都剔除。
    """
    title, body = "", []
    for line in _COMMENT.sub("", html_to_markdown(text)).replace("\r\n", "\n").splitlines():
        if _SEPARATOR.fullmatch(line):
            continue
        if not title and re.match(r"^\s*#\s+\S", line):
            title = _fold_line(line)
            continue
        folded = _fold_line(line)
        if folded:
            body.append(folded)
    return title, body


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
    content = _git(repo, "show", f"{sha}:{ctx['report_path']}")
    return {"week": week["week"], "commit": sha, "content": content}


def finish(work: pathlib.Path = WORK_DIR) -> tuple[dict, int]:
    result = {"acceptance": "failed", "auto_activate": False,
              "sandbox": "pending", "github_production": "not_run_acceptance_mode",
              "document_delivery": "pending", "c9": "pending", "notification_delivery": "pending"}
    try:
        evidence = sandbox_evidence(work)
        result.update(week=evidence["week"], sandbox_commit=evidence["commit"], quality="full", sandbox="passed")
        synced = read_json(work / "feishu.json")
        if (synced.get("test") is not True or synced.get("week") != evidence["week"]
                or synced.get("action") not in ("created", "updated") or not synced.get("document_id")):
            raise ValueError("测试文档未完整同步，不能认定验收通过")
        cfg = fs.cfg_load() or {}
        cli = fs.find_cli(cfg)
        if not cli:
            raise ValueError("未找到飞书 CLI，无法读回测试文档")
        # 此 probe 先读，确保自然到期后的第一次 API 调用留有证据。
        import credential_probe
        probe, code = credential_probe.run_probe(synced["document_id"])
        result["c9"] = probe.get("c9", "pending")
        if code:
            raise ValueError("实际 user 文档读取失败")
        fetched = fs.run_cli(cli, "docs", "+fetch", "--doc", synced["document_id"], "--as", "user")
        if fetched.get("error") or fs._business_failure(fetched):
            raise ValueError("正文读回失败")
        document = (fetched.get("data") or {}).get("document") or {}
        actual = document.get("content")
        if not isinstance(actual, str) or not actual:
            raise ValueError("正文读回为空")
        (work / "feishu-readback.md").write_text(actual, encoding="utf-8")
        expected = re.sub(r"(?m)^# ", "# [测试] ", evidence["content"], count=1)
        result.update(document_id=synced["document_id"], url=synced.get("url"),
                      notification="skipped", api_read="ok", document_delivery="read_back")
        exp_title, exp_body = document_parts(expected)
        act_title, act_body = document_parts(actual)
        if (exp_title, exp_body) != (act_title, act_body):
            first = next((i for i in range(max(len(exp_body), len(act_body)))
                          if i >= len(exp_body) or i >= len(act_body) or exp_body[i] != act_body[i]), None)
            result.update(acceptance="pending", content_match="manual_review",
                          title_match=exp_title == act_title,
                          body_lines=f"{len(act_body)}/{len(exp_body)}",
                          first_diff_line=first + 1 if first is not None else 0,
                          reason="读回正文与发布稿存在内容差异，请对照 feishu-content.md 与 feishu-readback.md")
        else:
            result.update(acceptance="passed", content_match="normalized_equal", document_delivery="passed")
        if not (work / "notification.txt").is_file():
            raise ValueError("缺少本次通知预览")
        # 再实际调用一次通知入口，验证其脚本级隔离，绝不借验收发真实消息。
        notify_env = dict(os.environ, AI_WEEKLY_TMP=str(work), TEST_RUN="1")
        notice = subprocess.run([sys.executable, str(SCRIPTS_DIR / "feishu_sync.py"), "notify",
                                 "--file", str(work / "notification.txt")],
                                capture_output=True, text=True, env=notify_env, timeout=30)
        if notice.returncode or "NOTIFY=skipped test=1" not in notice.stdout:
            raise ValueError("通知隔离未通过")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        # 不输出子进程 stderr、CLI 错误或配置原文。
        result["reason"] = "沙箱提交、质量门槛或飞书正文未完成验收；查看本次非敏感运行产物定位"
        result["acceptance"] = "failed"
    write_json(work / "acceptance.json", result)
    return result, 0 if result["acceptance"] == "passed" else 1


def _sync_published(work: pathlib.Path, context: dict) -> int:
    """只补交付已发布的沙箱稿；不重跑采集、写稿或协调发布。"""
    env = dict(os.environ, AI_WEEKLY_TMP=str(work), TEST_RUN="1")
    p = subprocess.run([sys.executable, str(SCRIPTS_DIR / "feishu_sync.py"), "sync",
                        "--from-published", "--sha", context["published_commit"],
                        "--week", context["week"], "--report", context["report_path"]],
                       capture_output=True, text=True, env=env, timeout=300)
    for line in p.stdout.splitlines():
        if line.startswith("SYNC="):
            print(line)
    return p.returncode


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
        # 扫码配置页面可选择不同应用；核对本项目指定身份后才允许任何补写入。
        import env_check
        cli = fs.find_cli(fs.cfg_load() or {})
        if not cli or env_check.check_binding(True, cli)[0] != "PASS":
            result["reason"] = "当前 CLI 尚未绑定指定应用；扫码选择小龙虾1号并核对 App ID 后再恢复"
            write_json(work / "resume.json", result)
            return result, 1
        # 在补同步可能触发刷新之前先观察，不能让恢复路径丢掉自然到期证据。
        import credential_probe
        observed, _ = credential_probe.run_probe(resume=True)
        result["c9"] = observed.get("c9", "pending")
        if _sync_published(work, context):
            result["reason"] = "飞书补交付未成功；按部署报告补齐现有应用配置与 user 授权后再恢复"
        else:
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
