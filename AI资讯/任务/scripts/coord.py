"""协调与锁：决定本次运行做什么，并靠 git 推送在多个智能体之间互斥。规则见 ../方案.md 7.9 节。

状态文件 AI资讯/数据/运行记录/{WEEK}.json 放在 main 上，同时是锁和当周的执行记录。
所有写操作都是"在远端最新的 main 上生成一个新提交并推送"：推送只有在远端仍是读到的那个提交时
才会被接受，所以同一时刻只有一个持有者。推送被拒时不变基、不合并，重新读取远端状态再决定。
运行过程中不改动仓库工作区：产出在 OUT_DIR（/tmp/ai-weekly/out）下，提交时由本脚本写入。

命令（先运行 weeks.py 生成 /tmp/ai-weekly/week.json）：
    coord.py start --platform NAME [--test]   决定本次做什么并取得锁
    coord.py wait                              等待持锁者，结果同 start
    coord.py renew                             检查点续期（租约剩余不足阈值时才推送）
    coord.py publish [--quality full|degraded|check_failed] [--allow-quality-override]
                                               推送前跑 check_run.py 推导质量，再提交 OUT_DIR 下的产出和状态文件
    coord.py verified --result pass|fail [--codes A,B] [--detail 说明]
                                               写校验结果；fail 时把锁转为运行，接着重跑
    coord.py fail --code CODE [--detail 说明]  放弃本次运行：释放锁，记录原因
    coord.py status [--week W]                 查看状态

输出第一行固定为 ACTION=...，执行手册按它分流：
    run      取得运行锁，完整运行
    verify   取得校验锁，做独立校验
    wait     有其他运行持锁，调用 coord.py wait 等待
    exit     本次不需要做任何事（已完成、需人工、他人在校验、本次刚产出）
    published / done / lost / error  见各命令说明
--test 时远端换成本地模拟仓库（共享本仓库的对象，不复制），不碰 GitHub。
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import pathlib
import random
import re
import string
import subprocess
import sys
import time

import tracelog
from common import OUT_DIR, REPO_DIR, WORK_DIR, load_config, read_json, write_json

BJT = dt.timezone(dt.timedelta(hours=8))
SCHEMA = 1
TASK = "ai-weekly"
PHASES = ("idle", "running", "produced", "verifying", "done", "needs_human")
COORD_FILE = "coord.json"
EXIT_ERROR, EXIT_LOST, EXIT_DENIED, EXIT_INVALID = 1, 4, 3, 5


class CoordError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}：{detail}")
        self.code, self.detail = code, detail


# ---------------------------------------------------------------- 配置与上下文


def coord_config() -> dict:
    cfg = dict(load_config("runtime")["coordination"])
    # 仅供测试：用环境变量覆盖时间参数（如把等待间隔缩短到 1 秒）
    override = os.environ.get("AI_WEEKLY_COORD")
    if override:
        cfg.update(json.loads(override))
    return cfg


@dataclasses.dataclass
class Ctx:
    repo: pathlib.Path
    work: pathlib.Path
    remote: str
    branch: str
    week: str
    mode: str  # normal / backfill（来自 week.json）
    report_path: str
    data_path: str
    state_path: str
    run_id: str
    platform: str
    test: bool
    cfg: dict

    @property
    def out(self) -> pathlib.Path:
        return self.work / "out"


def now() -> dt.datetime:
    return dt.datetime.now(BJT)


def iso(t: dt.datetime) -> str:
    return t.astimezone(BJT).isoformat(timespec="seconds")


def parse_time(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


def new_run_id(platform: str, t: dt.datetime) -> str:
    tail = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{platform}-{t.strftime('%Y%m%d-%H%M%S')}-{tail}"


def load_ctx(work: pathlib.Path = WORK_DIR) -> Ctx:
    try:
        saved = read_json(work / COORD_FILE)
    except OSError:
        raise CoordError("INTERNAL", f"没有 {work / COORD_FILE}：先运行 coord.py start")
    return ctx_from(saved, work)


def ctx_from(saved: dict, work: pathlib.Path) -> Ctx:
    return Ctx(
        repo=pathlib.Path(saved["repo"]), work=work, remote=saved["remote"], branch=saved["branch"],
        week=saved["week"], mode=saved["mode"], report_path=saved["report_path"],
        data_path=saved["data_path"], state_path=saved["state_path"], run_id=saved["run_id"],
        platform=saved["platform"], test=saved["test"], cfg=coord_config(),
    )


def save_ctx(ctx: Ctx, **extra) -> None:
    path = ctx.work / COORD_FILE
    try:
        saved = read_json(path)
    except OSError:
        saved = {}
    saved.update({
        "repo": str(ctx.repo), "remote": ctx.remote, "branch": ctx.branch, "week": ctx.week,
        "mode": ctx.mode, "report_path": ctx.report_path, "data_path": ctx.data_path,
        "state_path": ctx.state_path, "run_id": ctx.run_id, "platform": ctx.platform, "test": ctx.test,
    })
    saved.update(extra)
    write_json(path, saved)


def saved_value(ctx: Ctx, key: str, default=None):
    try:
        return read_json(ctx.work / COORD_FILE).get(key, default)
    except OSError:
        return default


# ---------------------------------------------------------------- git


def git(ctx: Ctx, *args: str, data: bytes | None = None, env: dict | None = None,
        check: bool = True) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    full_env.update(env or {})
    p = subprocess.run(["git", "-C", str(ctx.repo), *args], input=data, capture_output=True, env=full_env)
    if check and p.returncode != 0:
        raise CoordError("INTERNAL", f"git {' '.join(args[:3])} 失败：{p.stderr.decode('utf-8', 'replace').strip()}")
    return p


def out_text(p: subprocess.CompletedProcess) -> str:
    return p.stdout.decode("utf-8", "replace").strip()


def remote_tip(ctx: Ctx) -> str:
    """拉取远端分支，返回其最新提交。网络错误按 2、4、8 秒重试。"""
    last = ""
    for attempt in range(4):
        p = git(ctx, "fetch", "-q", ctx.remote, ctx.branch, check=False)
        if p.returncode == 0:
            return out_text(git(ctx, "rev-parse", "FETCH_HEAD"))
        last = p.stderr.decode("utf-8", "replace").strip()
        if attempt < 3:
            time.sleep(2 * 2**attempt)
    raise CoordError("PUSH_NETWORK", f"拉取远端失败：{last}")


def read_at(ctx: Ctx, sha: str, path: str) -> bytes | None:
    p = git(ctx, "cat-file", "-e", f"{sha}:{path}", check=False)
    if p.returncode != 0:
        return None
    return git(ctx, "cat-file", "blob", f"{sha}:{path}").stdout


def last_subject(ctx: Ctx, sha: str, path: str) -> str | None:
    s = out_text(git(ctx, "log", "-1", "--format=%s", sha, "--", path, check=False))
    return s or None


def identity_env(ctx: Ctx) -> dict:
    """仓库没有配置提交身份时，用任务自己的身份。"""
    env = {}
    if not out_text(git(ctx, "config", "user.name", check=False)):
        env.update(GIT_AUTHOR_NAME="ai-weekly", GIT_COMMITTER_NAME="ai-weekly")
    if not out_text(git(ctx, "config", "user.email", check=False)):
        env.update(GIT_AUTHOR_EMAIL="ai-weekly@users.noreply.github.com",
                   GIT_COMMITTER_EMAIL="ai-weekly@users.noreply.github.com")
    return env


def make_commit(ctx: Ctx, base: str, files: dict[str, bytes], message: str) -> str:
    """在 base 之上生成一个只改 files 的提交，不碰工作区和本地分支。"""
    index = ctx.work / "coord.index"
    env = {"GIT_INDEX_FILE": str(index)}
    if index.exists():
        index.unlink()
    git(ctx, "read-tree", base, env=env)
    for path, data in files.items():
        blob = out_text(git(ctx, "hash-object", "-w", "--stdin", data=data))
        git(ctx, "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=env)
    tree = out_text(git(ctx, "write-tree", env=env))
    index.unlink()
    env = identity_env(ctx)
    return out_text(git(ctx, "commit-tree", tree, "-p", base, data=message.encode("utf-8"), env=env))


def push(ctx: Ctx, sha: str) -> str:
    """推送提交到远端分支。返回 ok / rejected / denied / network。"""
    p = git(ctx, "push", "-q", ctx.remote, f"{sha}:refs/heads/{ctx.branch}", check=False)
    if p.returncode == 0:
        return "ok"
    err = p.stderr.decode("utf-8", "replace").lower()
    if any(k in err for k in ("rejected", "fetch first", "non-fast-forward", "cannot lock ref", "stale info")):
        return "rejected"
    if any(k in err for k in ("permission", "denied", "403", "not allowed", "protected branch")):
        return "denied"
    return "network"


def sync_local(ctx: Ctx, sha: str) -> None:
    """正式运行时把本地分支快进到刚推送的提交，避免下次同步时冲突；失败只记录。"""
    if ctx.test or ctx.remote != "origin":
        return
    branch = out_text(git(ctx, "rev-parse", "--abbrev-ref", "HEAD", check=False))
    if branch != ctx.branch:
        return
    p = git(ctx, "merge", "--ff-only", "-q", sha, check=False)
    if p.returncode != 0:
        tracelog.log("协调", "本地快进", "warn", detail=p.stderr.decode("utf-8", "replace").strip()[:200],
                     work_dir=ctx.work)


def setup_sandbox(repo: pathlib.Path, work: pathlib.Path, branch: str) -> str:
    """测试模式的模拟远端：裸仓库借用本仓库的对象（alternates），不复制数据。"""
    path = work / "sandbox.git"
    if not path.exists():
        subprocess.run(["git", "init", "-q", "--bare", str(path)], check=True)
        objects = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-path", "objects"],
                                 capture_output=True, text=True, check=True).stdout.strip()
        objects = (repo / objects).resolve() if not os.path.isabs(objects) else pathlib.Path(objects)
        (path / "objects" / "info" / "alternates").write_text(str(objects) + "\n")
        p = subprocess.run(["git", "-C", str(repo), "ls-remote", "origin", f"refs/heads/{branch}"],
                           capture_output=True, text=True)
        tip = p.stdout.split()[0] if p.returncode == 0 and p.stdout.strip() else ""
        if tip:
            subprocess.run(["git", "-C", str(repo), "fetch", "-q", "origin", branch], check=True)
        else:
            tip = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                 capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(["git", "--git-dir", str(path), "update-ref", f"refs/heads/{branch}", tip], check=True)
    return str(path)


# ---------------------------------------------------------------- 状态（纯函数，便于测试）


def validate_state(state, week: str) -> str | None:
    """状态文件格式不对时返回原因。"""
    if not isinstance(state, dict):
        return "不是 JSON 对象"
    if state.get("task") != TASK or state.get("week") != week:
        return f"task/week 不匹配：{state.get('task')}/{state.get('week')}"
    if state.get("phase") not in PHASES:
        return f"未知 phase：{state.get('phase')}"
    if not isinstance(state.get("attempts", 0), int):
        return "attempts 不是整数"
    lock = state.get("lock")
    if lock is not None and not (isinstance(lock, dict) and {"purpose", "run_id", "lease_until"} <= lock.keys()):
        return "lock 字段不完整"
    if state["phase"] in ("running", "verifying") and not lock:
        return f"{state['phase']} 状态没有锁"
    return None


def lease_expired(lock: dict, t: dt.datetime, skew_minutes: float) -> bool:
    return t > parse_time(lock["lease_until"]) + dt.timedelta(minutes=skew_minutes)


def decide(state: dict | None, t: dt.datetime, run_id: str, cfg: dict) -> tuple[str, str]:
    """根据状态决定动作：run / takeover / verify / verify_takeover / wait / exit / needs_human。"""
    if state is None:
        return "run", "本周还没有运行"
    phase, lock = state["phase"], state.get("lock")
    attempts, max_attempts = state.get("attempts", 0), cfg["max_attempts"]
    skew = cfg["clock_skew_minutes"]
    if phase == "done":
        v = state.get("verified") or {}
        return "exit", f"本周已完成（{v.get('platform', '?')} 于 {v.get('at', '?')} 校验通过）"
    if phase == "needs_human":
        return "exit", "本周已标为需人工处理"
    if phase == "idle":
        if attempts >= max_attempts:
            return "needs_human", f"产出尝试已达 {attempts} 次"
        return "run", "上次运行失败，重新运行" if attempts else "本周还没有运行"
    if phase == "running":
        if lock["run_id"] == run_id:
            return "run", "本次运行已持有运行锁"
        if not lease_expired(lock, t, skew):
            return "wait", f"{lock.get('platform', '?')} 正在运行，租约到 {lock['lease_until']}"
        if attempts >= max_attempts:
            return "needs_human", f"持锁者租约已过期，产出尝试已达 {attempts} 次"
        return "takeover", f"{lock.get('platform', '?')} 的租约已于 {lock['lease_until']} 过期"
    if phase == "produced":
        prod = state.get("produced") or {}
        if prod.get("run_id") == run_id:
            return "exit", "本次运行刚产出，不校验自己的产出"
        return "verify", f"{prod.get('platform', '?')} 已产出（{prod.get('quality', '?')}），尚未独立校验"
    if phase == "verifying":
        if lock["run_id"] == run_id:
            return "verify", "本次运行已持有校验锁"
        if not lease_expired(lock, t, skew):
            return "exit", f"{lock.get('platform', '?')} 正在校验，周报已产出"
        return "verify_takeover", f"{lock.get('platform', '?')} 的校验锁已于 {lock['lease_until']} 过期"
    return "exit", f"未知状态 {phase}"


def empty_state(week: str) -> dict:
    return {"schema": SCHEMA, "task": TASK, "week": week, "phase": "idle", "lock": None,
            "attempts": 0, "produced": None, "verified": None, "runs": [], "events": []}


def _run_entry(state: dict, run_id: str) -> dict | None:
    for r in reversed(state["runs"]):
        if r["run_id"] == run_id:
            return r
    return None


def _lock(ctx: Ctx, purpose: str, t: dt.datetime) -> dict:
    minutes = ctx.cfg["run_lease_minutes"] if purpose == "run" else ctx.cfg["verify_lease_minutes"]
    return {"purpose": purpose, "run_id": ctx.run_id, "platform": ctx.platform,
            "acquired_at": iso(t), "lease_until": iso(t + dt.timedelta(minutes=minutes))}


def run_mode(state: dict | None, ctx: Ctx, action: str, report_exists: bool) -> str:
    if ctx.mode == "backfill":
        return "backfill"
    if action == "takeover":
        return "takeover"
    if (state and state.get("produced")) or report_exists:
        return "rerun"
    return "normal"


def apply_acquire(state: dict | None, ctx: Ctx, action: str, t: dt.datetime, mode: str, reason: str) -> dict:
    s = json.loads(json.dumps(state)) if state else empty_state(ctx.week)
    purpose = "run" if action in ("run", "takeover") else "verify"
    s["lock"] = _lock(ctx, purpose, t)
    if purpose == "run":
        s["phase"] = "running"
        s["attempts"] = s.get("attempts", 0) + 1
    else:
        s["phase"] = "verifying"
    if not _run_entry(s, ctx.run_id):
        s["runs"].append({"run_id": ctx.run_id, "platform": ctx.platform, "started_at": iso(t)})
    entry = _run_entry(s, ctx.run_id)
    entry.update({"action": purpose, "mode": mode if purpose == "run" else "verify", "reason": reason,
                  "outcome": "running"})
    return s


def apply_needs_human(state: dict, ctx: Ctx, t: dt.datetime, reason: str) -> dict:
    s = json.loads(json.dumps(state))
    s["phase"], s["lock"] = "needs_human", None
    s["runs"].append({"run_id": ctx.run_id, "platform": ctx.platform, "started_at": iso(t),
                      "ended_at": iso(t), "action": "none", "outcome": "needs_human", "reason": reason,
                      "codes": ["ATTEMPTS_EXHAUSTED"]})
    return s


def apply_renew(state: dict, ctx: Ctx, t: dt.datetime) -> dict:
    s = json.loads(json.dumps(state))
    s["lock"] = _lock(ctx, s["lock"]["purpose"], t) | {"acquired_at": s["lock"]["acquired_at"]}
    return s


def _finish_entry(s: dict, ctx: Ctx, t: dt.datetime, outcome: str, codes: list[str], summary: dict | None,
                  **extra) -> None:
    entry = _run_entry(s, ctx.run_id)
    if entry is None:
        entry = {"run_id": ctx.run_id, "platform": ctx.platform, "started_at": iso(t)}
        s["runs"].append(entry)
    entry.update({"ended_at": iso(t), "outcome": outcome, "codes": codes, **extra})
    if summary is not None:
        entry["summary"] = summary


def apply_publish(state: dict, ctx: Ctx, t: dt.datetime, quality: str, files: list[str],
                  codes: list[str], summary: dict | None, gates: dict | None = None) -> dict:
    s = json.loads(json.dumps(state))
    entry = _run_entry(s, ctx.run_id) or {}
    s["phase"], s["lock"] = "produced", None
    s["produced"] = {"run_id": ctx.run_id, "platform": ctx.platform, "at": iso(t), "quality": quality,
                     "mode": entry.get("mode", "normal"), "files": files,
                     "gates": json.loads(json.dumps(gates or {}))}  # 深拷贝：重试时改的是状态里的那份
    s["verified"] = None
    _finish_entry(s, ctx, t, f"produced:{quality}", codes, summary)
    return s


def apply_verified(state: dict, ctx: Ctx, t: dt.datetime, result: str, codes: list[str], detail: str,
                   summary: dict | None) -> tuple[dict, str]:
    """返回 (新状态, 下一步动作)：done / run（转为运行，重跑）/ needs_human。"""
    s = json.loads(json.dumps(state))
    s["verified"] = {"run_id": ctx.run_id, "platform": ctx.platform, "at": iso(t), "result": result,
                     "codes": codes, "detail": detail}
    if result == "pass":
        s["phase"], s["lock"] = "done", None
        _finish_entry(s, ctx, t, "verified:pass", codes, summary)
        return s, "done"
    if s.get("attempts", 0) >= ctx.cfg["max_attempts"]:
        s["phase"], s["lock"] = "needs_human", None
        _finish_entry(s, ctx, t, "verified:fail", codes + ["ATTEMPTS_EXHAUSTED"], summary)
        return s, "needs_human"
    # 不通过：同一把锁直接转为运行，由本次运行重跑，中间没有空档
    _finish_entry(s, ctx, t, "verified:fail", codes, summary)
    s["phase"], s["lock"] = "running", _lock(ctx, "run", t)
    s["attempts"] = s.get("attempts", 0) + 1
    s["runs"].append({"run_id": ctx.run_id, "platform": ctx.platform, "started_at": iso(t),
                      "action": "run", "mode": "rerun", "reason": "校验不通过：" + ",".join(codes),
                      "outcome": "running"})
    return s, "run"


def apply_fail(state: dict, ctx: Ctx, t: dt.datetime, code: str, detail: str, summary: dict | None) -> dict:
    """放弃本次运行。校验中失败：周报已在，回到"已产出"等下一个校验；运行中失败：回到空闲或需人工。"""
    s = json.loads(json.dumps(state))
    codes = [code]
    if s["lock"]["purpose"] == "verify":
        s["phase"] = "produced"
    elif s.get("attempts", 0) >= ctx.cfg["max_attempts"]:
        s["phase"] = "needs_human"
        codes.append("ATTEMPTS_EXHAUSTED")
    else:
        s["phase"] = "idle"
    s["lock"] = None
    _finish_entry(s, ctx, t, "failed", codes, summary, detail=detail)
    return s


def merge_events(state: dict, events: list[dict], cap: int) -> dict:
    s = dict(state)
    s["events"] = (list(state.get("events", [])) + [tracelog.compact(e) for e in events])[-cap:]
    return s


def holds(state: dict | None, run_id: str, purpose: str) -> bool:
    lock = (state or {}).get("lock")
    return bool(lock) and lock["run_id"] == run_id and lock["purpose"] == purpose


# ---------------------------------------------------------------- 读写状态


def state_bytes(state: dict) -> bytes:
    return (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_state(ctx: Ctx, sha: str) -> dict | None:
    raw = read_at(ctx, sha, ctx.state_path)
    if raw is None:
        return None
    try:
        state = json.loads(raw)
    except ValueError:
        raise CoordError("STATE_INVALID", "状态文件不是合法的 JSON")
    why = validate_state(state, ctx.week)
    if why:
        raise CoordError("STATE_INVALID", why)
    return state


def new_events(ctx: Ctx) -> tuple[list[dict], int]:
    merged = saved_value(ctx, "merged_seq", 0)
    events = [e for e in tracelog.read_events(ctx.work) if e.get("seq", 0) > merged]
    last = max([merged] + [e.get("seq", 0) for e in events])
    return events, last


def write_state(ctx: Ctx, build, message_for, extra_files=None) -> tuple[str, dict, object]:
    """读取远端状态 → build(state, tip) 生成新状态 → 提交并推送；被拒就重新读取、重新生成。

    build 返回 (new_state, result)；new_state 为 None 表示不需要写（直接返回）。
    extra_files(state, tip) 返回要一起提交的其他文件。返回 (提交, 新状态, result)。
    """
    retries = ctx.cfg["push_retries"]
    for attempt in range(retries + 1):
        tip = remote_tip(ctx)
        state = read_state(ctx, tip)
        new_state, result = build(state, tip)
        if new_state is None:
            return "", state, result
        events, last_seq = new_events(ctx)
        new_state = merge_events(new_state, events, load_config("runtime")["trace"]["max_events_in_state"])
        files = dict(extra_files(new_state, tip)) if extra_files else {}
        files[ctx.state_path] = state_bytes(new_state)
        sha = make_commit(ctx, tip, files, message_for(new_state, result))
        outcome = push(ctx, sha)
        if outcome == "ok":
            save_ctx(ctx, merged_seq=last_seq)
            sync_local(ctx, sha)
            return sha, new_state, result
        tracelog.log("协调", "推送", "warn", "PUSH_REJECTED" if outcome == "rejected" else None,
                     f"第 {attempt + 1} 次推送：{outcome}", work_dir=ctx.work)
        if outcome == "denied":
            raise CoordError("PUSH_DENIED", "没有推送远端分支的权限")
        if outcome == "network":
            time.sleep(min(2 * 2**attempt, 16))
        else:
            time.sleep(random.uniform(0.2, 1.5))  # 被拒：错开一点再重新读取
    raise CoordError("PUSH_REJECTED", f"推送被拒 {retries + 1} 次")


# ---------------------------------------------------------------- 命令


def emit(action: str, *lines: str) -> None:
    print(f"ACTION={action}")
    for line in lines:
        print(line)


ACTION_OUT = {"run": "run", "takeover": "run", "verify": "verify", "verify_takeover": "verify"}


def acquire(ctx: Ctx) -> tuple[str, str]:
    """决定并取得锁。返回 (输出动作, 说明)。"""
    t = now()

    def build(state, tip):
        action, reason = decide(state, t, ctx.run_id, ctx.cfg)
        if action in ("exit", "wait"):
            return None, (action, reason)
        if action == "needs_human":
            return apply_needs_human(state, ctx, t, reason), ("exit", "已标为需人工：" + reason)
        if state and holds(state, ctx.run_id, "run" if action in ("run", "takeover") else "verify"):
            return None, (ACTION_OUT[action], reason)
        report_exists = read_at(ctx, tip, ctx.report_path) is not None
        mode = run_mode(state, ctx, action, report_exists)
        return apply_acquire(state, ctx, action, t, mode, reason), (ACTION_OUT[action], reason)

    def message(state, result):
        lock = state.get("lock") or {}
        if state["phase"] == "needs_human":
            return f"AI 周报状态 {ctx.week}：需人工"
        verb = {"run": "开始运行", "verify": "开始校验"}[lock["purpose"]]
        entry = _run_entry(state, ctx.run_id) or {}
        if entry.get("mode") == "takeover":
            verb = "接管运行"
        return f"AI 周报状态 {ctx.week}：{verb}（{ctx.platform}）"

    sha, state, (action, reason) = write_state(ctx, build, message)
    if action in ("run", "verify"):
        entry = _run_entry(state, ctx.run_id) or {}
        save_ctx(ctx, purpose=action, run_mode=entry.get("mode"), acquired_commit=sha)
        tracelog.log("协调", f"取得{'运行' if action == 'run' else '校验'}锁", "ok", detail=reason,
                     work_dir=ctx.work, mode=entry.get("mode"), commit=sha)
    else:
        tracelog.log("协调", action, "info", detail=reason, work_dir=ctx.work)
    return action, reason


def cmd_start(args) -> int:
    work = WORK_DIR
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,19}", args.platform):
        emit("error", "--platform 只能用小写字母、数字和连字符，最长 20 个字符")
        return EXIT_ERROR
    try:
        info = read_json(work / "week.json")
    except OSError:
        emit("error", f"没有 {work / 'week.json'}：先运行 weeks.py")
        return EXIT_ERROR
    cfg = coord_config()
    repo = pathlib.Path(os.environ.get("AI_WEEKLY_REPO", REPO_DIR))
    remote = args.remote
    if not remote and args.test:
        remote = setup_sandbox(repo, work, cfg["branch"])
    remote = remote or "origin"
    existing = {}
    try:
        existing = read_json(work / COORD_FILE)
    except OSError:
        pass
    t = now()
    run_id = existing.get("run_id") if existing.get("week") == info["week"] else None
    ctx = Ctx(repo=repo, work=work, remote=remote, branch=cfg["branch"], week=info["week"], mode=info["mode"],
              report_path=info["report_path"], data_path=info["data_path"],
              state_path=info.get("state_path") or f"AI资讯/数据/运行记录/{info['week']}.json",
              run_id=run_id or new_run_id(args.platform, t), platform=args.platform, test=args.test, cfg=cfg)
    save_ctx(ctx, started_at=existing.get("started_at") or iso(t))
    tracelog.log("协调", "start", detail=f"{ctx.platform} {ctx.week} 远端 {ctx.remote}", work_dir=work,
                 run_id=ctx.run_id, test=ctx.test)
    return run_and_report(ctx, lambda: acquire(ctx))


def run_and_report(ctx: Ctx, fn) -> int:
    try:
        action, reason = fn()
    except CoordError as e:
        tracelog.log("协调", "错误", "error", e.code if e.code in tracelog.ERROR_CODES else "INTERNAL",
                     e.detail, work_dir=ctx.work)
        action = "lost" if e.code == "LOCK_LOST" else "error"
        emit(action, f"错误码={e.code}", e.detail)
        return {"LOCK_LOST": EXIT_LOST, "PUSH_DENIED": EXIT_DENIED, "STATE_INVALID": EXIT_INVALID}.get(
            e.code, EXIT_ERROR)
    emit(action, reason, f"run_id={ctx.run_id} week={ctx.week} remote={ctx.remote}")
    return 0


def cmd_wait(args) -> int:
    ctx = load_ctx()
    cfg = ctx.cfg
    first = saved_value(ctx, "wait_started")
    if not first:
        first = iso(now())
        save_ctx(ctx, wait_started=first)
    give_up_at = parse_time(first) + dt.timedelta(minutes=cfg["wait_max_minutes"])
    call_end = now() + dt.timedelta(seconds=cfg["wait_call_max_seconds"])

    def once():
        while True:
            action, reason = acquire(ctx)
            if action != "wait":
                return action, reason
            if now() >= give_up_at:
                record_wait_timeout(ctx, reason)
                return "exit", f"累计等待已超过 {cfg['wait_max_minutes']} 分钟，退出：{reason}"
            if now() + dt.timedelta(seconds=cfg["wait_poll_seconds"]) > call_end:
                return "wait", f"本次等待到时，再调用一次 coord.py wait（{reason}）"
            time.sleep(cfg["wait_poll_seconds"])

    return run_and_report(ctx, once)


def record_wait_timeout(ctx: Ctx, reason: str) -> None:
    t = now()

    def build(state, tip):
        s = json.loads(json.dumps(state)) if state else empty_state(ctx.week)
        s["runs"].append({"run_id": ctx.run_id, "platform": ctx.platform, "started_at": saved_value(
            ctx, "started_at", iso(t)), "ended_at": iso(t), "action": "wait", "outcome": "wait_timeout",
            "codes": ["WAIT_TIMEOUT"], "reason": reason})
        return s, None

    tracelog.log("协调", "等待超时", "warn", "WAIT_TIMEOUT", reason, work_dir=ctx.work)
    try:
        write_state(ctx, build, lambda s, r: f"AI 周报状态 {ctx.week}：等待超时退出（{ctx.platform}）")
    except CoordError:
        pass  # 记录失败不影响退出


def cmd_renew(args) -> int:
    ctx = load_ctx()
    t = now()

    def build(state, tip):
        purpose = saved_value(ctx, "purpose", "run")
        if not holds(state, ctx.run_id, purpose):
            raise CoordError("LOCK_LOST", "锁已不在本次运行手里")
        left = parse_time(state["lock"]["lease_until"]) - t
        if left > dt.timedelta(minutes=ctx.cfg["renew_below_minutes"]):
            return None, ("ok", f"租约还剩 {int(left.total_seconds() // 60)} 分钟，无需续期")
        return apply_renew(state, ctx, t), ("ok", "已续期")

    def run():
        sha, state, result = write_state(ctx, build, lambda s, r: f"AI 周报状态 {ctx.week}：续期（{ctx.platform}）")
        if sha:
            tracelog.log("协调", "续期", "ok", detail=state["lock"]["lease_until"], work_dir=ctx.work)
        return result

    return run_and_report(ctx, run)


# 允许提交的产出路径（相对仓库根目录），与入口提示词的写入白名单一致
def allowed_paths(ctx: Ctx) -> list[re.Pattern]:
    return [
        re.compile(re.escape(ctx.report_path) + r"$"),
        re.compile(re.escape(ctx.data_path) + r"$"),
        re.compile(r"AI资讯/月报/\d{4}/\d{4}-\d{2}\.md$"),
        re.compile(r"AI资讯/季报/\d{4}/\d{4}-Q[1-4]\.md$"),
    ]


def collect_outputs(ctx: Ctx) -> tuple[dict[str, bytes], list[str]]:
    files, rejected = {}, []
    if ctx.out.exists():
        patterns = allowed_paths(ctx)
        for path in sorted(p for p in ctx.out.rglob("*") if p.is_file()):
            rel = path.relative_to(ctx.out).as_posix()
            if any(p.fullmatch(rel) for p in patterns):
                files[rel] = path.read_bytes()
            else:
                rejected.append(rel)
    return files, rejected


GATE_TIMEOUT_SECONDS = 120


def report_is_degraded(path: pathlib.Path) -> bool:
    """周报元数据里的 quality 是否为 degraded（降级版）。

    与 validate.py 用同一套解析（split_front_matter + yaml.safe_load），不能各用各的：
    `quality: "degraded"` 或行尾带注释的写法，validate 认、正则不认，就会出现
    「按降级版的宽松规则校验通过，却被标成 full 发布」。
    """
    import validate  # 延迟导入：coord 只在发布时读周报元数据

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    fm_text, _ = validate.split_front_matter(text)
    if fm_text is None:
        return False
    try:
        import yaml

        fm = yaml.safe_load(fm_text) or {}
    except Exception:  # noqa: BLE001 元数据坏掉时按非降级处理，交给 validate 报结构错误
        return False
    return isinstance(fm, dict) and fm.get("quality") == "degraded"


GATE_SCRIPT = pathlib.Path(__file__).resolve().parent / "check_run.py"  # 固定，不提供替换入口


def publish_gate(ctx: Ctx) -> tuple[bool, list[str]]:
    """发布前跑 check_run.py（内含 validate.py 的全部校验与质量门槛），返回 (是否通过, 错误码)。

    门槛结果由脚本给出，不由智能体声明；崩溃、超时或输出里没有 CODES= 时，说明本轮**没拿到**
    门槛结果，一律记 GATE_UNVERIFIED（让运维去查脚本或环境），而不是 GATE_INCOMPLETE
    （那个码的语义是「步骤没做」，会把人引向返工流程）。
    """
    timeout = int((ctx.cfg.get("publish") or {}).get("gate_timeout_seconds", GATE_TIMEOUT_SECONDS))
    try:
        p = subprocess.run([sys.executable, str(GATE_SCRIPT), "--work-dir", str(ctx.work)],
                           capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return False, ["GATE_UNVERIFIED"]
    codes = []
    for line in (p.stdout or "").splitlines():
        if line.startswith("CODES="):
            codes = [c for c in line[len("CODES="):].split(",") if c]
    if p.returncode != 0 and not codes:
        return False, ["GATE_UNVERIFIED"]
    return p.returncode == 0, codes


def derive_quality(gates_ok: bool, degraded: bool, requested: str | None) -> tuple[str, str | None]:
    """quality 由门槛结果推导；requested 只作期望值，不一致时返回 GATE_MISMATCH。"""
    derived = "degraded" if degraded else ("full" if gates_ok else "check_failed")
    if requested and requested != derived:
        return derived, "GATE_MISMATCH"
    return derived, None


def override_allowed(ctx: Ctx) -> bool:
    """能不能用 --allow-quality-override 覆盖门槛结果。

    只认回溯运行（week.json 的 mode=backfill）。不看 `--test` 标志：`--test` 允许显式指定
    任意远端（`--remote origin`、生产 URL 都可以），那种运行等于在生产上跑，按名字排除 origin
    挡不住，所以干脆不给测试运行这个权限——要覆盖就把 mode 设成 backfill，那是唯一真实场景。
    """
    return ctx.mode == "backfill"


# --allow-quality-override 能豁免的失败码，只有「产物早于本次运行」这一类。
# 回溯是补历史周报，复用当周存档材料属正常，材料旧可以用人工确认代替重跑；
# 但「没有产物」「搜索次数不够」「结构不合格」说的是产出内容本身，与时间无关，
# 一并豁免就会让结构错误、缺材料的周报带上 full（2026-11-12 评审复现：
# quality=full、gate=fail、codes=[GATE_INCOMPLETE, GATE_SEARCH_MIN, GATE_STRUCTURE]）。
OVERRIDABLE_CODES = frozenset({"GATE_STALE"})


def mark_gate_unverified(state: dict) -> None:
    """把本次产出的门槛记录降为「未验证」：检的不是最终提交的那份周报时用（周报被人工改过）。"""
    prod = state.setdefault("produced", {})
    gates = prod.setdefault("gates", {})
    gates["check_run"] = "skipped"
    codes = list(gates.get("codes") or [])
    if "GATE_UNVERIFIED" not in codes:
        codes.append("GATE_UNVERIFIED")
    gates["codes"] = codes
    prod["quality"] = "check_failed"


def report_is_manual(ctx: Ctx, tip: str) -> bool:
    """远端最新的周报提交不是本脚本写的（人工改过），本次发布不会覆盖它。"""
    subject = last_subject(ctx, tip, ctx.report_path)
    return bool(subject and not subject.startswith("AI 周报 "))


def publish_message(ctx: Ctx, state: dict, quality: str) -> str:
    entry = _run_entry(state, ctx.run_id) or {}
    tags = {"rerun": "重跑", "takeover": "接管", "backfill": "回溯"}.get(entry.get("mode"), "")
    tags = [x for x in (tags, {"degraded": "降级", "check_failed": "检查未通过"}.get(quality, "")) if x]
    return f"AI 周报 {ctx.week}" + (f"（{'，'.join(tags)}）" if tags else "")


def cmd_publish(args) -> int:
    ctx = load_ctx()
    t = now()

    if args.allow_quality_override:
        if not args.quality:
            emit("error", "--allow-quality-override 要同时给 --quality，说明按哪个质量发布")
            return EXIT_ERROR
        if not override_allowed(ctx):
            tracelog.log("提交", "拒绝覆盖", "error", "GATE_OVERRIDE_DENIED",
                         f"mode={ctx.mode} test={ctx.test} remote={ctx.remote} 时不能用 --allow-quality-override",
                         work_dir=ctx.work)
            emit("error", "GATE_OVERRIDE_DENIED：只有回溯（week.json 的 mode=backfill）可以覆盖门槛结果；"
                          "正式运行与测试运行都按门槛结果发布，或按第 4 步返工")
            return EXIT_ERROR
    # 周报被人工改过时本次不会提交 OUT_DIR 里的周报（见 extra），门槛检的就不是最终内容，按未验证处理
    manual = report_is_manual(ctx, remote_tip(ctx))
    if manual:
        gates_ok, gate_codes, gate_status = False, ["GATE_UNVERIFIED"], "skipped"
        tracelog.log("提交", "周报被人工修改", "warn", "MANUAL_EDIT",
                     "不覆盖远端周报，门槛结果不适用于本次提交内容，按未验证处理", work_dir=ctx.work)
    else:
        gates_ok, gate_codes = publish_gate(ctx)
        gate_status = "pass" if gates_ok else "fail"
    gates = {"check_run": gate_status, "codes": gate_codes}
    # 人工改过周报时提交的不是本次候选，按未验证处理；质量也不看候选的元数据（那份不提交）
    degraded = False if manual else report_is_degraded(ctx.out / ctx.report_path)
    if args.allow_quality_override:
        if manual:
            emit("error", "GATE_OVERRIDE_CONFLICT：周报被人工改过，本次提交的不是你的候选，不能声明产出质量")
            return EXIT_ERROR
        # 覆盖只用来跳过门槛的新鲜度判断，不能改产物本身的质量：必须和周报元数据一致
        want = "degraded" if degraded else "full"
        if args.quality != want:
            tracelog.log("提交", "拒绝覆盖", "error", "GATE_OVERRIDE_CONFLICT",
                         f"周报元数据是 {want}，声明的是 {args.quality}", work_dir=ctx.work)
            emit("error", f"GATE_OVERRIDE_CONFLICT：周报元数据是 {want}，不能覆盖成 {args.quality}；"
                          f"覆盖只用于跳过门槛的新鲜度检查")
            return EXIT_ERROR
        quality, mismatch = args.quality, None
        # 覆盖只能豁免「材料是旧的」；其余失败说明产出本身不合格，不能借覆盖变成 full
        blocked = [c for c in gate_codes if c not in OVERRIDABLE_CODES]
        if blocked:
            tracelog.log("提交", "拒绝覆盖", "error", "GATE_OVERRIDE_DENIED",
                         f"失败码不在可豁免范围：{','.join(blocked)}", work_dir=ctx.work)
            emit("error", "GATE_OVERRIDE_DENIED：覆盖只能豁免 GATE_STALE（材料早于本次运行）；"
                          f"本次还有 {'、'.join(blocked)}，需先按门槛返工，不能标为 {args.quality}")
            return EXIT_ERROR
        gates["override"] = quality
        if gate_codes:
            gates["waived"] = sorted(set(gate_codes))
    else:
        quality, mismatch = derive_quality(gates_ok, degraded, args.quality)
    if mismatch:
        tracelog.log("提交", "拒绝发布", "error", "GATE_MISMATCH",
                     f"门槛结果是 {quality}，与 --quality {args.quality} 不一致", work_dir=ctx.work)
        emit("error", f"GATE_MISMATCH：门槛结果是 {quality}，与 --quality {args.quality} 不一致；"
                      f"去掉 --quality 由脚本推导，或加 --allow-quality-override 显式覆盖")
        return EXIT_ERROR
    if "override" in gates:
        tracelog.log("提交", "质量覆盖", "warn", "GATE_OVERRIDE",
                     f"按 --quality {quality} 发布，门槛结果是 {'pass' if gates_ok else 'fail'}",
                     work_dir=ctx.work)
    if not gates_ok:
        tracelog.log("提交", "门槛未通过", "warn", ",".join(gate_codes) or "GATE_INCOMPLETE",
                     f"按 {quality} 发布", work_dir=ctx.work)

    files, rejected = collect_outputs(ctx)
    for rel in rejected:
        tracelog.log("提交", "白名单外的文件", "warn", detail=f"{rel} 不在写入白名单内，未提交", work_dir=ctx.work)
    if ctx.report_path not in files:
        emit("error", f"OUT_DIR 下没有周报：{ctx.out / ctx.report_path}")
        return EXIT_ERROR
    codes = list(dict.fromkeys(gate_codes + [c for c in (args.codes or "").split(",") if c]))
    dropped = []

    def extra(state, tip):
        out = dict(files)
        if report_is_manual(ctx, tip):
            out.pop(ctx.report_path)  # 周报被手工改过：不覆盖
            dropped.append(ctx.report_path)
            # 每次尝试都要降级：推送被拒后重试时，build 会按原来的 quality 重新生成状态
            mark_gate_unverified(state)
        return out

    def build(state, tip):
        if not holds(state, ctx.run_id, "run"):
            raise CoordError("LOCK_LOST", "运行锁已被接管或释放，放弃推送")
        events = tracelog.read_events(ctx.work)
        new = apply_publish(state, ctx, t, quality, sorted(files), codes, tracelog.summarize(events), gates)
        return new, None

    def run():
        sha, state, _ = write_state(
            ctx, build, lambda s, r: publish_message(ctx, s, (s.get("produced") or {}).get("quality") or quality),
            extra)
        if dropped:
            tracelog.log("提交", "周报被手工修改", "warn", "MANUAL_EDIT", "未覆盖周报，只提交了数据和状态",
                         work_dir=ctx.work)
        tracelog.log("提交", "已推送", "ok", detail=sha, work_dir=ctx.work, files=sorted(files))
        save_ctx(ctx, published_commit=sha)
        lines = f"commit={sha}" + ("；周报被手工修改过，未覆盖" if dropped else "")
        return "published", lines

    return run_and_report(ctx, run)


def cmd_verified(args) -> int:
    ctx = load_ctx()
    t = now()
    codes = [c for c in (args.codes or "").split(",") if c]

    def build(state, tip):
        if not holds(state, ctx.run_id, "verify"):
            raise CoordError("LOCK_LOST", "校验锁已被接管或释放")
        new, nxt = apply_verified(state, ctx, t, args.result, codes, args.detail or "",
                                  tracelog.summarize(tracelog.read_events(ctx.work)))
        return new, nxt

    def message(state, nxt):
        if nxt == "done":
            return f"AI 周报状态 {ctx.week}：校验通过（{ctx.platform}）"
        if nxt == "run":
            return f"AI 周报状态 {ctx.week}：校验不通过，转重跑（{','.join(codes) or '未注明'}）"
        return f"AI 周报状态 {ctx.week}：需人工"

    def run():
        sha, state, nxt = write_state(ctx, build, message)
        tracelog.log("校验", f"结果 {args.result}", "ok" if args.result == "pass" else "warn",
                     detail=",".join(codes), work_dir=ctx.work)
        if nxt == "run":
            save_ctx(ctx, purpose="run", run_mode="rerun", acquired_commit=sha)
            return "run", "校验不通过，已转为运行锁，开始重跑"
        if nxt == "done":
            return "done", "校验通过，本周已完成"
        return "exit", "校验不通过且尝试次数已用完，已标为需人工"

    return run_and_report(ctx, run)


def cmd_fail(args) -> int:
    ctx = load_ctx()
    t = now()

    def build(state, tip):
        purpose = saved_value(ctx, "purpose", "run")
        if not holds(state, ctx.run_id, purpose):
            raise CoordError("LOCK_LOST", "锁已不在本次运行手里，只在本地记录失败")
        tracelog.log("协调", "失败", "error", args.code, args.detail or "", work_dir=ctx.work)
        return apply_fail(state, ctx, t, args.code, args.detail or "",
                          tracelog.summarize(tracelog.read_events(ctx.work))), None

    def run():
        sha, state, _ = write_state(ctx, build, lambda s, r: f"AI 周报状态 {ctx.week}：失败（{args.code}）")
        if state["phase"] == "needs_human":
            return "exit", "已记录失败，本周尝试次数用完，标为需人工"
        return "exit", "已记录失败并释放锁"

    return run_and_report(ctx, run)


def cmd_status(args) -> int:
    work = WORK_DIR
    try:
        ctx = load_ctx(work)
    except CoordError:
        cfg = coord_config()
        week = args.week
        if not week:
            print("用法：coord.py status --week 2026-W45（或先运行 coord.py start）")
            return EXIT_ERROR
        ctx = Ctx(repo=pathlib.Path(os.environ.get("AI_WEEKLY_REPO", REPO_DIR)), work=work, remote="origin",
                  branch=cfg["branch"], week=week, mode="normal", report_path="", data_path="",
                  state_path=f"AI资讯/数据/运行记录/{week}.json", run_id="", platform="", test=False, cfg=cfg)
    try:
        state = read_state(ctx, remote_tip(ctx))
    except CoordError as e:
        print(f"{e.code}：{e.detail}")
        return EXIT_INVALID
    if state is None:
        print(f"{ctx.week}：还没有状态文件（空闲）")
        return 0
    lock = state.get("lock")
    print(f"{ctx.week}：{state['phase']}，产出尝试 {state.get('attempts', 0)} 次")
    if lock:
        print(f"  锁：{lock['purpose']}，{lock.get('platform')}，租约到 {lock['lease_until']}")
    for r in state["runs"]:
        print(f"  {r.get('started_at', '')} {r.get('platform')} {r.get('action')}/{r.get('mode', '')} → "
              f"{r.get('outcome')} {','.join(r.get('codes', []))}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--platform", required=True, help="所在平台的名称，小写英文，如产品名")
    s.add_argument("--test", action="store_true", help="测试模式：远端换成本地模拟仓库")
    s.add_argument("--remote", help=argparse.SUPPRESS)  # 测试用：指定远端
    sub.add_parser("wait")
    sub.add_parser("renew")
    p = sub.add_parser("publish")
    p.add_argument("--quality", choices=["full", "degraded", "check_failed"], default=None,
                   help="期望的产出质量；实际值由 check_run.py 的门槛结果推导，不一致时拒绝发布")
    p.add_argument("--allow-quality-override", action="store_true",
                   help="回溯或测试时按 --quality 直接发布，跳过与门槛结果的比对（记入 gates.override）")
    p.add_argument("--codes", help="本次运行遇到的错误码，逗号分隔")
    v = sub.add_parser("verified")
    v.add_argument("--result", choices=["pass", "fail"], required=True)
    v.add_argument("--codes")
    v.add_argument("--detail")
    f = sub.add_parser("fail")
    f.add_argument("--code", required=True)
    f.add_argument("--detail")
    st = sub.add_parser("status")
    st.add_argument("--week")
    args = ap.parse_args(argv)
    handler = {"start": cmd_start, "wait": cmd_wait, "renew": cmd_renew, "publish": cmd_publish,
               "verified": cmd_verified, "fail": cmd_fail, "status": cmd_status}[args.cmd]
    try:
        return handler(args)
    except CoordError as e:
        emit("error", f"错误码={e.code}", e.detail)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
