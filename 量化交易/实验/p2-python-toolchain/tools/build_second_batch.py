#!/usr/bin/env python
"""Build P2 lesson notebooks 37–42 and the L2 lab."""

from __future__ import annotations

from build_first_batch import (
    COMMON_SETUP,
    LABS,
    code,
    md,
    write_notebook,
)
from second_batch_37_38 import build_lesson_37, build_lesson_38
from second_batch_39_40 import build_lesson_39, build_lesson_40
from second_batch_41_42 import build_lesson_41, build_lesson_42


def build_lab_2():
    cells = [
        md(
            """
# L2 综合实验｜行情清洗与时间对齐

本实验整合第 34–39 课：

- Pandas 标签对齐与安全选择；
- 时间索引、时区与 OHLCV 契约；
- rolling/EWM 与历史可得性；
- MultiIndex、groupby 与行业去均值；
- 缺失原因、估值价格和可交易状态；
- `concat/merge/merge_asof` 与 point-in-time 基本面。

- 环境：`pkm-quant`
- 数据：固定随机种子生成的离线模拟行情（**非真实股票数据**）
- 输出：`outputs/L2_data_quality_report.csv`
- 状态：可运行学习稿；不代表策略收益承诺

> 本实验不把“填满表格”作为目标。目标是让每个值都能回答：它从哪里来、何时可得、能否交易、是否与正确股票和日期对齐。
"""
        ),
        md(
            """
## 1. 研究任务、输入与验收

我们从原始模拟日线构造一个有代表性的研究面板，并故意加入三类业务缺口：

1. `pre_listing`：资产尚未上市；
2. `suspension`：停牌，资产存续但不可交易；
3. `source_gap`：数据源缺口，应优先修复而非凭空插值。

随后完成：

```text
原始长表 → 键与 OHLCV 契约 → 缺失原因/可交易状态
          → 估值口径 → 行业截面特征
          → 按 available_at 合并基本面 → 数据质量报告
```

验收重点不是“没有 NaN”，而是：

- 唯一键、排序、字段关系、标签完整；
- 原始价不被覆盖；
- 停牌估值和模拟成交严格分开；
- 基本面只能在 `available_at` 之后出现；
- 行业中性化残差在每个“日期 × 行业”内均值为 0；
- 每只资产的缺失率、最长连续缺失和不可交易天数可审计。
"""
        ),
        code(COMMON_SETUP),
        md(
            """
## 2. 读取并展示原始模拟行情

先查看完整长表的行、列、证券和日期，再选择四只资产与最近 260 日。`copy()` 明确创建独立研究样本，后续修改不会污染原始 DataFrame。
"""
        ),
        code(
            """
# 读取完整模拟日线；选取 4 只资产和最近 260 个交易日。
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
symbols = ["BANK_A", "INSURE_A", "EV_A", "TECH_A"]
sample_dates = np.sort(daily["date"].unique())[-260:]
raw = (
    daily.loc[
        daily["symbol"].isin(symbols) & daily["date"].isin(sample_dates)
    ]
    .sort_values(["date", "symbol"])
    .reset_index(drop=True)
    .copy()
)

print("完整数据 shape:", daily.shape)
print("实验样本 shape:", raw.shape, "含义: 日期 × 股票长表")
print("日期:", raw["date"].min().date(), "→", raw["date"].max().date())
display(raw.head(8))

assert raw.shape[0] == 260 * 4
assert not raw.duplicated(["date", "symbol"]).any()
assert raw.groupby("symbol")["date"].nunique().eq(260).all()
"""
        ),
        md(
            """
## 3. 数据契约：键、类型和 OHLCV 关系

数据契约应在清洗前执行。这里集中检查：

- `date × symbol` 唯一；
- 日期升序、代码非空；
- 价格为正、成交量非负；
- `high ≥ max(open, close)`；
- `low ≤ min(open, close)`。

shape 正确不能替代这些语义检查。
"""
        ),
        code(
            """
# 对未引入缺口的原始样本执行完整数据契约。
required_columns = [
    "date", "symbol", "sector",
    "open", "high", "low", "close", "adj_close", "volume",
]
assert set(required_columns).issubset(raw.columns)
assert raw[["date", "symbol", "sector"]].notna().all().all()
assert not raw.duplicated(["date", "symbol"]).any()
assert raw[["open", "high", "low", "close", "adj_close"]].gt(0).all().all()
assert raw["volume"].ge(0).all()
assert (raw["high"] >= raw[["open", "close"]].max(axis=1)).all()
assert (raw["low"] <= raw[["open", "close"]].min(axis=1)).all()

contract_result = pd.Series(
    {
        "唯一键": True,
        "标签完整": True,
        "价格为正": True,
        "成交量非负": True,
        "OHLC 关系": True,
    },
    name="原始输入契约",
)
display(contract_result.to_frame())
"""
        ),
        md(
            """
## 4. 构造可解释缺口：`NaN` 之外还要有原因码

以下缺口由实验确定性构造，不是原 CSV 的真实问题：

- `TECH_A` 前 15 日：`pre_listing`；
- `EV_A` 中间连续 6 日：`suspension`；
- `BANK_A` 单日：`source_gap`。

我们保留四类信息：

```text
raw_adj_close     原始可观察价格
missing_reason    为什么缺失
tradable          当日能否模拟成交
valuation_price   按估值政策使用的价格（稍后生成）
```
"""
        ),
        code(
            """
# 在独立副本中加入三类缺口；原始 raw 不被覆盖。
panel = raw.copy()
panel["missing_reason"] = pd.NA
panel["tradable"] = True
price_columns = ["open", "high", "low", "close", "adj_close"]

tech_dates = (
    panel.loc[panel["symbol"].eq("TECH_A"), "date"]
    .sort_values()
    .iloc[:15]
)
ev_dates = (
    panel.loc[panel["symbol"].eq("EV_A"), "date"]
    .sort_values()
    .iloc[120:126]
)
bank_gap_date = (
    panel.loc[panel["symbol"].eq("BANK_A"), "date"]
    .sort_values()
    .iloc[80]
)

gap_specs = [
    ("TECH_A", tech_dates, "pre_listing"),
    ("EV_A", ev_dates, "suspension"),
    ("BANK_A", pd.Index([bank_gap_date]), "source_gap"),
]
for symbol, dates, reason in gap_specs:
    mask = panel["symbol"].eq(symbol) & panel["date"].isin(dates)
    panel.loc[mask, price_columns] = np.nan
    panel.loc[mask, "volume"] = 0
    panel.loc[mask, "missing_reason"] = reason
    panel.loc[mask, "tradable"] = False

missing_rows = panel.loc[
    panel["adj_close"].isna(),
    ["date", "symbol", "adj_close", "volume", "missing_reason", "tradable"],
]
display(missing_rows.head(24))

assert raw["adj_close"].notna().all()
assert panel["adj_close"].isna().sum() == 22
assert panel.loc[panel["adj_close"].isna(), "missing_reason"].notna().all()
assert not panel.loc[panel["adj_close"].isna(), "tradable"].any()
"""
        ),
        md(
            """
## 5. 宽表审计：缺失数、缺失率和最长连续缺失

`pivot(index="date", columns="symbol", values="adj_close")` 把长表重排为“日期 × 股票”价格矩阵。它要求每个键唯一，不会像 `pivot_table` 一样静默聚合重复键。

最长连续缺失比总缺失数更有解释力：12 个散落接口缺口与连续 12 日停牌不是同一种风险。
"""
        ),
        code(
            """
# 建立价格宽表，并定义最长连续 True 区段的确定性计算。
raw_price = panel.pivot(
    index="date",
    columns="symbol",
    values="adj_close",
).sort_index()
tradable = panel.pivot(
    index="date",
    columns="symbol",
    values="tradable",
).sort_index()

def longest_true_run(mask):
    values = pd.Series(mask, dtype=bool).to_numpy()
    longest = 0
    current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return int(longest)

quality = pd.DataFrame(index=raw_price.columns)
quality.index.name = "symbol"
quality["观测日"] = len(raw_price)
quality["缺失数"] = raw_price.isna().sum()
quality["缺失率"] = raw_price.isna().mean()
quality["不可交易日"] = (~tradable).sum()
quality["最长连续缺失"] = [
    longest_true_run(raw_price[symbol].isna())
    for symbol in raw_price.columns
]
display(quality)

assert quality.loc["TECH_A", "最长连续缺失"] == 15
assert quality.loc["EV_A", "最长连续缺失"] == 6
assert quality.loc["BANK_A", "最长连续缺失"] == 1
assert quality.loc["INSURE_A", "缺失数"] == 0
"""
        ),
        md(
            """
## 6. 估值价格不等于可交易价格

本实验只对 `suspension` 使用前一有效价格作为估值标记：

- 停牌期间 `valuation_price` 可沿用旧值；
- `tradable=False`，不得按该估值价模拟成交；
- 复牌日重新使用真实模拟价格，跳空进入持仓价值变化。

`pre_listing` 保持空值；`source_gap` 也保持空值，提醒研究者修复源数据。
"""
        ),
        code(
            """
# 先生成候选前向估值，再只回填 missing_reason == suspension 的单元。
valuation_price = raw_price.copy()
ffill_candidate = raw_price.ffill(limit=6)
reason_wide = panel.pivot(
    index="date",
    columns="symbol",
    values="missing_reason",
).sort_index()
suspension_mask = reason_wide.eq("suspension")
valuation_price = valuation_price.mask(
    suspension_mask,
    ffill_candidate,
)

ev_audit = pd.DataFrame(
    {
        "raw_price": raw_price["EV_A"],
        "valuation_price": valuation_price["EV_A"],
        "tradable": tradable["EV_A"],
        "reason": reason_wide["EV_A"],
    }
).loc[ev_dates.min() - pd.Timedelta(days=3): ev_dates.max() + pd.Timedelta(days=5)]
display(ev_audit)

assert valuation_price.loc[ev_dates, "EV_A"].notna().all()
assert not tradable.loc[ev_dates, "EV_A"].any()
assert valuation_price.loc[tech_dates, "TECH_A"].isna().all()
assert pd.isna(valuation_price.loc[bank_gap_date, "BANK_A"])
"""
        ),
        md(
            """
### 估值收益与复牌跳空

`pct_change(fill_method=None)` 对估值序列计算相邻日变化。停牌估值日会出现 0 收益；复牌日若价格变化，会集中体现跳空。0 收益不代表当日可交易。
"""
        ),
        code(
            """
# 计算估值收益，并展示停牌前后；收益与 tradable 必须并列解释。
valuation_return = valuation_price.pct_change(fill_method=None)
ev_return_audit = ev_audit.join(
    valuation_return["EV_A"].rename("valuation_return")
)
display(ev_return_audit)

resume_candidates = raw_price.index[
    (raw_price.index > ev_dates.max()) & raw_price["EV_A"].notna()
]
resume_date = resume_candidates[0]

assert valuation_return.loc[ev_dates, "EV_A"].eq(0).all()
assert np.isfinite(valuation_return.loc[resume_date, "EV_A"])
assert tradable.loc[resume_date, "EV_A"]
"""
        ),
        md(
            """
## 7. 行业截面特征：`groupby(...).transform(...)`

我们用估值收益构造长表，合并原始行业标签，再做逐日行业去均值：

\\[
neutral_{i,t}=r_{i,t}-\\overline{r}_{industry(i),t}
\\]

`transform("mean")` 保持原索引和行数；与 `agg("mean")` 的汇总结果不同。缺失值仍保持缺失，不被填成 0。
"""
        ),
        code(
            """
# 把收益宽表还原成长表，并安全合并每只资产唯一的行业映射。
return_long = (
    valuation_return.stack(future_stack=True)
    .rename("return")
    .reset_index()
)
sector_map = (
    raw[["symbol", "sector"]]
    .drop_duplicates()
    .sort_values("symbol")
)
assert not sector_map["symbol"].duplicated().any()

return_long = return_long.merge(
    sector_map,
    on="symbol",
    how="left",
    validate="many_to_one",
)
return_long["industry_mean"] = return_long.groupby(
    ["date", "sector"],
    dropna=False,
)["return"].transform("mean")
return_long["industry_neutral"] = (
    return_long["return"] - return_long["industry_mean"]
)

display(return_long.dropna(subset=["return"]).head(8))
assert len(return_long) == len(valuation_return) * valuation_return.shape[1]
assert return_long["sector"].notna().all()
"""
        ),
        code(
            """
# 只在每组至少有一个有效收益时检查中性化残差均值为 0。
neutral_check = (
    return_long.dropna(subset=["industry_neutral"])
    .groupby(["date", "sector"])["industry_neutral"]
    .mean()
)
print("最大行业残差均值绝对值:", neutral_check.abs().max())
np.testing.assert_allclose(neutral_check.to_numpy(), 0.0, atol=1e-12)
"""
        ),
        md(
            """
## 8. Point-in-time 基本面：按 `available_at` 合并

同一财务记录至少区分：

- `report_period`：报告覆盖期；
- `published_at`：公开发布时间；
- `available_at`：策略最早能合法使用的时间。

下面为每只模拟资产构造两次已知发布日期的质量分数，并在每只资产内部使用 `merge_asof(direction="backward")`。这样交易日只能看到当时已经可得的最近记录。
"""
        ),
        code(
            """
# 构造样本期内两次确定性模拟公告；它不是任何真实公司的财务数据。
available_1 = pd.Timestamp(sample_dates[60])
available_2 = pd.Timestamp(sample_dates[180])
report_1 = available_1 - pd.Timedelta(days=90)
report_2 = available_2 - pd.Timedelta(days=90)
published_1 = available_1 - pd.Timedelta(hours=6)
published_2 = available_2 - pd.Timedelta(hours=6)

fundamental_rows = []
for symbol_index, symbol in enumerate(symbols):
    fundamental_rows.extend(
        [
            {
                "symbol": symbol,
                "report_period": report_1,
                "published_at": published_1,
                "available_at": available_1,
                "quality_score": 0.55 + 0.03 * symbol_index,
            },
            {
                "symbol": symbol,
                "report_period": report_2,
                "published_at": published_2,
                "available_at": available_2,
                "quality_score": 0.58 + 0.02 * symbol_index,
            },
        ]
    )
fundamentals = pd.DataFrame(fundamental_rows)
display(fundamentals.head(8))

assert not fundamentals.duplicated(["symbol", "available_at"]).any()
assert (fundamentals["available_at"] > fundamentals["report_period"]).all()
assert (fundamentals["available_at"].dt.normalize() >= fundamentals["published_at"].dt.normalize()).all()
"""
        ),
        code(
            """
# 每只资产分别做 backward as-of join，避免把其他股票的财务记录串进来。
market_keys = (
    panel[["date", "symbol"]]
    .drop_duplicates()
    .rename(columns={"date": "trade_date"})
)
pit_parts = []
for symbol, left_part in market_keys.groupby("symbol", sort=False):
    right_part = fundamentals.loc[
        fundamentals["symbol"].eq(symbol)
    ].drop(columns="symbol")
    matched = pd.merge_asof(
        left_part.sort_values("trade_date"),
        right_part.sort_values("available_at"),
        left_on="trade_date",
        right_on="available_at",
        direction="backward",
        tolerance=pd.Timedelta("550D"),
    )
    pit_parts.append(matched)

pit = (
    pd.concat(pit_parts, ignore_index=True)
    .sort_values(["trade_date", "symbol"])
    .reset_index(drop=True)
)
display(pit.dropna(subset=["quality_score"]).head(8))

valid_time = pit["available_at"].isna() | pit["available_at"].le(pit["trade_date"])
assert len(pit) == len(market_keys)
assert valid_time.all()
assert pit["symbol"].isin(symbols).all()
"""
        ),
        md(
            """
### 用边界日期核对“何时开始可见”

不能只检查 `available_at <= trade_date`，还要选公告边界前后手工核对。若样本期没有覆盖某个边界，就应明确报告，而不是伪造通过。
"""
        ),
        code(
            """
# 对样本期内可见的每次公告，核对公告前最近交易日不可见新值、公告后开始可见。
boundary_checks = []
for row in fundamentals.itertuples(index=False):
    symbol_dates = pit.loc[pit["symbol"].eq(row.symbol), "trade_date"]
    before = symbol_dates[symbol_dates < row.available_at]
    after = symbol_dates[symbol_dates >= row.available_at]
    if len(before) and len(after):
        before_row = pit.loc[
            pit["symbol"].eq(row.symbol) & pit["trade_date"].eq(before.max())
        ].iloc[0]
        after_row = pit.loc[
            pit["symbol"].eq(row.symbol) & pit["trade_date"].eq(after.min())
        ].iloc[0]
        boundary_checks.append(
            {
                "symbol": row.symbol,
                "available_at": row.available_at,
                "前一交易日": before_row["trade_date"],
                "前一日可见版本": before_row["available_at"],
                "首个可见交易日": after_row["trade_date"],
                "首日可见版本": after_row["available_at"],
            }
        )
        assert pd.isna(before_row["available_at"]) or before_row["available_at"] < row.available_at
        assert after_row["available_at"] == row.available_at

boundary_table = pd.DataFrame(boundary_checks)
display(boundary_table)
assert len(boundary_table) > 0
"""
        ),
        md(
            """
## 9. 形成研究面板与质量报告

研究面板连接：

- 原始/估值/收益/行业中性收益；
- `tradable` 与 `missing_reason`；
- 当时可见的基本面分数。

合并使用明确键并验证行数，防止多对多连接静默膨胀。
"""
        ),
        code(
            """
# 把各链路按日期和股票合并；每一步都验证 cardinality。
base_panel = panel[
    ["date", "symbol", "sector", "adj_close", "tradable", "missing_reason"]
].rename(columns={"adj_close": "raw_price"})
valuation_long = (
    valuation_price.stack(future_stack=True)
    .rename("valuation_price")
    .reset_index()
)
feature_columns = return_long[
    ["date", "symbol", "return", "industry_neutral"]
]
pit_features = pit[
    ["trade_date", "symbol", "available_at", "quality_score"]
].rename(columns={"trade_date": "date"})

research_panel = (
    base_panel
    .merge(
        valuation_long,
        on=["date", "symbol"],
        how="left",
        validate="one_to_one",
    )
    .merge(
        feature_columns,
        on=["date", "symbol"],
        how="left",
        validate="one_to_one",
    )
    .merge(
        pit_features,
        on=["date", "symbol"],
        how="left",
        validate="one_to_one",
    )
    .sort_values(["date", "symbol"])
    .reset_index(drop=True)
)

print("研究面板 shape:", research_panel.shape)
display(research_panel.head(10))
assert len(research_panel) == len(panel)
assert not research_panel.duplicated(["date", "symbol"]).any()
assert (
    research_panel["available_at"].isna()
    | research_panel["available_at"].le(research_panel["date"])
).all()
"""
        ),
        code(
            """
# 输出按股票聚合的数据质量报告；报告的是问题，不是把问题藏起来。
quality_report = quality.copy()
quality_report["可估值日"] = valuation_price.notna().sum()
quality_report["有效收益日"] = valuation_return.notna().sum()
quality_report["基本面覆盖日"] = (
    research_panel.groupby("symbol")["quality_score"].apply(lambda s: s.notna().sum())
)
quality_report["基本面覆盖率"] = (
    research_panel.groupby("symbol")["quality_score"].apply(lambda s: s.notna().mean())
)

report_path = OUTPUT_DIR / "L2_data_quality_report.csv"
quality_report.to_csv(report_path, encoding="utf-8-sig")
display(quality_report)
print("已写入:", report_path)

assert report_path.exists()
assert report_path.stat().st_size > 100
assert quality_report.index.equals(raw_price.columns)
"""
        ),
        md(
            """
## 10. 结果解读

1. `TECH_A` 的上市前空值不应填充，基本面和价格都只能从合法可得时点进入研究。
2. `EV_A` 停牌期间可沿用估值标记，但 `tradable=False`，策略不能虚构成交。
3. `BANK_A` 的接口缺口保留为空，提示修复数据源；插值不是默认答案。
4. 行业去均值必须按“日期 × 行业”做截面计算；样本期累计收益去行业均值不是同一件事。
5. `merge_asof(direction="backward")` 只有在右表时间键是 `available_at` 时才具备 point-in-time 意义。
6. 最终报告保留缺失和覆盖率；“没有 NaN”不是数据质量的同义词。

## 11. 方法边界

- 本实验是确定性模拟数据，只验证工程语义，不代表真实证券或真实缺失机制。
- 行业映射在本实验中固定；生产环境应使用带生效日期的历史行业分类。
- 停牌估值政策、基金净值口径和账户风控规则可能不同，必须单独配置。
- `available_at` 还需结合公告时刻、时区、收盘后发布和下一可成交时点。
- 没有覆盖退市、代码变更、复权事件、跨市场日历、涨跌停与订单排队。
- 数据清洗应保留原始快照、修订版本和审计日志，不能只留下最终宽表。

## 12. 练习

1. 为 `source_gap` 增加一张修复表，用 `merge(validate="one_to_one")` 回补并保留修订来源。
2. 把 `EV_A` 停牌延长至 10 日，观察 `ffill(limit=6)` 后的估值空值。
3. 为行业分类增加 `effective_from/effective_to`，用 point-in-time 方式匹配历史分类。
4. 在研究面板上构造只使用当时可见数据的截面排名，并检查每日可投资资产数。
5. 故意让基本面维表出现重复键，观察 `validate` 如何阻止笛卡尔膨胀。
"""
        ),
    ]
    write_notebook(LABS / "L2_行情清洗与时间对齐.ipynb", cells)


def main():
    build_lesson_37()
    build_lesson_38()
    build_lesson_39()
    build_lesson_40()
    build_lesson_41()
    build_lesson_42()
    build_lab_2()


if __name__ == "__main__":
    main()
