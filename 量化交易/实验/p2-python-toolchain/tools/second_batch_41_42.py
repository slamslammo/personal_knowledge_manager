#!/usr/bin/env python
"""Build P2 lesson notebooks 41–42: Plotly and mplfinance."""

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
- 数据：固定随机种子生成的离线模拟行情（**非真实股票数据**）
- 状态：可运行学习稿；不代表策略收益承诺

> **来源边界**：课程材料没有提供可独立核验的完整源码和真实行情快照。本 Notebook 复现课程方法，不复述视频中真实股票的价格结论。
"""


def build_lesson_41():
    cells = [
        md(
            source_note(
                41,
                "Plotly 交互式 K 线与成交量",
                "41_youtube-rdeQXve2IME",
            )
        ),
        md(
            """
## 1. 本节量化问题

静态图适合论文、课件和归档；研究过程中却经常需要放大异常区段、悬停核对某日 OHLCV，并让价格、均线和成交量共享时间轴。

本节建立两层用法：

1. **Plotly Express（`px`）**：高级快捷接口，一行快速检查收盘价；
2. **Graph Objects（`go`）**：由 Figure 和 Trace 逐层搭建 K 线、均线与成交量；
3. `make_subplots(shared_xaxes=True)`：让上下图共享显示坐标；
4. `write_html`：导出不依赖 Python 的自包含网页。

注意：交互性只是诊断能力，不会自动保证数据对齐、信号正确或结论可靠。
"""
        ),
        md(
            """
## 2. 输入、输出与验收

**输入**

- `daily_prices.csv` 中虚构资产 `EV_A` 的日线；
- 字段：`date/open/high/low/close/volume`。

**输出**

- 快捷收盘价折线；
- K 线 + 20/60 日简单移动平均线（SMA）+ 成交量双面板；
- `outputs/41_interactive_candlestick.html` 自包含交互网页。

**验收**

- 日期唯一、升序，OHLC 关系合法；
- 主图和副图使用完全相同的日期序列；
- Figure 中每个 Trace 的名称、类型和面板位置可核对；
- HTML 文件真实写出且不是空壳。
"""
        ),
        code(COMMON_SETUP),
        code(
            """
# 本课新增 Plotly；分别导入快捷接口、底层对象接口和子图工具。
import plotly
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from IPython.display import IFrame, display

print("Plotly:", plotly.__version__)
"""
        ),
        md(
            """
## 3. 先查看原始长表

`read_csv(parse_dates=["date"])` 在读取时把日期文本转换为 `datetime64`。这里先显示原始列和前几行，再筛选单只资产；不能在不知道字段语义时直接绘图。
"""
        ),
        code(
            """
# 读取完整模拟日线，并展示数据规模、资产和原始字段。
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])

print("原始 shape:", daily.shape, "含义: 股票日 × 字段")
print("资产:", daily["symbol"].drop_duplicates().tolist())
display(daily.head(6))

assert not daily.duplicated(["date", "symbol"]).any()
assert {"date", "symbol", "open", "high", "low", "close", "volume"}.issubset(daily.columns)
"""
        ),
        md(
            """
## 4. 整理 Plotly 所需 OHLCV

课程中的 Candlestick（蜡烛图）至少需要日期、开盘、最高、最低、收盘。成交量是独立 Trace。

- `set_index("date")`：日期成为行标签；
- `rename(...)`：统一为易辨认的首字母大写字段；
- `tail(160)`：只画最近 160 个交易日，避免几千根蜡烛挤成一片；
- `rolling(20/60, min_periods=...)`：只使用当日及过去收盘价。
"""
        ),
        code(
            """
# 筛选一只虚构资产并改成绘图契约；均线未满窗口时保持 NaN。
ohlcv = (
    daily.loc[
        daily["symbol"].eq("EV_A"),
        ["date", "open", "high", "low", "close", "volume"],
    ]
    .sort_values("date")
    .set_index("date")
    .rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    .tail(160)
)
ohlcv["SMA20"] = ohlcv["Close"].rolling(20, min_periods=20).mean()
ohlcv["SMA60"] = ohlcv["Close"].rolling(60, min_periods=60).mean()

