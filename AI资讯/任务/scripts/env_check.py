"""定时任务环境自检与就绪标记：部署指南 4.9 清单（C1–C9）的机器化检查。

只检查、不安装、不授权：安装与授权由部署引导 prompts/env-bootstrap.md 承担
（那里的授权仅限 git、Node.js、lark-cli、PyYAML 四项；周报运行不获得安装授权）。

子命令：

    check（缺省）  全量检查，输出逐项状态与总结行，不读写标记。
    ensure         周报第 0 步用：标记有效（版本一致且 status=ok）直接 ENV=ok，
                   不重复检查；标记缺失/版本落后才做全量检查，通过后写标记。
    reset          删除标记（环境重建或强制重验时用）。

标记在环境侧 ~/.ai-weekly-env.json（不在 /tmp，不被周报起手清空；随凭据所在的
持久卷存活）。ENV_VERSION 是环境要求版本：环境要求变化（Node/lark-cli 最低版本、
appId、检查项增减）时改本文件的常量并 +1，所有环境下次 ensure 会因版本不一致
重做全量检查并刷新标记——这就是环境升级的触发机制。

总结行与状态：
    ENV=ok / ENV=missing:<编号> / ENV=needs_human:<编号> / ENV=fail:<编号>
    PASS 过；MISSING 缺失可安装；NEEDS_HUMAN 需用户操作；FAIL 环境问题；
    MANUAL 单次运行判不了，按部署指南人工执行。
退出码 0=就绪，1=有未过项。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys

from common import REPO_DIR, SCRIPTS_DIR
import feishu_sync

APP_ID = "cli_a92390bc96f9dbb4"
ENV_VERSION = 1
MARKER = pathlib.Path.home() / ".ai-weekly-env.json"
AUTH_DENIED_HINTS = ("could not read username", "authentication failed",
                     "terminal prompts disabled", "invalid username or password")
NODE_MIN = 18
CLI_MIN = (1, 0, 98)


def sh(argv: list[str], timeout: int = 30, env: dict | None = None) -> tuple[int, str]:
    """跑命令返回 (退出码, 合并输出)。命令不存在/超时按 127 处理。"""
    full_env = dict(os.environ)
    full_env.update(env or {})
    try:
        p = subprocess.run(argv, capture_output=True, text=True, env=full_env, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def _version_nums(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text)[:3]) or (0,)


def check_python() -> tuple[str, str, str]:
    """C0：python ≥3.10 与 PyYAML（PyYAML 由 requirements.txt 提供）。"""
    if sys.version_info < (3, 10):
        return "FAIL", "python", f"需 ≥3.10，实际 {sys.version.split()[0]}"
    try:
        import yaml  # noqa: F401
    except ImportError:
        return "MISSING", "PyYAML", "python3 -m pip install -r AI资讯/任务/requirements.txt"
    return "PASS", "python+PyYAML", sys.version.split()[0]


def check_git() -> tuple[str, str, str]:
    """C1：git 存在且可推送（演练检查，不产生提交）。凭据缺失是 NEEDS_HUMAN。"""
    rc, out = sh(["git", "--version"])
    if rc != 0:
        return "MISSING", "git", "系统包管理器安装 git"
    rc, out = sh(["git", "-C", str(REPO_DIR), "push", "--dry-run"],
                 env={"GIT_TERMINAL_PROMPT": "0"}, timeout=60)
    if rc == 0:
        return "PASS", "git推送演练", "dry-run 成功"
    low = out.lower()
    if any(h in low for h in AUTH_DENIED_HINTS):
        return "NEEDS_HUMAN", "git推送凭据", "无推送凭据：用户注入 PAT（repo scope）后重跑"
    return "FAIL", "git推送演练", out.strip()[-160:] or "推送失败"


def check_node() -> tuple[str, str, str]:
    """C2a：Node ≥18。"""
    rc, out = sh(["node", "-v"])
    if rc != 0:
        return "MISSING", "Node.js", f"安装 Node ≥{NODE_MIN}"
    v = _version_nums(out)
    if v[0] >= NODE_MIN:
        return "PASS", "Node.js", out.strip()
    return "MISSING", "Node.js", f"需 ≥{NODE_MIN}，实际 {out.strip()}"


def check_cli() -> tuple[str, str, str]:
    """C2b：lark-cli ≥1.0.98 且能执行（C3 的 PATH 稳定由 which/配置路径佐证）。"""
    cli = feishu_sync.find_cli(feishu_sync.cfg_load() or {})
    if not cli:
        return "MISSING", "lark-cli", "npm install -g @larksuite/cli@1.0.100"
    rc, out = sh([cli, "--version"], timeout=60)
    ver_line = next((ln for ln in out.splitlines() if "lark-cli" in ln), out.strip())
    if rc != 0:
        return "FAIL", "lark-cli", f"{cli} 无法执行：{(out or '').strip()[:120]}"
    v = _version_nums(ver_line)
    if v >= CLI_MIN:
        return "PASS", "lark-cli", f"{ver_line}（{cli}）"
    return "MISSING", "lark-cli", f"需 ≥{'.'.join(map(str, CLI_MIN))}，实际 {ver_line}"


def check_binding(cli_ok: bool, cli: str | None) -> tuple[str, str, str]:
    """C3+C4：应用绑定与 profile（appId 必须是本任务的应用）。"""
    if not cli_ok or not cli:
        return "MISSING", "应用绑定", "lark-cli 就绪后重查"
    out = feishu_sync.run_cli(cli, "config", "show")
    if out.get("error"):
        return "NEEDS_HUMAN", "应用绑定", f"config show 失败：{out['error'].get('detail', '')[:120]}"
    text = str(out)
    if APP_ID in text:
        return "PASS", "应用绑定", f"appId {APP_ID}"
    return ("NEEDS_HUMAN", "应用绑定",
            f"config show 未包含本任务 appId {APP_ID}：lark-cli config init --new 重新绑定")


def check_identities(cli_ok: bool, cli: str | None) -> tuple[tuple[str, str, str], tuple[str, str, str]]:
    """C5+C6：bot ready（通知）、user available（建文档）。user 缺失需 device flow 人工授权。"""
    if not cli_ok or not cli:
        return (("MISSING", "bot身份", "lark-cli 就绪后重查"),
                ("MISSING", "user身份", "lark-cli 就绪后重查"))
    st = feishu_sync._auth_status(cli)
    if st.get("error"):
        return (("FAIL", "bot身份", f"auth status 失败：{st['error'].get('detail', '')[:120]}"),
                ("FAIL", "user身份", "同上"))
    ids = st.get("identities") or {}
    bot = "PASS" if (ids.get("bot") or {}).get("available") else "NEEDS_HUMAN"
    user = "PASS" if (ids.get("user") or {}).get("available") else "NEEDS_HUMAN"
    return ((bot, "bot身份", "ready" if bot == "PASS" else "lark-cli config init 后重查"),
            (user, "user身份", "available" if user == "PASS"
             else "lark-cli auth login（device flow，需本人浏览器确认）"))


def check_outbound(cli_ok: bool) -> tuple[str, str, str]:
    """C8：飞书出站与代理（preflight 的现场判定，含自适应处理）。"""
    if not cli_ok:
        return "MISSING", "飞书出站", "lark-cli 就绪后重查"
    p = subprocess.run([sys.executable, str(SCRIPTS_DIR / "feishu_sync.py"), "preflight"],
                       capture_output=True, text=True, timeout=120)
    out = (p.stdout or "").strip()
    if "PREFLIGHT=ok" in out:
        return "PASS", "飞书出站", "preflight=ok"
    if "PREFLIGHT=degraded" in out or "PREFLIGHT=disabled" in out:
        return "FAIL", "飞书出站", out.splitlines()[-1][:120]
    return "FAIL", "飞书出站", (out or p.stderr or "preflight 无输出")[:120]


MANUAL_ITEMS = [
    ("MANUAL", "身份边界", "部署时人工验证：bot 建文档必须失败（99991672）、user 建文档必须成功"),
    ("MANUAL", "凭据持久化", "凭据目录挂持久卷；判据是两次任务间凭据仍在 + access 过期后首次调用成功"),
]


def run_checks() -> tuple[list[tuple[str, str, str]], str, int]:
    """返回 (逐项结果, 总结行, 退出码)。"""
    results = [check_python(), check_git(), check_node()]
    cli_item = check_cli()
    cli_ok = cli_item[0] == "PASS"
    cli = feishu_sync.find_cli(feishu_sync.cfg_load() or {})
    results.append(cli_item)
    results.append(check_binding(cli_ok, cli))
    bot, user = check_identities(cli_ok, cli)
    results += [bot, user, check_outbound(cli_ok)]
    results += MANUAL_ITEMS
    missing = [r[1] for r in results if r[0] == "MISSING"]
    human = [r[1] for r in results if r[0] == "NEEDS_HUMAN"]
    failed = [r[1] for r in results if r[0] == "FAIL"]
    parts = [f"ENV=missing:{','.join(missing)}" if missing else "",
             f"ENV=needs_human:{','.join(human)}" if human else "",
             f"ENV=fail:{','.join(failed)}" if failed else ""]
    summary = next((p for p in parts if p), "ENV=ok")
    return results, summary, 0 if summary == "ENV=ok" else 1


def read_marker() -> dict | None:
    try:
        d = json.loads(MARKER.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def write_marker(results: list[tuple[str, str, str]]) -> None:
    versions = {name: detail for _, name, detail in results if name in ("python+PyYAML", "Node.js", "lark-cli", "应用绑定")}
    MARKER.write_text(json.dumps({
        "env_version": ENV_VERSION,
        "status": "ok",
        "checked_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "versions": versions,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def print_results(results: list[tuple[str, str, str]]) -> None:
    for status, name, detail in results:
        print(f"[{status}] {name}：{detail}")


def cmd_check() -> int:
    results, summary, code = run_checks()
    print_results(results)
    print(summary)
    return code


def cmd_ensure() -> int:
    """周报第 0 步的就绪门：标记有效直接过；否则全量检查，通过才写标记。"""
    m = read_marker()
    if m and m.get("env_version") == ENV_VERSION and m.get("status") == "ok":
        print(f"ENV=ok（就绪标记有效：env_version={ENV_VERSION}，"
              f"checked_at={m.get('checked_at', '?')}）")
        return 0
    why = "标记缺失" if not m else f"标记版本落后（标记 {m.get('env_version')}，要求 {ENV_VERSION}）"
    print(f"ENV_CHECK={why}，做全量检查")
    results, summary, code = run_checks()
    print_results(results)
    if code == 0:
        write_marker(results)
        print(f"{summary}（已写就绪标记：{MARKER}）")
    else:
        print(summary)
    return code


def cmd_reset() -> int:
    MARKER.unlink(missing_ok=True)
    print(f"已删除就绪标记：{MARKER}")
    return 0


def main(argv: list[str] | None = None) -> int:
    cmd = (argv or sys.argv[1:])[0] if (argv or sys.argv[1:]) else "check"
    if cmd == "check":
        return cmd_check()
    if cmd == "ensure":
        return cmd_ensure()
    if cmd == "reset":
        return cmd_reset()
    print(f"未知子命令：{cmd}（可用：check / ensure / reset）", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
