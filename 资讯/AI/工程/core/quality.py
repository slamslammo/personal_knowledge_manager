"""发布质量判定：门槛检查、降级识别、quality 推导与未验证标记。

2026-11-20 从 coord.py 拆出：coord 只负责协调锁、状态机与白名单造树发布，
本模块回答「这篇稿子合格吗」。本模块不 import coord，避免循环依赖；
ctx 是 duck-typed 对象（需要 cfg / work / mode 属性），保持迁移前的函数签名。
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

GATE_TIMEOUT_SECONDS = 120
GATE_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "weekly" / "check_run.py"  # 固定，不提供替换入口


def report_is_degraded(path: pathlib.Path) -> bool:
    """周报元数据里的 quality 是否为 degraded（降级版）。

    与 validate.py 用同一套解析（split_front_matter + yaml.safe_load），不能各用各的：
    `quality: "degraded"` 或行尾带注释的写法，validate 认、正则不认，就会出现
    「按降级版的宽松规则校验通过，却被标成 full 发布」。
    """
    import validate  # 延迟导入：只在发布时读周报元数据

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


def publish_gate(ctx) -> tuple[bool, list[str]]:
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


def override_allowed(ctx) -> bool:
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