print("绘图区间:", ohlcv.index.min().date(), "→", ohlcv.index.max().date())
print("shape:", ohlcv.shape, "含义: 日期 × OHLCV/均线")
display(ohlcv.head(3))
display(ohlcv.tail(3))

assert isinstance(ohlcv.index, pd.DatetimeIndex)
assert ohlcv.index.is_unique and ohlcv.index.is_monotonic_increasing
assert (ohlcv["High"] >= ohlcv[["Open", "Close"]].max(axis=1)).all()
assert (ohlcv["Low"] <= ohlcv[["Open", "Close"]].min(axis=1)).all()
assert ohlcv["SMA20"].iloc[:19].isna().all()
assert ohlcv["SMA60"].iloc[:59].isna().all()
"""
        ),
        md(
            """
## 5. Plotly Express：快速看一眼

`px.line(data_frame, x, y)` 自动创建 Figure 和一条 Scatter Trace。它适合探索单一序列；复杂金融图仍应使用 Graph Objects。
"""
        ),
        code(
            """
# 快捷接口只画收盘价；检查生成的 Trace，而不是仅凭肉眼判断。
quick_data = ohlcv.reset_index()
quick_fig = px.line(
    quick_data,
    x="date",
    y="Close",
    title="EV_A 模拟收盘价｜Plotly Express",
    labels={"date": "日期", "Close": "模拟价格"},
)
quick_fig.update_layout(template="plotly_white", height=360)

quick_trace = quick_fig.data[0]
print("Trace 数量:", len(quick_fig.data))
print("Trace 类型:", quick_trace.type)
print("点数:", len(quick_trace.x))

assert len(quick_fig.data) == 1
assert quick_trace.type == "scatter"
assert len(quick_trace.x) == len(ohlcv)
"""
        ),
        md(
            """
## 6. Graph Objects：先用 5 日小样本理解 Trace

`go.Candlestick` 不是直接“画一张图片”，而是创建一层可交互的图形数据：

- `x`：日期；
- `open/high/low/close`：同长度的四条数组；
- `name`：图例名称。

Figure 是容器，Trace 是图层。后续均线和成交量都是额外 Trace。
"""
        ),
        code(
            """
# 用 5 日小样本构造一层蜡烛，并逐项核对 Trace 的数据长度。
five_days = ohlcv.iloc[:5]
small_fig = go.Figure(
    data=[
        go.Candlestick(
            x=five_days.index,
            open=five_days["Open"],
            high=five_days["High"],
            low=five_days["Low"],
            close=five_days["Close"],
            name="5 日 OHLC",
        )
    ]
)
small_trace = small_fig.data[0]

trace_check = pd.DataFrame(
    {
        "date": pd.to_datetime(small_trace.x),
        "open": np.asarray(small_trace.open, dtype=float),
        "high": np.asarray(small_trace.high, dtype=float),
        "low": np.asarray(small_trace.low, dtype=float),
        "close": np.asarray(small_trace.close, dtype=float),
    }
)
display(trace_check)

assert small_trace.type == "candlestick"
assert len(trace_check) == 5
np.testing.assert_allclose(trace_check["close"], five_days["Close"])
"""
        ),
        md(
            """
## 7. `make_subplots`：价格与成交量共享时间轴

`shared_xaxes=True` 只让两个面板共享**显示坐标**，不会替你检查数据是否对齐。因此这里所有 Trace 都从同一个 `ohlcv` 表取日期，并在生成后再次核对。

`row_heights=[0.72, 0.28]` 控制上下高度；`vertical_spacing` 控制间距。A 股习惯常用红涨绿跌，但颜色不是跨市场通用语义，必须保留图例和字段说明。
"""
        ),
        code(
            """
# 逐层加入 K 线、两条均线和成交量，所有图层共用同一个日期索引。
fig = make_subplots(
    rows=2,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.04,
    row_heights=[0.72, 0.28],
    subplot_titles=("模拟价格与均线", "成交量"),
)

