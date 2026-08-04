#!/usr/bin/env python
"""Build P2 lesson notebooks 39–40: point-in-time joins and honest charts."""

from __future__ import annotations

from build_first_batch import (
    COMMON_SETUP,
    NOTEBOOKS,
    code,
    md,
    write_notebook,
)


def source_note(number: int, title: str, package: str) -> str:
    return f"""
# 第 {number} 课｜{title}

本 Notebook 对应「365 天量化金融」第 {number} 课。课程方法来自本地完整视频、课件截图和本地 Whisper 口播整理；这里将课程 API 重建为可离线执行、可核对的量化教学实现，并补充数据契约、断言与方法边界。

- 图文口播：`/Users/mojiawen/Documents/学习资料归档/_暂存/pam-video-captures/365-days-quant-finance/{package}/index.html`
- 环境：`pkm-quant`
- 数据：固定随机种子生成的离线模拟行情与本课内构造的模拟财报（**均非真实证券数据**）
- 状态：可运行学习稿；不代表策略收益承诺

> **来源边界**：课程材料没有提供可独立核验的完整 Python 源码和真实行情快照。本 Notebook 复现课程方法，不把口播中的股票、数值或图形当作离线验收基准。
"""


def build_lesson_39():
    cells = [
        md(
            source_note(
                39,
                "合并行情与财报：point-in-time 数据",
                "39_youtube-iksBIxLykTU",
            )
        ),
        md(
            """
## 1. 本节量化问题

行情通常是高频长表，行业是低频维表，财报又按季度发布。研究任务不是“让两张表成功拼起来”，而是让每个交易时点只看到当时已经公开且可以使用的信息。

本节按由小到大的顺序回答四个问题：

1. `pd.concat` 沿行、沿列分别改变什么；
2. `merge` 的 `inner/outer/left` 如何决定保留哪些精确键；
3. `validate` 和 `indicator` 如何把多对多膨胀、未匹配键变成可检查结果；
4. `merge_asof(direction="backward")` 如何构造 point-in-time 财报快照，并证明使用 `report_period` 会造成未来数据泄漏。

核心原则：

> **财报属于哪个季度，不等于市场何时知道这份财报。**
"""
        ),
        md(
            """
## 2. 输入、输出与验收

**输入**

- `daily_prices.csv`：固定种子生成的 6 只虚构资产日线；
- 本 Notebook 内构造的模拟行业维表和模拟财报发布表；
- 所有 ROE 均为十进制的累计年初至今口径，例如 `0.08 = 8%`。

**输出**

- 行、列拼接的带标签小表；
- 精确键连接的匹配审计；
- 每个 `(trade_at, symbol)` 对应的最近已知财报；
- 发布前后可直接核对的阶梯式 ROE 快照。

**验收**

- 行情联合键唯一，行业维表每个 `symbol` 至多一行；
- point-in-time 合并不改变行情行数；
- 每个已匹配的 `available_at <= trade_at`；
- 公告在收盘后发布时，当日 15:00 快照看不到，下一可用时点才看到；
- 原始 ROE 排名只作为表连接演示，不冒充策略回测。
"""
        ),
        code(COMMON_SETUP),
        md(
            """
## 3. `concat(axis=0)`：沿行追加同结构记录

先用两只虚构资产的确定性小表观察默认行为。两张表字段相同，`axis=0` 沿行轴追加：

- 原来每张表 2 行，拼接后应有 4 行；
- `ignore_index=True` 丢弃各自的旧行号，重新生成 `0..3`；
- 它不检查业务主键，真实数据拼接后仍要检查 `(date, symbol)` 是否重复。
"""
        ),
        code(
            r"""
# 两张表字段完全相同；每一行仍代表“某日、某只资产的一条价格记录”。
alpha_rows = pd.DataFrame(
    {
        "date": pd.to_datetime(["2025-01-02", "2025-01-03"]),
        "symbol": ["ALPHA", "ALPHA"],
        "close": [100.0, 101.0],  # ALPHA 两日收盘价
    }
)
beta_rows = pd.DataFrame(
    {
        "date": pd.to_datetime(["2025-01-02", "2025-01-03"]),
        "symbol": ["BETA", "BETA"],
        "close": [50.0, 49.5],    # BETA 两日收盘价
    }
)

# axis=0 沿行追加；ignore_index=True 重新生成连续行号。
row_concat = pd.concat(
    [alpha_rows, beta_rows],
    axis=0,
    ignore_index=True,
)

assert row_concat.shape == (4, 3)
assert row_concat.index.tolist() == [0, 1, 2, 3]
assert not row_concat.duplicated(["date", "symbol"]).any()
print("沿行拼接后 shape =", row_concat.shape, "含义：4 条价格记录 × 3 个字段")
row_concat
"""
        ),
        md(
            """
## 4. `concat(axis=1)`：按标签并排放置列

沿列拼接不是按“第几行”硬贴，而是先对齐索引标签。下面两只资产的日期范围错开一天：

- 结果索引取两个日期集合的并集，共 4 天；
- `ALPHA` 在 1 月 6 日没有记录，`BETA` 在 1 月 2 日没有记录；
- 两个缺口显示为 `NaN`，不能在没有业务依据时直接填成 0。
"""
        ),
        code(
            r"""
# 两个 Series 的日期标签并不完全相同。
alpha_close = pd.Series(
    [100.0, 101.0, 102.0],
    index=pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"]),
    name="ALPHA",
)
beta_close = pd.Series(
    [49.5, 50.5, 51.0],
    index=pd.to_datetime(["2025-01-03", "2025-01-06", "2025-01-07"]),
    name="BETA",
)

# axis=1 新增列；Pandas 先按日期标签并集对齐。
column_concat = pd.concat(
    [alpha_close, beta_close],
    axis=1,
)

assert column_concat.shape == (4, 2)
assert column_concat.isna().sum().to_dict() == {"ALPHA": 1, "BETA": 1}
print("沿列拼接后 shape =", column_concat.shape, "含义：日期并集 × 两只资产")
column_concat
"""
        ),
        md(
            """
## 5. `merge`：用精确业务键连接事实表和维表

`merge` 与 `concat` 的关键差别是显式声明连接键。下面价格表有 `ALPHA/BETA/GAMMA`，行业维表有 `ALPHA/BETA/DELTA`。

| `how` | 保留的键 | 本例用途 |
|---|---|---|
| `inner` | 两边交集 | 只看两表都存在的资产 |
| `left` | 左表全部键 | 给行情补充行业且不丢行情 |
| `outer` | 两边并集 | 审计双方各自缺失的键 |

`indicator=True` 生成 `_merge`：`both/left_only/right_only` 分别表示匹配、只在左表、只在右表。它比只看 `NaN` 更准确，因为原始字段本身也可能合法缺失。
"""
        ),
        code(
            r"""
# 价格事实表包含 3 只资产；行业维表故意缺 GAMMA、额外含 DELTA。
price_today = pd.DataFrame(
    {
        "symbol": ["ALPHA", "BETA", "GAMMA"],
        "close": [101.0, 49.5, 80.0],
    }
)
sector_dimension = pd.DataFrame(
    {
        "symbol": ["ALPHA", "BETA", "DELTA"],
        "sector": ["科技", "金融", "公用事业"],
    }
)

# validate="many_to_one" 声明：左侧可有多条行情，右侧每个 symbol 只能有一行。
inner_join = price_today.merge(
    sector_dimension,
    on="symbol",
    how="inner",
    validate="many_to_one",
)
left_join = price_today.merge(
    sector_dimension,
    on="symbol",
    how="left",
    validate="many_to_one",
    indicator=True,
)
outer_join = price_today.merge(
    sector_dimension,
    on="symbol",
    how="outer",
    validate="many_to_one",
    indicator=True,
)

assert set(inner_join["symbol"]) == {"ALPHA", "BETA"}
assert len(left_join) == len(price_today)
assert left_join["_merge"].eq("left_only").sum() == 1
assert set(outer_join.loc[outer_join["_merge"].eq("right_only"), "symbol"]) == {"DELTA"}

print("inner 行数 =", len(inner_join), "；left 行数 =", len(left_join), "；outer 行数 =", len(outer_join))
outer_join.sort_values("symbol").reset_index(drop=True)
"""
        ),
        md(
            """
## 6. `validate`：在结果膨胀前拦截错误基数

如果行业维表中同一资产出现两行，普通 `merge` 会复制左表记录。代码仍能运行，但金额、收益和样本数都可能被重复计算。

下面故意制造重复维度键，并在 `try/except` 中捕获预期的 `MergeError`。Notebook 不产生红色报错，同时明确展示保护机制确实生效。
"""
        ),
        code(
            r"""
# ALPHA 在右表出现两次，不再满足 many_to_one。
duplicated_dimension = pd.concat(
    [sector_dimension, sector_dimension.iloc[[0]]],
    ignore_index=True,
)

try:
    price_today.merge(
        duplicated_dimension,
        on="symbol",
        how="left",
        validate="many_to_one",
    )
except pd.errors.MergeError as error:
    print("预期拦截：行业维表的 symbol 不唯一。")
    print("异常类型：", type(error).__name__)
else:
    raise AssertionError("validate 未拦截重复维度键")

assert duplicated_dimension["symbol"].duplicated().any()
"""
        ),
        md(
            """
## 7. point-in-time 的三个时间字段

财报连接至少要区分：

| 字段 | 含义 | 能否直接作为交易时点连接键 |
|---|---|---|
| `report_period` | 财报覆盖期末，例如 2024-12-31 | **不能**；此时报告通常尚未发布 |
| `published_at` | 发布源记录的公告时间 | 还要结合时区、收盘和处理延迟 |
| `available_at` | 研究系统确认可使用的最早时点 | 可以；但生成规则必须可追溯 |

本小例子把交易快照固定在 15:00。`ALPHA` 的年报在 1 月 3 日 18:00 发布，设定为 1 月 6 日 09:30 可用；因此 1 月 3 日收盘快照只能看到旧报告。

所有名称、价格、ROE 和时间均为教学模拟数据。
"""
        ),
        code(
            r"""
# 交易事实表：3 个交易时点 × 2 只虚构资产。
trade_demo = pd.DataFrame(
    {
        "trade_at": pd.to_datetime(
            [
                "2025-01-03 15:00", "2025-01-03 15:00",
                "2025-01-06 15:00", "2025-01-06 15:00",
                "2025-01-08 15:00", "2025-01-08 15:00",
            ]
        ),
        "symbol": ["ALPHA", "BETA", "ALPHA", "BETA", "ALPHA", "BETA"],
        "close": [101.0, 49.5, 102.0, 50.5, 103.0, 51.0],
    }
)

# 财报表：roe_ytd 是十进制累计 ROE；0.10 表示 10%。
fundamental_demo = pd.DataFrame(
    {
        "symbol": ["ALPHA", "BETA", "ALPHA", "BETA"],
        "report_period": pd.to_datetime(
            ["2024-09-30", "2024-09-30", "2024-12-31", "2024-12-31"]
        ),
        "published_at": pd.to_datetime(
            [
                "2024-11-01 18:00",
                "2024-11-01 18:00",
                "2025-01-03 18:00",  # 当日 15:00 之后发布
                "2025-01-07 18:00",
            ]
        ),
        "available_at": pd.to_datetime(
            [
                "2024-11-04 09:30",
                "2024-11-04 09:30",
                "2025-01-06 09:30",  # ALPHA 新报告从这里开始可见
                "2025-01-08 09:30",  # BETA 新报告从这里开始可见
            ]
        ),
        "roe_ytd": [0.10, 0.08, 0.12, 0.09],
    }
)

assert not trade_demo.duplicated(["trade_at", "symbol"]).any()
assert not fundamental_demo.duplicated(["available_at", "symbol"]).any()
assert fundamental_demo["published_at"].le(fundamental_demo["available_at"]).all()
fundamental_demo
"""
        ),
        md(
            """
## 8. `merge_asof`：只向后找最近已知记录

关键参数逐一对应业务约束：

- `left_on="trade_at"`：每个行情快照的决策时点；
- `right_on="available_at"`：财报真正可使用的时点；
- `by="symbol"`：只允许同一资产内部匹配；
- `direction="backward"`：只找不晚于交易时点的最近记录；
- `tolerance=180D`：超过 180 天的财报视为陈旧并返回缺失；
- `allow_exact_matches=True`：恰好在可用时点的记录可以使用。

`merge_asof` 要求连接时间全局升序，因此这里先按“时间、资产”排序。若先按资产分组再让时间从头开始，许多 Pandas 版本会拒绝执行。
"""
        ),
        code(
            r"""
# merge_asof 的 on 键必须全局升序；symbol 作为同一时点的稳定次序。
trade_demo_sorted = trade_demo.sort_values(
    ["trade_at", "symbol"]
).reset_index(drop=True)
fundamental_demo_sorted = fundamental_demo.sort_values(
    ["available_at", "symbol"]
).reset_index(drop=True)

pit_demo = pd.merge_asof(
    trade_demo_sorted,
    fundamental_demo_sorted,
    left_on="trade_at",
    right_on="available_at",
    by="symbol",
    direction="backward",
    tolerance=pd.Timedelta("180D"),
    allow_exact_matches=True,
)

# 预期阶梯：
# ALPHA: 10% -> 12% -> 12%
# BETA :  8% ->  8% ->  9%
observed_roe = (
    pit_demo.pivot(
        index="trade_at",
        columns="symbol",
        values="roe_ytd",
    )
    .sort_index()
    [["ALPHA", "BETA"]]
)
expected_roe = np.array(
    [
        [0.10, 0.08],
        [0.12, 0.08],
        [0.12, 0.09],
    ]
)

np.testing.assert_allclose(observed_roe.to_numpy(), expected_roe)
assert len(pit_demo) == len(trade_demo)
assert pit_demo["available_at"].le(pit_demo["trade_at"]).all()
print("point-in-time 校验通过：发布前看旧值，available_at 到达后才切换。")
observed_roe.style.format("{:.1%}")
"""
        ),
        md(
            """
## 9. 反例：用 `report_period` 会把未来财报带回过去

下面只替换右侧时间键，错误地按财报期末向后找。2024 年报的 `report_period=2024-12-31`，所以 2025-01-03 的交易快照会匹配到尚未发布的年报。

这正是 look-ahead bias：数值、shape、排序都可能看起来正常，但当时的市场参与者并不知道这份数据。
"""
        ),
        code(
            r"""
# 错误示范：把财报覆盖期末当成市场可知时点。
leaky_demo = pd.merge_asof(
    trade_demo.sort_values(["trade_at", "symbol"]),
    fundamental_demo.sort_values(["report_period", "symbol"]),
    left_on="trade_at",
    right_on="report_period",
    by="symbol",
    direction="backward",
    tolerance=pd.Timedelta("180D"),
)

leak_audit = (
    pit_demo[["trade_at", "symbol", "roe_ytd"]]
    .rename(columns={"roe_ytd": "正确：按 available_at"})
    .merge(
        leaky_demo[["trade_at", "symbol", "roe_ytd"]].rename(
            columns={"roe_ytd": "错误：按 report_period"}
        ),
        on=["trade_at", "symbol"],
        how="inner",
        validate="one_to_one",
    )
)
leak_audit["是否泄漏"] = (
    leak_audit["正确：按 available_at"]
    != leak_audit["错误：按 report_period"]
)

alpha_jan3 = leak_audit.loc[
    leak_audit["trade_at"].eq(pd.Timestamp("2025-01-03 15:00"))
    & leak_audit["symbol"].eq("ALPHA")
].iloc[0]
assert np.isclose(alpha_jan3["正确：按 available_at"], 0.10)
assert np.isclose(alpha_jan3["错误：按 report_period"], 0.12)
assert leak_audit["是否泄漏"].any()
print("已证明：仅把连接键换成 report_period，就会把未发布数据带回过去。")
leak_audit
"""
        ),
        md(
            """
## 10. `tolerance`：让陈旧财报显式失效

`direction="backward"` 只保证“不看未来”，并不限制向过去追溯多久。若最后一份财报已经非常陈旧，继续沿用也可能不符合研究定义。

下面把交易时点推进到 2025 年 10 月；最近财报已超过 180 天，因此 `roe_ytd` 应为 `NaN`。这里的缺失表示“没有满足时效规则的记录”，不能擅自解释成 ROE 为 0。
"""
        ),
        code(
            r"""
# 单个远期快照用于验证 tolerance；价格本身只作占位。
stale_trade = pd.DataFrame(
    {
        "trade_at": [pd.Timestamp("2025-10-01 15:00")],
        "symbol": ["ALPHA"],
        "close": [110.0],
    }
)
stale_result = pd.merge_asof(
    stale_trade.sort_values(["trade_at", "symbol"]),
    fundamental_demo.sort_values(["available_at", "symbol"]),
    left_on="trade_at",
    right_on="available_at",
    by="symbol",
    direction="backward",
    tolerance=pd.Timedelta("180D"),
)

assert pd.isna(stale_result.loc[0, "roe_ytd"])
print("陈旧记录已拒绝：超过 180 天后 roe_ytd =", stale_result.loc[0, "roe_ytd"])
stale_result
"""
        ),
        md(
            """
## 11. 回到完整模拟行情：建立行情事实表

下面读取 6 只虚构资产，并截取 2024-03-20 至 2024-09-06：

- `date` 是交易日期标签；
- `trade_at = date + 15:00` 是本课约定的收盘研究快照；
- `(trade_at, symbol)` 必须唯一；
- 这里的“工作日”来自 fixture，不等于真实交易所日历。

先验证原始行情，再连接任何维度或财报。
"""
        ),
        code(
            r"""
# 读取固定种子的模拟日线；只保留本课所需时段和字段。
daily = pd.read_csv(
    DATA_DIR / "daily_prices.csv",
    parse_dates=["date"],
)
market = (
    daily.loc[
        daily["date"].between("2024-03-20", "2024-09-06"),
        ["date", "symbol", "adj_close", "volume"],
    ]
    .sort_values(["date", "symbol"])
    .reset_index(drop=True)
)
market["trade_at"] = market["date"] + pd.Timedelta(hours=15)

assert market["symbol"].nunique() == 6
assert not market.duplicated(["trade_at", "symbol"]).any()
assert market["adj_close"].gt(0).all()
assert market["volume"].ge(0).all()
print("行情 shape =", market.shape)
print("日期范围 =", market["date"].min().date(), "至", market["date"].max().date())
print("资产 =", market["symbol"].drop_duplicates().tolist())
market.head(6)
"""
        ),
        md(
            """
## 12. 先用精确键补行业

行业是每只资产一条记录的维表，适合普通 `merge`：

- 从原始长表提取唯一 `(symbol, sector)`；
- 合并前断言 `symbol` 唯一；
- 用 `how="left"` 保留全部行情；
- 用 `validate="many_to_one"` 声明右表基数；
- 用 `_merge` 验证本样本没有行业缺口。

真实历史行业分类可能随时间变化；那时它本身也是 point-in-time 维度，不能压成静态一行。
"""
        ),
        code(
            r"""
# 构造本 fixture 的静态行业维表，并给每条行情补充行业。
sector_dimension_full = (
    daily[["symbol", "sector"]]
    .drop_duplicates()
    .sort_values("symbol")
    .reset_index(drop=True)
)
assert not sector_dimension_full["symbol"].duplicated().any()

market_with_sector = market.merge(
    sector_dimension_full,
    on="symbol",
    how="left",
    validate="many_to_one",
    indicator=True,
)

assert len(market_with_sector) == len(market)
assert market_with_sector["_merge"].eq("both").all()
print("行业匹配率 =", f"{market_with_sector['_merge'].eq('both').mean():.1%}")
market_with_sector.head(6)
"""
        ),
        md(
            """
## 13. 构造可追溯的模拟财报发布表

为每只虚构资产建立 4 期累计 ROE：

- `annual_roe_reference` 只是生成数值的教学参数，不是真实公司 ROE；
- `ytd_fraction` 让 Q1、半年、前三季度、全年呈现累计口径；
- `published_at` 是模拟发布时刻；
- `available_at` 是本研究系统允许使用的时刻；
- 同一 `(symbol, available_at)` 只能有一条记录。

注意：并非所有数据库中的 ROE 都是累计口径。季度单季、年化、TTM 和平均净资产口径不能混用，必须读取字段定义。
"""
        ),
        code(
            r"""
# 每只虚构资产的教学年化参照值；0.16 表示 16%。
annual_roe_table = pd.DataFrame(
    {
        "symbol": ["BANK_A", "ENERGY_A", "EV_A", "INSURE_A", "POWER_A", "TECH_A"],
        "annual_roe_reference": [0.10, 0.11, 0.14, 0.09, 0.07, 0.16],
    }
)

# 四期报告的覆盖期、模拟发布时间、可用时点和累计比例。
release_schedule = pd.DataFrame(
    {
        "report_label": ["2023Q3", "2023FY", "2024Q1", "2024H1"],
        "report_period": pd.to_datetime(
            ["2023-09-30", "2023-12-31", "2024-03-31", "2024-06-30"]
        ),
        "published_at": pd.to_datetime(
            [
                "2023-10-30 18:00",
                "2024-03-28 18:00",
                "2024-04-26 18:00",
                "2024-08-29 18:00",
            ]
        ),
        "available_at": pd.to_datetime(
            [
                "2023-10-31 09:30",
                "2024-03-29 09:30",
                "2024-04-29 09:30",
                "2024-08-30 09:30",
            ]
        ),
        "ytd_fraction": [0.75, 1.00, 0.25, 0.50],
    }
)

# 这里有意做笛卡尔积：6 只资产 × 4 个报告期 = 24 条模拟财报。
fundamentals = annual_roe_table.merge(
    release_schedule,
    how="cross",
)
fundamentals["roe_ytd"] = (
    fundamentals["annual_roe_reference"]
    * fundamentals["ytd_fraction"]
).round(4)
fundamentals = fundamentals[
    [
        "symbol",
        "report_label",
        "report_period",
        "published_at",
        "available_at",
        "roe_ytd",
    ]
].sort_values(["available_at", "symbol"]).reset_index(drop=True)

assert fundamentals.shape == (24, 6)
assert not fundamentals.duplicated(["symbol", "available_at"]).any()
assert fundamentals["published_at"].le(fundamentals["available_at"]).all()
print("模拟财报 shape =", fundamentals.shape, "含义：资产 × 报告期")
fundamentals.head(8)
"""
        ),
        md(
            """
## 14. 完整 point-in-time 合并

行业补充使用精确键，财报补充使用时点键。这里设置 220 天时效窗口，是为了让样本开始时仍可使用 2023Q3；它只是本教学例子的研究规则，不是通用财报保鲜期。

验收不只检查“没有报错”，还检查：

1. 合并前后行情行数一致；
2. 行情联合键仍唯一；
3. 所有匹配记录的 `available_at` 不晚于 `trade_at`；
4. 本确定性样本每个时点都能找到 220 天内的报告。
"""
        ),
        code(
            r"""
# 删除 merge 审计列后，按时间、资产排序并执行 point-in-time 合并。
market_for_pit = (
    market_with_sector.drop(columns="_merge")
    .sort_values(["trade_at", "symbol"])
    .reset_index(drop=True)
)
fundamentals_for_pit = (
    fundamentals.sort_values(["available_at", "symbol"])
    .reset_index(drop=True)
)

pit_result = pd.merge_asof(
    market_for_pit,
    fundamentals_for_pit,
    left_on="trade_at",
    right_on="available_at",
    by="symbol",
    direction="backward",
    tolerance=pd.Timedelta("220D"),
    allow_exact_matches=True,
)

matched = pit_result["available_at"].notna()
assert len(pit_result) == len(market_for_pit)
assert not pit_result.duplicated(["trade_at", "symbol"]).any()
assert (
    pit_result.loc[matched, "available_at"]
    <= pit_result.loc[matched, "trade_at"]
).all()
assert matched.all()

print("PIT 结果 shape =", pit_result.shape)
print("行情保留率 =", f"{len(pit_result) / len(market_for_pit):.1%}")
print("220 天内财报匹配率 =", f"{matched.mean():.1%}")
pit_result.head(6)
"""
        ),
        md(
            """
## 15. 发布日前后审计：结果应呈阶梯变化

选 `TECH_A` 在三个发布窗口前后核对：

- 2024-03-28 15:00：年报 18:00 才发布，仍应看到 2023Q3；
- 2024-03-29 15:00：年报已在 09:30 可用，应切到 2023FY；
- 2024-04-26 15:00：Q1 尚未发布，仍看到 2023FY；
- 2024-04-29 15:00：切到 2024Q1；
- 2024-08-29 15:00：半年报尚未发布，仍看到 2024Q1；
- 2024-08-30 15:00：切到 2024H1。

这种“跨发布日期才跳变”的阶梯结构，是 point-in-time 快照最直观的检查之一。
"""
        ),
        code(
            r"""
# 抽取 TECH_A 的发布窗口，并把 ROE 额外显示为百分数。
audit_dates = pd.to_datetime(
    [
        "2024-03-28",
        "2024-03-29",
        "2024-04-26",
        "2024-04-29",
        "2024-08-29",
        "2024-08-30",
    ]
)
tech_audit = (
    pit_result.loc[
        pit_result["symbol"].eq("TECH_A")
        & pit_result["date"].isin(audit_dates),
        [
            "date",
            "trade_at",
            "report_label",
            "report_period",
            "published_at",
            "available_at",
            "roe_ytd",
        ],
    ]
    .sort_values("trade_at")
    .assign(roe_ytd_percent=lambda frame: frame["roe_ytd"] * 100)
)

reported_period_by_date = tech_audit.set_index("date")["report_period"]
assert reported_period_by_date.loc[pd.Timestamp("2024-03-28")] == pd.Timestamp("2023-09-30")
assert reported_period_by_date.loc[pd.Timestamp("2024-03-29")] == pd.Timestamp("2023-12-31")
assert reported_period_by_date.loc[pd.Timestamp("2024-04-26")] == pd.Timestamp("2023-12-31")
assert reported_period_by_date.loc[pd.Timestamp("2024-04-29")] == pd.Timestamp("2024-03-31")
assert reported_period_by_date.loc[pd.Timestamp("2024-08-29")] == pd.Timestamp("2024-03-31")
assert reported_period_by_date.loc[pd.Timestamp("2024-08-30")] == pd.Timestamp("2024-06-30")
print("发布窗口断言全部通过。")
tech_audit
"""
        ),
        md(
            """
## 16. 课程式“最高 ROE”筛选，只做连接结果核对

下面在每天的 6 只资产中选原始累计 ROE 最高者，用来确认横截面结果可分组、可排序。它**不是策略回测**：

- 同一天同一报告期内，本模拟数据的 ROE 在发布之间不变；
- 原始 ROE 跨行业未做口径统一和行业中性化；
- 没有收益标签、执行价格、持仓期、换手、成本或样本外检验；
- “某资产入选多少天”只描述这张模拟输入表。
"""
        ),
        code(
            r"""
# 每个 trade_at 按 ROE 降序、symbol 升序稳定排序，取第一行。
top_roe_by_day = (
    pit_result.dropna(subset=["roe_ytd"])
    .sort_values(
        ["trade_at", "roe_ytd", "symbol"],
        ascending=[True, False, True],
    )
    .groupby("trade_at", sort=False)
    .head(1)
    .reset_index(drop=True)
)
selection_counts = (
    top_roe_by_day["symbol"]
    .value_counts()
    .rename_axis("symbol")
    .rename("selected_days")
    .to_frame()
)

assert top_roe_by_day["trade_at"].is_unique
assert len(top_roe_by_day) == pit_result["trade_at"].nunique()
print("每日横截面数 =", len(top_roe_by_day))
display(top_roe_by_day[["date", "symbol", "sector", "report_label", "roe_ytd"]].head())
selection_counts
"""
        ),
        md(
            """
## 17. 量化意义与方法边界

- `concat` 只负责沿轴组合，不替你检查业务主键、单位、复权口径或时区。
- `merge` 应显式写 `on/how/validate`；默认 `inner` 可能静默丢失左表记录。
- `_merge` 说明键是否匹配；普通字段的 `NaN` 还可能来自源数据本身。
- 多对多连接不一定错误，但必须是明确的业务设计；事实表补维度通常不应多对多。
- `direction="backward"` 只有在右键确实是 `available_at` 时才能防未来函数；换成 `report_period` 仍会泄漏。
- `by="symbol"` 不可省略，否则一只资产可能匹配到另一只资产最近发布的财报。
- `tolerance` 是研究规则，不是“越大越好”；过大允许陈旧数据，过小会扩大缺失。
- 收盘后公告何时可用取决于时区、采集延迟和执行时点；真实系统应保存原始发布时间、入库时间和规则版本。
- 同一报告可能更正或重发；必须保存版本并明确“当时看到的版本”，不能用最终修订值覆盖历史。
- 证券代码可能复用或变更；生产连接应使用稳定证券标识并记录公司行动。
- ROE 可能是单季、累计、年化或 TTM；Q1“重置”只适用于累计口径。
- 原始 ROE 跨行业比较会受杠杆、会计口径和行业结构影响；排名本身不是收益证据。
- 本 fixture 没有停牌、退市、幸存者偏差、货币差异和财报修订，不构成真实投资研究。

## 18. 可复用结论与练习

```text
原始事实表 → 主键/单位/时间契约
           → 精确维度 merge(validate + indicator)
           → 财报 published_at / available_at
           → 按时间、资产排序
           → merge_asof(by + backward + tolerance)
           → 行数、时点、发布日期阶梯审计
```

练习：

1. 把 `ALPHA` 新报告的 `available_at` 改到 2025-01-03 14:00，先写出 15:00 快照的预期，再运行断言。
2. 删除 `by="symbol"`，找出发生跨资产误配的最小输入；不要把错误结果用于后续计算。
3. 给行业维表加入重复 `ALPHA`，比较没有 `validate` 时行数如何膨胀。
4. 给同一财报加入“初始版/修订版”，设计 `version`、`available_at` 和去重规则。
5. 把 `tolerance` 从 220 天改为 90 天，统计缺失率，并解释它是研究规则变化而不是数据自动变差。
"""
        ),
    ]
    write_notebook(NOTEBOOKS / "39_财报行情合并与时点一致性.ipynb", cells)


