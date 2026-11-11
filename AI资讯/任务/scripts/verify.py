"""独立校验：在远端最新版本上检查另一次运行的产出，由脚本判断，不靠模型。规则见 ../方案.md 7.9 节。

取得校验锁（coord.py start 输出 ACTION=verify）后运行。检查：
1. 产出质量：降级版或"检查未通过"的产出直接判不通过，由本次运行重跑；
2. 重跑全部校验与门槛（validate.py），HN 数字对照新采集的数据，允许随时间自然变化（--tolerance）；
3. 数据说明有自动生成的部分（finalize.py 运行过）；
4. ②④ 的链接能否打开：404/410 算错误，超时和 403 只记警告（可能是校验方自己的网络问题）。

--record 时把结果写回状态文件（调用 coord.py verified）：通过则本周完成；不通过则锁转为运行，
输出 ACTION=run，接着按执行手册重跑。

用法：
    python3 verify.py --record
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor

import collect_hn
import coord
import tracelog
from common import fetch, load_config, write_json
from finalize import AUTO_BEGIN
from validate import ARTICLES, LINK_RE, RELEASES, run_checks, section_bodies, split_front_matter
from weeks import Week


def links_to_check(text: str) -> list[str]:
    sec = section_bodies(split_front_matter(text)[1])
    links = LINK_RE.findall(sec.get(RELEASES, "") + sec.get(ARTICLES, ""))
    return list(dict.fromkeys(u.strip() for u in links if "news.ycombinator.com" not in u))


def check_link(url: str) -> tuple[str, str]:
    """返回 (dead/ok/unknown, 说明)。"""
    res = fetch(url, timeout=20, retries=1, max_redirects=3, max_bytes=4096)
    if res.status in (404, 410):
        return "dead", f"HTTP {res.status}"
    if res.ok or 300 <= res.status < 400:
        return "ok", ""
    return "unknown", res.error or f"HTTP {res.status}"


def override_conflict(produced: dict, report_file) -> bool:
    """声明 full、但周报元数据是降级版：run_checks 只会走宽松规则，full 名不副实。

    publish 侧已经拒绝这种组合，这里防的是旧状态文件与手工写入。
    """
    return produced.get("quality") == "full" and coord.report_is_degraded(report_file)


def verify(ctx: coord.Ctx, tolerance: float) -> tuple[bool, list[str], list[str]]:
    """返回 (是否通过, 错误码, 说明)。"""
    week = Week.parse(ctx.week)
    vdir = ctx.work / "verify"
    vdir.mkdir(parents=True, exist_ok=True)
    tip = coord.remote_tip(ctx)
    state = coord.read_state(ctx, tip) or {}
    codes, notes = [], []

    produced = state.get("produced") or {}
    if produced.get("quality") in ("degraded", "check_failed"):
        code = "WRITE_FAILED" if produced["quality"] == "degraded" else "GATE_STRUCTURE"
        codes.append(code)
        notes.append(f"产出为 {produced['quality']}，需要重跑")
    if "gates" not in produced:
        codes.append("GATE_UNVERIFIED")
        notes.append("状态文件缺少 gates 记录（发布前没有跑门槛），按检查未通过处理")
    elif produced["gates"].get("override"):
        notes.append(f"产出发布时显式覆盖了门槛结果（{produced['gates']['override']}），按覆盖后的质量校验")

    report_raw = coord.read_at(ctx, tip, ctx.report_path)
    data_raw = coord.read_at(ctx, tip, ctx.data_path)
    if report_raw is None:
        return False, ["GATE_INCOMPLETE"], [f"远端没有周报 {ctx.report_path}"]
    report_file, data_file = vdir / "report.md", vdir / "data.json"
    report_file.write_bytes(report_raw)
    if data_raw is not None:
        data_file.write_bytes(data_raw)
    text = report_raw.decode("utf-8")
    # 覆盖成 full、但周报自己写着降级：run_checks 会按元数据走宽松校验，full 名不副实，需要重跑
    if override_conflict(produced, report_file):
        codes.append("GATE_OVERRIDE_CONFLICT")
        notes.append("发布时声明 full，但周报元数据是降级版（只过了降级版的宽松校验）")

    hn = collect_hn.collect(week, load_config("ranking")["hn_query"]["min_points"])
    write_json(vdir / "hn.json", hn)
    materials = {"hn": hn} if hn.get("status") == "ok" else None
    if materials is None:
        notes.append("HN 重新采集失败，跳过数字核对")
    backfill = (produced.get("mode") or ctx.mode) == "backfill"  # 标题按产出时的模式校验
    rep = run_checks(week, backfill, report_file, data_file if data_raw is not None else None,
                     materials=materials, tolerance=tolerance)
    if rep.errors:
        codes += [c for c in rep.codes if c not in codes] or ["GATE_STRUCTURE"]
        notes += rep.errors
    if AUTO_BEGIN not in text:
        codes.append("GATE_INCOMPLETE")
        notes.append("数据说明没有自动生成的部分")

    links = links_to_check(text)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(check_link, links))
    for url, (status, why) in zip(links, results):
        if status == "dead":
            if "GATE_LINK_DEAD" not in codes:
                codes.append("GATE_LINK_DEAD")
            notes.append(f"链接打不开（{why}）：{url}")
        elif status == "unknown":
            tracelog.log("校验", "链接", "warn", detail=f"{url}：{why}（不计为错误）", work_dir=ctx.work)
    tracelog.log("校验", "完成", "ok" if not codes else "warn", codes[0] if codes else None,
                 f"检查链接 {len(links)} 个；" + "；".join(notes[:5]), work_dir=ctx.work)
    return not codes, codes, notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tolerance", type=float, default=0.15, help="HN 数字允许的变化比例")
    ap.add_argument("--record", action="store_true", help="把结果写回状态文件")
    args = ap.parse_args(argv)
    ctx = coord.load_ctx()
    if coord.saved_value(ctx, "purpose") != "verify":
        print("ACTION=error\n本次运行没有持有校验锁：先运行 coord.py start")
        return 1
    try:
        ok, codes, notes = verify(ctx, args.tolerance)
    except coord.CoordError as e:
        print(f"ACTION=error\n错误码={e.code}\n{e.detail}")
        return 1
    print(f"VERIFY={'pass' if ok else 'fail'}")
    for n in notes:
        print(f"- {n}")
    if codes:
        print("CODES=" + ",".join(codes))
    if not args.record:
        return 0 if ok else 1
    record = ["verified", "--result", "pass" if ok else "fail"]
    if codes:
        record += ["--codes", ",".join(codes), "--detail", "；".join(notes)[:500]]
    return coord.main(record)


if __name__ == "__main__":
    sys.exit(main())
