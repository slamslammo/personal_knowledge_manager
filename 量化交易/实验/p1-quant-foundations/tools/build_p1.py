#!/usr/bin/env python
"""Build P1 fixtures, lesson notebooks, module labs and artifact manifest."""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import nbformat
import numpy as np
import pandas as pd
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
COURSE_ROOT = ROOT.parents[3] / "pam-video-captures" / "365-days-quant-finance"
OUTLINE_PATH = COURSE_ROOT / "official-outline.json"

sys.path.insert(0, str(TOOLS))
from lab_cells import lab_cells  # noqa: E402
from lesson_cells import CODE_LESSONS, FORMULAS, lesson_cells  # noqa: E402
from p1_config import CAPABILITIES, DETAILS, MODULES  # noqa: E402


NOTEBOOKS = ROOT / "notebooks"
LABS = ROOT / "labs"
NOTES = ROOT / "notes"
REPORTS = ROOT / "reports"
DATA = ROOT / "data" / "fixtures"
OUTPUTS = ROOT / "outputs"
for path in (NOTEBOOKS, LABS, NOTES, REPORTS, DATA, OUTPUTS):
    path.mkdir(parents=True, exist_ok=True)


KERNEL_METADATA = {
    "kernelspec": {
        "display_name": "Python (pkm-quant)",
        "language": "python",
        "name": "pkm-quant",
    },
    "language_info": {"name": "python", "version": "3.11"},
}


BOOTSTRAP = """from pathlib import Path
import json
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path.cwd()
if not (ROOT / "data" / "fixtures").exists():
    ROOT = ROOT.parent
DATA_DIR = ROOT / "data" / "fixtures"
OUTPUT_DIR = ROOT / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RANDOM_SEED = 365
print("项目:", ROOT)
print("数据:", DATA_DIR)
print("数据身份: 固定随机种子生成的模拟教学数据，不是真实证券行情")
"""


def module_for(number: int) -> dict:
    return next(
        module
        for module in MODULES
        if module["start"] <= number <= module["end"]
    )


