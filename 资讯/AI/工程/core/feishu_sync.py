"""飞书交付：预检（preflight）、同步周报（sync）、读回核对（verify）、发送通知（notify）。

设计依据 ../../文档/提案/2026-11-14-飞书接入与定时任务收敛.md（v4 终版）：

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
- 测试隔离：TEST_RUN=1 或 coord.json 的 test 标记（coord --test 不导出环境变量，
  交付脚本必须两个来源都认，评审 P1-1）。测试模式 sync 用 [测试] 标题前缀查重，
  notify 直接跳过。注意 overwrite 会以内容 H1 重置文档标题，因此测试模式把前缀
  同时写进内容 H1。

2026-11-16 按外部评审（提案《2026-11-15 飞书实现与 W45 重跑评审》及其附件）第二轮修复：

- P1-2 查重：标题改为结构匹配（去 [测试] 后以「AI 周报」开头 + 周编号边界检查），
  「关于 AI 周报…问题汇总」不再命中；search 遍历 has_more/page_token 翻页后再判唯一。
- P1-3 成功判定：update 的 data.result 必须是 success（partial_success/failed 按
  写入不完整走幂等重试）；create 必须拿到非空 document_id。
- P2-4 包装层：run_cli 解析 stderr 的结构化错误信封，network 类型保留可重试。
- P2-5 失败语义：sync/notify 每次现场刷新 preflight（旧 no_doc/off 缓存不短路补
  交付）；缓存文档 fetch 区分 missing/unknown，unknown 不落到 create；create 网络
  失败记 action=unknown，下次 0 候选时拒绝盲目重建（FEISHU_CREATE_UNKNOWN）。
- P2-6 notify：网络类失败（结果不明）用同一幂等键重试，只有确定拒绝才换键发
  fallback，避免双发。
- P2-7 身份与代理：docs 命令显式 --as user；删除 LARK_CLI_NO_PROXY 全局开关
  （会把另一个仍有效的代理一起禁掉），只移除探测失败的回环代理变量本身。

2026-11-20 版本规划 P0（补交付重复建文档）：

- _doc_state 只有明确 not-found 才判 missing；权限、网络、CLI 输出异常一律
  unknown（结果不明不能证明文档不存在），避免落到搜索 0 候选 create。
- cmd_sync 在失败/结果不明时把已知 document_id、url 继承进 feishu.json，
  下次补交付继续核对原文档，不再因丢 ID 退回搜索而重复新建。
"""
from __future__ import annotations

import argparse
import datetime as dt
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

import paths
import tracelog
from common import REPO_DIR, WORK_DIR, load_config, read_json, write_json
from weeks import Week

MODE_FILE = "feishu-mode.json"
RESULT_FILE = "feishu.json"
READBACK_FILE = "feishu-delivery-check.json"
NOTIFY_FILE = "feishu-notify-receipt.json"
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
    不设 LARK_CLI_NO_PROXY 全局开关：混合代理场景下它会把另一个仍有效的代理
    一起禁掉（评审 P2-7）；移除失效变量本身即可，剩余有效代理继续生效。
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
    return env, removed


def _parse_envelope(text: str) -> dict | None:
    """从 stdout/stderr 文本解析 CLI JSON 信封；解析不了返回 None。"""
    text = (text or "").strip()
    if not text:
        return None
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        return None
    return out if isinstance(out, dict) else None