fig.add_trace(
    go.Candlestick(
        x=ohlcv.index,
        open=ohlcv["Open"],
        high=ohlcv["High"],
        low=ohlcv["Low"],
        close=ohlcv["Close"],
        increasing_line_color="#d62728",
        decreasing_line_color="#2ca02c",
        name="OHLC",
    ),
    row=1,
    col=1,
)
fig.add_trace(
    go.Scatter(x=ohlcv.index, y=ohlcv["SMA20"], mode="lines", name="SMA20"),
    row=1,
    col=1,
)
fig.add_trace(
    go.Scatter(x=ohlcv.index, y=ohlcv["SMA60"], mode="lines", name="SMA60"),
    row=1,
    col=1,
)

volume_colors = np.where(
    ohlcv["Close"].ge(ohlcv["Open"]),
    "#d62728",
    "#2ca02c",
)
fig.add_trace(
    go.Bar(
        x=ohlcv.index,
        y=ohlcv["Volume"],
        marker_color=volume_colors,
        name="Volume",
    ),
    row=2,
    col=1,
)

fig.update_layout(
    title="EV_A 模拟行情｜交互 K 线、均线与成交量",
    template="plotly_white",
    height=720,
    hovermode="x unified",
    legend_orientation="h",
    margin=dict(l=60, r=30, t=90, b=45),
)
fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
fig.update_yaxes(title_text="模拟价格", row=1, col=1)
_ = fig.update_yaxes(title_text="成交量", row=2, col=1)
"""
        ),
        md(
            """
### 图层结构检查

不能因为图“看起来对齐”就默认正确。下面把 Figure 内部的 Trace 清单变成表格，并验证四层的日期与原数据完全一致。
"""
        ),
        code(
            """
# 把 Figure 内部结构转换为可核对表格；四层日期必须与 ohlcv 索引一致。
trace_manifest = pd.DataFrame(
    [
        {
            "序号": index,
            "名称": trace.name,
            "类型": trace.type,
            "点数": len(trace.x),
        }
        for index, trace in enumerate(fig.data, start=1)
    ]
)
display(trace_manifest)

expected_names = ["OHLC", "SMA20", "SMA60", "Volume"]
assert trace_manifest["名称"].tolist() == expected_names
assert trace_manifest["点数"].eq(len(ohlcv)).all()
for trace in fig.data:
    pd.testing.assert_index_equal(
        pd.DatetimeIndex(trace.x),
        ohlcv.index,
        check_names=False,
    )
"""
        ),
        md(
            """
## 8. 导出自包含交互网页

`include_plotlyjs=True` 会把 Plotly JavaScript 一并写入文件，所以网页较大，但离线双击也能缩放和悬停。`write_image` 是另一条静态导出链路，通常还需 Kaleido；本课不混用。
"""
        ),
        code(
            """
# 写出自包含 HTML，并检查文件存在、大小和关键 HTML 标记。
interactive_path = OUTPUT_DIR / "41_interactive_candlestick.html"
fig.write_html(
    interactive_path,
    include_plotlyjs=True,
    full_html=True,
)
html_head = interactive_path.read_text(encoding="utf-8")[:500]

print("已写入:", interactive_path)
print("文件大小:", round(interactive_path.stat().st_size / 1024 / 1024, 2), "MiB")

assert interactive_path.exists()
assert interactive_path.stat().st_size > 1_000_000
assert "<html" in html_head.lower()
assert "plotly" in html_head.lower()
"""
        ),
        md(
            """
### 在 Notebook / 静态报告中嵌入交互成品

下方 iframe 指向 `outputs/41_interactive_candlestick.html`。在 Jupyter 和导出的课程报告里都可直接操作；若单独移动报告文件，应同时保留 `outputs/` 的相对目录结构。
"""
        ),
        code(
            """
# 相对路径同时适用于 notebooks/ 和 reports/ 目录中的页面。
display(
    IFrame(
        src="../outputs/41_interactive_candlestick.html",
        width="100%",
        height=740,
    )
)
"""
        ),
        md(
            """
## 9. 量化意义与方法边界