def generate_fixtures() -> None:
    rng = np.random.default_rng(365)
    dates = pd.bdate_range("2023-01-03", periods=756)
    symbols = [
        "SIM_MARKET",
        "SIM_VALUE",
        "SIM_GROWTH",
        "SIM_DEFENSIVE",
        "SIM_COMMODITY",
        "SIM_BOND",
    ]
    betas = np.array([1.0, 0.82, 1.25, 0.55, 0.35, -0.10])
    drifts = np.array([0.00025, 0.00028, 0.00036, 0.00018, 0.00015, 0.00009])
    idio_vol = np.array([0.002, 0.006, 0.009, 0.004, 0.008, 0.0025])
    market_shock = rng.standard_t(df=7, size=len(dates)) * 0.008
    log_returns = (
        drifts[None, :]
        + market_shock[:, None] * betas[None, :]
        + rng.normal(size=(len(dates), len(symbols))) * idio_vol[None, :]
    )
    prices = np.exp(np.log(np.array([100, 42, 35, 28, 55, 98])) + np.cumsum(log_returns, axis=0))
    daily = pd.DataFrame(prices, index=dates, columns=symbols)
    daily_long = (
        daily.rename_axis(index="date", columns="symbol")
        .stack()
        .rename("adj_close")
        .reset_index()
    )
    daily_long["raw_close"] = daily_long["adj_close"]
    daily_long["currency"] = "CNY"
    daily_long["frequency"] = "1d"
    daily_long.to_csv(DATA / "daily_prices.csv", index=False, float_format="%.8f")

    book_rows = []
    mid = 100.0
    for level in range(1, 6):
        book_rows.append(
            {
                "snapshot_time": "2025-01-02 10:00:00+08:00",
                "side": "bid",
                "level": level,
                "price": mid - 0.01 * level,
                "quantity": 180 + level * 120,
            }
        )
        book_rows.append(
            {
                "snapshot_time": "2025-01-02 10:00:00+08:00",
                "side": "ask",
                "level": level,
                "price": mid + 0.01 * level,
                "quantity": 140 + level * 130,
            }
        )
    pd.DataFrame(book_rows).to_csv(DATA / "order_book.csv", index=False)

    tick_times = pd.date_range(
        "2025-01-02 09:30:01+08:00", periods=240, freq="5s"
    )
    tick_price = 100 + np.cumsum(rng.choice([-0.01, 0.0, 0.01], len(tick_times)))
    ticks = pd.DataFrame(
        {
            "timestamp": tick_times,
            "price": tick_price,
            "quantity": rng.integers(10, 300, len(tick_times)),
            "symbol": "SIM_A",
        }
    )
    ticks.to_csv(DATA / "intraday_ticks.csv", index=False, float_format="%.4f")

    actions = pd.DataFrame(
        [
            {
                "date": "2025-01-06",
                "symbol": "SIM_A",
                "action": "split",
                "value": 2.0,
                "announced_at": "2024-12-20",
            },
            {
                "date": "2025-03-10",
                "symbol": "SIM_A",
                "action": "cash_dividend",
                "value": 0.30,
                "announced_at": "2025-02-20",
            },
        ]
    )
    actions.to_csv(DATA / "corporate_actions.csv", index=False)

    metadata = {
        "schema": "p1.quant-fixtures.v1",
        "identity": "synthetic",
        "seed": 365,
        "warning": "固定随机种子生成的模拟教学数据，不是真实证券行情，不可用于投资结论。",
        "timezone_convention": "Asia/Shanghai",
        "annualization_periods": 252,
        "files": {
            "daily_prices.csv": {
                "shape": list(daily_long.shape),
                "frequency": "1 business day",
                "adjustment": "simulated adjusted close",
            },
            "order_book.csv": {
                "shape": [len(book_rows), len(book_rows[0])],
                "frequency": "single L2 snapshot",
            },
            "intraday_ticks.csv": {
                "shape": list(ticks.shape),
                "frequency": "5 seconds",
            },
            "corporate_actions.csv": {
                "shape": list(actions.shape),
                "frequency": "event",
            },
        },
    }
    (DATA / "fixture_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (DATA / "README.md").write_text(
        "# P1 教学数据\n\n"
        "本目录数据全部为固定随机种子生成或手工构造的模拟教学数据，"
        "不是真实证券行情，不可用于策略收益或投资结论。\n\n"
        "- `daily_prices.csv`：六个模拟资产的 756 个交易日价格。\n"
        "- `order_book.csv`：一张五档模拟订单簿快照。\n"
        "- `intraday_ticks.csv`：5 秒频率模拟逐笔样例。\n"
        "- `corporate_actions.csv`：拆股和现金分红教学事件。\n"
        "- `fixture_metadata.json`：生成方式、shape 和口径。\n",
        encoding="utf-8",
    )


def course_source(number: int, outline_by_number: dict[int, dict]) -> str:
    lesson = outline_by_number[number]
    return lesson.get("mapping", {}).get("localHtml", "")


def notebook_intro(number: int, outline: dict) -> str:
    detail = DETAILS[number]
    module = module_for(number)
    source = course_source(number, outline)
    return f"""# 第 {number:02d} 课｜{outline[number]["outlineTitle"]}

> **数据身份**：固定随机种子生成的模拟教学数据，不是真实证券行情。  
> **环境**：`pkm-quant` · Python 3.11 · 默认离线运行。  
> **课程原始材料**：`{source}`  
> **所属模块**：P1-{module["id"]} · {module["title"]}

## 本节量化问题

{detail["question"]}

## 准确定义与策略报告位置

{detail["concepts"]}

- **核心关系**：{FORMULAS[number]}
- **写入报告**：{detail["report_field"]}
- **P2 衔接**：{detail["p2"]}
"""


def notebook_boundary(number: int) -> str:
    detail = DETAILS[number]
    return f"""## 方法边界与阶段验收

{detail["boundary"]}

完成本课后应能：

1. 不看课程材料准确解释核心概念和公式符号；
2. 用小样本手工核对 Notebook 的关键结果；
3. 说明结果能支持什么判断、不能支持什么判断；
4. 指出它在策略报告中的位置，以及仍缺少的数据、成本或稳健性证据。
"""


