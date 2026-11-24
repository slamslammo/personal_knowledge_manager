"""从已发布 Git 正文更新年度表。可按同一期间和提交单独补交付。"""
import argparse
import fcntl
import json
import os
import re
import subprocess
import time
from urllib.parse import quote

import yaml

import feishu_sync
import paths
from common import REPO_DIR, load_config
from weeks import Week


def published_row(period, sha, text, has_board):
    year, label = period.split("-")
    if label.startswith("W"):
        week = Week.parse(period)
        month = week.thursday.month
        layer, section, report = "周", r"①[^\n]*概览[^\n]*", paths.report(year, period)
        coverage = (1, int(has_board))
        key = label
    else:
        report = paths.period_report(period)
        meta = yaml.safe_load(text.split("---", 2)[1])
        if meta["quality"] not in ("full", "degraded"):
            raise ValueError("历史专题走人工回看")
        quarter = label.startswith("Q")
        layer, section = ("季", "季度主线") if quarter else ("月", "月度主线")
        month = (int(label[1:]) - 1) * 3 + 1 if quarter else int(label)
        key = label if quarter else label + "月"
        coverage = tuple(int(meta["coverage"][k].removesuffix("周")) for k in ("正文", "榜单"))
    group = (month - 1) // 3 + 1
    part = re.search(r"(?ms)^## " + section + r"\n(.*?)(?=^## |\Z)", text)
    bullets = [] if not part else re.findall(r"(?m)^- (.+)", part[1])[:3]
    if not bullets:
        raise ValueError("已发布正文缺少概览要点")
    brief = [re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s).replace("**", "") for s in bullets]
    order = group * 100000
    if layer != "季":
        order += month * 1000 + (100 + int(label[1:]) if layer == "周" else 1)
    return {"标题": key + (" · AI 周报" if layer == "周" else f" · {layer}度汇总"),
            "期间编号": key, "层级": [layer], "归属年": [year], "归属季": [f"Q{group}"],
            "归属月": "00 · 季度汇总" if layer == "季" else f"{month:02d}月",
            "排序键": order, "正文覆盖周数": coverage[0], "榜单覆盖周数": coverage[1],
            "状态": ["有正式报告"], "证据等级": ["B(归纳)"], "备注": None,
            "关键信息": "\n".join(n + s for n, s in zip("①②③", brief)),
            "报告链接": f"https://github.com/slamslammo/personal_knowledge_manager/blob/{sha}/{quote(report)}"}


def sync(period, sha):
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("需要已发布的完整提交号")
    repo = str(REPO_DIR)
    def git(*args):
        return subprocess.check_output(["git", "-C", repo, *args], stderr=subprocess.DEVNULL)
    year, label = period.split("-")
    if label.startswith("W"):
        Week.parse(period)
        path = paths.report(year, period)
    else:
        path = paths.period_report(period)
    git("fetch", "-q", "origin", "refs/heads/main")
    tip = git("rev-parse", "FETCH_HEAD").decode().strip()
    git("merge-base", "--is-ancestor", sha, tip)
    text = git("cat-file", "blob", f"{sha}:{path}")
    if text != git("cat-file", "blob", f"{tip}:{path}"):
        raise ValueError("正文已经更新，请用最新发布提交补索引")
    board = bool(git("ls-tree", sha, "--", paths.data(period))) if label.startswith("W") else False
    fields = published_row(period, sha, text.decode(), board)
    cfg = feishu_sync.cfg_load() or {}
    if not cfg.get("enabled", True):
        raise ValueError("飞书交付已关闭")
    target = cfg.get("annual_tables", {}).get(year)
    cli = feishu_sync.find_cli(cfg)
    if not target or not cli:
        raise ValueError("年度表配置或 lark-cli 缺失")
    def call(cmd, *args):
        r = feishu_sync.run_cli(cli, "base", cmd, "--as", "user", "--base-token", target["base"],
                                "--table-id", target["table"], *args)
        if not r.get("ok") or "data" not in r:
            raise ValueError(f"{cmd} 未确认，核对权限或收据后重试")
        return r["data"]
    def lookup():
        d = call("+record-list", "--format", "json", "--limit", "200")
        if d.get("has_more"):
            raise ValueError("年度表超过 200 行，需核对表或分页")
        matches = []
        for rid, values in zip(d["record_id_list"], d["data"], strict=True):
            row = dict(zip(d["fields"], values))
            if (row["归属年"] == [year] and row["层级"] == fields["层级"]
                    and str(row["期间编号"]).rstrip("月") == label):
                matches.append((rid, row))
        if len(matches) > 1:
            raise ValueError("期间行重复，先核对记录")
        return matches[0] if matches else (None, {})
    def same(row):
        for key, value in fields.items():
            actual = row.get(key)
            if key == "报告链接" and actual and actual.endswith("](" + value + ")"):
                continue
            if actual != value:
                return False
        return True
    state = paths.state_dir(REPO_DIR) / "annual-index" / year
    state.mkdir(parents=True, exist_ok=True)
    marker = state / (period + ".pending")
    with (state / (period + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rid, row = lookup()
        if not same(row):
            if not rid:
                if marker.exists():
                    raise ValueError("上次创建未确认，先从表内核对，不重复创建")
                marker.touch(exist_ok=False)
            call("+record-upsert", *(["--record-id", rid] if rid else []),
                 "--json", json.dumps(fields, ensure_ascii=False))
            for delay in (0, 1, 3, 5):
                if delay:
                    time.sleep(delay)
                if same(lookup()[1]):
                    break
            else:
                raise ValueError("年度表读回尚未一致，可按同一提交补验")
        marker.unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--period", required=True)
    p.add_argument("--sha", required=True)
    p.add_argument("--test", action="store_true")
    args = p.parse_args()
    if args.test or os.environ.get("TEST_RUN") == "1" or load_config("deployment")["mode"] != "production":
        print("INDEX=skipped test=1")
        return 0
    try:
        sync(args.period, args.sha)
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print(f"INDEX=pending {exc}")
        return 1
    print("INDEX=updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