- 交互图适合异常日复核、策略诊断和研究分享；静态图适合课件、PDF 和版本归档。
- K 线必须使用同一频率、同一时区、同一复权口径的 OHLC；不能把复权收盘与未复权开高低混在一根蜡烛中。
- `shared_xaxes=True` 不会检查数据索引；绘图前仍需显式对齐。
- SMA 是历史平滑指标，不是“平均持仓成本”的严格估计，也不保证穿越后继续上涨。
- 成交量放大不能仅凭 OHLCV 判断“主力买入”或交易者身份。
- 自包含 HTML 会携带完整悬停数据；真实项目发布前要检查敏感数据、版权和文件体积。
- 交互图帮助发现问题，不替代样本外验证、成本模型和统计检验。

## 10. 可复用结论与练习

可复用流程：

```text
OHLCV 契约 → 日期/字段断言 → 指标计算
           → Figure + Trace 分层 → 图层清单校验
           → 自包含 HTML → 浏览器交互复核
```

练习：

1. 把 `EV_A` 改为另一只模拟资产，仍保持四层日期完全一致。
2. 增加策略净值和回撤面板，但不要使用双轴制造视觉相关。
3. 将 160 日改为 756 日，比较可读性和 HTML 文件大小。
4. 故意打乱成交量日期，验证现有断言能够发现错位。
"""
        ),
    ]
    write_notebook(NOTEBOOKS / "41_Plotly交互K线.ipynb", cells)


def build_lesson_42():
    cells = [
        md(
            source_note(
                42,
                "mplfinance K 线、指标与信号标注",
                "42_youtube-xvHD9f4vHEE",
            )
        ),
        md(
            """
## 1. 本节量化问题

第 41 课用 Plotly 逐层搭交互图；本课改用专门面向 OHLCV 的 `mplfinance`，快速生成适合复盘归档的静态 K 线。

课程主线：

1. `mpf.plot(..., type="candle")` 画 K 线；
2. `mav=(5, 20, 60)` 与 `volume=True` 加均线和成交量；
3. `make_addplot` 叠加布林带与金叉/死叉；
4. `style` 和 `savefig` 生成高清图片；
5. 通过一个最小回测诊断说明：把交叉点画出来，不等于策略可盈利。
"""
        ),
        md(
            """
## 2. 输入、输出与验收

**输入**：`daily_prices.csv` 中虚构资产 `EV_A` 最近 220 个交易日。

**输出**

- 完整 K 线、5/20/60 日均线与成交量；
- 20 日布林带；
- 5/20 日金叉、死叉标记；
- `outputs/42_mplfinance_review.png` 高清静态图；
- 信号次数、换手与交易成本拖累的诊断表。

**验收**

- `DatetimeIndex` 唯一、升序；列名严格为 `Open/High/Low/Close/Volume`；
- OHLC 关系合法；
- 信号只在均线形成后出现，并保持原日期索引；
- 当日收盘生成信号，仓位从下一交易日收益开始生效；
- 输出图片存在且可读取。
"""
        ),
        code(COMMON_SETUP),
        code(
            """
# 本课新增 mplfinance；Image 用于在静态报告中显示已保存图片。
import mplfinance as mpf
from IPython.display import Image, display

print("mplfinance:", mpf.__version__)
"""
        ),
        md(
            """
## 3. 准备 mplfinance 数据契约

`mplfinance` 默认要求：

- 行索引是升序 `DatetimeIndex`；
- 列名为 `Open/High/Low/Close/Volume`；
- 每一行是一根同频率 K 线。

大小写、日期类型或排序错误都会导致报错或错图。
"""
        ),
        code(
            """
# 从完整模拟长表筛选单资产，并严格改成 mplfinance 所需列名。
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
price = (
    daily.loc[
        daily["symbol"].eq("EV_A"),
        ["date", "open", "high", "low", "close", "volume"],
    ]
    .sort_values("date")
    .set_index("date")
    .rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    .tail(220)
)

print("shape:", price.shape, "含义: 日期 × OHLCV")
print("区间:", price.index.min().date(), "→", price.index.max().date())
display(price.head(3))
display(price.tail(3))

assert isinstance(price.index, pd.DatetimeIndex)
assert price.index.is_unique and price.index.is_monotonic_increasing
assert price.columns.tolist() == ["Open", "High", "Low", "Close", "Volume"]
assert (price["High"] >= price[["Open", "Close"]].max(axis=1)).all()
assert (price["Low"] <= price[["Open", "Close"]].min(axis=1)).all()
assert price["Volume"].ge(0).all()
"""
        ),
        md(
            """