def run_cli(cli: str, *args: str, timeout: int = 60, stdin_text: str | None = None,
            stdin_path: str | os.PathLike | None = None) -> dict:
    """执行 lark-cli 并解析 JSON 信封；网络层异常包装为 type=network 的统一结构。

    官方 CLI 的失败信封可能写在 stderr（评审 P2-4）：stdout 解析不到时必须再试
    stderr，否则 network/timeout 会被错标成 cli/bad_output，重试分支失效、
    权限 code/hint 丢失。

    stdin_text 用于把正文直接送入 CLI（对应 --content - / --markdown -）。
    CLI 的 @file 只接受 cwd、/tmp、~/files 三个根；运行时工作目录由 paths.py
    推导到仓库父级，不在白名单内，故正文必须走 stdin，不能落临时文件。

    传 stdin_path 时由本函数读文件，调用方只需把参数换成 "-" 并给出路径，
    便于测试在不落盘的情况下模拟。
    """
    if stdin_text is None and stdin_path is not None:
        stdin_text = pathlib.Path(stdin_path).read_text(encoding="utf-8")
    env, removed = adapt_proxy_env()
    try:
        p = subprocess.run([cli, *args], input=stdin_text, capture_output=True,
                           text=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"type": "network", "subtype": "timeout", "detail": f"{timeout}s 超时",
                                       "_removed_proxies": removed}}
    except OSError as e:
        return {"ok": False, "error": {"type": "network", "subtype": type(e).__name__, "detail": str(e),
                                       "_removed_proxies": removed}}
    out = _parse_envelope(p.stdout)
    if out is None:
        out = _parse_envelope(p.stderr)
    if out is None:
        out = {"error": {"type": "cli", "subtype": "bad_output", "detail": (p.stderr or p.stdout)[:300]}}
    if "error" not in out and p.returncode != 0:
        out["error"] = {"type": "cli", "subtype": "exit_code",
                        "detail": f"rc={p.returncode} {(p.stderr or '')[:200]}"}
    if "error" not in out and out.get("ok") is False:
        out["error"] = {"type": "cli", "subtype": "not_ok",
                        "detail": json.dumps(out, ensure_ascii=False)[:200]}
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
    return paths.report(week[:4], week)


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


def _project_test_mode() -> bool:
    """初始化之前也适用项目隔离；配置缺失或非法时保守跳过真实通知。"""
    try:
        cfg = load_config("deployment")
        return not isinstance(cfg, dict) or cfg.get("mode") != "production"
    except Exception:
        return True


def is_test() -> bool:
    """测试模式判定：项目验收模式、TEST_RUN=1、coord.json 任一为真。

    coord --test 只写运行状态文件，不导出环境变量；手册里 TEST_RUN=1 写在单条
    命令前也不会影响后续独立命令。交付脚本必须两个来源都认，否则未导出时会
    匹配正式文档、发送真实通知。任一来源为真即按测试处理（宁可误判为测试，
    不可漏判为正式——前者最坏多一篇 [测试] 文档，后者会覆盖正式文档/发真实通知）。
    """
    if os.environ.get("TEST_RUN") == "1":
        return True
    try:
        if read_json(WORK_DIR / "coord.json").get("test"):
            return True
    except Exception:
        pass
    return _project_test_mode()


def title_matches(title: str, week: str, test: bool) -> bool:
    """查重命中条件：标题结构匹配（评审 P1-2）。

    去掉 [测试] 前缀后必须以栏目「AI 周报」开头且含本周编号（带词边界）：
    「包含」匹配会把「关于 AI 周报 · 2026-W45 的问题汇总」当成覆盖对象；
    前缀匹配开头即可，间隔号与「（回溯版）」等可变后缀不受影响。
    """
    t = (title or "").strip()
    if test:
        if not t.startswith("[测试]"):
            return False
        t = t[len("[测试]"):].strip()
    elif t.startswith("[测试]"):
        return False
    if not t.startswith("AI 周报"):
        return False
    return re.search(rf"(?<![\w-]){re.escape(week)}(?![\w-])", t) is not None


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


def ensure_mode(refresh: bool = False) -> str:
    """读降级模式。refresh=True 时重新跑 preflight：sync/notify 必须以现场状态为准，

    旧 no_doc/off 缓存会把已修复授权的补交付短路掉（评审 P2-5）。
    """
    if refresh or read_mode() is None:
        cmd_preflight(None)
    return read_mode() or "off"