def build_lesson_40():
    cells = [
        md(
            source_note(
                40,
                "同一结果表驱动诚实可视化",
                "40_youtube-4-CXG3SyWpI",
            )
        ),
        md(
            """
## 1. 本节量化问题

课程把价格、均线交叉、成交量、归一化净值和回撤放到一张多面板图。本节保留这条可视化主线，同时增加一个更重要的研究约束：

> **先在同一张带日期索引的结果表中计算全部序列，再让所有面板只读取这张表。**

这样可以区分：

- 归一化价格（买入持有基准）与真正按信号、持仓和成本得到的策略净值；
- 信号发现日与可执行持仓日；
- `sharex=True` 的视觉共享与数据本身的索引对齐；
- 图形展示与统计证据。

本节先用 5 个确定数值手算回撤，再回到完整模拟行情。
"""
        ),
        md(
            """
## 2. 输入、输出与验收

**输入**

- `daily_prices.csv` 中虚构资产 `TECH_A` 最近 504 个工作日观测；
- 复权收盘价和模拟成交量；
- 20/60 日简单移动平均，单边换仓成本 5 bp。

**输出**

- 唯一的 `result` 结果表：价格、均线、事件、滞后持仓、成本、净值、回撤共享同一索引；
- 价格/信号、成交量/策略净值、策略回撤三面板图；
- `outputs/40_strategy_dashboard.png`。

**验收**

- 日期索引唯一、升序，价格为正、成交量非负；
- MA20 前 19 个、MA60 前 59 个值为空；
- 金叉和死叉不在同一天发生；
- `position[t]` 只由 `t-1` 收盘后已知状态决定；
- 策略净值有限且为正，回撤不大于 0；
- 归一化价格与策略净值使用不同列名、不同图例；
- 图片成功保存且不是空文件。

504 个工作日观测只是约两个交易年，不等于精确两个自然年。
"""
        ),
        code(COMMON_SETUP),
        md(
            """
## 3. 先用 5 个数值手算回撤

回撤公式：

```text
running_peak[t] = max(nav[0], ..., nav[t])
drawdown[t]     = nav[t] / running_peak[t] - 1
```

示例净值 `[1.00, 1.10, 1.05, 1.20, 0.90]` 的最后一个峰值是 `1.20`，最后回撤为 `0.90 / 1.20 - 1 = -25%`。

`cummax()` 只使用当前和过去值，因此适合历史回撤计算；最严重回撤是最小的负数，而不是绝对值最小。
"""
        ),
        code(
            r"""
# 确定性小例子：每一行都可以手工核对。
demo_nav = pd.Series(
    [1.00, 1.10, 1.05, 1.20, 0.90],
    index=pd.date_range("2025-01-01", periods=5, freq="D"),
    name="nav",
)
demo_peak = demo_nav.cummax()
demo_drawdown = demo_nav / demo_peak - 1
drawdown_demo = pd.DataFrame(
    {
        "nav": demo_nav,
        "running_peak": demo_peak,
        "drawdown": demo_drawdown,
    }
)

expected_drawdown = np.array(
    [0.0, 0.0, -0.0454545454545, 0.0, -0.25]
)
np.testing.assert_allclose(
    drawdown_demo["drawdown"].to_numpy(),
    expected_drawdown,
    atol=1e-12,
)
assert np.isclose(drawdown_demo["drawdown"].min(), -0.25)
assert np.isclose(drawdown_demo["drawdown"].max(), 0.0)
print("手工校验通过：最大历史回撤 =", f"{drawdown_demo['drawdown'].min():.1%}")
drawdown_demo.style.format(
    {
        "nav": "{:.2f}",
        "running_peak": "{:.2f}",
        "drawdown": "{:.2%}",
    }
)
"""
        ),
        md(
            """
## 4. Figure、Axes、`subplots` 和 `sharex`

`plt.subplots` 同时创建：

- `Figure`：整张画布；
- `Axes`：每一个坐标区域。

`plt.plot(...)` 会操作“当前 Axes”；在多面板研究图中显式写 `ax.plot(...)` 更容易确认内容画到哪个面板。

`sharex=True` 只让面板共享**显示坐标范围和刻度**，不会替两个独立 Series 对齐日期。下面小图安全，是因为两个面板都读取同一个 `drawdown_demo` 索引。
"""
        ),
        code(
            r"""
# 两个面板读取同一张小结果表；sharex 只管理显示，不执行数据连接。
fig_demo, axes_demo = plt.subplots(
    2,
    1,
    figsize=(7.2, 4.8),
    sharex=True,
    gridspec_kw={"height_ratios": [2, 1]},
    constrained_layout=True,
)
ax_nav_demo, ax_drawdown_demo = axes_demo

ax_nav_demo.plot(
    drawdown_demo.index,
    drawdown_demo["nav"],
    marker="o",
    label="NAV",
)
ax_nav_demo.set_ylabel("NAV")
ax_nav_demo.legend()
ax_nav_demo.grid(alpha=0.25)

ax_drawdown_demo.fill_between(
    drawdown_demo.index,
    drawdown_demo["drawdown"].to_numpy(),
    0,
    color="#D55E00",
    alpha=0.30,
    label="Drawdown",
)
ax_drawdown_demo.set_ylabel("Drawdown")
ax_drawdown_demo.legend()
ax_drawdown_demo.grid(alpha=0.25)

assert axes_demo.shape == (2,)
assert ax_nav_demo.get_figure() is fig_demo
plt.show()
plt.close(fig_demo)
"""
        ),
        md(
            """
## 5. 读取完整模拟行情并建立唯一结果表

先读取原始长表，再筛选 `TECH_A` 最近 504 行。`result` 从此成为本课唯一的序列来源：

- 行索引是日期；
- 每列是一种可追踪的价格、信号、持仓或绩效量；
- 新计算结果继续写回 `result`，避免价格、成交量、信号各自拥有悄悄错位的索引。

本数据为固定种子模拟行情，不是任何真实科技股。
"""
        ),
        code(
            r"""
# 读取模拟日线，筛选单只虚构资产并保留最近 504 个工作日观测。
daily = pd.read_csv(
    DATA_DIR / "daily_prices.csv",
    parse_dates=["date"],
)
result = (
    daily.loc[
        daily["symbol"].eq("TECH_A"),
        ["date", "adj_close", "volume"],
    ]
    .sort_values("date")
    .set_index("date")
    .tail(504)
    .copy()
)

assert isinstance(result.index, pd.DatetimeIndex)
assert result.index.is_monotonic_increasing
assert result.index.is_unique
assert len(result) == 504
assert result["adj_close"].gt(0).all()
assert result["volume"].ge(0).all()

print("result.shape =", result.shape, "含义：交易日 × 原始字段")
print("日期范围 =", result.index.min().date(), "至", result.index.max().date())
print("原始列 =", result.columns.tolist())
result.head()
"""
        ),
        md(
            """
## 6. 简单收益与买入持有归一化价格

`pct_change(fill_method=None)` 计算相邻复权收盘价的简单收益，第一天没有前值，所以为 `NaN`。

`adj_close / adj_close.iloc[0]` 表示把样本第一天价格归一到 1。若忽略交易成本，它等价于在起点买入并一直持有该资产的净值路径；它**不是**后面 20/60 日交叉策略的净值。

课程画面中的“归一化净值”和最终数值依赖原视频数据。本离线模拟数据不会复现那些具体数值。
"""
        ),
        code(
            r"""
# 简单收益第一行必为空；buy_hold_nav 只是归一化价格路径。
result["asset_return"] = result["adj_close"].pct_change(
    fill_method=None
)
result["buy_hold_nav"] = (
    result["adj_close"]
    / result["adj_close"].iloc[0]
)

assert pd.isna(result["asset_return"].iloc[0])
assert result["asset_return"].iloc[1:].notna().all()
assert result["asset_return"].iloc[1:].gt(-1).all()
assert np.isclose(result["buy_hold_nav"].iloc[0], 1.0)
np.testing.assert_allclose(
    result["buy_hold_nav"].to_numpy(),
    (
        result["adj_close"]
        / result["adj_close"].iloc[0]
    ).to_numpy(),
)

print("买入持有归一化起点 =", f"{result['buy_hold_nav'].iloc[0]:.4f}")
print("买入持有归一化终点 =", f"{result['buy_hold_nav'].iloc[-1]:.4f}")
result[["adj_close", "asset_return", "buy_hold_nav"]].head()
"""
        ),
        md(
            """
## 7. 20/60 日简单移动平均

`rolling(window, min_periods=window).mean()` 使用当前及过去 `window` 个观测：

- MA20 至少需要 20 个价格，因此前 19 行是 `NaN`；
- MA60 至少需要 60 个价格，因此前 59 行是 `NaN`；
- 窗口按“观测行数”计数，不自动理解交易所休市日；
- 均线是历史平滑，不是预测值。

先单独计算均线并检查热身期，再讨论交叉事件。
"""
        ),
        code(
            r"""
# min_periods 与窗口相同，避免用不足 20/60 日的短样本冒充完整均线。
result["ma20"] = (
    result["adj_close"]
    .rolling(window=20, min_periods=20)
    .mean()
)
result["ma60"] = (
    result["adj_close"]
    .rolling(window=60, min_periods=60)
    .mean()
)

assert result["ma20"].iloc[:19].isna().all()
assert result["ma20"].iloc[19:].notna().all()
assert result["ma60"].iloc[:59].isna().all()
assert result["ma60"].iloc[59:].notna().all()

print("MA20 首个有效日期 =", result["ma20"].first_valid_index().date())
print("MA60 首个有效日期 =", result["ma60"].first_valid_index().date())
result[["adj_close", "ma20", "ma60"]].iloc[[0, 18, 19, 58, 59]]
"""
        ),
        md(
            """
## 8. 从“均线状态”识别“交叉事件”

`ma20 > ma60` 是每天的持仓状态候选；金叉/死叉则只发生在状态切换日：

```text
golden_cross = 昨日不在上方，今日转到上方
death_cross  = 昨日在上方，今日转到下方
```

只有今天和昨天两条均线都有效时才允许产生事件，避免 MA60 刚结束热身期时制造假金叉。事件用于标记，不等于已经成交。
"""
        ),
        code(
            r"""
# 两条均线都存在才是可比较状态。
result["ma_valid"] = (
    result["ma20"].notna()
    & result["ma60"].notna()
)
result["above_ma60"] = (
    result["ma20"] > result["ma60"]
)

previous_valid = result["ma_valid"].shift(
    1,
    fill_value=False,
)
previous_above = result["above_ma60"].shift(
    1,
    fill_value=False,
)

# 事件必须有连续两个有效均线状态。
result["golden_cross"] = (
    result["ma_valid"]
    & previous_valid
    & result["above_ma60"]
    & ~previous_above
)
result["death_cross"] = (
    result["ma_valid"]
    & previous_valid
    & ~result["above_ma60"]
    & previous_above
)
result["signal"] = np.select(
    [result["golden_cross"], result["death_cross"]],
    ["golden_cross", "death_cross"],
    default="",
)

assert not (
    result["golden_cross"]
    & result["death_cross"]
).any()
assert result.loc[
    result["golden_cross"] | result["death_cross"],
    "ma_valid",
].all()

event_table = result.loc[
    result["signal"].ne(""),
    ["adj_close", "ma20", "ma60", "signal"],
]
print("金叉次数 =", int(result["golden_cross"].sum()))
print("死叉次数 =", int(result["death_cross"].sum()))
event_table.head(10)
"""
        ),
        md(
            """
## 9. 信号滞后一日成为持仓

若均线使用第 `t` 日收盘价计算，则完整信号要到收盘后才知道，不能再用同一个收盘价成交并赚取第 `t` 日收益。

本教学模型采用：

```text
position[t] = (ma20 > ma60)[t-1]
```

即昨天收盘后的状态决定今天的 close-to-close 收益暴露。它避免同收盘未来函数，但仍是简化假设：没有开盘跳空、滑点、涨跌停、停牌和订单成交过程。
"""
        ),
        code(
            r"""
# 热身期的状态按空仓处理；shift(1) 保证今天持仓只依赖昨天状态。
active_signal_state = result["above_ma60"].where(
    result["ma_valid"],
    False,
)
result["position"] = (
    active_signal_state
    .shift(1, fill_value=False)
    .astype(float)
)

assert result["position"].isin([0.0, 1.0]).all()
assert result["position"].iloc[0] == 0.0
np.testing.assert_array_equal(
    result["position"].iloc[1:].to_numpy(),
    active_signal_state.iloc[:-1].astype(float).to_numpy(),
)
print("滞后校验通过：position[t] 与昨日均线状态逐行一致。")

# 展示第一个事件附近，而不是只输出无法解释的长向量。
if event_table.empty:
    event_window = result.iloc[55:65]
else:
    first_event_position = result.index.get_loc(event_table.index[0])
    event_window = result.iloc[
        max(0, first_event_position - 2):
        first_event_position + 4
    ]
event_window[
    [
        "adj_close",
        "ma20",
        "ma60",
        "signal",
        "position",
    ]
]
"""
        ),
        md(
            """
## 10. 从持仓得到含成本策略净值

先计算每个分量，再生成净值：

| 列 | 公式 | 含义 |
|---|---|---|
| `gross_strategy_return` | `position × asset_return` | 未扣成本的日收益 |
| `turnover` | `abs(position[t]-position[t-1])` | 本例单资产换仓量 |
| `transaction_cost` | `turnover × 0.0005` | 5 bp 单边教学成本 |
| `strategy_return` | `gross_return - cost` | 扣成本日收益 |
| `strategy_nav` | `(1 + strategy_return).cumprod()` | 扣成本累计净值 |

成本在持仓变化日一次性扣除。真实市场还要定义佣金、印花税、买卖价差、市场冲击和实际成交价。
"""
        ),
        code(
            r"""
# 第一日收益没有前值，作为净值起点按 0 处理。
safe_asset_return = result["asset_return"].fillna(0.0)
result["gross_strategy_return"] = (
    result["position"]
    * safe_asset_return
)

# 单资产 0/1 持仓的绝对变化就是换手；首日按初始建仓量处理。
result["turnover"] = result["position"].diff().abs()
result.iloc[
    0,
    result.columns.get_loc("turnover"),
] = abs(result["position"].iloc[0])

cost_rate = 0.0005  # 5 bp = 0.05%，仅为教学假设。
result["transaction_cost"] = (
    result["turnover"]
    * cost_rate
)
result["strategy_return"] = (
    result["gross_strategy_return"]
    - result["transaction_cost"]
)
result["gross_strategy_nav"] = (
    1.0 + result["gross_strategy_return"]
).cumprod()
result["strategy_nav"] = (
    1.0 + result["strategy_return"]
).cumprod()

assert result["turnover"].notna().all()
assert result["turnover"].ge(0).all()
assert result["transaction_cost"].ge(0).all()
assert result["strategy_return"].gt(-1).all()
assert np.isfinite(result["strategy_nav"]).all()
assert result["strategy_nav"].gt(0).all()
assert (
    result["strategy_nav"].iloc[-1]
    <= result["gross_strategy_nav"].iloc[-1] + 1e-12
)

print("成本率 =", f"{cost_rate:.2%}")
print("累计换手 =", f"{result['turnover'].sum():.1f}")
print("累计教学成本（收益率点数相加）=", f"{result['transaction_cost'].sum():.4f}")
result[
    [
        "asset_return",
        "position",
        "turnover",
        "transaction_cost",
        "strategy_return",
        "strategy_nav",
    ]
].tail()
"""
        ),
        md(
            """
## 11. 从策略净值计算回撤

本课最终图的回撤面板必须来自 `strategy_nav`，不能误用价格或另一条净值：

```text
strategy_peak     = strategy_nav.cummax()
strategy_drawdown = strategy_nav / strategy_peak - 1
```

回撤为 0 表示处于历史新高，负数表示距离此前峰值的百分比损失。最大历史回撤取最小值，并同时保存发生日期，便于回到行情和持仓审计。
"""
        ),
        code(
            r"""
# 继续写入同一个 result，保证净值、峰值和回撤逐日同索引。
result["strategy_peak"] = result["strategy_nav"].cummax()
result["strategy_drawdown"] = (
    result["strategy_nav"]
    / result["strategy_peak"]
    - 1.0
)

max_drawdown_date = result["strategy_drawdown"].idxmin()
max_drawdown = result.loc[
    max_drawdown_date,
    "strategy_drawdown",
]

assert result["strategy_drawdown"].le(1e-12).all()
assert np.isclose(result["strategy_drawdown"].max(), 0.0)
assert np.isclose(
    max_drawdown,
    result["strategy_drawdown"].min(),
)
print("策略最大历史回撤 =", f"{max_drawdown:.2%}")
print("最大回撤日期 =", max_drawdown_date.date())
result[
    [
        "strategy_nav",
        "strategy_peak",
        "strategy_drawdown",
    ]
].loc[:max_drawdown_date].tail()
"""
        ),
        md(
            """
## 12. 绘图前先输出可核对指标

图适合观察时间结构，精确数值应由带标签输出承担。这里明确区分：

- `buy_hold_final_nav`：归一化价格的终值；
- `gross_strategy_final_nav`：均线策略未扣成本终值；
- `net_strategy_final_nav`：均线策略扣教学成本终值；
- `max_strategy_drawdown`：扣成本策略的最大历史回撤。

如果图例只写模糊的“净值”，这三条序列很容易被混淆。
"""
        ),
        code(
            r"""
# 全部指标都从同一 result 表读取；先打印样本信息，再显示数值表。
metrics = pd.Series(
    {
        "observations": float(len(result)),
        "golden_cross_count": float(result["golden_cross"].sum()),
        "death_cross_count": float(result["death_cross"].sum()),
        "total_turnover": float(result["turnover"].sum()),
        "buy_hold_final_nav": float(result["buy_hold_nav"].iloc[-1]),
        "gross_strategy_final_nav": float(result["gross_strategy_nav"].iloc[-1]),
        "net_strategy_final_nav": float(result["strategy_nav"].iloc[-1]),
        "max_strategy_drawdown": float(result["strategy_drawdown"].min()),
    },
    name="value",
)

print("样本起点 =", result.index.min().date())
print("样本终点 =", result.index.max().date())
print("最大回撤日 =", max_drawdown_date.date())
metrics.to_frame().round(6)
"""
        ),
        md(
            """
## 13. 字体与标签回退

`COMMON_SETUP` 已从本机字体中优先选择 PingFang、Arial Unicode、Hiragino 或 Heiti，并设置：

```python
plt.rcParams["axes.unicode_minus"] = False
```

若这些中文字体都不存在，Matplotlib 会回退到 DejaVu Sans。DejaVu Sans 不完整覆盖中文，继续画中文标题会产生 `Glyph ... missing from font` 警告和方框字。

因此下面在没有已知中文字体时自动改用英文图内标签。Notebook 的中文 Markdown 仍由浏览器字体正常显示。
"""
        ),
        code(
            r"""
# 图内文字根据字体能力选择；数据、列名和计算结果不受语言影响。
has_known_chinese_font = chinese_font != "DejaVu Sans"
if has_known_chinese_font:
    plot_labels = {
        "title": "模拟资产：价格、信号、成交量、策略净值与回撤",
        "price": "复权收盘价",
        "ma20": "20 日均线",
        "ma60": "60 日均线",
        "golden": "金叉（信号日）",
        "death": "死叉（信号日）",
        "price_axis": "模拟价格",
        "volume": "成交量",
        "volume_axis": "成交量（百万模拟单位）",
        "strategy_nav": "扣成本策略净值",
        "nav_axis": "策略净值（起点 1）",
        "drawdown": "策略回撤",
        "drawdown_axis": "回撤",
    }
else:
    plot_labels = {
        "title": "Synthetic asset: price, signals, volume, strategy NAV and drawdown",
        "price": "Adjusted close",
        "ma20": "20-day SMA",
        "ma60": "60-day SMA",
        "golden": "Golden cross (signal date)",
        "death": "Death cross (signal date)",
        "price_axis": "Synthetic price",
        "volume": "Volume",
        "volume_axis": "Volume (synthetic millions)",
        "strategy_nav": "Net strategy NAV",
        "nav_axis": "Strategy NAV (start=1)",
        "drawdown": "Strategy drawdown",
        "drawdown_axis": "Drawdown",
    }

print("Matplotlib 字体 =", chinese_font)
print("图内标签语言 =", "中文" if has_known_chinese_font else "English fallback")
"""
        ),
        md(
            """
## 14. 三面板图：全部由同一 `result` 表驱动

布局参数：

- `plt.subplots(3, 1, sharex=True)`：3 行 1 列，共享日期显示轴；
- `height_ratios=[3, 1, 1.3]`：价格面板最高，成交量最低，回撤居中；
- 第二面板 `twinx()`：左轴是百万模拟成交量，右轴是扣成本策略净值；
- `MonthLocator(interval=3)`：每 3 个月一个主刻度；
- `DateFormatter("%Y-%m")`：只改变日期显示格式，不删除数据点。

双轴会让两条序列看起来比实际更同步，因此必须使用不同颜色、左右轴标签和独立图例。若分析重点是相关性，应优先分成独立面板或先标准化，而不是靠调双轴范围制造视觉关系。
"""
        ),
        code(
            r"""
# 创建 3 个主 Axes；constrained_layout 自动为标题、图例和旋转日期留空间。
import matplotlib.dates as mdates
from matplotlib.ticker import PercentFormatter

fig, axes = plt.subplots(
    3,
    1,
    figsize=(12.8, 9.6),
    sharex=True,
    gridspec_kw={"height_ratios": [3.0, 1.0, 1.3]},
    constrained_layout=True,
)
ax_price, ax_volume, ax_drawdown = axes

# 面板 1：价格、两条均线和信号发现日。
ax_price.plot(
    result.index,
    result["adj_close"],
    color="#222222",
    linewidth=1.2,
    label=plot_labels["price"],
)
ax_price.plot(
    result.index,
    result["ma20"],
    color="#0072B2",
    linewidth=1.4,
    label=plot_labels["ma20"],
)
ax_price.plot(
    result.index,
    result["ma60"],
    color="#E69F00",
    linewidth=1.4,
    label=plot_labels["ma60"],
)
ax_price.scatter(
    result.index[result["golden_cross"]],
    result.loc[result["golden_cross"], "adj_close"],
    marker="^",
    s=52,
    color="#009E73",
    edgecolor="white",
    linewidth=0.5,
    zorder=4,
    label=plot_labels["golden"],
)
ax_price.scatter(
    result.index[result["death_cross"]],
    result.loc[result["death_cross"], "adj_close"],
    marker="v",
    s=52,
    color="#D55E00",
    edgecolor="white",
    linewidth=0.5,
    zorder=4,
    label=plot_labels["death"],
)
ax_price.set_ylabel(plot_labels["price_axis"])
ax_price.legend(
    loc="upper left",
    ncol=3,
    fontsize=9,
)
ax_price.grid(alpha=0.22)

# 面板 2 左轴：成交量，换算为百万模拟单位，避免难读的大整数。
volume_million = result["volume"] / 1_000_000
ax_volume.bar(
    result.index,
    volume_million,
    width=1.8,
    color="#9AA0A6",
    alpha=0.55,
    label=plot_labels["volume"],
)
ax_volume.set_ylabel(
    plot_labels["volume_axis"],
    color="#5F6368",
)
ax_volume.tick_params(
    axis="y",
    colors="#5F6368",
)
ax_volume.legend(
    loc="upper left",
    fontsize=9,
)
ax_volume.grid(axis="y", alpha=0.18)

# 面板 2 右轴：明确画扣成本策略净值，而不是归一化价格。
ax_strategy_nav = ax_volume.twinx()
ax_strategy_nav.plot(
    result.index,
    result["strategy_nav"],
    color="#7B2CBF",
    linewidth=1.35,
    label=plot_labels["strategy_nav"],
)
ax_strategy_nav.set_ylabel(
    plot_labels["nav_axis"],
    color="#7B2CBF",
)
ax_strategy_nav.tick_params(
    axis="y",
    colors="#7B2CBF",
)
ax_strategy_nav.spines["right"].set_color("#7B2CBF")
ax_strategy_nav.legend(
    loc="upper right",
    fontsize=9,
)

# 面板 3：由同一张表中的 strategy_drawdown 填充到 0。
ax_drawdown.fill_between(
    result.index,
    result["strategy_drawdown"].to_numpy(dtype=float),
    0,
    color="#D55E00",
    alpha=0.30,
    label=plot_labels["drawdown"],
)
ax_drawdown.plot(
    result.index,
    result["strategy_drawdown"],
    color="#D55E00",
    linewidth=0.9,
)
ax_drawdown.axhline(
    0,
    color="#333333",
    linewidth=0.8,
)
ax_drawdown.scatter(
    [max_drawdown_date],
    [max_drawdown],
    color="#B00020",
    s=34,
    zorder=5,
)
ax_drawdown.annotate(
    f"{max_drawdown:.1%}",
    xy=(max_drawdown_date, max_drawdown),
    xytext=(8, -18),
    textcoords="offset points",
    color="#B00020",
    fontsize=9,
)
ax_drawdown.set_ylabel(plot_labels["drawdown_axis"])
ax_drawdown.yaxis.set_major_formatter(
    PercentFormatter(1.0)
)
ax_drawdown.legend(
    loc="lower left",
    fontsize=9,
)
ax_drawdown.grid(alpha=0.22)

# 日期必须仍是 DatetimeIndex，locator/formatter 才按真实时间工作。
ax_drawdown.xaxis.set_major_locator(
    mdates.MonthLocator(interval=3)
)
ax_drawdown.xaxis.set_major_formatter(
    mdates.DateFormatter("%Y-%m")
)
plt.setp(
    ax_drawdown.get_xticklabels(),
    rotation=30,
    ha="right",
)

fig.suptitle(
    plot_labels["title"],
    fontsize=15,
    # 某些 macOS 中文字体没有名为 bold 的独立字重；直接使用 600
    # 可保持标题层级，同时避免 Matplotlib 的字体回退提示。
    fontweight=600,
)
fig.align_ylabels(axes)

# 保存前完成全部格式调整；保存后检查文件真实存在且非空。
chart_path = OUTPUT_DIR / "40_strategy_dashboard.png"
fig.savefig(
    chart_path,
    dpi=170,
    bbox_inches="tight",
    facecolor="white",
)

assert len(fig.axes) == 4  # 3 个主轴 + 1 个 twinx 右轴
assert chart_path.exists()
assert chart_path.stat().st_size > 0
print("图表已保存：", chart_path)
print("图片字节数：", chart_path.stat().st_size)
plt.show()
plt.close(fig)
"""
        ),
        md(
            """
## 15. 图后审计：展示数据与绘图数据必须一致

保存图片不是验收终点。下面再次检查：

- 所有关键列都属于同一 `result`；
- 结果表没有重复日期；
- 图中信号数量等于结果表事件数量；
- 图中回撤最小点来自扣成本策略净值。

图形不能独立证明这些关系，断言和带标签表格才是证据。
"""
        ),
        code(
            r"""
# 明确列出最终图所依赖的字段，避免误接另一张临时表。
plot_columns = [
    "adj_close",
    "volume",
    "ma20",
    "ma60",
    "golden_cross",
    "death_cross",
    "strategy_nav",
    "strategy_drawdown",
]
assert set(plot_columns).issubset(result.columns)
assert result.index.is_unique
assert result.index.is_monotonic_increasing
assert int(result["golden_cross"].sum()) == len(
    result.loc[result["golden_cross"]]
)
assert int(result["death_cross"].sum()) == len(
    result.loc[result["death_cross"]]
)
assert result["strategy_drawdown"].idxmin() == max_drawdown_date

print("绘图字段审计通过：", plot_columns)
result[plot_columns].tail(3)
"""
        ),
        md(
            """
## 16. 量化意义与方法边界

- 同一结果表能减少错位，但不能替代对复权、时区、交易日历和字段单位的检查。
- `sharex=True` 只共享显示轴，不会自动连接或重采样不同数据源。
- `twinx()` 会引入第二套纵轴；若单位、颜色和图例不清晰，读者容易误判同步关系。
- `MonthLocator` 只减少刻度密度，不会删除行情点；把日期先转成分类字符串会失去真实时间间隔语义。
- 中文标题依赖字体字形；缺字体时应安装可追溯字体或使用英文回退，而不是屏蔽 warning。
- MA60 前 59 行为空是算法热身期，不应填 0 后制造交叉。
- 图上的金叉/死叉是收盘后发现的事件，不等于同日收盘成交。
- 本例用昨日状态乘今日 close-to-close 收益，只是无同收盘泄漏的简化执行模型，不是订单级回测。
- `buy_hold_nav` 是归一化价格；`strategy_nav` 才包含信号、持仓、收益和成本。二者不可共用模糊的“净值”标签。
- 回撤描述已发生路径，不能估计未来最大亏损；最大回撤还应结合持续时间和恢复时间。
- 成交量放大不能证明“机构买入/卖出”，OHLCV 不包含交易者身份。
- 本例没有税费差异、滑点、冲击、停牌、涨跌停、分红现金流和参数样本外验证，不构成真实策略证据。
- 可视化用于发现和沟通问题；显著性、稳健性、基准和样本外表现仍需单独检验。

## 17. 可复用结论与练习

```text
原始 OHLCV → 索引/价格/成交量契约
           → 同一 result 表
           → 历史均线 → 交叉事件
           → 信号滞后 → 持仓/换手/成本
           → 策略净值 → 峰值/回撤
           → 带标签指标 → 多面板图
```

练习：

1. 把持仓从 `shift(1)` 改成不滞后，比较结果并指出为何同收盘执行不成立。
2. 分别设置 0、5 bp、20 bp 成本，比较毛净值差和换手；不要只看最终收益。
3. 把第二面板的双轴拆成两个独立面板，比较可读性和视觉相关性。
4. 构造缺少一个交易日的成交量 Series，证明 `sharex=True` 不会替数据对齐。
5. 计算回撤持续时间和恢复日期，并核对最大回撤区间，而不只标记谷底。
6. 将样本拆成前后两段，只在前段选择均线参数，再在后段展示，避免用全样本挑最好看的图。
"""
        ),
    ]
    write_notebook(NOTEBOOKS / "40_同一结果表驱动策略可视化.ipynb", cells)
