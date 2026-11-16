"""环境检查：核心生产依赖与飞书交付分开判定。

check/ensure 的 ENV=ok 仅表示 Python/PyYAML 与 git 核心可用；飞书缺失
输出 DELIVERY=degraded，不能阻断 Git 周报。部署验收可用 check --require-delivery。
ensure 的 core_ready 标记只缓存核心检查，不代表跨任务持久化/续期验收完成。
有效标记仍检查本地核心依赖是否存在；真实推送由 coord.py start 证明。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys

from common import REPO_DIR
import feishu_sync

APP_ID = "cli_a92390bc96f9dbb4"
ENV_VERSION = 2
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
    rc, out = sh(["git", "-C", str(REPO_DIR), "push", "--dry-run", "origin", "HEAD:main"],
                 env={"GIT_TERMINAL_PROMPT": "0"}, timeout=60)
    if rc == 0:
        return "PASS", "git推送演练", "dry-run 成功"
    low = out.lower()
    if any(h in low for h in AUTH_DENIED_HINTS):
        return "NEEDS_HUMAN", "git推送凭据", "配置本仓库 GitHub 写入身份后重跑；已有授权可用，无需固定 PAT 类型"
    return "FAIL", "git推送演练", "推送演练失败；在平台核对远端、网络和写权限，不回显可能含凭据的原始输出"


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
        return "FAIL", "lark-cli", "CLI 无法执行；检查安装与 PATH"
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
        return "NEEDS_HUMAN", "应用绑定", "config show 失败；检查应用配置（不回显凭据）"
    active = out.get("data") if isinstance(out.get("data"), dict) else out
    app_id = active.get("appId") or active.get("app_id")
    if app_id == APP_ID:
        return "PASS", "应用绑定", f"appId {APP_ID}"
    return ("NEEDS_HUMAN", "应用绑定",
            f"当前激活应用不是 {APP_ID}：按部署手册绑定正确 profile")


def check_identities(cli_ok: bool, cli: str | None) -> tuple[tuple[str, str, str], tuple[str, str, str]]:
    """C5+C6：bot ready（通知）、user available（建文档）。user 缺失需 device flow 人工授权。"""
    if not cli_ok or not cli:
        return (("MISSING", "bot身份", "lark-cli 就绪后重查"),
                ("MISSING", "user身份", "lark-cli 就绪后重查"))
    st = feishu_sync._auth_status(cli)
    if st.get("error"):
        return (("FAIL", "bot身份", "auth status 失败；检查授权和网络（不回显凭据）"),
                ("FAIL", "user身份", "同上"))
    ids = st.get("identities") or {}
    bot = "PASS" if (ids.get("bot") or {}).get("available") else "NEEDS_HUMAN"
    user = "PASS" if (ids.get("user") or {}).get("available") else "NEEDS_HUMAN"
    return ((bot, "bot身份", "ready" if bot == "PASS" else "lark-cli config init 后重查"),
            (user, "user身份", "available" if user == "PASS"
             else "lark-cli auth login（device flow，需本人浏览器确认）"))


def check_outbound(cli_ok: bool) -> tuple[str, str, str]:
    """C8：实际向服务端验证身份；普通 auth status 不能证明出站。"""
    if not cli_ok:
        return "MISSING", "飞书出站", "lark-cli 就绪后重查"
    cli = feishu_sync.find_cli(feishu_sync.cfg_load() or {})
    if not cli:
        return "MISSING", "飞书出站", "lark-cli 就绪后重查"
    out = feishu_sync.run_cli(cli, "auth", "status", "--verify")
    if out.get("error"):
        return "FAIL", "飞书出站", "服务端鉴权验证失败；检查代理、网络及授权，不回显原始错误"
    data = out.get("data") if isinstance(out.get("data"), dict) else out
    identities = data.get("identities") or {}
    if (data.get("verified") is True and all(
            (identities.get(kind) or {}).get("verified") is True and
            (identities.get(kind) or {}).get("available") is True
            for kind in ("bot", "user"))):
        return "PASS", "飞书出站", "auth status --verify 服务端验证通过；文档权限另以实际读写验收"
    return "FAIL", "飞书出站", "服务端未确认 user/bot 均可用；文档交付降级，继续 Git 周报"


MANUAL_ITEMS = [
    ("MANUAL", "身份边界", "文档显式使用 user 实测读写；通知使用 bot 实测到达；不要求 bot 无文档权限"),
    ("MANUAL", "凭据持久化", "核实平台的跨任务状态保存机制；两个独立任务免扫码，过期调用刷新，后续任务继承刷新状态"),
]


def _summary(results: list[tuple[str, str, str]], prefix: str) -> str:
    for status, label in (("MISSING", "missing"), ("NEEDS_HUMAN", "needs_human"), ("FAIL", "fail")):
        names = [r[1] for r in results if r[0] == status]
        if names:
            return f"{prefix}={label}:{','.join(names)}"
    return f"{prefix}=ok"


def delivery_summary(results: list[tuple[str, str, str]]) -> str:
    """MANUAL 不属于机器依赖，但永远另报 ACCEPTANCE=pending。"""
    items = results[2:8]
    failed = [name for status, name, _ in items if status != "PASS"]
    return "DELIVERY=degraded:" + ",".join(failed) if failed else "DELIVERY=ok"


def run_checks() -> tuple[list[tuple[str, str, str]], str, int]:
    """返回 (逐项结果, 核心总结行, 核心退出码)，交付层始终不阻断核心。"""
    results = [check_python(), check_git(), check_node()]
    cli_item = check_cli()
    cli_ok = cli_item[0] == "PASS"
    cli = feishu_sync.find_cli(feishu_sync.cfg_load() or {})
    results.append(cli_item)
    results.append(check_binding(cli_ok, cli))
    bot, user = check_identities(cli_ok, cli)
    results += [bot, user, check_outbound(cli_ok)]
    results += MANUAL_ITEMS
    summary = _summary(results[:2], "ENV")
    return results, summary, 0 if summary == "ENV=ok" else 1


def read_marker() -> dict | None:
    try:
        d = json.loads(MARKER.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def write_marker(results: list[tuple[str, str, str]]) -> None:
    versions = {name: detail for _, name, detail in results[:2]}
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(json.dumps({
        "env_version": ENV_VERSION,
        "status": "core_ready",
        "acceptance": "pending",
        "checked_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "versions": versions,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def print_results(results: list[tuple[str, str, str]]) -> None:
    for status, name, detail in results:
        print(f"[{status}] {name}：{detail}")


def cmd_check(require_delivery: bool = False) -> int:
    results, summary, code = run_checks()
    print_results(results)
    print(summary)
    delivery = delivery_summary(results)
    print(delivery)
    print("ACCEPTANCE=pending（机器检查不代表跨任务、续期及通知到达验收）")
    return code or (1 if require_delivery and delivery != "DELIVERY=ok" else 0)


def check_git_binary() -> tuple[str, str, str]:
    rc, _ = sh(["git", "--version"])
    return ("PASS", "git", "可执行") if rc == 0 else ("MISSING", "git", "需安装 git")


def cmd_ensure() -> int:
    """核心就绪缓存；标记不能掩盖核心工具丢失，更不能代替生产验收。"""
    m = read_marker()
    if m and m.get("env_version") == ENV_VERSION and m.get("status") == "core_ready":
        local = [check_python(), check_git_binary()]
        summary = _summary(local, "ENV")
        print_results(local)
        print(summary)
        print("DELIVERY=unchecked（仅使用核心缓存；动态交付由 preflight/实际 API 判定）")
        print("ACCEPTANCE=pending（核心标记不是生产验收凭证）")
        return 0 if summary == "ENV=ok" else 1
    print("ENV_CHECK=核心标记缺失或版本落后，检查核心与交付依赖")
    results, summary, code = run_checks()
    print_results(results)
    print(summary)
    print(delivery_summary(results))
    print("ACCEPTANCE=pending（人工项、跨任务与续期仍需实际验收）")
    if code == 0:
        write_marker(results)
        print(f"CORE_MARKER={MARKER}")
    return code


def cmd_reset() -> int:
    MARKER.unlink(missing_ok=True)
    print(f"已删除就绪标记：{MARKER}")
    return 0


def main(argv: list[str] | None = None) -> int:
    cmd = (argv or sys.argv[1:])[0] if (argv or sys.argv[1:]) else "check"
    if cmd == "check":
        return cmd_check(require_delivery="--require-delivery" in (argv or sys.argv[1:]))
    if cmd == "ensure":
        return cmd_ensure()
    if cmd == "reset":
        return cmd_reset()
    print(f"未知子命令：{cmd}（可用：check / ensure / reset）", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