# ---------------------------------------------------------------- sync

def search_candidates(cli: str, week: str, test: bool, max_pages: int = 10) -> list[dict] | None:
    """按周编号翻页搜索并过滤出本周文档候选。search 调用失败返回 None（与 0 候选区分）。

    只取首页无法证明唯一（评审 P1-2）：目标在第二页会重复 create，跨页两篇
    也不会报歧义。遍历 has_more/page_token 后再判断候选集合。
    """
    cands: list[dict] = []
    page_token = ""
    for _ in range(max_pages):
        argv = ["docs", "+search", "--query", week, "--as", "user", "--page-size", "20"]
        if page_token:
            argv += ["--page-token", page_token]
        out = run_cli(cli, *argv)
        if out.get("error"):
            return None
        data = out.get("data") or {}
        for r in data.get("results") or []:
            meta = r.get("result_meta") or {}
            if meta.get("doc_types") != "DOCX":
                continue
            title = strip_highlight(r.get("title_highlighted"))
            if title_matches(title, week, test):
                cands.append({"token": meta.get("token"), "title": title, "url": meta.get("url")})
        if not data.get("has_more"):
            return cands
        page_token = data.get("page_token") or ""
        if not page_token:
            return None
    # 搜索分页未完成，不能把已读取的部分当作零候选或唯一候选。
    return None


def _business_failure(out: dict) -> str | None:
    """业务层未完整成功的原因；完整成功（或无 result 字段的命令）返回 None。

    update/create 的 data.result ∈ success|partial_success|failed（评审 P1-3）：
    partial_success 表示写入不完整（warnings 里有失败块），不能记 updated/created。
    """
    data = out.get("data") or {}
    result = data.get("result")
    if result in (None, "success"):
        return None
    warnings = "; ".join(str(w) for w in (data.get("warnings") or []))[:200]
    return f"result={result}" + (f" warnings={warnings}" if warnings else "")


def _overwrite(cli: str, token: str, content_file: pathlib.Path) -> dict:
    """覆盖已有文档。幂等：网络失败与写入不完整（partial_success/failed）都可重试。"""
    out = run_cli(cli, "docs", "+update", "--doc", token, "--command", "overwrite",
                  "--doc-format", "markdown", "--content", "-", "--as", "user",
                  stdin_path=content_file)
    if out.get("error"):
        return {"action": "retry" if (out["error"].get("type") == "network") else "failed", "error": out["error"]}
    why = _business_failure(out)
    if why:
        return {"action": "retry", "error": {"type": "business", "subtype": "partial_write", "detail": why}}
    return {"action": "updated", "document_id": token}


def _create(cli: str, title: str, content_file: pathlib.Path, folder: str) -> dict:
    """创建文档。超时/网络失败不重试：响应丢失时文档可能已建，而索引有延迟，

    重搜为空不能证明未创建；盲目再 create 会产生重复文档（评审修正点 2）。
    网络类失败返回 action=unknown（结果不明），写入 feishu.json 供下次补交付收敛，
    不能像普通失败一样丢弃（评审 P2-5）。
    """
    argv = ["docs", "+create", "--doc-format", "markdown", "--content", "-",
            "--title", title, "--as", "user"]
    if folder:
        argv += ["--parent-token", folder]
    out = run_cli(cli, *argv, stdin_path=content_file)
    if out.get("error"):
        err = out["error"]
        return {"action": "unknown" if err.get("type") == "network" else "failed", "error": err}
    why = _business_failure(out)
    if why:
        return {"action": "failed", "error": {"type": "business", "subtype": "partial_write", "detail": why}}
    doc = (out.get("data") or {}).get("document") or {}
    if not doc.get("document_id"):
        return {"action": "failed", "error": {"type": "business", "subtype": "no_document_id",
                                              "detail": "create 返回缺少 document_id"}}
    return {"action": "created", "document_id": doc["document_id"], "url": doc.get("url")}