## 4. 一行接口：K 线、均线和成交量

`mav=(5, 20, 60)` 表示三条简单移动平均线；它们由收盘价计算。`volume=True` 创建成交量副图。`returnfig=True` 返回 Figure/Axes，便于继续加工和测试。
"""
        ),
        code(
            """
# 采用 A 股常见的红涨绿跌配色，并获得 Figure 供后续检查。
market_colors = mpf.make_marketcolors(
    up="#d62728",
    down="#2ca02c",
    edge="inherit",
    wick="inherit",
    volume="inherit",
)
course_style = mpf.make_mpf_style(
    base_mpf_style="yahoo",
    marketcolors=market_colors,
    rc={"font.family": chinese_font},
)

basic_fig, basic_axes = mpf.plot(
    price,
    type="candle",
    mav=(5, 20, 60),
    volume=True,
    style=course_style,
    title="EV_A 模拟行情｜K 线 + MAV + 成交量",
    ylabel="模拟价格",
    ylabel_lower="成交量",
    returnfig=True,
    figsize=(12, 7),
)

print("Axes 数量:", len(basic_axes))
assert len(basic_axes) >= 2
plt.close(basic_fig)
"""
        ),
        md(
            """
## 5. 布林带：先准确写出公式

20 日布林带（Bollinger Bands）的常见定义：

\\[
Middle_t = SMA_{20}(t)
\\]

\\[
Upper_t = Middle_t + 2\\sigma_{20}(t),\\quad
Lower_t = Middle_t - 2\\sigma_{20}(t)
\\]

这里 pandas `std()` 默认 `ddof=1`（样本标准差）。窗口 20、倍数 2 只是惯例，不是自然定律；价格触轨也不是确定性买卖信号。
"""
        ),
        code(
            """
# 计算 20 日中轨与样本标准差，再得到上下轨；前 19 日保持 NaN。
middle = price["Close"].rolling(20, min_periods=20).mean()
rolling_std = price["Close"].rolling(20, min_periods=20).std(ddof=1)
bollinger = pd.DataFrame(
    {
        "Middle": middle,
        "Upper": middle + 2 * rolling_std,
        "Lower": middle - 2 * rolling_std,
    },
    index=price.index,
)

display(bollinger.dropna().head(3).round(4))

assert bollinger.iloc[:19].isna().all().all()
assert (bollinger["Upper"].dropna() >= bollinger["Middle"].dropna()).all()
assert (bollinger["Middle"].dropna() >= bollinger["Lower"].dropna()).all()
"""
        ),
        md(
            """
## 6. 金叉与死叉：条件和时点

令快线为 5 日 SMA、慢线为 20 日 SMA：

- 金叉：今日 `SMA5 > SMA20`，昨日 `SMA5 <= SMA20`；
- 死叉：今日 `SMA5 < SMA20`，昨日 `SMA5 >= SMA20`。

信号本身落在计算完成的收盘日。若策略使用当日收盘价生成信号，不能再让该仓位赚取同一日收益；下面把仓位延迟一期。
"""
        ),
        code(
            """
# 先计算均线和“快线在慢线上方”的状态，再检测状态切换。
signals = pd.DataFrame(index=price.index)
signals["SMA5"] = price["Close"].rolling(5, min_periods=5).mean()
signals["SMA20"] = price["Close"].rolling(20, min_periods=20).mean()
signals["above"] = signals["SMA5"].gt(signals["SMA20"])
prior_above = signals["above"].shift(1, fill_value=False)
signals["golden_cross"] = signals["above"] & ~prior_above
signals["death_cross"] = ~signals["above"] & prior_above

# 长期均线尚未形成的日期不允许出现交叉信号。
valid_signal_window = signals["SMA20"].notna()
signals.loc[~valid_signal_window, ["golden_cross", "death_cross"]] = False

signal_dates = pd.concat(
    [
        signals.loc[signals["golden_cross"], ["SMA5", "SMA20"]].assign(事件="金叉"),
        signals.loc[signals["death_cross"], ["SMA5", "SMA20"]].assign(事件="死叉"),
    ]
).sort_index()

