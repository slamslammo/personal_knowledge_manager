"""运行时目录的唯一入口：查询、校验、清理、归档。

运行会话通过本脚本查询、清理与归档工作目录。

用法：
  python3 workdir.py print                 # 输出本次工作目录（供手册的 $W）
  python3 workdir.py root                  # 输出运行时根
  python3 workdir.py check                 # 校验路径合法，非法退出非零
  python3 workdir.py clean                 # 保留清单式清理（不清跨运行状态）
  python3 workdir.py archive --week WEEK  # 归档关键证据并写/合并 MANIFEST.json

约束：路径不合法时显式失败，不静默回退 /tmp；清理前先归档，且绝不整目录删除。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths  # noqa: E402
from common import REPO_DIR, WORK_DIR, read_json, write_json  # noqa: E402


def _now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _load(path: pathlib.Path) -> dict:
    """读可选的 JSON 留痕；文件不存在时返回空字典，不让归档因缺项失败。"""
    if not path.exists():
        return {}
    data = read_json(path)
    return data if isinstance(data, dict) else {}


def cmd_print(args) -> int:
    print(str(WORK_DIR))
    return 0


def cmd_root(args) -> int:
    print(str(paths.runtime_root(REPO_DIR)))
    return 0


def cmd_check(args) -> int:
    try:
        paths.validate_work_dir(WORK_DIR, REPO_DIR)
    except (ValueError, OSError) as exc:
        print(f"WORKDIR_INVALID: {exc}", file=sys.stderr)
        return 1
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    print(f"WORKDIR=ok {WORK_DIR}")
    return 0


def cmd_clean(args) -> int:
    """保留清单式清理：先归档本次证据，再删除可再生的 scratch。

    与旧的 rm -rf 不同，CLEAN_PRESERVE 中的跨运行状态必须留下，
    否则飞书防重状态与交付收据会丢失。
    """
    paths.validate_work_dir(WORK_DIR, REPO_DIR)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    week_json = WORK_DIR / paths.FILES["week"]
    week = None
    if week_json.exists():
        week = _load(week_json).get("week")
    if week and not args.no_archive:
        cmd_archive(argparse.Namespace(week=week, no_manifest=False))

    removed = []
    for entry in sorted(WORK_DIR.iterdir(), key=lambda p: p.name):
        if entry.name in paths.CLEAN_PRESERVE:
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
        removed.append(entry.name)
    kept = sorted(p.name for p in WORK_DIR.iterdir())
    print(f"CLEAN=ok removed={len(removed)} kept={','.join(kept) or '(none)'}")
    return 0


def _manifest_path(week: str) -> pathlib.Path:
    return paths.archive_dir(week, REPO_DIR) / paths.FILES["manifest"]


def _run_entry(week: str) -> dict:
    """从本次运行的留痕里提取可比对的元数据；缺失字段写 None，不猜。"""
    coord = _load(WORK_DIR / paths.FILES["coord"])
    deployment = _load(WORK_DIR / paths.FILES["deployment"])
    week_meta = _load(WORK_DIR / paths.FILES["week"])
    receipt = _load(WORK_DIR / paths.FILES["feishu_notify_receipt"])
    feishu = _load(WORK_DIR / paths.FILES["feishu"])
    return {
        "week": week,
        "recorded_at": _now(),
        "run_id": coord.get("run_id"),
        "mode": coord.get("mode") or week_meta.get("mode"),
        "test": coord.get("test"),
        "platform": coord.get("platform"),
        "deployment_mode": deployment.get("mode"),
        "git_sha": coord.get("published_commit"),
        "feishu_action": feishu.get("action"),
        "feishu_document_id": feishu.get("document_id"),
        "notify_message_id": receipt.get("message_id"),
        # token 消耗的可比对来源：会话记录。留空由后续对比时补，不让脚本杜撰。
        "session_id": None,
        "model": None,
    }


def cmd_archive(args) -> int:
    """按周归档不可再生的关键证据；一周一份，多次运行合并进 runs[]。"""
    week = args.week
    target = paths.archive_dir(week, REPO_DIR)
    target.mkdir(parents=True, exist_ok=True)

    copied = []
    for name in paths.ARCHIVE_EVIDENCE:
        src = WORK_DIR / name
        if not src.exists():
            continue
        dest = target / name
        shutil.copy2(src, dest)
        copied.append(name)

    # 最终输出（周报）单独存一份，便于逐字对比；文件名与仓库内一致。
    report_name = paths.archive_report_path(week, week[:4])
    rel = None
    week_meta = _load(WORK_DIR / paths.FILES["week"])
    rel = week_meta.get("report_path")
    if rel:
        src = WORK_DIR / "out" / rel
        if src.exists():
            shutil.copy2(src, target / report_name)
            copied.append(report_name)

    manifest_path = _manifest_path(week)
    manifest = _load(manifest_path)
    manifest.setdefault("schema", 1)
    manifest["week"] = week
    manifest["archive_dir"] = str(target)
    manifest.setdefault("created_at", _now())
    manifest["updated_at"] = _now()
    manifest["files"] = sorted(set(copied))
    runs = manifest.setdefault("runs", [])
    entry = _run_entry(week)
    # 幂等：同一 run_id 不重复追加。
    if entry["run_id"] and any(r.get("run_id") == entry["run_id"] for r in runs):
        for i, r in enumerate(runs):
            if r.get("run_id") == entry["run_id"]:
                runs[i] = entry
                break
    else:
        runs.append(entry)
    write_json(manifest_path, manifest)
    print(f"ARCHIVE=ok {target} files={len(copied)} runs={len(runs)}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="运行时目录查询与生命周期管理")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("print", help="输出本次工作目录")
    sub.add_parser("root", help="输出运行时根")
    sub.add_parser("check", help="校验路径合法")
    p_clean = sub.add_parser("clean", help="保留清单式清理")
    p_clean.add_argument("--no-archive", action="store_true", help="跳过归档（仅测试用）")
    p_arch = sub.add_parser("archive", help="按周归档关键证据")
    p_arch.add_argument("--week", required=True, help="ISO 周，如 2026-W41")
    args = ap.parse_args(argv)
    return {
        "print": cmd_print,
        "root": cmd_root,
        "check": cmd_check,
        "clean": cmd_clean,
        "archive": cmd_archive,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
