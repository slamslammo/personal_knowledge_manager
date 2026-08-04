#!/usr/bin/env python
"""Generate the P2 notebooks for lessons 37 and 38."""

from __future__ import annotations

from build_first_batch import (
    COMMON_SETUP,
    NOTEBOOKS,
    code,
    md,
    source_note,
    write_notebook,
)


def build_lesson_37():
    cells = [
        md(
            source_note(
                37,
                "MultiIndex、分组与行业中性化",
                "37_youtube-95k-gTun3mg",
            )
        ),
        md(
            """
## 本节量化问题

一篮子股票看似来自多个行业，并不代表资金真正分散。本节用 pandas 面板数据回答四个问题：

1. 如何在“日期 × 股票”宽表与带双层索引的长表之间转换；
2. 如何按行业执行 split–apply–combine；
3. 股票数量占比与持仓资金暴露为什么不是一回事；
4. 如何在每个交易日的截面上去除行业均值，并识别单成员行业的解释陷阱。

### 输入与预期输出

- 小例子：`2 日 × 4 股票 × 2 行业`的确定收益，用于手工核对；
- 完整行情：`daily_prices.csv` 中 6 只虚构股票的模拟日线；
- 输出：长宽表、行业统计、行业组合收益、持仓行业暴露和中性化诊断；
- 验收：键唯一、标签完整、长宽表往返一致、中性化后每个“日期 × 行业”的均值为 0。
"""
        ),
        md(
            """
## 本节数据是什么？

本节数据全部离线运行：

- 小例子由代码直接写出，结果完全确定；
- 完整行情是固定随机种子 `365` 生成的**模拟数据**，包含 756 个工作日和 6 只虚构股票；
- 股票代码、行业、价格、成交量和收益不对应任何真实证券。

视频中的十只真实 A 股收益没有随本地材料提供数据来源、复权方式和成分选择规则，因此这里只保留课程方法，不复用其收益数字作为事实结论。
"""
        ),
        code(COMMON_SETUP),
        md(
            """
## 方法地图

| 方法 | 输入 | 输出 | 本节用途 |
|---|---|---|---|
| `pivot` | 唯一的“日期 × 股票”长表 | 日期为行、股票为列的宽表 | 查看多资产收益矩阵 |
| `stack` | 宽表 | 列标签压入行索引的长 Series | 得到 `date, symbol` MultiIndex |
| `unstack` | MultiIndex Series/DataFrame | 指定索引层展开为列 | 恢复宽表 |
| `groupby().agg()` | 分组后的观测 | 每组一行或多项汇总 | 行业均值、标准差、计数 |
| `groupby().transform()` | 分组后的观测 | 与原数据等长、索引对齐 | 把行业均值放回每一行 |
| `pivot_table` | 可能含重复组合的长表 | 分组聚合后的透视表 | 明确汇总口径 |

`pivot` 不聚合，遇到重复键会报错；`pivot_table` 会聚合，因此必须显式写 `aggfunc`。
"""
        ),
        md(
            """
## 小例子：先展示原始长表

一行表示某个交易日、某只股票的一期简单收益。两个行业各有两只股票，避免单成员行业的中性化残差被机械地压成 0。
"""
        ),
        code(
            r"""
# 构造 2 日 × 4 股票的确定性长表；return 使用小数表示。
mini_panel = pd.DataFrame(
    [
        ("2024-01-02", "ALPHA_1", "行业A", 0.02),
        ("2024-01-02", "ALPHA_2", "行业A", 0.00),
        ("2024-01-02", "BETA_1", "行业B", -0.01),
        ("2024-01-02", "BETA_2", "行业B", 0.01),
        ("2024-01-03", "ALPHA_1", "行业A", 0.01),
        ("2024-01-03", "ALPHA_2", "行业A", 0.03),
        ("2024-01-03", "BETA_1", "行业B", 0.02),
        ("2024-01-03", "BETA_2", "行业B", 0.00),
    ],
    columns=["date", "symbol", "industry", "return"],
)
mini_panel["date"] = pd.to_datetime(mini_panel["date"])

assert mini_panel.shape == (8, 4)
assert not mini_panel.duplicated(["date", "symbol"]).any()
assert mini_panel["industry"].notna().all()
mini_panel
"""
        ),
        md(
            """
## `pivot`：把唯一长表变成收益宽表

- `index="date"`：每行一个交易日；
- `columns="symbol"`：每列一只股票；
- `values="return"`：格子里放简单收益率。

由于每个“日期 × 股票”组合只有一行，`pivot` 不需要也不允许静默聚合。
"""
        ),
        code(
            r"""
# 将确定性长表重排为 2 × 4 的带标签收益矩阵。
mini_wide = mini_panel.pivot(
    index="date",
    columns="symbol",
    values="return",
).sort_index()

expected_wide = np.array(
    [
        [0.02, 0.00, -0.01, 0.01],
        [0.01, 0.03, 0.02, 0.00],
    ]
)
assert mini_wide.shape == (2, 4)
np.testing.assert_allclose(mini_wide.to_numpy(), expected_wide)
mini_wide
"""
        ),
        md(
            """
## `stack` 与 `unstack`：长宽表往返

`stack()` 将股票列压入行索引，得到索引层为 `date, symbol` 的 Series；`unstack("symbol")` 再把股票层展开为列。

有缺失值时，堆叠后的行数可能不是简单的 `日期数 × 股票数`；本例无缺失，因此应有 `2 × 4 = 8` 条观测。重复键、层级名称和排序都要显式检查。
"""
        ),
        code(
            r"""
# 宽表堆叠成长 Series，再按 symbol 层恢复原宽表。
mini_stacked = mini_wide.stack().rename("return")
mini_restored = mini_stacked.unstack("symbol")

assert mini_stacked.index.names == ["date", "symbol"]
assert len(mini_stacked) == 8
pd.testing.assert_frame_equal(mini_restored, mini_wide)

display(
    pd.DataFrame(
        {
            "shape": [
                str(mini_wide.shape),
                str(mini_stacked.shape),
                str(mini_restored.shape),
            ]
        },
        index=["原宽表", "stack 后", "unstack 后"],
    )
)
mini_stacked.to_frame()
"""
        ),
        md(
            """
## `groupby` 的最小确定性例子

视频用三只股票说明 split–apply–combine。这里使用虚构名称和小数收益：

1. split：按行业标签拆成两组；
2. apply：每组计算算术平均；
3. combine：将两个行业结果拼回带标签 Series。

传入 `groupby` 的标签 Series 会按股票索引对齐；如果标签缺失，默认可能被排除，因此先断言标签完整。
"""
        ),
        code(
            r"""
# 两只行业A股票分别涨 2% 和 1%，行业B股票跌 3%。
one_day_move = pd.Series(
    {"ALPHA_1": 0.02, "ALPHA_2": 0.01, "BETA_1": -0.03},
    name="return",
)
one_day_industry = pd.Series(
    {"ALPHA_1": "行业A", "ALPHA_2": "行业A", "BETA_1": "行业B"},
    name="industry",
)

assert one_day_industry.reindex(one_day_move.index).notna().all()
one_day_industry_mean = one_day_move.groupby(one_day_industry).mean()

assert np.isclose(one_day_industry_mean.loc["行业A"], 0.015)
assert np.isclose(one_day_industry_mean.loc["行业B"], -0.03)
one_day_industry_mean.rename("行业平均收益").to_frame()
"""
        ),
        md(
            """
## `agg`：每个行业形成汇总行

`agg` 会压缩行数。下面对小面板的全部“股票日”观测计算均值、样本标准差和数量。

这里的 `sample_std` 混合了日期方向的波动和行业内部股票差异，不能直接称为“行业组合波动率”；真正的行业组合波动要先算每天的行业组合收益，再沿时间求标准差。
"""
        ),
        code(
            r"""
# 对每个行业的全部股票日观测执行多项聚合。
mini_industry_agg = mini_panel.groupby("industry")["return"].agg(
    mean_stock_day_return="mean",
    sample_std="std",
    observations="count",
)

assert mini_industry_agg.loc["行业A", "observations"] == 4
assert mini_industry_agg.loc["行业B", "observations"] == 4
mini_industry_agg.round(6)
"""
        ),
        md(
            """
## `transform`：逐日去除行业均值

严格的简单行业去均值应在**每个日期的截面**执行：

> 中性化值 = 个股值 − 同日同行业均值

`transform("mean")` 返回与原表等长、索引不变的结果，因此可以安全地逐行相减。这里演示的是简单等权去均值；回归残差法还可以同时控制规模、风格和其他暴露。
"""
        ),
        code(
            r"""
# 将同日同行业均值放回每一行，再计算中性化收益。
mini_neutral = mini_panel.copy()
mini_neutral["date_industry_mean"] = mini_neutral.groupby(
    ["date", "industry"]
)["return"].transform("mean")
mini_neutral["neutral_return"] = (
    mini_neutral["return"] - mini_neutral["date_industry_mean"]
)

neutral_check = mini_neutral.groupby(
    ["date", "industry"]
)["neutral_return"].mean()
group_size_check = mini_neutral.groupby(
    ["date", "industry"]
)["symbol"].nunique()

assert mini_neutral["date_industry_mean"].index.equals(mini_panel.index)
assert (group_size_check >= 2).all()
np.testing.assert_allclose(neutral_check.to_numpy(), 0.0, atol=1e-15)
mini_neutral.round(
    {
        "return": 4,
        "date_industry_mean": 4,
        "neutral_return": 4,
    }
)
"""
        ),
        md(
            """
## 股票数量占比不等于资金行业暴露

四只股票在两个行业各有两只，因此按股票数量看是 `50% / 50%`。如果目标权重为 `[50%, 30%, 10%, 10%]`，资金暴露却是 `80% / 20%`。

行业权重 HHI 为各行业资金暴露平方和；本例为 `0.8² + 0.2² = 0.68`。它只是一种集中度诊断，不衡量行业间相关性。
"""
        ),
        code(
            r"""
# 用同一组股票对比数量占比、资金暴露和行业权重 HHI。
mini_symbol_industry = (
    mini_panel[["symbol", "industry"]]
    .drop_duplicates()
    .set_index("symbol")["industry"]
    .sort_index()
)
mini_weights = pd.Series(
    {
        "ALPHA_1": 0.50,
        "ALPHA_2": 0.30,
        "BETA_1": 0.10,
        "BETA_2": 0.10,
    },
    name="target_weight",
).sort_index()

count_share = mini_symbol_industry.value_counts(normalize=True)
capital_exposure = mini_weights.groupby(mini_symbol_industry).sum()
mini_exposure_audit = pd.concat(
    [
        count_share.rename("股票数量占比"),
        capital_exposure.rename("资金行业暴露"),
    ],
    axis=1,
).sort_index()
mini_exposure_hhi = float((capital_exposure**2).sum())

assert np.isclose(mini_weights.sum(), 1.0)
assert np.isclose(capital_exposure.sum(), 1.0)
assert np.isclose(mini_exposure_audit.loc["行业A", "股票数量占比"], 0.5)
assert np.isclose(mini_exposure_audit.loc["行业A", "资金行业暴露"], 0.8)
assert np.isclose(mini_exposure_hhi, 0.68)

display(mini_exposure_audit)
pd.DataFrame(
    {"值": [mini_exposure_hhi]},
    index=["行业权重 HHI"],
)
"""
        ),
        md(
            """
## 回到完整模拟行情：先看原始长表

`daily_prices.csv` 一行是一个交易日、一只虚构股票的一组 OHLCV 行情。先展示首个日期的全部股票，确认行业标签与价格仍在原始长表中。
"""
        ),
        code(
            r"""
# 读取模拟日线，并展示首个日期的 6 只股票。
daily = pd.read_csv(
    DATA_DIR / "daily_prices.csv",
    parse_dates=["date"],
)
first_date = daily["date"].min()
first_date_rows = daily.loc[
    daily["date"].eq(first_date),
    ["date", "symbol", "sector", "adj_close", "volume"],
]

assert daily.shape == (4536, 9)
assert daily["date"].nunique() == 756
assert daily["symbol"].nunique() == 6
first_date_rows
"""
        ),
        md(
            """
## 构造完整收益宽表

先用 `pivot` 得到带日期和股票标签的复权收盘价矩阵，再按每只股票列计算简单日收益。模拟价格无缺失，因此只删除没有前值的第一日。
"""
        ),
        code(
            r"""
# 将原始长表重排为价格宽表，并计算 755 × 6 的日收益宽表。
close = daily.pivot(
    index="date",
    columns="symbol",
    values="adj_close",
).sort_index()
assert close.notna().all().all()

returns_wide = close.pct_change(fill_method=None).iloc[1:]
assert returns_wide.shape == (755, 6)
assert returns_wide.index.is_unique
assert returns_wide.columns.is_unique
returns_wide.head().round(6)
"""
        ),
        md(
            """
## 堆叠收益并对齐行业标签

`stack()` 后一行对应一个“日期 × 股票”收益。行业映射先从原始表去重，并断言每只股票只有一个静态行业标签，再通过股票代码映射到长表。

真实研究不能假设行业永远不变；生产数据应使用带生效日期的 point-in-time 行业映射。
"""
        ),
        code(
            r"""
# 构造收益长表，并按 symbol 对齐静态行业标签。
full_symbol_industry = (
    daily[["symbol", "sector"]]
    .drop_duplicates()
    .set_index("symbol")["sector"]
)
assert full_symbol_industry.index.is_unique

returns_long = (
    returns_wide.stack()
    .rename("return")
    .reset_index()
)
returns_long["industry"] = returns_long["symbol"].map(
    full_symbol_industry
)

assert returns_long.shape[0] == 755 * 6
assert not returns_long.duplicated(["date", "symbol"]).any()
assert returns_long["industry"].notna().all()
returns_long.head(8).round({"return": 6})
"""
        ),
        md(
            """
## `pivot_table`：明确“股票日观测”的聚合口径

下面显式指定 `mean/std/count`。其中标准差来自行业内全部股票日观测，混合了时间变化和股票间差异，因此列名明确写成 `stock_day_std`，不把它冒充行业组合波动率。
"""
        ),
        code(
            r"""
# 用 pivot_table 汇总行业内全部股票日观测，并显式指定聚合函数。
industry_pivot = pd.pivot_table(
    returns_long,
    index="industry",
    values="return",
    aggfunc=["mean", "std", "count"],
)
industry_pivot = industry_pivot.droplevel(1, axis=1).rename(
    columns={
        "mean": "mean_stock_day_return",
        "std": "stock_day_std",
        "count": "stock_day_count",
    }
)

assert industry_pivot["stock_day_count"].sum() == len(returns_long)
industry_pivot.round(6)
"""
        ),
        md(
            """
## 正确计算等权行业组合的日收益和波动

先在每个交易日对行业内股票收益取等权均值，得到“日期 × 行业”日收益表；再沿时间计算样本标准差并按 `√252` 年化。

固定成分和每日等权均值隐含每天恢复等权，忽略交易成本和不可交易约束，只用于方法演示。
"""
        ),
        code(
            r"""
# 先形成每日等权行业组合，再计算时间序列统计量。
sector_daily_return = returns_long.groupby(
    ["date", "industry"]
)["return"].mean().unstack("industry")

sector_asset_count = full_symbol_industry.value_counts()
sector_statistics = pd.DataFrame(
    {
        "mean_daily_return": sector_daily_return.mean(),
        "daily_volatility": sector_daily_return.std(ddof=1),
        "annualized_volatility": (
            sector_daily_return.std(ddof=1) * np.sqrt(252)
        ),
        "asset_count": sector_asset_count,
    }
)

assert sector_daily_return.shape[0] == returns_wide.shape[0]
assert sector_daily_return.notna().all().all()
sector_statistics.round(6)
"""
        ),
        md(
            """
### 行业累计收益的口径

下面复利的是“每日等权、每日恢复权重”的行业组合收益：

> 期末累计收益 = `prod(1 + 每日行业组合收益) - 1`

它不同于“先算每只股票两年累计收益，再取行业算术平均”。两种口径都可以描述样本，但不能混称为同一个行业组合。
"""
        ),
        code(
            r"""
# 复利每日等权行业收益，并用带标签表格展示期末值。
sector_wealth = (1 + sector_daily_return).cumprod()
sector_terminal_return = sector_wealth.iloc[-1] - 1

assert (sector_wealth > 0).all().all()
sector_terminal_return.rename(
    "每日等权再平衡行业组合期末累计收益"
).to_frame().round(4)
"""
        ),
        md(
            """
## 完整行情的行业去均值与单成员陷阱

完整模拟数据中只有金融行业有两只股票，其他行业都只有一只。`transform("mean")` 仍能让每组残差均值为 0，但单成员行业的残差必然为 0，只是因为“自己减自己”。

因此，零残差不能解释为该股票“完全靠行业上涨”，而应标记为没有足够同行可比较。
"""
        ),
        code(
            r"""
# 对每个日期、每个行业执行简单等权去均值，并诊断行业样本数。
full_neutral = returns_long.copy()
full_neutral["industry_mean_return"] = full_neutral.groupby(
    ["date", "industry"]
)["return"].transform("mean")
full_neutral["neutral_return"] = (
    full_neutral["return"] - full_neutral["industry_mean_return"]
)

full_neutral_check = full_neutral.groupby(
    ["date", "industry"]
)["neutral_return"].mean()
np.testing.assert_allclose(
    full_neutral_check.to_numpy(),
    0.0,
    atol=1e-15,
)

neutral_diagnostic = pd.DataFrame(
    {
        "asset_count": sector_asset_count,
        "mean_absolute_neutral_return": (
            full_neutral.assign(
                absolute_neutral_return=full_neutral[
                    "neutral_return"
                ].abs()
            )
            .groupby("industry")["absolute_neutral_return"]
            .mean()
        ),
    }
)
neutral_diagnostic["singleton_group"] = (
    neutral_diagnostic["asset_count"] == 1
)
neutral_diagnostic.round(6)
"""
        ),
        md(
            """
## 完整模拟持仓的行业暴露

下面给 6 只虚构股票指定一组教学目标权重。行业股票数量占比回答“有几只”，资金暴露回答“投了多少钱”；两者必须分列展示。
"""
        ),
        code(
            r"""
# 用确定性目标权重计算资金行业暴露和行业权重 HHI。
target_weights = pd.Series(
    {
        "BANK_A": 0.25,
        "INSURE_A": 0.15,
        "EV_A": 0.30,
        "POWER_A": 0.10,
        "ENERGY_A": 0.10,
        "TECH_A": 0.10,
    },
    name="target_weight",
)
assert set(target_weights.index) == set(full_symbol_industry.index)
assert np.isclose(target_weights.sum(), 1.0)

full_count_share = full_symbol_industry.value_counts(normalize=True)
full_capital_exposure = target_weights.groupby(
    full_symbol_industry
).sum()
full_exposure_audit = pd.concat(
    [
        full_count_share.rename("股票数量占比"),
        full_capital_exposure.rename("资金行业暴露"),
    ],
    axis=1,
).sort_index()
full_exposure_hhi = float((full_capital_exposure**2).sum())

assert np.isclose(full_capital_exposure.sum(), 1.0)
assert np.isclose(full_exposure_hhi, 0.28)
display(full_exposure_audit.round(4))
pd.DataFrame(
    {"值": [full_exposure_hhi]},
    index=["行业权重 HHI"],
)
"""
        ),
        md(
            """
## 可复用结论

1. 先用 pandas 标签保证日期、股票和行业对齐，再做分组统计；
2. `agg` 用于汇总，`transform` 用于把组统计量放回原行；
3. `stack/unstack` 前后都要检查层级名、唯一键、缺失组合和 shape；
4. 行业数量集中度、资金暴露和收益相关性是不同诊断；
5. 中性化应按每个历史时点执行，并保存中性化前后分布和暴露检查。

## 方法边界

- 视频的真实股票收益缺少可复现来源，本 Notebook 不据此作市场结论；
- 当前行业分类不能回填历史，必须使用带生效日期的行业映射；
- `groupby` 默认可能排除缺失行业标签，计算前必须断言标签完整；
- 单成员和小样本行业无法稳定估计同行基准；
- 等权行业均值不等于市值加权指数；
- 简单去行业均值不会自动消除规模、价值、流动性等其他风格暴露；
- 若策略目标就是行业轮动，中性化可能删除目标信号；
- 全样本统计是描述性结果，不能作为同一期间的无未来信息选股证据。

## 练习

1. 把 `mini_weights` 改为四只股票等权，比较数量占比、资金暴露和 HHI。
2. 删除 `mini_panel` 的一条记录，观察 `stack` 行数和 `unstack` 后的缺失位置。
3. 给小例子增加第三个只有一只股票的行业，解释为什么其中性化残差恒为 0。
4. 将行业均值改为持仓权重加权均值，并验证每组的加权残差均值为 0。
"""
        ),
    ]
    write_notebook(
        NOTEBOOKS / "37_MultiIndex分组与行业中性化.ipynb",
        cells,
    )


