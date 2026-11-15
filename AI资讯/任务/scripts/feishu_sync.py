"""飞书交付：预检（preflight）、同步周报（sync）、发送通知（notify）。

设计依据 ../提案/2026-11-14-飞书接入与定时任务收敛.md（v4 终版）：

- 单运行者、无锁；幂等靠「栏目 + ISO 周」查重 + 唯一性校验 + overwrite。
- 同步源是 git 已发布内容（git show <ref>:<path>），不是 /tmp 候选稿——候选稿可能被
  人工修改保护排除，与入库内容不一致。
- 代理自适应：只清「回环地址 + 连续探测无监听」的代理变量（本机 WorkBuddy 注入的
  死端口）；非回环地址一律保留（云端真实代理与 CA 链路，一次探测失败不能作证据）。
- create 与 overwrite 的重试语义不同：overwrite 幂等可重试；create 超时/网络失败
  不重试——响应丢失时文档可能已创建，而搜索有索引延迟，重搜为空不能证明未创建，
  盲目再 create 会产生重复文档。create 失败靠补交付（--from-published）收敛。
- 搜索索引延迟的配套兜底：create 成功后立刻重跑（同机补交付/紧接重试）时，新文档
  可能还没进索引，search 0 候选会导致重复 create。因此同步前先看上次结果文件
  feishu.json 里记录的本周 document_id：能 fetch 到就直接 overwrite，不经过 search。
- 降级不阻塞：飞书失效（off/no_doc/no_notify）时周报照常发 git，事后补交付。
- 测试隔离：TEST_RUN=1 时 sync 用 [测试] 标题前缀查重（不碰正式文档），notify 直接跳过。
  注意 overwrite 会以内容 H1 重置文档标题，因此测试模式把前缀同时写进内容 H1。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import time

from common import REPO_DIR, WORK_DIR, load_config, read_json, write_json
import tracelog

MODE_FILE = "feishu-mode.json"
RESULT_FILE = "feishu.json"
CONNECTOR_CLI = pathlib.Path.home() / ".workbuddy/binaries/node/cli-connector-packages/bin/lark-cli"
PROXY_VARS = ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy")
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
MAX_ATTEMPTS = 3


# ---------------------------------------------------------------- 基础

def find_cli(cfg: dict) -> str | None:
    """按 cli_path → PATH → WorkBuddy 连接器路径的顺序探测 lark-cli。"""
    cand = (cfg.get("cli_path") or "").strip()
    if cand:
        return cand if pathlib.Path(cand).exists() else None
    found = shutil.which("lark-cli")
    if found:
        return found
    return str(CONNECTOR_CLI) if CONNECTOR_CLI.exists() else None


def _proxy_addr(value: str):
    m = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/:]+):(\d+)", value.strip())
    if not m:
        m = re.match(r"^([^/:]+):(\d+)$", value.strip())
    return (m.group(1), int(m.group(2))) if m else None


def _listening(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def adapt_proxy_env(env: dict | None = None) -> tuple[dict, list]:
    """返回 (环境, 被移除的变量名)。

    只移除「回环地址 + 连续两次探测无监听」的代理变量：这是本机 WorkBuddy 注入
    动态死端口的特征。非回环地址一律保留——云端代理通常是远端主机，TCP 探测
    本身可能瞬断，一次（甚至两次）失败都不能作为清除依据。
    """
    env = dict(env if env is not None else os.environ)
    removed = []
    for var in PROXY_VARS:
        val = env.get(var)
        if not val:
            continue
        addr = _proxy_addr(val)
        if not addr or addr[0] not in LOOPBACK:
            continue
        if not _listening(*addr) and not _listening(*addr):
            removed.append(var)
    for var in removed:
        env.pop(var, None)
    if removed:
        env["LARK_CLI_NO_PROXY"] = "1"
    return env, removed


def run_cli(cli: str, *args: str, timeout: int = 60) -> dict:
    """执行 lark-cli 并解析 JSON 输出；网络层异常包装为 type=network 的统一结构。"""
    env, removed = adapt_proxy_env()
    try:
        p = subprocess.run([cli, *args], capture_output=True, text=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"type": "network", "subtype": "timeout", "detail": f"{timeout}s 超时",
                                       "_removed_proxies": removed}}
    except OSError as e:
        return {"ok": False, "error": {"type": "network", "subtype": type(e).__name__, "detail": str(e),
                                       "_removed_proxies": removed}}
    try:
        out = json.loads(p.stdout) if p.stdout.strip() else {}
    except json.JSONDecodeError:
        out = {}
    if not isinstance(out, dict):
        out = {}
    if "error" not in out and (p.returncode != 0 or not out):
        out["error"] = {"type": "cli", "subtype": "bad_output", "detail": (p.stderr or p.stdout)[:300]}
    if "error" in out:
        out["ok"] = False
        out["error"]["_removed_proxies"] = removed
    elif "ok" not in out:
        out["ok"] = True
    return out


def cfg_load() -> dict | None:
    try:
        cfg = load_config("feishu")
    except Exception:  # 文件缺失或 yaml 不可读都按配置不可用处理
        return None
    return cfg if isinstance(cfg, dict) else None


def write_mode(mode: str, **extra) -> None:
    write_json(WORK_DIR / MODE_FILE, {"mode": mode, **extra})


def read_mode() -> str | None:
    try:
        return read_json(WORK_DIR / MODE_FILE).get("mode")
    except Exception:
        return None


def week_from_weekjson() -> str | None:
    try:
        return read_json(WORK_DIR / "week.json").get("week")
    except Exception:
        return None


def report_path_for(week: str) -> str:
    return f"AI资讯/周报/{week[:4]}/{week}.md"


def git_show(ref: str, path: str) -> str | None:
    p = subprocess.run(["git", "-C", str(REPO_DIR), "show", f"{ref}:{path}"],
                       capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def strip_highlight(text: str) -> str:
    """去掉 search 结果标题里的高亮标签（<h>/<hb>/<b>）。"""
    return re.sub(r"</?[a-z]+>", "", text or "")


def report_h1(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def is_test() -> bool:
    return os.environ.get("TEST_RUN") == "1"


def title_matches(title: str, week: str, test: bool) -> bool:
    """查重命中条件：标题含栏目「AI 周报」与 ISO 周编号（H1 实际是「AI 周报 · 2026-W45…」，

    带间隔号与可变后缀，不能前缀匹配）；测试模式额外要求 [测试] 前缀。
    """
    if "AI 周报" not in title or week not in title:
        return False
    return title.startswith("[测试]") if test else not title.startswith("[测试]")


# ---------------------------------------------------------------- preflight

def _auth_status(cli: str) -> dict:
    """auth status 网络层失败重试 2 次；拿不到状态按不可达处理。"""
    for attempt in range(3):
        out = run_cli(cli, "auth", "status")
        err = out.get("error") or {}
        if not err:
            return out
        if err.get("type") != "network":
            return out
        if attempt < 2:
            time.sleep(2 * 2 ** attempt)
    return out


def cmd_preflight(_args) -> int:
    cfg = cfg_load()
    if cfg is None:
        write_mode("off", reason="FEISHU_CONFIG_MISSING")
        tracelog.log("飞书", "预检", "warn", "FEISHU_CONFIG_MISSING", "config/feishu.yaml 缺失或不可读，飞书交付整体降级")
        print("PREFLIGHT=degraded:off CODE=FEISHU_CONFIG_MISSING")
        return 0
    if not cfg.get("enabled", True):
        write_mode("off", reason="disabled")
        print("PREFLIGHT=disabled")
        return 0
    cli = find_cli(cfg)
    if not cli:
        write_mode("off", reason="FEISHU_CLI_NOT_FOUND")
        tracelog.log("飞书", "预检", "warn", "FEISHU_CLI_NOT_FOUND", "未找到 lark-cli")
        print("PREFLIGHT=degraded:off CODE=FEISHU_CLI_NOT_FOUND")
        return 0
    st = _auth_status(cli)
    if st.get("error"):
        subtype = (st["error"].get("subtype") or "")
        code = "FEISHU_UNREACHABLE" if st["error"].get("type") == "network" else "FEISHU_AUTH_INVALID"
        write_mode("off", reason=code)
        tracelog.log("飞书", "预检", "warn", code, subtype or str(st["error"].get("detail", ""))[:120])
        print(f"PREFLIGHT=degraded:off CODE={code}")
        return 0
    ids = st.get("identities") or {}
    bot_ok = bool((ids.get("bot") or {}).get("available"))
    user_ok = bool((ids.get("user") or {}).get("available"))
    if bot_ok and user_ok:
        write_mode("full", bot=True, user=True)
        tracelog.log("飞书", "预检", "ok")
        print("PREFLIGHT=ok")
        return 0
    if user_ok:
        mode, code = "no_notify", "FEISHU_BOT_INVALID"
    elif bot_ok:
        mode, code = "no_doc", "FEISHU_USER_INVALID"
    else:
        mode, code = "off", "FEISHU_AUTH_INVALID"
    write_mode(mode, bot=bot_ok, user=user_ok)
    tracelog.log("飞书", "预检", "warn", code, f"mode={mode}")
    print(f"PREFLIGHT=degraded:{mode} CODE={code}")
    return 0


def ensure_mode() -> str:
    m = read_mode()
    if m is None:
        cmd_preflight(None)
        m = read_mode() or "off"
    return m


# ---------------------------------------------------------------- sync

def search_candidates(cli: str, week: str, test: bool) -> list[dict] | None:
    """按周编号搜索并过滤出本周文档候选。search 调用失败返回 None（与 0 候选区分）。"""
    out = run_cli(cli, "docs", "+search", "--query", week)
    if out.get("error"):
        return None
    cands = []
    for r in ((out.get("data") or {}).get("results") or []):
        meta = r.get("result_meta") or {}
        if meta.get("doc_types") != "DOCX":
            continue
        title = strip_highlight(r.get("title_highlighted"))
        if title_matches(title, week, test):
            cands.append({"token": meta.get("token"), "title": title, "url": meta.get("url")})
    return cands


def _overwrite(cli: str, token: str, content_file: pathlib.Path) -> dict:
    """覆盖已有文档。幂等，网络失败可重试。"""
    out = run_cli(cli, "docs", "+update", "--doc", token, "--command", "overwrite",
                  "--doc-format", "markdown", "--content", f"@{content_file}")
    if out.get("error"):
        return {"action": "retry" if (out["error"].get("type") == "network") else "failed", "error": out["error"]}
    return {"action": "updated", "document_id": token}


def _create(cli: str, title: str, content_file: pathlib.Path, folder: str) -> dict:
    """创建文档。超时/网络失败不重试：响应丢失时文档可能已建，而索引有延迟，

    重搜为空不能证明未创建；盲目再 create 会产生重复文档（评审修正点 2）。
    """
    argv = ["docs", "+create", "--doc-format", "markdown", "--content", f"@{content_file}", "--title", title]
    if folder:
        argv += ["--parent-token", folder]
    out = run_cli(cli, *argv)
    if out.get("error"):
        return {"action": "failed", "error": out["error"]}
    doc = (out.get("data") or {}).get("document") or {}
    return {"action": "created", "document_id": doc.get("document_id"), "url": doc.get("url")}


def _sync_via_search(cli: str, week: str, test: bool, title: str,
                     content_file: pathlib.Path, folder: str) -> dict:
    """搜索查重路径：>1 候选拒绝覆盖、1 候选 overwrite、0 候选 create。"""
    for attempt in range(MAX_ATTEMPTS):
        cands = search_candidates(cli, week, test)
        if cands is None:
            # search 本身失败：按网络问题重试（search 是只读，重试安全）
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(2 * 2 ** attempt)
                continue
            tracelog.log("飞书", "同步", "error", "FEISHU_SYNC_FAILED", "search 重试后仍失败")
            return {"action": "failed"}
        if len(cands) > 1:
            tracelog.log("飞书", "同步", "error", "FEISHU_AMBIGUOUS_DOC",
                         f"{len(cands)} 篇同周文档：{','.join(c['token'] for c in cands)}")
            return {"action": "ambiguous", "candidates": cands}
        if len(cands) == 1:
            r = _overwrite(cli, cands[0]["token"], content_file)
            if r.get("action") == "retry" and attempt < MAX_ATTEMPTS - 1:
                time.sleep(2 * 2 ** attempt)
                continue
            if "url" not in r and cands[0].get("url"):
                # overwrite 成功不带 url，用候选里的补全（第 6 步通知链接要用）
                r["url"] = cands[0]["url"]
            return r
        return _create(cli, title, content_file, folder)  # create 不重试（见函数注释）
    return {"action": "failed"}


def _cached_result(week: str, test: bool) -> dict | None:
    """上次同步结果文件里本周的记录（同机紧接重跑的幂等兜底）。

    create 成功后搜索索引有延迟（实测数十秒内查不到），立刻重跑会因 0 候选
    重复 create；用结果文件里的 document_id 直接 overwrite 可避开索引窗口。
    """
    try:
        d = read_json(WORK_DIR / RESULT_FILE)
    except Exception:
        return None
    if d.get("week") == week and bool(d.get("test")) == test and d.get("document_id"):
        return d
    return None


def _doc_exists(cli: str, token: str) -> bool:
    return not run_cli(cli, "docs", "+fetch", "--doc", token).get("error")


def cmd_sync(args) -> int:
    mode = ensure_mode()
    if mode in ("off", "no_doc"):
        print(f"SYNC=skipped mode={mode}")
        return 0
    cfg = cfg_load() or {}
    cli = find_cli(cfg)
    if not cli:
        print("SYNC=error CODE=FEISHU_CLI_NOT_FOUND")
        return 1
    week = args.week or week_from_weekjson()
    if not week:
        tracelog.log("飞书", "同步", "error", "FEISHU_WEEK_UNKNOWN", "无法确定周编号")
        print("SYNC=error CODE=FEISHU_WEEK_UNKNOWN")
        return 1
    ref = args.sha or "main"
    path = args.report or report_path_for(week)
    content = git_show(ref, path)
    if content is None:
        tracelog.log("飞书", "同步", "error", "FEISHU_SOURCE_MISSING", f"git show {ref}:{path} 失败")
        print(f"SYNC=error CODE=FEISHU_SOURCE_MISSING")
        return 1
    test = is_test()
    h1 = report_h1(content) or f"AI 周报 · {week}"
    title = f"[测试] {h1}" if test else h1
    if test and h1:
        # overwrite 会用内容 H1 重置文档标题（实测）：标题前缀必须写进内容 H1，
        # 否则覆盖后标题丢前缀，测试文档漏出隔离、会被正式查重命中。
        content = re.sub(r"(?m)^# ", "# [测试] ", content, count=1)
    content_file = WORK_DIR / "feishu-content.md"
    content_file.parent.mkdir(parents=True, exist_ok=True)
    content_file.write_text(content, encoding="utf-8")
    folder = (cfg.get("folder_token") or "").strip()

    result = None
    cached = _cached_result(week, test)
    if cached and _doc_exists(cli, cached["document_id"]):
        # 命中同机缓存：直接 overwrite，绕开搜索索引延迟窗口
        for attempt in range(MAX_ATTEMPTS):
            r = _overwrite(cli, cached["document_id"], content_file)
            if r.get("action") == "retry" and attempt < MAX_ATTEMPTS - 1:
                time.sleep(2 * 2 ** attempt)
                continue
            if "url" not in r and cached.get("url"):
                r["url"] = cached["url"]
            result = r
            break
    if result is None:
        result = _sync_via_search(cli, week, test, title, content_file, folder)

    result = result or {"action": "failed"}
    out_obj = {"week": week, "test": test, "title": title, **{k: v for k, v in result.items() if k != "error"}}
    write_json(WORK_DIR / RESULT_FILE, out_obj)
    action = result.get("action")
    if action in ("created", "updated"):
        tracelog.log("飞书", "同步", "ok", detail=f"{action} {result.get('document_id')}",
                     document_id=result.get("document_id"), url=result.get("url"))
        print(f"SYNC={action} document_id={result.get('document_id')}")
        return 0
    code = "FEISHU_AMBIGUOUS_DOC" if action == "ambiguous" else "FEISHU_SYNC_FAILED"
    if action == "failed":
        tracelog.log("飞书", "同步", "error", code, json.dumps(result.get("error") or {}, ensure_ascii=False)[:200])
    print(f"SYNC=error CODE={code}")
    return 1


# ---------------------------------------------------------------- notify

def cmd_notify(args) -> int:
    if is_test():
        print("NOTIFY=skipped test=1")
        return 0
    mode = ensure_mode()
    if mode in ("off", "no_notify"):
        print(f"NOTIFY=skipped mode={mode}")
        return 0
    cfg = cfg_load() or {}
    cli = find_cli(cfg)
    uid = ((cfg.get("notify") or {}).get("user_open_id") or "").strip()
    if not cli or not uid:
        print("NOTIFY=error CODE=FEISHU_CONFIG_MISSING")
        return 1
    text = pathlib.Path(args.file).read_text(encoding="utf-8")
    week = week_from_weekjson() or "unknown"
    key = f"ai-weekly-{week}-{hashlib.md5(text.encode('utf-8')).hexdigest()[:8]}"
    out = run_cli(cli, "im", "+messages-send", "--as", "bot", "--user-id", uid,
                  "--markdown", f"@{args.file}", "--idempotency-key", key)
    if out.get("error") and args.fallback_file and pathlib.Path(args.fallback_file).exists():
        out = run_cli(cli, "im", "+messages-send", "--as", "bot", "--user-id", uid,
                      "--markdown", f"@{args.fallback_file}", "--idempotency-key", key + "-fb")
    if out.get("error"):
        err = out["error"]
        tracelog.log("飞书", "通知", "error", "FEISHU_NOTIFY_FAILED",
                     (err.get("detail") or err.get("subtype") or "")[:200])
        print("NOTIFY=failed CODE=FEISHU_NOTIFY_FAILED")
        return 1
    tracelog.log("飞书", "通知", "ok", detail=f"idempotency={key}")
    print("NOTIFY=sent")
    return 0


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="飞书交付：preflight / sync / notify")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight", help="飞书环境预检（写 feishu-mode.json）")
    sp = sub.add_parser("sync", help="同步周报到飞书")
    sp.add_argument("--from-published", action="store_true", help="同步 git 已发布内容（语义标记，源始终取自 git）")
    sp.add_argument("--sha", help="已发布的提交号（缺省 main）")
    sp.add_argument("--week", help="ISO 周（缺省读 week.json）")
    sp.add_argument("--report", help="仓库内周报相对路径（缺省按周推导）")
    sp = sub.add_parser("notify", help="以 bot 发送通知")
    sp.add_argument("--file", required=True, help="通知正文文件")
    sp.add_argument("--fallback-file", help="发送失败时的精简版文件")
    args = ap.parse_args()
    return {"preflight": cmd_preflight, "sync": cmd_sync, "notify": cmd_notify}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
