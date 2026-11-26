"""月季报准备与发布。写作在两次调用之间进行，期间、输入版本和榜单由脚本确定。"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import pathlib
import re
import subprocess
import sys
from types import SimpleNamespace

import yaml

from annual_index import published_row, record_receipt_path

import coord
import paths
from common import REPO_DIR, load_config, read_json, write_json
from period_aggregate import aggregate, markdown, weeks_for
from weeks import BJT, Week


def source_files(period, weeks):
    if "-Q" in period:
        first = int(period[-1]) * 3 - 2
        return [paths.period_report(f"{period[:4]}-{i:02d}") for i in range(first, first + 3)]
    return [paths.report(w[:4], w) for w in weeks]


def prepare(ctx, period, sha):
    weeks = weeks_for(period)
    reports = source_files(period, weeks)
    board_dir = ctx.work / "boards"
    # 某些宿主对 pathlib.mkdir 的 shim 即使带 exist_ok=True 也会抛 EEXIST，
    # 先显式判断目录已存在再跳过，避免把本地环境差异当成发布失败。
    if not board_dir.is_dir():
        board_dir.mkdir(exist_ok=True)
    material = []
    blobs = {}
    notes = []
    count = 0
    degraded = False
    states = [] if "-Q" in period else [paths.state(w) for w in weeks]
    for path in reports + [paths.data(w) for w in weeks] + states:
        raw = coord.read_at(ctx, sha, path)
        blobs[path] = coord.out_text(coord.git(ctx, "rev-parse", f"{sha}:{path}")) if raw is not None else None
        if path in reports:
            if raw is None:
                raise ValueError(f"缺少已发布报告 {path}")
            body = raw.decode()
            meta = yaml.safe_load(body.split("---", 2)[1])
            key = "month" if "-Q" in period else "week"
            if not isinstance(meta, dict) or meta.get(key) != pathlib.Path(path).stem:
                raise ValueError(f"输入元数据与文件期间不符：{path}")
            if "-Q" in period:
                if meta.get("quality") not in ("full", "degraded"):
                    raise ValueError(f"需要正式月报 {path}")
                match = re.fullmatch(r"(\d+)周", str(meta["coverage"]["正文"]))
                if not match or int(match[1]) > len(weeks_for(meta["month"])):
                    raise ValueError(f"正文覆盖周数无效：{path}")
                count += int(match[1])
            else:
                count += 1
            if meta.get("quality", "full") != "full":
                degraded = True
                notes.append(f"{pathlib.Path(path).stem} 输入质量为 {meta.get('quality')}")
            material.append(f"来源 {path}\n\n{body}")
        elif path in states:
            produced = (json.loads(raw).get("produced") or {}) if raw else {}
            if not produced:
                notes.append(f"{pathlib.Path(path).stem} 缺少发布质量记录")
            elif produced.get("quality") != "full":
                degraded = True
                notes.append(f"{pathlib.Path(path).stem} 发布质量为 {produced.get('quality')}")
        else:
            local = board_dir / pathlib.Path(path).name
            if raw is None:
                local.unlink(missing_ok=True)
            else:
                local.write_bytes(raw)
    ranking = aggregate(period, weeks, board_dir)
    top = load_config("ranking")["monthly"]["github_top_n"]
    board = markdown(ranking, top) if ranking["ranked"] else "本期缺少可汇总的新增 star 数值。\n"
    (ctx.work / "materials.md").write_text("\n\n".join(material))
    (ctx.work / "board.md").write_text(board)
    manifest = dict(period=period, source=sha, inputs=blobs, reports=reports, weeks=weeks,
                    body_weeks=count, notes=notes, degraded=degraded, board_weeks=ranking["coverage"]["weeks_with_board"])
    write_json(ctx.work / "inputs.json", manifest)
    return manifest


def render(ctx, manifest):
    period = manifest["period"]
    quarter = "-Q" in period
    name = "季报" if quarter else "月报"
    sections = (["季度主线", "重点发布与技术方向", "开源与产业趋势", "回看上季判断", "下一季度观察点"]
                if quarter else ["月度主线", "关键时间线", "话题演变", "精选必读"])
    body = (ctx.work / "body.md").read_text().strip()
    source_line = f"<!-- source: {manifest['source']} -->"
    first, _, body = body.partition("\n")
    if first != source_line:
        raise ValueError("草稿来源版本不符，请按当前输入核稿")
    body = body.strip()
    if not body.startswith("## ") or "{{" in body:
        raise ValueError("正文应从主线开始，不能保留模板占位符")
    chapters = re.split(r"(?m)^## (.+)\n", body + "\n")
    if chapters[1::2] != sections or any(not t.strip() for t in chapters[2::2]):
        raise ValueError("正文必需章节为 " + "、".join(sections))
    if len(re.findall(r"(?m)^- .{6,}", chapters[2])) < 2 or "https://" not in body:
        raise ValueError("主线至少写两条有证据的要点，正文附原文链接")
    if not quarter:
        reads = re.findall(r"(?m)^\d+\. .+https?://", chapters[-1])
        if len(reads) != load_config("ranking")["monthly"]["must_read"]:
            raise ValueError("精选必读的数量或原文链接不完整")
    if body.count("<!-- period-board -->") != 1:
        raise ValueError("在榜单位置放一处 <!-- period-board -->")
    coverage = {"正文": f"{manifest['body_weeks']}周", "榜单": f"{manifest['board_weeks']}周"}
    meta = {"quarter" if quarter else "month": period, "weeks": manifest["weeks"], "coverage": coverage,
            "quality": "full" if not manifest["degraded"] and manifest["board_weeks"] == len(manifest["weeks"]) else "degraded",
            "source": manifest["source"]}
    if quarter:
        meta["months"] = [pathlib.Path(p).stem for p in manifest["reports"]]
        coverage["月报"] = "3/3"
    links = [f"- [{pathlib.Path(p).stem}](https://github.com/slamslammo/personal_knowledge_manager/blob/{manifest['source']}/{p})" for p in manifest["reports"]]
    board = (ctx.work / "board.md").read_text().strip()
    body = body.replace("<!-- period-board -->", board)
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
    result = f"---\n{head}---\n\n# AI {name} · {period}\n\n{body}\n\n## 数据说明\n\n" + "\n".join(links)
    notes = manifest["notes"]
    if notes:
        result += "\n\n" + "；".join(notes) + "。"
    return (result + "\n").encode()


def publish(ctx, period, tip):
    m = read_json(ctx.work / "inputs.json")
    if m["period"] != period or not re.fullmatch(r"[a-f0-9]{40}", m["source"]):
        raise ValueError("准备记录与期间不符")
    # 重新从固定提交取得输入和榜单。草稿之外的本地文件不作为发布依据。
    source = m["source"]
    if coord.git(ctx, "merge-base", "--is-ancestor", source, tip, check=False).returncode:
        raise ValueError("准备提交不属于目标分支")
    m = prepare(ctx, period, source)
    for path, blob in m["inputs"].items():
        current = coord.git(ctx, "rev-parse", "--verify", f"{tip}:{path}", check=False)
        if (coord.out_text(current) if current.returncode == 0 else None) != blob:
            raise ValueError(f"输入已变化，请重新准备并核稿：{path}")
    report = paths.period_report(period)
    content = render(ctx, m)
    existing = coord.read_at(ctx, tip, report)
    if existing == content:
        return coord.out_text(coord.git(ctx, "log", "-1", "--format=%H", tip, "--", report))
    if existing is not None:
        raise ValueError("该期已有不同发布稿，保留现稿，修订请走 PR")
    sha = coord.make_commit(ctx, tip, {report: content}, f"AI 资讯发布 {period}")
    if coord.push(ctx, sha) != "ok":
        raise ValueError("推送结果未确认；重试前核对目标分支")
    if coord.read_at(ctx, coord.remote_tip(ctx), report) != content:
        raise ValueError("发布后 Git 正文字节核对失败")
    return sha


# 年度表「关键信息」用 ①②③ 逐行列出核心事实，通知里换成 1）2）3）。
NOTICE_NUMBERS = {"①": "1）", "②": "2）", "③": "3）", "④": "4）", "⑤": "5）"}


def notification_text(period, sha, fields, record_url=None, test=False):
    """生成月/季报的飞书 Markdown 通知，与周报同款呈现。

    全文唯一真值源仍是 Git：年度表当期行保留 GitHub 正文链接供检索，通知里
    不再暴露它，也不重复贴原文链接；改放年度表当期记录的直达链接（年报：），
    链接来自 annual_index.py 的运行时收据，取不到就不写这一行、不伪造。
    """
    layer = fields["层级"][0]
    section = "季度主线" if layer == "季" else "月度主线"
    target = "本地沙箱" if test else "main"
    lines = [f"【AI {layer}报 {period}】", "", f"**{section}**"]
    for line in fields["关键信息"].splitlines():
        line = line.strip()
        if not line:
            continue
        marker, body = line[0], line[1:].strip()
        num = NOTICE_NUMBERS.get(marker)
        lines.append(f"{num}**{body}**" if num else f"- **{body}**")
    lines += ["", f"提交：已推送到{target}（{sha[:7]}）"]
    if record_url:
        lines.append(f"年报：{record_url}")
    return "\n".join(lines) + "\n"


def deliver(ctx, period, sha):
    content = coord.read_at(ctx, sha, paths.period_report(period)).decode()
    fields = published_row(period, sha, content, False)
    (ctx.work / "published.md").write_bytes(content.encode())
    note = ctx.work / "notification.txt"
    if ctx.test:
        note.write_text(notification_text(period, sha, fields, test=True))
        print("INDEX=skipped NOTIFY=skipped")
        return True
    env = dict(os.environ, AI_WEEKLY_TMP=str(ctx.work))
    core = pathlib.Path(__file__).parent
    # 先更新年度表，才有当期记录的直达链接；通知在索引之后生成，才能带上链接。
    index = subprocess.run([sys.executable, str(core / "annual_index.py"), "--period", period,
                            "--sha", sha], env=env)
    record_url = None
    receipt_path = record_receipt_path()
    if receipt_path.is_file():
        data = read_json(receipt_path) or {}
        if data.get("period") == period and data.get("sha") == sha:
            url = data.get("url")
            if isinstance(url, str) and url.startswith("https://"):
                record_url = url
    receipt = ctx.work / "notification-delivered.json"
    if receipt.exists() and read_json(receipt).get("sha") == sha:
        # 通知已确认发出：只补索引，不重写通知文件、不重发。
        return index.returncode == 0
    note.write_text(notification_text(period, sha, fields, record_url))
    pending = ctx.work / "notification-pending.json"
    if pending.exists():
        print("NOTIFY=unknown 请先核对上次收件")
        return False
    write_json(pending, {"sha": sha})
    notice = subprocess.run([sys.executable, str(core / "feishu_sync.py"), "notify",
                             "--file", str(note)], env=env, capture_output=True, text=True)
    print(notice.stdout.strip())
    if notice.returncode == 0 and "NOTIFY=sent" in notice.stdout:
        write_json(receipt, {"sha": sha})
        pending.unlink()
        return index.returncode == 0
    if ("NOTIFY=skipped" in notice.stdout or "NOTIFY=failed" in notice.stdout
            or "CODE=FEISHU_CONFIG_MISSING" in notice.stdout):
        # 发送前的确定性失败（缺 CLI / 接收人）永远不会被重试修好，除非配置先补好；
        # 清除 pending 让补好配置后的下一次发布可以重试。真正的未知结果仍保留 pending。
        pending.unlink()
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "publish"])
    parser.add_argument("--period", required=True)
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    try:
        weeks = weeks_for(args.period)
        if dt.datetime.now(BJT).date() <= Week.parse(weeks[-1]).end:
            raise ValueError("最后一个归属周尚未结束")
        kind = "quarterly" if "-Q" in args.period else "monthly"
        test = args.test or os.getenv("TEST_RUN") == "1" or load_config("deployment")["mode"] != "production"
        work = paths.period_work_dir(kind, args.period, REPO_DIR) / ("sandbox" if test else "production")
        paths.validate_work_dir(work, REPO_DIR)
        work.mkdir(parents=True, exist_ok=True)
        with (work / "period.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            remote = coord.setup_sandbox(REPO_DIR, work, "main") if test else "origin"
            ctx = SimpleNamespace(repo=REPO_DIR, work=work, remote=remote, branch="main", test=test)
            tip = coord.remote_tip(ctx)
            if args.action == "prepare":
                source = tip
                existing = coord.read_at(ctx, tip, paths.period_report(args.period))
                if existing is not None:
                    meta = yaml.safe_load(existing.decode().split("---", 2)[1])
                    source = meta.get("source", "")
                    if not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}", source):
                        raise ValueError("已有报告须走修订流程，不能覆盖")
                prepare(ctx, args.period, source)
                draft = work / "body.md"
                if not draft.exists():
                    draft.write_text(f"<!-- source: {source} -->\n")
                print(f"PREPARE=ok period={args.period} source={source} work={work}")
            else:
                sha = publish(ctx, args.period, tip)
                print(f"PUBLISHED=ok period={args.period} sha={sha} test={int(test)} work={work}")
                if not deliver(ctx, args.period, sha):
                    print("DELIVER=partial Git 已发布")
                    return 1
        return 0
    except (OSError, ValueError, KeyError, IndexError, coord.CoordError, subprocess.SubprocessError) as exc:
        print(f"PERIOD=failed {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