print("金叉次数:", int(signals["golden_cross"].sum()))
print("死叉次数:", int(signals["death_cross"].sum()))
display(signal_dates.head(10).round(4))

assert not (signals["golden_cross"] & signals["death_cross"]).any()
assert not signals.iloc[:19][["golden_cross", "death_cross"]].any().any()
assert signal_dates.index.isin(price.index).all()
"""
        ),
        md(
            """
## 7. `make_addplot`：指标和信号保持原日期索引

`make_addplot` 接受与主表等长、同索引的序列。没有信号的日期用 `NaN`，而不是删行；否则标记会落到错误日期。

金叉三角放在当日最低价下方，死叉三角放在最高价上方。它们是**信号发现日**标记，不声称可以在同一收盘价成交。
"""
        ),
        code(
            """
# 用 NaN 保留完整日期轴，只在信号日生成三角标记位置。
golden_marker = pd.Series(np.nan, index=price.index, name="金叉")
death_marker = pd.Series(np.nan, index=price.index, name="死叉")
golden_marker.loc[signals["golden_cross"]] = (
    price.loc[signals["golden_cross"], "Low"] * 0.97
)
death_marker.loc[signals["death_cross"]] = (
    price.loc[signals["death_cross"], "High"] * 1.03
)

add_plots = [
    mpf.make_addplot(bollinger["Middle"], color="#2f4f4f", width=1.0),
    mpf.make_addplot(bollinger["Upper"], color="#6a5acd", width=0.8),
    mpf.make_addplot(bollinger["Lower"], color="#6a5acd", width=0.8),
    mpf.make_addplot(
        golden_marker,
        type="scatter",
        marker="^",
        markersize=70,
        color="#d62728",
    ),
    mpf.make_addplot(
        death_marker,
        type="scatter",
        marker="v",
        markersize=70,
        color="#2ca02c",
    ),
]

assert golden_marker.notna().sum() == signals["golden_cross"].sum()
assert death_marker.notna().sum() == signals["death_cross"].sum()
pd.testing.assert_index_equal(golden_marker.index, price.index)
"""
        ),
        md(
            """
## 8. 高清导出并显示

`savefig` 中的 `dpi=160` 控制像素密度，`bbox_inches="tight"` 减少多余边缘。保存后关闭 Figure，避免批量生成报告时积累内存。
"""
        ),
        code(
            """
# 生成课程成品图；使用 addplot 叠加布林带和交叉信号。
from matplotlib.lines import Line2D

image_path = OUTPUT_DIR / "42_mplfinance_review.png"
review_fig, review_axes = mpf.plot(
    price,
    type="candle",
    mav=(5, 20, 60),
    mavcolors=("#1f77b4", "#ff8c00", "#2ca02c"),
    volume=True,
    addplot=add_plots,
    style=course_style,
    title="EV_A 模拟行情｜布林带与均线交叉（仅作诊断）",
    ylabel="模拟价格",
    ylabel_lower="成交量",
    returnfig=True,
    figsize=(14, 9),
    warn_too_much_data=500,
)

# mplfinance 不会自动为全部 addplot 生成易读图例，因此显式说明每条线和信号。
legend_handles = [
    Line2D([0], [0], color="#1f77b4", lw=1.2, label="MA5"),
    Line2D([0], [0], color="#ff8c00", lw=1.2, label="MA20"),
    Line2D([0], [0], color="#2ca02c", lw=1.2, label="MA60"),
    Line2D([0], [0], color="#2f4f4f", lw=1.0, label="布林中轨"),
    Line2D([0], [0], color="#6a5acd", lw=1.0, label="布林上下轨"),
    Line2D(
        [0], [0], marker="^", color="none", markerfacecolor="#d62728",
        markeredgecolor="#d62728", markersize=7, label="金叉信号日"
    ),
    Line2D(
        [0], [0], marker="v", color="none", markerfacecolor="#2ca02c",
        markeredgecolor="#2ca02c", markersize=7, label="死叉信号日"
    ),
]
review_axes[0].legend(
    handles=legend_handles,
    loc="upper left",
    ncol=3,
    fontsize=8,
    framealpha=0.88,
)