def _sync_via_search(cli: str, week: str, test: bool, title: str,
                     content_file: pathlib.Path, folder: str, forbid_create: bool = False) -> dict:
    """搜索查重路径：>1 候选拒绝覆盖、1 候选 overwrite、0 候选 create。

    forbid_create：上次 create 结果不明（action=unknown）时，0 候选不能证明未创建
    （可能已建但索引未收录），拒绝盲目重建，报 FEISHU_CREATE_UNKNOWN 人工核查（评审 P2-5）。
    """
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
        if forbid_create:
            tracelog.log("飞书", "同步", "error", "FEISHU_CREATE_UNKNOWN",
                         "上次 create 结果不明且搜索 0 候选：文档可能已建但索引未收录，拒绝盲目重建")
            return {"action": "failed",
                    "error": {"type": "business", "subtype": "create_unknown",
                              "detail": "上次 create 结果不明，搜索 0 候选不能证明未创建，人工核查后重试"}}
        return _create(cli, title, content_file, folder)  # create 不重试（见函数注释）
    return {"action": "failed"}


def _cached_result(week: str, test: bool) -> dict | None:
    """上次同步结果文件里本周的记录（同机紧接重跑的幂等兜底）。

    create 成功后搜索索引有延迟（实测数十秒内查不到），立刻重跑会因 0 候选
    重复 create；用结果文件里的 document_id 直接 overwrite 可避开索引窗口。
    week/test 匹配即返回（含 action=unknown 的无 document_id 记录，评审 P2-5）。
    """
    try:
        d = read_json(WORK_DIR / RESULT_FILE)
    except Exception:
        return None
    if d.get("week") == week and bool(d.get("test")) == test:
        return d
    return None


# 只有响应明确表示「文档不存在」才能判 missing。权限不足、网络超时、CLI 输出
# 异常都不能证明文档不存在；若当成 missing，会落到搜索 0 候选 create，在权限
# 不足或索引延迟时产生重复文档（版本规划 P0）。分类风格同 classify_push_error。
_NOT_FOUND_MARKERS = ("not_found", "notfound", "not found", "404", "does not exist",
                      "doc_not_exist", "document not found", "文档不存在")


def _doc_state(cli: str, token: str) -> str:
    """缓存文档状态：exists / missing / unknown（评审 P2-5、版本规划 P0）。

    网络类失败是 unknown——临时读失败被当成不存在，叠加搜索索引延迟会重复 create。
    权限类失败同样是 unknown：不是 network，但也不能证明文档不存在。
    只有明确 not-found 才判 missing；无法归类时保守取 unknown（宁可停下人工核查，
    也不重复建文档）。
    """
    out = run_cli(cli, "docs", "+fetch", "--doc", token, "--as", "user")
    err = out.get("error")
    if not err:
        return "exists"
    blob = " ".join(str(err.get(k, "")) for k in ("type", "subtype", "code", "detail")).lower()
    if err.get("type") != "network" and any(k in blob for k in _NOT_FOUND_MARKERS):
        return "missing"
    return "unknown"