def build_lesson_notebooks(outline: dict[int, dict]) -> None:
    for number in sorted(CODE_LESSONS):
        detail = DETAILS[number]
        cells = [
            new_markdown_cell(notebook_intro(number, outline)),
            new_markdown_cell(
                "## 运行环境与数据契约\n\n"
                "先确认项目、数据目录和数据身份。后续联网数据源必须通过适配层进入，"
                "不能改变本 Notebook 的研究计算口径。"
            ),
            new_code_cell(BOOTSTRAP),
        ]
        for heading, explanation, code in lesson_cells(number):
            cells.append(new_markdown_cell(f"## {heading}\n\n{explanation}"))
            cells.append(new_code_cell(code.strip()))
        cells.append(new_markdown_cell(notebook_boundary(number)))
        notebook = new_notebook(cells=cells, metadata=KERNEL_METADATA)
        path = NOTEBOOKS / f"{detail['basename']}.ipynb"
        nbformat.write(notebook, path)


def build_lab_notebooks() -> None:
    for module in MODULES:
        lab = module["lab"]
        cells = [
            new_markdown_cell(
                f"# P1-{lab['id']}｜{lab['title']}\n\n"
                f"> **对应课程**：第 {module['start']}–{module['end']} 课  \n"
                f"> **模块**：P1-{module['id']} · {module['title']}  \n"
                "> **数据身份**：固定随机种子模拟教学数据，不是真实证券行情。\n\n"
                f"{lab['description']}\n\n"
                f"本实验向最终策略报告提供：**{module['report_field']}**。"
            ),
            new_code_cell(BOOTSTRAP),
        ]
        for heading, explanation, code in lab_cells(lab["id"]):
            cells.append(new_markdown_cell(f"## {heading}\n\n{explanation}"))
            cells.append(new_code_cell(code.strip()))
        cells.append(
            new_markdown_cell(
                "## 验收\n\n"
                "- 关键计算能由小例子或独立公式核对；\n"
                "- 数据时点、信号时点和成交时点没有混用；\n"
                "- 结果同时包含金融含义和失败边界；\n"
                "- 产物能够进入第 29 课策略报告和第 30 课能力矩阵。"
            )
        )
        nbformat.write(
            new_notebook(cells=cells, metadata=KERNEL_METADATA),
            LABS / f"{lab['basename']}.ipynb",
        )


def escape(value: object) -> str:
    return html.escape(str(value))