def build_lesson_38():
    cells = [
        md(
            source_note(
                38,
                "缺失值处理与可交易性",
                "38_youtube-6z6aaxjGZcA",
            )
        ),
        md(
            """
## 本节量化问题

行情中的 `NaN` 可能代表停牌、未上市、退市、交易日历不一致或数据源故障。它们在表格里都显示为空，但回测规则完全不同。

本节重点不是“把空格填满”，而是回答：

1. 缺失发生在哪里、持续多久、原因是什么；
2. `ffill`、`bfill`、普通插值和时间插值分别使用什么信息；
3. 为什么估值价格、原始价格和可交易状态必须分开；
4. 如何按数据真正的公布时间构造无未来信息特征。

### 输入与预期输出

- 小例子：确定 Series，用于核对三种填补和时间插值；
- 完整行情：从模拟日线中截取 `484 日 × 4 股票`，人工注入连续 12 日教学缺口；
- 输出：缺失审计、完整样本损失、停牌估值/交易状态表、point-in-time 宏观对齐；
- 验收：缺失位置、填补结果、删除行数、复牌跳空和公布日前不可用状态均有断言。
"""
        ),
        md(
            """
## 本节数据是什么？

`daily_prices.csv` 是固定随机种子生成的模拟行情，不是真实证券数据。连续 12 日缺失由本 Notebook **人工注入**，只能称为“教学缺口”，不能冒充真实停牌。

后面的停牌和宏观发布日期例子也由代码直接构造，用于稳定演示业务规则，不评价任何真实公司、市场或数据供应商。
"""
        ),
        code(COMMON_SETUP),
        md(
            """
## 小例子：缺失值不能用等号判断

IEEE 浮点 `NaN` 不等于自身，因此 `value == np.nan` 不是可靠判断。pandas 应使用 `pd.isna()` / `pd.notna()`；它们也能识别 `None`、`NaT` 和 `pd.NA`。

对 Series 使用 `.isna()` 会得到同 shape 布尔掩码，`.sum()` 才是缺失数量。
"""
        ),
        code(
            r"""
# 构造含 3 个缺失位置的确定 Series，并展示缺失掩码。
missing_demo = pd.Series(
    [10.0, np.nan, np.nan, 13.0, np.nan, 15.0],
    name="原始值",
)
missing_mask = missing_demo.isna()

assert np.nan != np.nan
assert pd.isna(np.nan)
assert missing_demo.isna().sum() == 3
assert missing_mask.tolist() == [
    False, True, True, False, True, False
]

pd.DataFrame(
    {
        "原始值": missing_demo,
        "isna": missing_mask,
    }
)
"""
        ),
        md(
            """
## 同一缺口的三种处理

| 方法 | 信息来源 | 本例含义 |
|---|---|---|
| `ffill()` | 最近一个过去有效值 | `[10,10,10,13,13,15]` |
| `bfill()` | 下一个未来有效值 | `[10,13,13,13,15,15]` |
| `interpolate()` | 缺口两侧端点 | `[10,11,12,13,14,15]` |

`ffill` 没有显式读取未来，但可能制造陈旧价格；`bfill` 和双侧插值若用于缺口时点的交易信号，会直接使用未来信息。
"""
        ),
        code(
            r"""
# 并排计算三种方法，并用确定数组核对每个位置。
filled_demo = pd.DataFrame(
    {
        "原始值": missing_demo,
        "ffill": missing_demo.ffill(),
        "bfill": missing_demo.bfill(),
        "linear_interpolate": missing_demo.interpolate(),
    }
)

np.testing.assert_allclose(
    filled_demo["ffill"].to_numpy(),
    [10, 10, 10, 13, 13, 15],
)
np.testing.assert_allclose(
    filled_demo["bfill"].to_numpy(),
    [10, 13, 13, 13, 15, 15],
)
np.testing.assert_allclose(
    filled_demo["linear_interpolate"].to_numpy(),
    [10, 11, 12, 13, 14, 15],
)
filled_demo
"""
        ),
        md(
            """
## 普通插值与按时间插值

普通 `interpolate()` 把相邻行位置视为等距；`interpolate(method="time")` 按 DatetimeIndex 的实际时间距离分配变化。

下面的日期间隔为 1、3、3、1 天，因此两种结果不同。时间插值前应保证索引单调递增且唯一。两种方法都使用最后的 `108`，所以都不适合作为缺口期间的实时交易信号。
"""
        ),
        code(
            r"""
# 在不等间隔日期上对比按位置和按实际时间插值。
time_demo = pd.Series(
    [100.0, np.nan, np.nan, np.nan, 108.0],
    index=pd.to_datetime(
        [
            "2024-01-01",
            "2024-01-02",
            "2024-01-05",
            "2024-01-08",
            "2024-01-09",
        ]
    ),
    name="原始值",
)
assert time_demo.index.is_monotonic_increasing
assert time_demo.index.is_unique

position_interpolation = time_demo.interpolate()
time_interpolation = time_demo.interpolate(method="time")

np.testing.assert_allclose(
    position_interpolation.to_numpy(),
    [100, 102, 104, 106, 108],
)
np.testing.assert_allclose(
    time_interpolation.to_numpy(),
    [100, 101, 104, 107, 108],
)
pd.DataFrame(
    {
        "原始值": time_demo,
        "按位置插值": position_interpolation,
        "按时间插值": time_interpolation,
    }
)
"""
        ),
        md(
            """
## 回到完整模拟行情：先看原始数据

先读取原始模拟长表并展示首日记录，再重排成价格宽表。此时尚未注入缺失。
"""
        ),
        code(
            r"""
# 读取模拟行情，并展示首个日期的全部虚构股票。
daily = pd.read_csv(
    DATA_DIR / "daily_prices.csv",
    parse_dates=["date"],
)
first_date = daily["date"].min()
first_date_rows = daily.loc[
    daily["date"].eq(first_date),
    ["date", "symbol", "sector", "adj_close", "volume"],
]

assert daily.shape == (4536, 9)
assert daily["date"].nunique() == 756
assert daily["symbol"].nunique() == 6
first_date_rows
"""
        ),
        md(
            """
## 构造 `484 日 × 4 股票`完整价格面板

先由原始表生成无缺失价格矩阵，再选前 484 个交易日和 4 只股票。这个副本是注入教学缺口前的基准。
"""
        ),
        code(
            r"""
# 从完整价格矩阵中确定性选择 484 日和 4 只虚构股票。
close_full = daily.pivot(
    index="date",
    columns="symbol",
    values="adj_close",
).sort_index()
selected_symbols = [
    "BANK_A",
    "ENERGY_A",
    "EV_A",
    "INSURE_A",
]
complete_prices = close_full.loc[
    :,
    selected_symbols,
].iloc[:484].copy()

assert complete_prices.shape == (484, 4)
assert complete_prices.notna().all().all()
complete_prices.head()
"""
        ),
        md(
            """
## 人工注入连续 12 日缺口并审计

这里只把 `EV_A` 的连续 12 日设为 `NaN`。它没有真实业务原因，因此命名为 `simulated_gap`，不能直接解释成停牌。

除了总缺失数，还要报告缺失率和最长连续缺失；零星接口错误与连续停牌在业务上不同。
"""
        ),
        code(
            r"""
# 在完整副本中注入一个连续 12 日教学缺口。
raw_prices = complete_prices.copy()
gap_symbol = "EV_A"
gap_dates = raw_prices.index[200:212]
raw_prices.loc[gap_dates, gap_symbol] = np.nan

def longest_missing_run(series):
    missing = series.isna()
    if not missing.any():
        return 0
    run_id = (~missing).cumsum()
    return int(missing.groupby(run_id).sum().max())

missing_audit = pd.DataFrame(
    {
        "missing_count": raw_prices.isna().sum(),
        "missing_rate": raw_prices.isna().mean(),
        "longest_missing_run": [
            longest_missing_run(raw_prices[column])
            for column in raw_prices.columns
        ],
    }
)

assert raw_prices.shape == (484, 4)
assert raw_prices.isna().sum().sum() == 12
assert missing_audit.loc[gap_symbol, "missing_count"] == 12
assert missing_audit.loc[gap_symbol, "longest_missing_run"] == 12
missing_audit
"""
        ),
        md(
            """
## 缺失热力图：红色只是缺失位置，不是程序告警

布尔矩阵中 `True` 表示缺失。热力图用于快速定位缺口集中在哪只资产、哪段时间；它不能判断缺失原因。
"""
        ),
        code(
            r"""
# 将缺失布尔矩阵画成资产 × 日期热力图。
fig, ax = plt.subplots(figsize=(10, 2.8))
sns.heatmap(
    raw_prices.isna().T,
    ax=ax,
    cmap="Reds",
    vmin=0,
    vmax=1,
    cbar=False,
    xticklabels=False,
    yticklabels=True,
)
ax.set_title("模拟价格缺失位置（红色 = NaN）")
ax.set_xlabel("交易日")
ax.set_ylabel("股票")
fig.tight_layout()
fig.savefig(
    OUTPUT_DIR / "38_missing_map.png",
    dpi=160,
    bbox_inches="tight",
)
plt.show()
"""
        ),
        md(
            """
## `dropna()` 的整行连累效应

`raw_prices.dropna()` 默认是 `axis=0, how="any"`：任意一列缺失就删除整行。

本例只有 `EV_A` 缺 12 日，但完整样本会从 484 日减少到 472 日，其他三只股票在这 12 日的有效观测也一起被删除。真实研究应根据目标资产集合显式使用 `subset`、`how` 或 `thresh`，并报告损失。
"""
        ),
        code(
            r"""
# 比较完整样本删除前后，每只股票保留下来的有效观测数。
complete_case_prices = raw_prices.dropna(
    axis=0,
    how="any",
)
dropna_impact = pd.DataFrame(
    {
        "dropna 前有效观测": raw_prices.notna().sum(),
        "dropna 后有效观测": complete_case_prices.notna().sum(),
    }
)
dropna_impact["被连带删除"] = (
    dropna_impact["dropna 前有效观测"]
    - dropna_impact["dropna 后有效观测"]
)

other_symbols = [
    symbol for symbol in selected_symbols
    if symbol != gap_symbol
]
assert complete_case_prices.shape == (472, 4)
assert raw_prices.loc[gap_dates, other_symbols].notna().all().all()
assert (dropna_impact.loc[other_symbols, "被连带删除"] == 12).all()
dropna_impact
"""
        ),
        md(
            """
## 停牌例子：估值价格不等于可交易价格

下面单独构造一个确定性停牌例子：

- `raw_price` 保存真实观察值，不覆盖；
- `valuation_price` 用旧价延续持仓估值；
- `tradable` 决定能否下单；
- `missing_reason` 记录停牌原因；
- 复牌价 `87.4` 相对最后有效价 `100` 的跳空为 `-12.6%`。

`ffill` 可以用于演示估值政策，但停牌日绝不能据填充值模拟成交。
"""
        ),
        code(
            r"""
# 分列保存原始报价、估值价、收益、可交易状态和缺失原因。
suspension_dates = pd.date_range(
    "2024-01-02",
    periods=5,
    freq="B",
)
suspension_raw_price = pd.Series(
    [100.0, np.nan, np.nan, np.nan, 87.4],
    index=suspension_dates,
    name="raw_price",
)
suspension_tradable = suspension_raw_price.notna()
suspension_valuation_price = suspension_raw_price.ffill()
suspension_valuation_return = (
    suspension_valuation_price.pct_change(fill_method=None)
)
observed_quote_return = (
    suspension_raw_price.dropna()
    .pct_change(fill_method=None)
    .reindex(suspension_dates)
)
suspension_reason = pd.Series(
    [
        "observed",
        "suspension",
        "suspension",
        "suspension",
        "observed",
    ],
    index=suspension_dates,
    name="missing_reason",
)

suspension_audit = pd.concat(
    [
        suspension_raw_price,
        suspension_valuation_price.rename("valuation_price"),
        suspension_valuation_return.rename("valuation_return"),
        observed_quote_return.rename("observed_quote_return"),
        suspension_tradable.rename("tradable"),
        suspension_reason,
    ],
    axis=1,
)

assert not suspension_tradable.iloc[1:4].any()
np.testing.assert_allclose(
    suspension_valuation_return.iloc[1:4],
    0.0,
)
assert np.isclose(suspension_valuation_return.iloc[-1], -0.126)
assert np.isclose(observed_quote_return.iloc[-1], -0.126)
suspension_audit
"""
        ),
        md(
            """
### 为什么不能只在原始空值价格上直接算收益？

`raw_price.pct_change(fill_method=None)` 在复牌日看到的前一行仍是 `NaN`，因此可能无法得到跨停牌跳空。可选的透明做法是：

1. 用估值序列计算持仓价值变化，同时保留 `tradable=False`；
2. 对非空真实报价序列计算相邻有效报价收益，再把结果对齐到复牌日。

两种做法都必须保留原始报价，不能把填充值冒充真实成交价。
"""
        ),
        md(
            """
## 未上市与停牌必须使用不同状态

未上市前没有合法市场价格，也不属于当时投资池；停牌则是资产已经上市但暂时不可交易。二者不能只靠同一个 `NaN` 猜测。
"""
        ),
        code(
            r"""
# 同样是 NaN，用 listed/tradable/reason 明确区分业务状态。
listing_dates = pd.date_range(
    "2024-02-01",
    periods=4,
    freq="B",
)
listing_example = pd.DataFrame(
    {
        "raw_price": [np.nan, np.nan, 50.0, 51.0],
        "listed": [False, False, True, True],
        "tradable": [False, False, True, True],
        "missing_reason": [
            "pre_listing",
            "pre_listing",
            "observed",
            "observed",
        ],
    },
    index=listing_dates,
)

assert listing_example.loc[
    ~listing_example["listed"],
    "raw_price",
].isna().all()
assert not listing_example.loc[
    ~listing_example["listed"],
    "tradable",
].any()
listing_example
"""
        ),
        md(
            """
## 宏观数据必须从公布日开始可用

月度指标可以在**公布以后**向后延续到下一次公布，但不能从所属月份月初或报告期末提前填入。

下面假设 CPI 同比在 `2024-02-15` 首次公布为 `0.7`，在 `2024-03-15` 公布新值 `0.8`。`2024-02-14` 仍必须为空。
"""
        ),
        code(
            r"""
# 按 available_at 对齐低频宏观数据，再沿策略交易日向后填充。
macro_releases = pd.Series(
    {
        pd.Timestamp("2024-02-15"): 0.7,
        pd.Timestamp("2024-03-15"): 0.8,
    },
    name="cpi_yoy",
)
strategy_calendar = pd.bdate_range(
    "2024-02-12",
    "2024-03-20",
)
daily_macro = macro_releases.reindex(
    strategy_calendar
).ffill()

assert pd.isna(daily_macro.loc["2024-02-14"])
assert daily_macro.loc["2024-02-15"] == 0.7
assert daily_macro.loc["2024-03-14"] == 0.7
assert daily_macro.loc["2024-03-15"] == 0.8
daily_macro.loc[
    [
        "2024-02-14",
        "2024-02-15",
        "2024-03-14",
        "2024-03-15",
    ]
].to_frame()
"""
        ),
        md(
            """
## 可复用结论

1. 先审计缺失位置、比例、最长连续区间和业务原因，再选择处理方式；
2. 原始值、清洗值、缺失原因和可交易状态分列保存；
3. `ffill` 只说明没有显式读取未来，不代表价格可交易或风险没有失真；
4. `bfill` 和双侧插值若用于历史时点信号，会使用未来信息；
5. 财务和宏观特征必须按 `available_at` 与修订版本做 point-in-time 对齐。

## 方法边界

- 人工注入缺口不代表真实停牌，只用于验证代码；
- `ffill` 可能制造零收益和陈旧价格，应记录最大陈旧天数或使用 `limit`；
- 插值价格不是实际市场路径，不可用于模拟缺口期间成交；
- 停牌期间订单可能无法成交，复牌还需考虑涨跌停、流动性和成交规则；
- 未上市、退市、跨市场日历和代码变更必须分别处理；
- 对全样本使用均值填补、插值或标准化也可能引入未来信息；
- 静默删除长期停牌或退市股票会产生幸存者偏差；
- 公司行动和复权错误不能当作普通缺失值填补。

## 练习

1. 为 `raw_prices` 增加第二段零星缺失，比较总缺失数和最长连续缺失。
2. 使用 `dropna(subset=["EV_A"])`，解释它与四列完整样本的区别。
3. 给估值 `ffill` 设置 `limit=2`，观察长期缺口仍保留为空的位置。
4. 将 CPI 的值错误地放到月初并向后填充，指出哪些日期出现未来信息。
"""
        ),
    ]
    write_notebook(
        NOTEBOOKS / "38_缺失值处理与可交易性.ipynb",
        cells,
    )


def main():
    build_lesson_37()
    build_lesson_38()


if __name__ == "__main__":
    main()
