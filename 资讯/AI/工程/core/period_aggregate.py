"""期间榜单聚合：从周榜 JSON 明细按 week_stars 跨周累加，不复用已裁剪的周榜 Top N。

规则（与 2026-11-24 展示规范一致）：
- 每个仓库按 full_name 跨周去重，累加有数值的 week_stars；
- 记录贡献周数与 days_covered；空值、未入榜、缺周榜均不当零；
- 没有 star 数值的仓库不进入 star 榜，可在回顾清单单列名次/上榜次数；
- 只输出 JSON 与 Markdown 片段到工作目录，不写仓库、不发布。

用法：
  python3 period_aggregate.py --period 2026-10 --top 10 --out <work>/aggregate.json
"""

from __future__ import annotations

import argparse
import re

import paths
import weeks as calendar
import json
import pathlib
import sys

WEEKLY_DIR = paths.repo_root(pathlib.Path(__file__).resolve().parent) / paths.DATA_REL / "github-weekly"


def weeks_for(period: str) -> list[str]:
    if re.fullmatch(r"[0-9]{4}-Q[1-4]", period):
        span = calendar.weeks_in_quarter(int(period[:4]), int(period[-1]))
    elif re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", period):
        span = calendar.weeks_in_month(int(period[:4]), int(period[-2:]))
    else:
        raise ValueError(f"非法期间：{period}")
    return [w.label for w in span]


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def aggregate(period: str, weeks: list[str] | None = None,
              weekly_dir: pathlib.Path = WEEKLY_DIR) -> dict:
    weeks = weeks if weeks is not None else weeks_for(period)
    rows: dict[str, dict] = {}
    missing: list[str] = []
    for label in weeks:
        p = weekly_dir / f"{label}.json"
        if not p.is_file():
            missing.append(label)
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("week") != label or not isinstance(data.get("repos"), list):
            raise ValueError(f"榜单期间或格式错误：{label}")
        seen = set()
        for r in data["repos"]:
            if r.get("status") not in {"candidate", "new", "top5"}:
                continue
            name = r.get("full_name")
            if not isinstance(name, str) or not name:
                continue
            key = name.casefold()
            if key in seen:
                raise ValueError(f"{label} 榜单仓库重复：{name}")
            seen.add(key)
            item = rows.setdefault(key, {
                "full_name": name, "total": 0, "contributing_weeks": [],
                "days_covered": 0, "no_star_weeks": [], "best_position": None,
                "appearances": 0,
            })
            item["appearances"] += 1
            pos = r.get("trendshift_position")
            if _num(pos):
                item["best_position"] = min(
                    item["best_position"] if item["best_position"] is not None else pos, pos)
            stars = r.get("week_stars")
            days = r.get("days_covered")
            if _num(stars):
                item["total"] += stars
                item["contributing_weeks"].append(label)
                if _num(days):
                    item["days_covered"] += days
            else:
                item["no_star_weeks"].append(label)
    ranked = sorted(
        (x for x in rows.values() if x["contributing_weeks"]),
        key=lambda x: (-x["total"], x["full_name"]),
    )
    no_star = [x for x in rows.values() if not x["contributing_weeks"]]
    no_star.sort(key=lambda x: (x["best_position"] is None, x["best_position"] or 0, -x["appearances"]))
    return {
        "period": period, "weeks": weeks, "missing_weeks": missing,
        "coverage": {"weeks_total": len(weeks), "weeks_with_board": len(weeks) - len(missing)},
        "caliber": "已存周榜样本的新增 star 合计（无存档期间不计零）",
        "ranked": ranked, "no_star": no_star,
    }


def markdown(result: dict, top_n: int = 10) -> str:
    p = result["period"]
    lines = [
        f"> 口径：{result['caliber']}；覆盖 {result['coverage']['weeks_with_board']}/"
        f"{result['coverage']['weeks_total']} 周。空值、未入榜、缺周榜均不当零。",
        "",
        f"## 月度 GitHub 榜 Top {top_n}" if len(p) == 7 and p[5] != "Q"
        else f"## 季度 GitHub 榜 Top {top_n}",
        "",
        "| # | 仓库 | 合计 star | 贡献周数 | 覆盖天数 | 缺测 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for i, r in enumerate(result["ranked"][:top_n], 1):
        miss = ",".join(r["no_star_weeks"]) or "-"
        lines.append(
            f"| {i} | [{r['full_name']}](https://github.com/{r['full_name']}) | "
            f"{r['total']} | {len(r['contributing_weeks'])} | {r['days_covered']} | {miss} |")
    if result["missing_weeks"]:
        lines += ["", "缺周榜：" + ", ".join(result["missing_weeks"]) + "（不计零）"]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--period", required=True, help="YYYY-MM 或 YYYY-QN")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--out", required=True, help="输出到工作目录的 JSON 路径")
    ap.add_argument("--md-out", help="可选：Markdown 片段输出路径")
    args = ap.parse_args()
    try:
        result = aggregate(args.period)
    except (ValueError, OSError) as e:
        print(f"AGGREGATE_FAILED: {e}", file=sys.stderr)
        return 1
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.md_out:
        pathlib.Path(args.md_out).write_text(markdown(result, args.top), encoding="utf-8")
    print(f"AGGREGATE=ok period={args.period} weeks={result['coverage']['weeks_with_board']}"
          f"/{result['coverage']['weeks_total']} ranked={len(result['ranked'])} out={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