def html_page(title: str, eyebrow: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<style>
:root{{color-scheme:dark;--bg:#111310;--panel:#1a1d19;--ink:#f2f1e9;--muted:#a4aaa1;--line:#343a32;--accent:#d39a25;font:16px/1.75 -apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans CJK SC",sans-serif}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink)}}main{{width:min(960px,calc(100% - 32px));margin:40px auto 80px}}article{{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:clamp(22px,5vw,50px)}}.eyebrow{{color:var(--accent);font:700 12px ui-monospace,monospace;letter-spacing:.14em}}h1{{font-size:clamp(32px,6vw,58px);line-height:1.08;margin:12px 0 22px}}h2{{margin-top:34px}}p,li{{color:#c7cbc4}}strong{{color:#fff}}table{{width:100%;border-collapse:collapse;margin:18px 0}}th,td{{border:1px solid var(--line);padding:10px;text-align:left;vertical-align:top}}th{{color:#f4cd76;background:#20251f}}code{{background:#252a24;padding:2px 5px;border-radius:5px}}.chain{{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}}.chain span{{border:1px solid #5b5134;border-radius:999px;padding:5px 10px;color:#e4c174}}.callout{{border-left:4px solid var(--accent);padding:12px 16px;background:#22251e;color:#e0e2dc}}a{{color:#9fd5b6}}
@media(max-width:600px){{article{{padding:20px}}th,td{{padding:7px;font-size:13px}}}}
</style></head><body><main><article><div class="eyebrow">{escape(eyebrow)}</div>{body}</article></main></body></html>"""


def special_body(number: int) -> str:
    if number == 1:
        return """
<h2>阶段目标</h2>
<p>能够解释一条交易想法如何从市场假设，经过数据和统计验证，变成一份包含收益、风险、成本和基准的策略报告。</p>
<h2>研究证据链</h2>
<div class="chain"><span>交易想法</span><span>市场假设</span><span>数据契约</span><span>收益与风险</span><span>统计证据</span><span>执行与成本</span><span>策略报告</span></div>
<p class="callout">学习顺序可以螺旋推进，但报告中的证据不能缺项。第 29 课负责交付，第 30 课负责验收。</p>
"""
    if number == 2:
        return """
<h2>决策体系对照</h2>
<table><tr><th>维度</th><th>量化决策</th><th>主观决策</th></tr>
<tr><td>规则</td><td>显式、可复现、可批量验证</td><td>可包含难以形式化的情境判断</td></tr>
<tr><td>一致性</td><td>同输入通常得到同输出</td><td>可能受状态、经验和叙事影响</td></tr>
<tr><td>优势</td><td>规模、速度、纪律和审计</td><td>稀缺信息、制度理解和非结构化判断</td></tr>
<tr><td>主要风险</td><td>错误数据、过拟合、模型失效和自动放大</td><td>认知偏差、执行不一致和难以复盘</td></tr></table>
"""
    if number == 3:
        return """
<h2>按优势来源而不是模型复杂度分类</h2>
<table><tr><th>流派</th><th>主要优势来源</th><th>典型周期</th><th>关键约束</th></tr>
<tr><td>因子投资</td><td>风险补偿、行为偏差或制度摩擦</td><td>周到年</td><td>拥挤、换手、暴露和容量</td></tr>
<tr><td>统计套利</td><td>相对定价偏离和短期统计依赖</td><td>分钟到月</td><td>结构变化、做空和成本</td></tr>
<tr><td>做市/高频</td><td>流动性补偿、价差和速度</td><td>毫秒到日内</td><td>延迟、库存、队列和基础设施</td></tr></table>
"""
    if number == 25:
        return """
<h2>交易场所研究清单</h2>
<table><tr><th>维度</th><th>需要核对的内容</th><th>影响</th></tr>
<tr><td>交易时间</td><td>时区、连续/集合竞价、午休和节假日</td><td>数据对齐与信号可得时点</td></tr>
<tr><td>订单规则</td><td>支持的订单类型、最小单位、涨跌停</td><td>成交概率和滑点</td></tr>
<tr><td>结算与做空</td><td>T+0/T+1、借券、保证金</td><td>资金占用和策略可执行性</td></tr>
<tr><td>费用与数据</td><td>交易费、市场数据权限和深度</td><td>成本、回测精度和合规</td></tr></table>
<p class="callout">规则会变化。实盘前必须回到交易所、经纪商和监管机构的一手文件核对。</p>
"""
    if number == 30:
        rows = "".join(
            f"<tr><td>{escape(name)}</td><td>{escape(course)}</td><td>{escape(lab)}</td><td>{escape(report)}</td>"
            "<td>□解释　□手算　□代码　□边界　□报告</td></tr>"
            for name, course, lab, report in CAPABILITIES
        )
        return f"""
<h2>五级验收</h2>
<ol><li>能准确解释</li><li>能手工计算或画出机制</li><li>能用代码复现</li><li>能识别边界</li><li>能写入策略报告</li></ol>
<h2>十项核心能力矩阵</h2>
<table><tr><th>能力</th><th>课程</th><th>实验</th><th>报告字段</th><th>验收状态</th></tr>{rows}</table>
<p class="callout">完成 P1 不等于具备实盘条件。下一阶段用 P2 把已理解的金融概念转成可复现、可测试和可交付的工具链。</p>
"""
    raise KeyError(number)


def build_non_code_notes(outline: dict[int, dict]) -> None:
    for number in (1, 2, 3, 25, 30):
        detail = DETAILS[number]
        module = module_for(number)
        source = course_source(number, outline)
        markdown = (
            f"# 第 {number:02d} 课｜{outline[number]['outlineTitle']}\n\n"
            f"- 所属模块：P1-{module['id']} · {module['title']}\n"
            f"- 原始材料：`{source}`\n"
            f"- 策略报告字段：{detail['report_field']}\n\n"
            f"## 本节量化问题\n\n{detail['question']}\n\n"
            f"## 准确定义\n\n{detail['concepts']}\n\n"
            f"## 方法边界\n\n{detail['boundary']}\n\n"
            f"## P2 衔接\n\n{detail['p2']}\n"
        )
        (NOTES / f"{detail['basename']}.md").write_text(markdown, encoding="utf-8")
        body = (
            f"<h1>第 {number:02d} 课｜{escape(outline[number]['outlineTitle'])}</h1>"
            f"<p><strong>本节量化问题：</strong>{escape(detail['question'])}</p>"
            f"<p><strong>课程定位：</strong>{escape(detail['concepts'])}</p>"
            f"<p><strong>写入策略报告：</strong>{escape(detail['report_field'])}</p>"
            + special_body(number)
            + f"<h2>方法边界</h2><p>{escape(detail['boundary'])}</p>"
            + f"<h2>P2 衔接</h2><p>{escape(detail['p2'])}</p>"
        )
        (REPORTS / f"{detail['basename']}.html").write_text(
            html_page(
                outline[number]["outlineTitle"],
                f"P1-{module['id']} · 第 {number:02d} 课 · 知识讲解",
                body,
            ),
            encoding="utf-8",
        )


def build_manifest(outline: dict[int, dict]) -> None:
    lessons = []
    for number in range(1, 31):
        detail = DETAILS[number]
        has_notebook = number in CODE_LESSONS
        lessons.append(
            {
                "number": number,
                "title": outline[number]["outlineTitle"],
                "module": module_for(number)["id"],
                "source": course_source(number, outline),
                "report": f"reports/{detail['basename']}.html",
                "notebook": (
                    f"notebooks/{detail['basename']}.ipynb"
                    if has_notebook
                    else None
                ),
                "artifactType": (
                    "knowledge-report-and-notebook"
                    if has_notebook
                    else "knowledge-report"
                ),
                "strategyReportField": detail["report_field"],
                "status": "built",
            }
        )
    manifest = {
        "schema": "p1.quant-foundations.artifacts.v1",
        "courseRange": [1, 30],
        "environment": "pkm-quant",
        "dataDefault": "offline-synthetic-fixtures",
        "singleBrowserEntry": str(COURSE_ROOT / "knowledge-map.html"),
        "modules": MODULES,
        "lessons": lessons,
        "labs": [
            {
                "id": module["lab"]["id"],
                "module": module["id"],
                "title": module["lab"]["title"],
                "report": f"reports/{module['lab']['basename']}.html",
                "notebook": f"labs/{module['lab']['basename']}.ipynb",
                "status": "built",
            }
            for module in MODULES
        ],
        "counts": {
            "knowledgeReports": 30,
            "lessonNotebooks": len(CODE_LESSONS),
            "labs": len(MODULES),
        },
    }
    (ROOT / "artifact-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    outline_data = json.loads(OUTLINE_PATH.read_text(encoding="utf-8"))
    outline = {
        int(lesson["number"]): lesson
        for lesson in outline_data["lessons"]
        if int(lesson["number"]) <= 30
    }
    if set(outline) != set(range(1, 31)):
        raise RuntimeError("official-outline.json 缺少 P1 第 1–30 课")
    generate_fixtures()
    build_lesson_notebooks(outline)
    build_lab_notebooks()
    build_non_code_notes(outline)
    build_manifest(outline)
    print(
        json.dumps(
            {
                "knowledge_reports": 5,
                "lesson_notebooks": len(CODE_LESSONS),
                "labs": len(MODULES),
                "fixtures": 4,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