review_fig.savefig(image_path, dpi=160, bbox_inches="tight")
plt.close(review_fig)

print("已写入:", image_path)
print("文件大小:", round(image_path.stat().st_size / 1024, 1), "KiB")
assert image_path.exists()
assert image_path.stat().st_size > 50_000

display(Image(filename=str(image_path)))
"""
        ),
        md(
            """
## 9. 别把“画出信号”误当成“验证策略”

下面只做一个时序和成本诊断：

- 日收益：`Close.pct_change()`；
- 决策状态：快线在慢线上方；
- 执行仓位：决策状态 `shift(1)`，从下一日收益开始生效；
- 换手：仓位绝对变化；
- 成本：每次仓位变化按 10 bp（0.10%）扣减。

这仍不是完整 A 股回测：没有滑点、涨跌停、停牌、T+1、手续费最低额或复权事件。
"""
        ),
        code(
            """
# 用下一期仓位避免同日收盘信号偷取同日收益，并量化换手成本拖累。
diagnostic = pd.DataFrame(index=price.index)
diagnostic["asset_return"] = price["Close"].pct_change(fill_method=None)
diagnostic["decision"] = signals["above"].astype(float)
diagnostic["position"] = diagnostic["decision"].shift(1, fill_value=0.0)
diagnostic["turnover"] = diagnostic["position"].diff().abs().fillna(
    diagnostic["position"].abs()
)
diagnostic["gross_return"] = (
    diagnostic["position"] * diagnostic["asset_return"].fillna(0.0)
)
cost_rate = 0.001
diagnostic["net_return"] = (
    diagnostic["gross_return"] - diagnostic["turnover"] * cost_rate
)
diagnostic["gross_nav"] = (1 + diagnostic["gross_return"]).cumprod()
diagnostic["net_nav"] = (1 + diagnostic["net_return"]).cumprod()

summary = pd.Series(
    {
        "信号切换次数": int(diagnostic["turnover"].gt(0).sum()),
        "累计换手": diagnostic["turnover"].sum(),
        "期末毛净值": diagnostic["gross_nav"].iloc[-1],
        "期末净净值": diagnostic["net_nav"].iloc[-1],
        "成本拖累": diagnostic["gross_nav"].iloc[-1] - diagnostic["net_nav"].iloc[-1],
    },
    name="诊断结果",
)
display(summary.to_frame().round(6))

assert diagnostic["position"].iloc[0] == 0.0
assert diagnostic["gross_nav"].gt(0).all()
assert diagnostic["net_nav"].gt(0).all()
assert diagnostic["net_nav"].iloc[-1] <= diagnostic["gross_nav"].iloc[-1] + 1e-12
"""
        ),
        md(
            """
## 10. 量化意义与方法边界

- mplfinance 是 OHLCV 高层绘图工具；它减少样板代码，但不会验证复权、时区或可交易性。
- `mav` 是历史均线，不是未来预测；均线交叉在震荡期可能频繁反转并产生高换手。
- 布林带上/下轨是波动参照；触轨不等于必然反转。
- 图上的金叉/死叉是信号发现日，不等同于下单日和成交日。
- `Close`、`Open/High/Low` 必须使用兼容的复权口径，否则蜡烛结构会失真。
- 模拟数据只验证代码和时序；不能推断真实市场、真实证券或未来收益。
- 交易成本诊断不是完整回测，策略结论还需样本外、基准、参数稳定性和可执行性检验。

## 11. 可复用结论与练习

```text
OHLCV 契约 → 均线/布林带/事件计算
           → 同索引 NaN 信号序列 → make_addplot
           → 高清静态图 → 下一期执行与成本诊断
```

练习：

1. 将 5/20 日均线改为 10/60 日，比较信号次数、换手和成本拖累。
2. 将 `cost_rate` 设为 0、5 bp、20 bp，绘制净值差异。
3. 把信号标记从发现日改为下一交易日开盘执行日，并解释所需价格字段。
4. 把布林带参数从 `(20, 2)` 改为 `(40, 2.5)`，但不要用同一数据挑“最好看”的参数后宣称有效。
"""
        ),
    ]
    write_notebook(NOTEBOOKS / "42_mplfinance复盘图.ipynb", cells)