def cmd_sync(args) -> int:
    mode = ensure_mode(refresh=True)
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
    forbid_create = bool(cached and cached.get("action") == "unknown"
                         and not cached.get("document_id"))
    if cached and cached.get("document_id"):
        state = _doc_state(cli, cached["document_id"])
        if state == "exists":
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
        elif state == "unknown":
            # 临时读失败不能当不存在：宁可失败也不落到搜索 0 候选 create（评审 P2-5）
            tracelog.log("飞书", "同步", "error", "FEISHU_SYNC_FAILED",
                         f"缓存文档 {cached['document_id']} 读取结果不明，为避免重复创建终止")
            result = {"action": "failed",
                      "error": {"type": "network", "subtype": "fetch_unknown",
                                "detail": f"缓存文档 {cached['document_id']} 读取结果不明，人工核查后重试"}}
        # missing → 落入搜索路径
    if result is None:
        result = _sync_via_search(cli, week, test, title, content_file, folder,
                                  forbid_create=forbid_create)

    result = result or {"action": "failed"}
    action = result.get("action")
    out_obj = {"week": week, "test": test, "title": title, **{k: v for k, v in result.items() if k != "error"}}
    if forbid_create and action not in ("created", "updated"):
        # 本次错误照常报告。查不到、查不全或更新失败都不能证明上次创建未成功。
        # 保留上次结果不明，后续补交付才会继续禁止新建。
        out_obj["action"] = "unknown"
    if action not in ("created", "updated") and cached and cached.get("document_id"):
        # 版本规划 P0：失败或结果不明时不得丢掉已知文档 ID。否则下次补交付
        # _cached_result 拿不到 ID 就会退回搜索，0 候选（索引延迟/权限不足）时
        # 重复建文档。只有确认原文档不存在（_doc_state=missing）并完成查重后
        # 新建成功，才会用新的 document_id 覆盖这里。
        out_obj.setdefault("document_id", cached["document_id"])
        if cached.get("url"):
            out_obj.setdefault("url", cached["url"])
    write_json(WORK_DIR / RESULT_FILE, out_obj)
    if action in ("created", "updated"):
        tracelog.log("飞书", "同步", "ok", detail=f"{action} {result.get('document_id')}",
                     document_id=result.get("document_id"), url=result.get("url"))
        print(f"SYNC={action} document_id={result.get('document_id')}")
        return 0
    code = {"ambiguous": "FEISHU_AMBIGUOUS_DOC", "unknown": "FEISHU_SYNC_UNKNOWN"}.get(action, "FEISHU_SYNC_FAILED")
    tracelog.log("飞书", "同步", "error", code, json.dumps(result.get("error") or {}, ensure_ascii=False)[:200])
    print(f"SYNC=error CODE={code}")
    return 1


# ---------------------------------------------------------------- verify

def cmd_verify(args) -> int:
    """只读核对指定提交与实际文档，失败时保留 sync 的文档 ID 供补交付。"""
    from document_compare import compare_documents

    week = args.week or week_from_weekjson()
    receipt = {"week": week, "source_sha": args.sha, "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}

    def record(status: str, code: str | None = None) -> int:
        receipt.update(status=status, code=code)
        write_json(WORK_DIR / READBACK_FILE, receipt)
        tracelog.log("飞书", "正文核对", "ok" if status == "passed" else "warn", code,
                     source_sha=receipt["source_sha"], document_id=receipt.get("document_id"))
        print(f"READBACK={status}" + (f" CODE={code}" if code else ""))
        return 0 if status == "passed" else 1

    if not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        return record("failed", "FEISHU_READBACK_SHA_REQUIRED")
    try:
        week = Week.parse(week or "").label
    except ValueError:
        return record("failed", "FEISHU_WEEK_UNKNOWN")
    token = args.doc
    if not token:
        cached = _cached_result(week, test=False) or {}
        if cached.get("action") in ("created", "updated"):
            token = cached.get("document_id")
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        return record("failed", "FEISHU_READBACK_DOC_REQUIRED")
    receipt["document_id"] = token
    expected = git_show(args.sha, report_path_for(week))
    if not expected:
        return record("failed", "FEISHU_SOURCE_MISSING")
    cli = find_cli(cfg_load() or {})
    if not cli:
        return record("failed", "FEISHU_CLI_NOT_FOUND")
    out = run_cli(cli, "docs", "+fetch", "--doc", token, "--as", "user")
    data = out.get("data")
    if out.get("error") or not isinstance(data, dict) or _business_failure(out):
        return record("pending", "FEISHU_READBACK_UNAVAILABLE")
    document = data.get("document")
    actual = document.get("content") if isinstance(document, dict) else None
    if not isinstance(actual, str) or not actual or document.get("document_id", token) != token:
        return record("pending", "FEISHU_READBACK_UNAVAILABLE")
    comparison = compare_documents(expected, actual)
    receipt.update(comparison)
    if comparison["content_match"] != "normalized_equal":
        return record("pending", "FEISHU_READBACK_MISMATCH")
    return record("passed")


# ---------------------------------------------------------------- notify

def cmd_notify(args) -> int:
    if is_test():
        print("NOTIFY=skipped test=1")
        return 0
    (WORK_DIR / NOTIFY_FILE).unlink(missing_ok=True)
    mode = ensure_mode(refresh=True)
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

    def send(file: str, k: str) -> dict:
        # 正文走 stdin：CLI 的 @file 白名单不含仓库父级下的运行时工作目录。
        return run_cli(cli, "im", "+messages-send", "--as", "bot", "--user-id", uid,
                       "--markdown", "-", "--idempotency-key", k,
                       stdin_path=file)

    out = send(args.file, key)
    err = out.get("error")
    if err and err.get("type") == "network":
        # 结果不明：首条可能已送达，换键重发会双发（评审 P2-6）。
        # 用同一幂等键重试一次（服务端按幂等键去重），仍不明则报 unknown 人工核对。
        out = send(args.file, key)
        if out.get("error"):
            e = out["error"]
            tracelog.log("飞书", "通知", "error", "FEISHU_NOTIFY_UNKNOWN",
                         (e.get("detail") or e.get("subtype") or "")[:200])
            print("NOTIFY=unknown CODE=FEISHU_NOTIFY_UNKNOWN")
            return 1
    elif err and args.fallback_file and pathlib.Path(args.fallback_file).exists():
        # 确定拒绝（业务/权限类）：首条未发出，可安全换键发精简版
        key += "-fb"
        out = send(args.fallback_file, key)
    if out.get("error"):
        err = out["error"]
        tracelog.log("飞书", "通知", "error", "FEISHU_NOTIFY_FAILED",
                     (err.get("detail") or err.get("subtype") or "")[:200])
        print("NOTIFY=failed CODE=FEISHU_NOTIFY_FAILED")
        return 1
    data = out.get("data")
    message_id = data.get("message_id") if isinstance(data, dict) else None
    receipt = {"week": week, "status": "api_accepted", "idempotency_key": key,
               "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    if isinstance(message_id, str) and re.fullmatch(r"[A-Za-z0-9_-]+", message_id):
        receipt["message_id"] = message_id
    write_json(WORK_DIR / NOTIFY_FILE, receipt)
    tracelog.log("飞书", "通知", "ok", detail=f"idempotency={key}")
    print("NOTIFY=sent")
    return 0


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="飞书交付：preflight / sync / verify / notify")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight", help="飞书环境预检（写 feishu-mode.json）")
    sp = sub.add_parser("sync", help="同步周报到飞书")
    sp.add_argument("--from-published", action="store_true", help="同步 git 已发布内容（语义标记，源始终取自 git）")
    sp.add_argument("--sha", help="已发布的提交号（缺省 main）")
    sp.add_argument("--week", help="ISO 周（缺省读 week.json）")
    sp.add_argument("--report", help="仓库内周报相对路径（缺省按周推导）")
    sp = sub.add_parser("verify", help="只读核对正式飞书文档与指定已发布提交")
    sp.add_argument("--sha", required=True, help="已发布的完整提交号")
    sp.add_argument("--week", help="ISO 周（缺省读 week.json）")
    sp.add_argument("--doc", help="文档 ID（缺省读本周正式同步结果）")
    sp = sub.add_parser("notify", help="以 bot 发送通知")
    sp.add_argument("--file", required=True, help="通知正文文件")
    sp.add_argument("--fallback-file", help="发送失败时的精简版文件")
    args = ap.parse_args()
    return {"preflight": cmd_preflight, "sync": cmd_sync, "verify": cmd_verify, "notify": cmd_notify}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
