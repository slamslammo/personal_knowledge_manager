#!/usr/bin/env python
"""Build P2 lessons 43–50 and integrated labs L3–L4."""

from __future__ import annotations

from build_first_batch import COMMON_SETUP, LABS, NOTEBOOKS, code, md, write_notebook


PACKAGES = {
    43: "43_youtube-c-HzVf8XECk",
    44: "44_youtube-7slVGsPS9_s",
    45: "45_youtube-7aCPO9jVHjI",
    46: "46_youtube-iePGy3ipV_0",
    47: "47_youtube-M46pgFS52KI",
    48: "48_youtube-KeYUHIKJ6MY",
    49: "49_youtube-II9gdYytXMk",
    50: "50_youtube-iBTEouhPvC4",
}


def source_note(number: int, title: str, data_note: str) -> str:
    return f"""
# 第 {number} 课｜{title}

本 Notebook 对应「365 天量化金融」第 {number} 课。课程方法来自本地完整视频、课件截图和本地 Whisper 口播整理；这里把它重建为默认离线、可核对、可重复执行的量化教学实现。

- 图文口播：`/Users/mojiawen/Documents/pam-video-captures/365-days-quant-finance/{PACKAGES[number]}/index.html`
- 环境：`pkm-quant`
- 数据：{data_note}
- 状态：可运行学习稿；不代表策略收益承诺

> 网络接口和研究计算分离：Notebook 默认不请求第三方服务。真实接口只作为适配层示意，计算使用带来源声明的本地快照，避免限流、字段变化和历史数据重算破坏复现。
"""


def end_note(items: str) -> str:
    return f"""
## 方法边界与复用结论

{items}

本课代码验证的是方法和数据契约，不是未来收益。迁移到真实研究前，还需重新核对来源授权、复权、时区、可得时间、交易成本和样本外边界。
"""


def build_43():
    cells = [
        md(source_note(43, "yfinance 数据适配与复权口径", "离线模拟行情；接口结构仿照 yfinance，非 Yahoo 真实数据")),
        md("""
## 本节量化问题

`yfinance.download` 的难点不是函数调用，而是三件事：批量下载的 MultiIndex 如何按标签读取、拆股/分红后应该使用哪种价格、接口失败如何形成可追溯状态。

本节输出：

1. 一个 yfinance 风格的 `字段 × 股票` MultiIndex 快照；
2. 原始收盘价与复权收盘价的拆股对照；
3. 带版本、参数、哈希和逐标的状态的缓存清单。
"""),
        code(COMMON_SETUP),
        md("""
## 1. 批量结果的 MultiIndex 不是普通二维列

yfinance 批量下载常把列组织为两层：第一层是 `Close/Volume` 等字段，第二层是股票代码。应使用 `vendor["Close"]` 按字段标签取得“日期 × 股票”矩阵，不能假设某一列位置永远是收盘价。
"""),
        code("""
# 把本地长表重排为 yfinance 风格的两层列，并显示原始结构。
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
sample = daily.loc[daily["symbol"].isin(["BANK_A", "EV_A", "TECH_A"])].copy()
parts = {
    "Close": sample.pivot(index="date", columns="symbol", values="close"),
    "Adj Close": sample.pivot(index="date", columns="symbol", values="adj_close"),
    "Volume": sample.pivot(index="date", columns="symbol", values="volume"),
}
vendor = pd.concat(parts, axis=1).sort_index()
vendor.columns.names = ["Price", "Ticker"]

print("列层级:", vendor.columns.names)
display(vendor.head(3))

close = vendor["Close"]
assert close.shape == (756, 3)
assert close.columns.tolist() == ["BANK_A", "EV_A", "TECH_A"]
"""),
        md("""
## 2. 复权价格处理拆股造成的机械跳变

下面在虚构资产上构造 2 拆 1：拆股日之后每股原始价格减半，但持股数翻倍，经济价值没有因此腰斩。`Adjusted Close` 把历史序列调整到可连续比较的口径。

标准化净值为 `NAV_t = P_t / P_0`。只有价格口径一致时，标准化曲线才可比较。
"""),
        code("""
# 构造拆股事件，比较原始价格收益与复权价格收益。
base = close["TECH_A"].iloc[:80].copy()
split_date = base.index[40]
raw_close = base.copy()
raw_close.loc[split_date:] = raw_close.loc[split_date:] / 2
adjusted_close = base.copy()
actions = pd.DataFrame({"Stock Splits": [2.0], "Dividends": [0.0]}, index=[split_date])

comparison = pd.DataFrame({
    "raw_close": raw_close,
    "adjusted_close": adjusted_close,
})
comparison["raw_return"] = comparison["raw_close"].pct_change()
comparison["adjusted_return"] = comparison["adjusted_close"].pct_change()
comparison["adjusted_nav"] = comparison["adjusted_close"] / comparison["adjusted_close"].iloc[0]

display(actions)
display(comparison.loc[split_date - pd.Timedelta(days=3): split_date + pd.Timedelta(days=3)])
assert comparison.loc[split_date, "raw_return"] < -0.45
assert abs(comparison.loc[split_date, "adjusted_return"]) < 0.10
"""),
        md("""
## 3. 缓存必须同时保存请求参数与失败状态

同一文件名不能说明使用了哪个 yfinance 版本、是否 `auto_adjust=True`、哪些代码为空。这里把参数、数据范围和 SHA-256 一起写入清单。真实适配器应对限流和空表分别记录，而不是把失败资产悄悄删掉。
"""),
        code("""
# 生成可追溯的离线缓存和逐标的状态。
import hashlib
import importlib.metadata as metadata

cache_path = OUTPUT_DIR / "43_yfinance_style_snapshot.csv"
vendor.to_csv(cache_path)
digest = hashlib.sha256(cache_path.read_bytes()).hexdigest()
status = pd.DataFrame([
    {"ticker": ticker, "status": "ok", "rows": int(close[ticker].notna().sum())}
    for ticker in close.columns
] + [{"ticker": "MISSING_DEMO", "status": "empty", "rows": 0}])
manifest = {
    "adapter": "yfinance-style-offline",
    "yfinance_version": metadata.version("yfinance"),
    "auto_adjust": False,
    "price_fields": ["Close", "Adj Close", "Volume"],
    "date_start": str(vendor.index.min().date()),
    "date_end": str(vendor.index.max().date()),
    "sha256": digest,
}
(OUTPUT_DIR / "43_yfinance_manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8"
)
display(status)
display(pd.Series(manifest, name="value").to_frame())
assert status.set_index("ticker").loc["MISSING_DEMO", "status"] == "empty"
assert len(digest) == 64
"""),
        md(end_note("""
- `download` 与 `Ticker.history` 的返回结构和默认值会随版本变化，必须固定参数并记录版本。
- `auto_adjust`、`Close`、`Adj Close` 的语义不能凭字段名猜测；公司行动要与 `actions` 抽查。
- yfinance 是非官方研究接口，限流、空表和部分失败属于数据质量状态。
""")),
    ]
    write_notebook(NOTEBOOKS / "43_yfinance数据适配与复权口径.ipynb", cells)


def build_44():
    cells = [
        md(source_note(44, "AkShare A股数据契约与时点", "离线构造的 A 股接口快照；非真实证券或财报数据")),
        md("""
## 本节量化问题

AkShare 同时覆盖行情、指数成分和财务数据，但三者的时间语义不同：

- 行情要记录 `adjust=qfq/hfq/none`；
- 指数权重要记录 `effective_date`；
- 财报要区分 `report_period`、`published_at` 和回测可用的 `available_at`。

本节用离线快照演示适配层如何把中文字段统一为稳定 schema。
"""),
        code(COMMON_SETUP),
        md("""
## 1. 适配器负责字段翻译，不让研究代码依赖网站列名

`rename` 把供应商中文字段转换为统一字段；`assign` 加入代码、复权和来源。后续计算只读取标准列，即使接口列名变化，也只修改适配器。
"""),
        code("""
# 构造 AkShare 风格中文响应，再规范为统一日线契约。
raw_ak = (
    pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
    .query("symbol == 'BANK_A'")
    .head(8)
    .rename(columns={
        "date": "日期", "open": "开盘", "high": "最高", "low": "最低",
        "close": "收盘", "volume": "成交量",
    })
)

def normalize_ak_daily(frame, symbol, adjust):
    mapping = {"日期": "date", "开盘": "open", "最高": "high", "最低": "low",
               "收盘": "close", "成交量": "volume"}
    result = frame.rename(columns=mapping)[list(mapping.values())].copy()
    result["symbol"] = symbol
    result["adjustment"] = adjust
    result["source"] = "akshare-style-offline"
    return result.sort_values("date").reset_index(drop=True)

bars = normalize_ak_daily(raw_ak, "DEMO_A", "qfq")
display(raw_ak.head(3))
display(bars.head(3))
assert bars.columns.tolist() == [
    "date", "open", "high", "low", "close", "volume",
    "symbol", "adjustment", "source",
]
assert bars["adjustment"].eq("qfq").all()
"""),
        md("""
## 2. 指数成分要按生效日期做 point-in-time 选择

`effective_date <= as_of_date` 表示只使用当时已经生效的权重。下面同一股票在两个季度有不同权重；如果直接取最新行，就会把未来调仓信息带回过去。
"""),
        code("""
# 选择研究日当时已生效的最新一组指数权重。
weights = pd.DataFrame({
    "effective_date": pd.to_datetime([
        "2024-01-01", "2024-01-01", "2024-04-01", "2024-04-01"
    ]),
    "symbol": ["DEMO_A", "DEMO_B", "DEMO_A", "DEMO_B"],
    "weight": [0.60, 0.40, 0.45, 0.55],
})
as_of_date = pd.Timestamp("2024-03-15")
valid_date = weights.loc[weights["effective_date"].le(as_of_date), "effective_date"].max()
point_in_time_weights = weights.loc[weights["effective_date"].eq(valid_date)].copy()

display(point_in_time_weights)
assert point_in_time_weights["weight"].sum() == 1.0
assert point_in_time_weights.set_index("symbol").loc["DEMO_A", "weight"] == 0.60
"""),
        md("""
## 3. 累计利润表不能直接当单季度值

A 股利润表常报告“年初至报告期”的累计金额。单季度值的规则是：

- 第一季度：`single_quarter = cumulative`；
- 后续季度：`single_quarter_t = cumulative_t - cumulative_{t-1}`；
- 跨年时重新从第一季度起算。

回测合并使用 `available_at`，而不是 `report_period`。
"""),
        code("""
# 从累计利润得到单季度利润，并保留公告可得时间。
financials = pd.DataFrame({
    "symbol": ["DEMO_A"] * 4,
    "report_period": pd.to_datetime(["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31"]),
    "published_at": pd.to_datetime(["2024-04-25", "2024-08-20", "2024-10-28", "2025-03-25"]),
    "cumulative_profit": [10.0, 23.0, 31.0, 48.0],
})
financials["available_at"] = financials["published_at"] + pd.Timedelta(days=1)
financials["fiscal_year"] = financials["report_period"].dt.year
financials["single_quarter_profit"] = (
    financials.groupby(["symbol", "fiscal_year"])["cumulative_profit"].diff()
    .fillna(financials["cumulative_profit"])
)

display(financials)
np.testing.assert_allclose(financials["single_quarter_profit"], [10, 13, 8, 17])
assert (financials["available_at"] > financials["report_period"]).all()
"""),
        md("""
## 4. 空表也是失败，不是“没有股票”

接口即使没有抛异常，也可能成功返回空表。适配器应把它记录为 `empty` 并阻断后续计算。
"""),
        code("""
# 把响应分成 ok、empty 和 schema_error 三种明确状态。
def inspect_response(frame, required):
    if frame.empty:
        return {"status": "empty", "rows": 0, "missing_columns": []}
    missing = sorted(set(required) - set(frame.columns))
    return {
        "status": "schema_error" if missing else "ok",
        "rows": len(frame),
        "missing_columns": missing,
    }

checks = pd.DataFrame([
    inspect_response(bars, ["date", "symbol", "close"]),
    inspect_response(pd.DataFrame(), ["date", "symbol", "close"]),
    inspect_response(bars.drop(columns="close"), ["date", "symbol", "close"]),
])
display(checks)
assert checks["status"].tolist() == ["ok", "empty", "schema_error"]
"""),
        md(end_note("""
- AkShare 聚合公开站点而非统一官方源，关键数据应与交易所和公司公告复核。
- qfq/hfq 的数值可能因后续公司行动重算；可复现研究必须保存快照。
- 指数成分、财报和行情都有各自的有效时间，不能统一用“日期”一个字段代替。
""")),
    ]
    write_notebook(NOTEBOOKS / "44_AkShare数据契约与时点.ipynb", cells)


def build_45():
    cells = [
        md(source_note(45, "SQLite 行情库与幂等增量", "离线模拟行情，写入本地教学数据库")),
        md("""
## 本节量化问题

`to_sql(if_exists="append")` 只会追加，不会自动去重。稳定行情库需要：

1. `PRIMARY KEY(symbol, date, adjustment)`；
2. 参数化查询和匹配查询模式的复合索引；
3. `UPSERT` 让重复同步幂等；
4. 事务保证一批更新要么全部成功、要么全部回滚。
"""),
        code(COMMON_SETUP),
        code("""
# sqlite3 属于 Python 标准库；数据库是可重复生成的实验产物。
import sqlite3

db_path = OUTPUT_DIR / "45_market_data.sqlite"
if db_path.exists():
    db_path.unlink()
connection = sqlite3.connect(db_path)
print("数据库:", db_path)
"""),
        md("""
## 1. 先建约束，再写数据

唯一键包含复权口径，因为同一股票同一天的原始价、前复权价不是同一条记录。`CHECK` 约束在写入阶段阻止明显非法价格和成交量。
"""),
        code("""
# 建立行情表和“股票 + 日期”查询索引。
connection.executescript(\"\"\"
CREATE TABLE prices (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    adjustment TEXT NOT NULL,
    open REAL NOT NULL CHECK(open > 0),
    high REAL NOT NULL CHECK(high > 0),
    low REAL NOT NULL CHECK(low > 0),
    close REAL NOT NULL CHECK(close > 0),
    volume INTEGER NOT NULL CHECK(volume >= 0),
    source TEXT NOT NULL,
    PRIMARY KEY (symbol, date, adjustment)
);
CREATE INDEX idx_prices_symbol_date ON prices(symbol, date);
\"\"\")
schema = pd.read_sql_query("PRAGMA table_info(prices)", connection)
display(schema[["name", "type", "notnull", "pk"]])
assert {"symbol", "date", "adjustment", "close"}.issubset(schema["name"])
"""),
        md("""
## 2. UPSERT 让重复同步不重复插入

`ON CONFLICT ... DO UPDATE` 以唯一键定位已有行。下面把同一批数据写两次，行数仍保持不变；这就是本实验的幂等性证据。
"""),
        code("""
# 准备 12 行标准记录，并定义参数化 UPSERT。
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
batch = (
    daily.query("symbol == 'BANK_A'")
    .head(12)
    .assign(
        date=lambda x: x["date"].dt.strftime("%Y-%m-%d"),
        adjustment="none",
        source="fixture",
    )
)
columns = ["symbol", "date", "adjustment", "open", "high", "low", "close", "volume", "source"]
sql = \"\"\"
INSERT INTO prices(symbol,date,adjustment,open,high,low,close,volume,source)
VALUES(?,?,?,?,?,?,?,?,?)
ON CONFLICT(symbol,date,adjustment) DO UPDATE SET
  open=excluded.open, high=excluded.high, low=excluded.low,
  close=excluded.close, volume=excluded.volume, source=excluded.source
\"\"\"
records = list(batch[columns].itertuples(index=False, name=None))
with connection:
    connection.executemany(sql, records)
with connection:
    connection.executemany(sql, records)

row_count = connection.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
print("重复写入两次后的行数:", row_count)
assert row_count == len(batch) == 12
"""),
        md("""
## 3. 参数化查询与查询计划

问号 `?` 是参数占位符，值不会被拼进 SQL 文本。`EXPLAIN QUERY PLAN` 用于确认“股票 + 日期区间”查询命中索引，而不是凭小数据耗时猜测。
"""),
        code("""
# 按代码和日期区间查询，并检查 SQLite 的执行计划。
query = \"\"\"
SELECT symbol,date,close,volume
FROM prices
WHERE symbol=? AND date>=? AND date<=?
ORDER BY date
\"\"\"
params = ("BANK_A", "2023-01-05", "2023-01-13")
result = pd.read_sql_query(query, connection, params=params, parse_dates=["date"])
plan = connection.execute("EXPLAIN QUERY PLAN " + query, params).fetchall()

display(result)
display(pd.DataFrame(plan, columns=["id", "parent", "unused", "detail"]))
assert result["date"].is_monotonic_increasing
assert any("idx_prices_symbol_date" in row[-1] for row in plan)
"""),
        md("""
## 4. 事务失败必须回滚整批

第二行故意写入负价格，触发 `CHECK`。由于两行在同一个 `with connection:` 事务内，前一行也不会残留。
"""),
        code("""
# 捕获教学性完整性错误，并验证原子回滚。
before = connection.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
bad_records = [
    ("DEMO_A", "2025-01-02", "none", 10, 11, 9, 10.5, 100, "demo"),
    ("DEMO_A", "2025-01-03", "none", 10, 11, 9, -1.0, 100, "demo"),
]
try:
    with connection:
        connection.executemany(sql, bad_records)
except sqlite3.IntegrityError as exc:
    print("已捕获并回滚:", type(exc).__name__)

after = connection.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
print("事务前/后行数:", before, after)
assert before == after
connection.close()
"""),
        md(end_note("""
- SQLite 适合单机、读多写少的研究库；高并发写入需换更合适的数据库。
- 索引提高读性能但占空间并降低写速，应按真实查询模式建立。
- 数据库文件仍需备份、版本和来源清单；“存进数据库”不等于数据可信。
""")),
    ]
    write_notebook(NOTEBOOKS / "45_SQLite行情库与幂等增量.ipynb", cells)


def build_46():
    cells = [
        md(source_note(46, "可复现量化数据流水线", "离线模拟行情；每阶段输出状态和哈希")),
        md("""
## 本节量化问题

把脚本拆成函数不等于可靠流水线。稳定边界是：

```text
config → fetch → clean/validate → analyze → plot → manifest
```

每个阶段职责单一，由数据契约连接；一个标的失败时保留其状态，不能伪装成整批成功。
"""),
        code(COMMON_SETUP),
        md("""
## 1. 配置是输入，不应散落在代码中

配置集中记录标的、日期、价格字段和输出版本。哈希把配置内容压缩成可追踪标识；内容变化时哈希也变化。
"""),
        code("""
# 创建稳定排序的配置，并计算 SHA-256。
import hashlib

config = {
    "symbols": ["BANK_A", "EV_A", "MISSING_A"],
    "start": "2024-01-01",
    "end": "2025-12-31",
    "price_field": "adj_close",
    "pipeline_version": 1,
}
config_text = json.dumps(config, ensure_ascii=False, sort_keys=True)
config_hash = hashlib.sha256(config_text.encode()).hexdigest()
display(pd.Series({**config, "config_hash": config_hash[:12]}, name="value").to_frame())
"""),
        md("""
## 2. 四个函数只通过明确 DataFrame 契约连接

- `fetch` 只读取快照并按标的筛选；
- `clean` 检查必需列、唯一键、排序和正价格；
- `analyze` 计算区间收益、最大回撤和观测数；
- `plot` 只消费分析阶段已经生成的净值表。
"""),
        code("""
# 实现职责单一的四阶段函数。
def fetch_snapshot(symbol):
    frame = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
    result = frame.loc[frame["symbol"].eq(symbol)].copy()
    if result.empty:
        raise LookupError(f"{symbol}: empty snapshot")
    return result

def clean_bars(frame):
    required = {"date", "symbol", "adj_close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    result = frame.sort_values(["symbol", "date"]).reset_index(drop=True)
    assert not result.duplicated(["symbol", "date"]).any()
    assert result["adj_close"].gt(0).all()
    return result

def analyze_bars(frame):
    prices = frame.set_index("date")["adj_close"]
    nav = prices / prices.iloc[0]
    drawdown = nav / nav.cummax() - 1
    metrics = {
        "rows": len(frame),
        "start": str(frame["date"].min().date()),
        "end": str(frame["date"].max().date()),
        "interval_return": float(nav.iloc[-1] - 1),
        "max_drawdown": float(drawdown.min()),
    }
    return metrics, pd.DataFrame({"nav": nav, "drawdown": drawdown})

def plot_analysis(result_table, symbol):
    axis = result_table["nav"].plot(figsize=(8, 3), title=f"{symbol} 模拟净值")
    axis.set(xlabel="日期", ylabel="净值")
    axis.grid(alpha=0.2)
    figure = axis.figure
    figure.tight_layout()
    output = OUTPUT_DIR / f"46_{symbol}_nav.png"
    figure.savefig(output, dpi=140)
    plt.close(figure)
    return output
"""),
        md("""
## 3. 编排器记录逐标的证据

`run_one` 负责串联阶段和捕获错误，返回统一状态。输出表同时包含成功和失败资产，便于断点续跑。
"""),
        code("""
# 批量运行；单个空资产只标记失败，不影响其余结果。
def run_one(symbol):
    try:
        raw = fetch_snapshot(symbol)
        clean = clean_bars(raw)
        metrics, result_table = analyze_bars(clean)
        chart = plot_analysis(result_table, symbol)
        return {"symbol": symbol, "status": "ok", **metrics, "chart": chart.name, "error": ""}
    except Exception as exc:
        return {"symbol": symbol, "status": "failed", "error": str(exc)}

statuses = pd.DataFrame([run_one(symbol) for symbol in config["symbols"]])
display(statuses)
assert statuses["status"].tolist() == ["ok", "ok", "failed"]
assert statuses.loc[statuses["status"].eq("ok"), "rows"].eq(756).all()
"""),
        md("""
## 4. Manifest 让结果可重跑

清单保存配置哈希、阶段状态和输入数据哈希。这里的输入是固定快照；如果快照内容变化，即使文件名相同也会被发现。
"""),
        code("""
# 保存流水线清单；JSON 使用稳定字段，便于后续比较。
input_path = DATA_DIR / "daily_prices.csv"
manifest = {
    "pipeline": "lesson-46-offline",
    "config": config,
    "config_sha256": config_hash,
    "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
    "status": statuses.fillna("").to_dict(orient="records"),
}
manifest_path = OUTPUT_DIR / "46_pipeline_manifest.json"
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
print("已写入:", manifest_path)
assert manifest_path.exists()
assert len(manifest["input_sha256"]) == 64
"""),
        md(end_note("""
- 单一职责不是函数越小越好；边界应围绕稳定的数据语义。
- 图表和指标必须消费同一结果表，避免展示与计算口径分叉。
- 真实批处理还需重试、日志、缓存、增量水位和失败恢复。
""")),
    ]
    write_notebook(NOTEBOOKS / "46_可复现量化数据流水线.ipynb", cells)


def build_47():
    cells = [
        md(source_note(47, "技术指标公式与可执行时点", "离线模拟 OHLCV；指标由 pandas 手工实现")),
        md("""
## 本节量化问题

MA、RSI、MACD、ATR 都是历史价格的确定性变换。重点不是记住默认参数，而是明确公式、窗口、NaN 与信号何时可成交。
"""),
        code(COMMON_SETUP),
        md("""
## 1. 用可手算序列核对 MA 和 RSI

- `SMA_n`：最近 n 个收盘价的算术平均；
- `RSI_n = 100 - 100/(1+RS)`；
- `RS = 平均上涨幅度 / 平均下跌幅度`。

`min_periods=n` 表示窗口未满时保留 NaN，不用短样本冒充完整指标。
"""),
        code("""
# 先用 6 个价格展示 3 日均线和 RSI 的中间量。
small = pd.Series([100, 102, 101, 104, 106, 103], name="close", dtype=float)
delta = small.diff()
gain = delta.clip(lower=0)
loss = -delta.clip(upper=0)
sma3 = small.rolling(3, min_periods=3).mean()
avg_gain = gain.rolling(3, min_periods=3).mean()
avg_loss = loss.rolling(3, min_periods=3).mean()
rsi3 = 100 - 100 / (1 + avg_gain / avg_loss)

check = pd.DataFrame({"close": small, "delta": delta, "gain": gain, "loss": loss, "SMA3": sma3, "RSI3": rsi3})
display(check)
assert sma3.iloc[2] == (100 + 102 + 101) / 3
"""),
        md("""
## 2. 在完整 OHLCV 上实现 MA、RSI、MACD 与 ATR

`ewm(span, adjust=False)` 计算递归 EMA。ATR 的 True Range 同时考虑日内高低与隔夜跳空，量纲是价格金额，不是方向。
"""),
        code("""
# 构造完整指标表，并保留窗口未满产生的 NaN。
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
bars = daily.query("symbol == 'EV_A'").sort_values("date").set_index("date").copy()
close = bars["close"]
delta = close.diff()
gain = delta.clip(lower=0)
loss = -delta.clip(upper=0)

bars["MA20"] = close.rolling(20, min_periods=20).mean()
bars["MA60"] = close.rolling(60, min_periods=60).mean()
avg_gain = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
avg_loss = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
bars["RSI14"] = 100 - 100 / (1 + avg_gain / avg_loss)
ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
bars["DIF"] = ema12 - ema26
bars["DEA"] = bars["DIF"].ewm(span=9, adjust=False, min_periods=9).mean()
bars["MACD_hist"] = bars["DIF"] - bars["DEA"]
previous_close = close.shift(1)
true_range = pd.concat([
    bars["high"] - bars["low"],
    (bars["high"] - previous_close).abs(),
    (bars["low"] - previous_close).abs(),
], axis=1).max(axis=1)
bars["ATR14"] = true_range.ewm(alpha=1/14, adjust=False, min_periods=14).mean()

display(bars[["close", "MA20", "RSI14", "DIF", "DEA", "MACD_hist", "ATR14"]].tail())
assert bars["MA20"].iloc[:19].isna().all()
assert bars["ATR14"].dropna().gt(0).all()
"""),
        md("""
## 3. 当日收盘形成的信号要到下一期执行

`raw_signal_t` 使用 t 日收盘后才能确定。策略收益写为

`strategy_return_t = position_{t-1} × asset_return_t - cost_t`。

因此 `position = raw_signal.shift(1)`；不做这一步会假设能够以已经知道的收盘价成交。
"""),
        code("""
# 比较错误的同收盘成交与向后移动一日的可执行信号。
features = bars.dropna(subset=["MA20", "MA60"]).copy()
features["asset_return"] = features["close"].pct_change(fill_method=None)
features["raw_signal"] = (features["MA20"] > features["MA60"]).astype(int)
features["position"] = features["raw_signal"].shift(1).fillna(0)
features["turnover"] = features["position"].diff().abs().fillna(features["position"].abs())
features["strategy_return"] = (
    features["position"] * features["asset_return"] - 0.001 * features["turnover"]
)
features["wrong_same_close_return"] = features["raw_signal"] * features["asset_return"]

display(features[["close", "MA20", "MA60", "raw_signal", "position", "strategy_return"]].head())
assert features["position"].iloc[1] == features["raw_signal"].iloc[0]
"""),
        md("""
## 4. 图表区分指标发现日与持有收益
"""),
        code("""
# 绘制价格均线和 RSI；图表只做诊断，不把阈值当作投资建议。
fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
bars[["close", "MA20", "MA60"]].tail(220).plot(ax=axes[0], title="EV_A 模拟价格与移动平均")
bars["RSI14"].tail(220).plot(ax=axes[1], title="RSI(14)", color="tab:purple")
axes[1].axhline(70, color="tab:red", linestyle="--", label="常用参考 70")
axes[1].axhline(30, color="tab:green", linestyle="--", label="常用参考 30")
axes[0].set_ylabel("模拟价格")
axes[1].set_ylabel("RSI")
axes[1].set_xlabel("日期")
axes[1].legend()
fig.tight_layout()
fig.savefig(OUTPUT_DIR / "47_indicators.png", dpi=150)
plt.show()
"""),
        md(end_note("""
- RSI 70/30 是常用参数，不是上涨或下跌概率。
- 多个价格指标可能高度相关，“共振”不等于独立证据。
- 指标公式正确不代表策略可实现；成交时点、成本和参数稳定性仍需样本外检验。
""")),
    ]
    write_notebook(NOTEBOOKS / "47_技术指标公式与可执行时点.ipynb", cells)


def build_48():
    cells = [
        md(source_note(48, "SciPy 厚尾收益与极端风险", "固定随机种子的厚尾模拟收益；用于分布检验")),
        md("""
## 本节量化问题

正态模型用均值和标准差概括风险，但金融收益常见尖峰厚尾。这里比较 Normal Distribution（正态分布）、Student's t Distribution（学生 t 分布）和经验尾部计数。
"""),
        code(COMMON_SETUP),
        code("""
# 导入 SciPy 分布、拟合与检验工具。
from scipy import stats
print("SciPy stats ready")
"""),
        md("""
## 1. 先用已知自由度生成可重复厚尾样本

Student t 的自由度 `df` 越小尾越厚；`df <= 2` 时理论方差不存在。本例取 `df=4`，再缩放到约 1% 的日波动。
"""),
        code("""
# 生成固定种子的厚尾收益，并计算标准化 z 分数。
rng = np.random.default_rng(365)
returns = pd.Series(stats.t.rvs(df=4, size=3000, random_state=rng) * 0.008, name="return")
z = (returns - returns.mean()) / returns.std(ddof=1)
summary = returns.describe(percentiles=[0.001, 0.01, 0.05, 0.95, 0.99, 0.999])
display(summary.to_frame())
print("样本超额峰度:", round(stats.kurtosis(returns, fisher=True), 3))
assert len(returns) == 3000
assert stats.kurtosis(returns, fisher=True) > 0
"""),
        md("""
## 2. 拟合正态与 t 分布

- `stats.norm.fit` 返回 `loc, scale`；
- `stats.t.fit` 返回 `df, loc, scale`；
- 拟合参数来自同一样本，所以普通 K–S p 值只能作为诊断，不能当严格的“模型已被证明”。
"""),
        code("""
# 拟合两种分布，并比较对数似然和经验分位数。
normal_loc, normal_scale = stats.norm.fit(returns)
t_df, t_loc, t_scale = stats.t.fit(returns)
ll_normal = stats.norm.logpdf(returns, normal_loc, normal_scale).sum()
ll_t = stats.t.logpdf(returns, t_df, t_loc, t_scale).sum()
fit_table = pd.DataFrame({
    "model": ["Normal", "Student-t"],
    "location": [normal_loc, t_loc],
    "scale": [normal_scale, t_scale],
    "df": [np.nan, t_df],
    "log_likelihood": [ll_normal, ll_t],
})
display(fit_table)
print("拟合 t 自由度:", round(t_df, 2))
assert t_df > 2
"""),
        md("""
## 3. 直接比较 3σ 左尾的理论次数与实际次数

正态预测次数约为 `N × Φ(-3)`。实际计数来自标准化收益 `z < -3`。这比只看直方图更直接地暴露尾部低估。
"""),
        code("""
# 计算正态理论次数、t 拟合次数和实际左尾事件数。
k = 3
n = len(z)
actual = int((z < -k).sum())
normal_expected = n * stats.norm.cdf(-k)
t_threshold = (returns.mean() - k * returns.std(ddof=1) - t_loc) / t_scale
t_expected = n * stats.t.cdf(t_threshold, t_df)
tail_table = pd.DataFrame({
    "口径": ["正态理论", "t 拟合", "实际样本"],
    "3σ左尾次数": [normal_expected, t_expected, actual],
})
display(tail_table)
assert actual >= 0
"""),
        md("""
## 4. Bootstrap 给经验 1% 分位数一个不确定区间

Bootstrap 对原样本有放回重采样，每次计算 1% 分位数。区间反映有限样本估计误差，但不能创造样本中从未出现的危机机制。
"""),
        code("""
# 用固定种子重复抽样，估计经验 1% VaR 分位数区间。
bootstrap_rng = np.random.default_rng(366)
quantiles = np.array([
    np.quantile(bootstrap_rng.choice(returns.to_numpy(), size=n, replace=True), 0.01)
    for _ in range(400)
])
interval = np.quantile(quantiles, [0.025, 0.5, 0.975])
print("1% 分位数 Bootstrap 95% 区间/中位数:", np.round(interval, 5))
assert interval[0] <= interval[1] <= interval[2]
"""),
        code("""
# 绘制经验密度与两种拟合密度，重点观察尾部而非只看中心。
x = np.linspace(returns.quantile(0.002), returns.quantile(0.998), 500)
fig, ax = plt.subplots(figsize=(9, 4.5))
ax.hist(returns, bins=70, density=True, alpha=0.35, label="厚尾模拟收益")
ax.plot(x, stats.norm.pdf(x, normal_loc, normal_scale), label="Normal fit")
ax.plot(x, stats.t.pdf(x, t_df, t_loc, t_scale), label=f"Student-t fit (df={t_df:.1f})")
ax.set(title="收益分布：正态与 Student-t", xlabel="日收益率", ylabel="概率密度")
ax.legend()
fig.tight_layout()
fig.savefig(OUTPUT_DIR / "48_fat_tail_fit.png", dpi=150)
plt.show()
"""),
        md(end_note("""
- 同样本估参后再做普通 K–S 检验会影响 p 值分布，严格检验需参数修正、Bootstrap 或样本外数据。
- 静态 t 分布仍不能表达波动聚集和成串危机事件。
- 风险报告应同时给经验分位数、尾部计数和压力情景，不能只给正态 VaR。
""")),
    ]
    write_notebook(NOTEBOOKS / "48_SciPy厚尾收益与极端风险.ipynb", cells)


def build_49():
    cells = [
        md(source_note(49, "statsmodels 因子回归与稳健推断", "固定随机种子的模拟因子与资产收益")),
        md("""
## 本节量化问题

因子回归把资产超额收益拆成 Alpha、市场/风格暴露和残差。本节不仅输出系数，还同时输出标准误、t 值、p 值、置信区间、R² 和滚动稳定性。
"""),
        code(COMMON_SETUP),
        code("""
# statsmodels 的公式接口负责 OLS；HAC 用于时间序列稳健标准误。
import statsmodels.api as sm
import statsmodels.formula.api as smf
import statsmodels
print("statsmodels:", statsmodels.__version__)
"""),
        md("""
## 1. 构造已知真值的三因子样本

模型为：

`asset_excess = alpha + beta_m*MKT + beta_s*SMB + beta_h*HML + epsilon`

因为真实参数由我们设置，回归结果可以与真值核对；这比拿未知真实数据只看 p 值更适合学习。
"""),
        code("""
# 生成 756 日因子和带自相关噪声的模拟资产超额收益。
rng = np.random.default_rng(365)
n = 756
dates = pd.bdate_range("2023-01-03", periods=n)
factors = pd.DataFrame({
    "MKT": rng.normal(0.0003, 0.010, n),
    "SMB": rng.normal(0.0000, 0.006, n),
    "HML": rng.normal(0.0000, 0.005, n),
}, index=dates)
epsilon = np.zeros(n)
innovations = rng.normal(0, 0.007, n)
for i in range(1, n):
    epsilon[i] = 0.25 * epsilon[i - 1] + innovations[i]
true_params = {"Intercept": 0.00015, "MKT": 1.10, "SMB": 0.35, "HML": -0.20}
factors["asset_excess"] = (
    true_params["Intercept"] + 1.10 * factors["MKT"]
    + 0.35 * factors["SMB"] - 0.20 * factors["HML"] + epsilon
)
display(factors.head())
"""),
        md("""
## 2. OLS 系数与 HAC/Newey–West 标准误

HAC 不改变 OLS 系数点估计，只调整标准误和推断。`maxlags=5` 是本例的日频演示参数，不是通用最优值。
"""),
        code("""
# 拟合三因子回归，并用 HAC 协方差重新计算推断。
ols = smf.ols("asset_excess ~ MKT + SMB + HML", data=factors).fit()
hac = ols.get_robustcov_results(cov_type="HAC", maxlags=5)
names = ols.model.exog_names
result = pd.DataFrame({
    "estimate": hac.params,
    "std_error_HAC": hac.bse,
    "t_value": hac.tvalues,
    "p_value": hac.pvalues,
}, index=names)
confidence = pd.DataFrame(hac.conf_int(), index=names, columns=["ci_low", "ci_high"])
result = result.join(confidence)
result["true_value"] = pd.Series(true_params)

display(result)
print("R²:", round(ols.rsquared, 4))
print("日 Alpha 简单年化:", f"{result.loc['Intercept', 'estimate'] * 252:.2%}")
assert abs(result.loc["MKT", "estimate"] - 1.10) < 0.15
"""),
        md("""
## 3. Alpha、Beta、R² 回答不同问题

- Alpha：控制因子后的截距；
- Beta：条件平均敏感度；
- R²：样本内收益变异的解释比例。

R² 高不代表收益高，Alpha 显著也不自动代表可交易超额。
"""),
        code("""
# 用一张解释表防止混用三个指标。
interpretation = pd.DataFrame([
    {"指标": "Alpha", "本例数值": result.loc["Intercept", "estimate"], "回答": "控制因子后的平均截距"},
    {"指标": "Market Beta", "本例数值": result.loc["MKT", "estimate"], "回答": "市场变化 1 单位时的条件变化"},
    {"指标": "R²", "本例数值": ols.rsquared, "回答": "样本内被模型解释的变异比例"},
])
display(interpretation)
"""),
        md("""
## 4. 滚动回归检查暴露是否稳定

固定窗口只使用窗口内样本。下面每 20 日估计一次最近 126 日市场 Beta；这是诊断区间稳定性，不是预测未来 Beta。
"""),
        code("""
# 用 126 日窗口滚动估计市场 Beta，减少图中重复点。
rolling_rows = []
window = 126
for end in range(window, len(factors) + 1, 20):
    sample = factors.iloc[end - window:end]
    fit = smf.ols("asset_excess ~ MKT + SMB + HML", data=sample).fit()
    rolling_rows.append({"date": sample.index[-1], "MKT_beta": fit.params["MKT"]})
rolling_beta = pd.DataFrame(rolling_rows).set_index("date")
axis = rolling_beta.plot(figsize=(9, 3.5), title="126 日滚动市场 Beta（模拟数据）")
axis.axhline(1.10, color="black", linestyle="--", label="生成真值 1.10")
axis.set(xlabel="窗口结束日", ylabel="Beta")
axis.legend()
axis.figure.tight_layout()
axis.figure.savefig(OUTPUT_DIR / "49_rolling_beta.png", dpi=150)
plt.show()
assert len(rolling_beta) > 20
"""),
        md(end_note("""
- 金融误差常有异方差和自相关，时间序列推断应考虑 HAC 或更完整模型。
- 因子暴露会漂移，整段回归只是区间平均。
- 显著 Alpha 仍可能来自遗漏因子、数据挖掘、成本或不可交易暴露。
""")),
    ]
    write_notebook(NOTEBOOKS / "49_statsmodels因子回归与稳健推断.ipynb", cells)


def build_50():
    cells = [
        md(source_note(50, "scikit-learn 防泄漏时序分类", "离线模拟日线；用于时间序列机器学习方法验证")),
        md("""
## 本节量化问题

预测明日涨跌时，特征只能使用 t 日及以前信息，标签是 `y_t = 1[r_{t+1}>0]`。预处理必须只在训练折拟合，验证必须保持时间顺序，最终策略收益还要把信号延迟和成本纳入。
"""),
        code(COMMON_SETUP),
        code("""
# 导入时序切分、Pipeline、标准化和逻辑回归。
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, balanced_accuracy_score
import sklearn
print("scikit-learn:", sklearn.__version__)
"""),
        md("""
## 1. 特征与标签的时间方向

特征使用历史收益、滚动波动率和均线偏离；标签用 `return.shift(-1)` 指向下一日。最后一行没有未来标签，因此删除。这里不使用 centered rolling，也不从未来回填 NaN。
"""),
        code("""
# 构造 point-in-time 特征表，并显示标签对齐关系。
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
asset = daily.query("symbol == 'TECH_A'").sort_values("date").set_index("date")
frame = pd.DataFrame(index=asset.index)
frame["return_1d"] = asset["adj_close"].pct_change(fill_method=None)
frame["return_5d"] = asset["adj_close"].pct_change(5, fill_method=None)
frame["vol_20d"] = frame["return_1d"].rolling(20, min_periods=20).std()
frame["ma_gap_20d"] = asset["adj_close"] / asset["adj_close"].rolling(20, min_periods=20).mean() - 1
frame["next_return"] = frame["return_1d"].shift(-1)
frame["label"] = (frame["next_return"] > 0).astype(int)
dataset = frame.dropna().copy()
features = ["return_1d", "return_5d", "vol_20d", "ma_gap_20d"]

display(dataset[features + ["next_return", "label"]].head())
assert dataset.index.is_monotonic_increasing
assert dataset["next_return"].iloc[0] == frame["return_1d"].shift(-1).loc[dataset.index[0]]
"""),
        md("""
## 2. Pipeline 把标准化锁在每个训练折内部

`Pipeline` 依次在训练折执行 `StandardScaler.fit_transform` 和模型 `fit`，测试折只调用 `transform/predict`。随机 `shuffle` 不适用于这里。
"""),
        code("""
# 使用扩展窗口 TimeSeriesSplit 生成样本外预测。
X = dataset[features]
y = dataset["label"]
splitter = TimeSeriesSplit(n_splits=5)
oof_probability = pd.Series(np.nan, index=dataset.index, name="probability")
fold_rows = []

for fold, (train_idx, test_idx) in enumerate(splitter.split(X), start=1):
    model = Pipeline([
        ("scale", StandardScaler()),
        ("logit", LogisticRegression(max_iter=1000, random_state=365)),
    ])
    model.fit(X.iloc[train_idx], y.iloc[train_idx])
    probability = model.predict_proba(X.iloc[test_idx])[:, 1]
    oof_probability.iloc[test_idx] = probability
    fold_rows.append({
        "fold": fold,
        "train_end": X.index[train_idx[-1]].date(),
        "test_start": X.index[test_idx[0]].date(),
        "test_end": X.index[test_idx[-1]].date(),
        "train_rows": len(train_idx),
        "test_rows": len(test_idx),
    })

folds = pd.DataFrame(fold_rows)
display(folds)
assert (pd.to_datetime(folds["train_end"]) < pd.to_datetime(folds["test_start"])).all()
"""),
        md("""
## 3. 分类指标必须与基线比较

多数类基线总是预测训练/评价样本中更常见的类别。Accuracy 受类别比例影响，因此同时报告 Balanced Accuracy。
"""),
        code("""
# 仅在有样本外预测的日期评价，并与多数类基线比较。
evaluation = dataset.loc[oof_probability.notna()].copy()
evaluation["probability"] = oof_probability.dropna()
evaluation["prediction"] = (evaluation["probability"] >= 0.5).astype(int)
majority_class = int(evaluation["label"].mean() >= 0.5)
baseline = np.full(len(evaluation), majority_class)
metrics = pd.Series({
    "model_accuracy": accuracy_score(evaluation["label"], evaluation["prediction"]),
    "model_balanced_accuracy": balanced_accuracy_score(evaluation["label"], evaluation["prediction"]),
    "baseline_accuracy": accuracy_score(evaluation["label"], baseline),
    "positive_rate": evaluation["label"].mean(),
    "observations": len(evaluation),
})
display(metrics.to_frame("value"))
assert evaluation["probability"].between(0, 1).all()
"""),
        md("""
## 4. 分类结果要转成可执行、成本后的策略

预测是在 t 日特征完成后得到，持仓从下一日开始。`position = prediction.shift(1)`，成本按持仓变化绝对值收取。策略使用的是当日资产收益，不是标签中的下一日收益直接乘同日预测。
"""),
        code("""
# 把样本外预测向后移动一日，并与 Buy & Hold 比较。
evaluation["asset_return"] = frame.loc[evaluation.index, "return_1d"]
evaluation["position"] = evaluation["prediction"].shift(1).fillna(0)
evaluation["turnover"] = evaluation["position"].diff().abs().fillna(evaluation["position"].abs())
evaluation["strategy_return"] = (
    evaluation["position"] * evaluation["asset_return"] - 0.001 * evaluation["turnover"]
)
evaluation["strategy_nav"] = (1 + evaluation["strategy_return"]).cumprod()
evaluation["buy_hold_nav"] = (1 + evaluation["asset_return"]).cumprod()

axis = evaluation[["strategy_nav", "buy_hold_nav"]].plot(
    figsize=(9, 4), title="样本外净值：逻辑回归 vs Buy & Hold（模拟数据）"
)
axis.set(xlabel="日期", ylabel="净值")
axis.grid(alpha=0.2)
axis.figure.tight_layout()
axis.figure.savefig(OUTPUT_DIR / "50_oof_strategy.png", dpi=150)
plt.show()
assert evaluation["position"].iloc[1] == evaluation["prediction"].iloc[0]
"""),
        md(end_note("""
- 轻微高于 50% 的准确率可能是噪声或类别不平衡，需跨时期、跨标的和置信区间验证。
- Accuracy 忽略涨跌幅大小；交易成本和少数大行情可能完全改变收益结果。
- 特征重要性不等于因果或稳定预测能力；所有变换都必须在每个训练折内部拟合。
""")),
    ]
    write_notebook(NOTEBOOKS / "50_sklearn防泄漏时序分类.ipynb", cells)


def build_l3():
    cells = [
        md("""
# L3 综合实验｜数据获取、存储与报告

本实验整合第 43–46 课：离线数据适配器 → schema 校验 → SQLite 幂等写入 → 指标与图表 → 可追溯清单。

- 环境：`pkm-quant`
- 数据：固定模拟日线，适配器名称仅模拟 yfinance/AkShare 返回结构
- 输出：`outputs/L3_market_store.sqlite`、`L3_data_report.csv/png/json`
- 状态：可运行学习稿
"""),
        md("""
## 1. 研究任务与验收

统一两个“供应商”的列名和复权口径，将结果写入唯一键数据库；重复运行不增加行数；报告同时说明成功资产、失败资产、日期范围、区间收益、最大回撤和输入哈希。
"""),
        code(COMMON_SETUP),
        code("""
# 导入本地存储和哈希工具。
import sqlite3
import hashlib
"""),
        md("""
## 2. 两个适配器输出相同的数据契约

研究层只接收 `date/symbol/adjustment/close/volume/source`。接口自身的中文列、MultiIndex 或默认参数不进入后续逻辑。
"""),
        code("""
# 从同一离线快照模拟两个不同供应商，再标准化为统一长表。
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])

def adapt_global(symbol):
    raw = daily.loc[daily["symbol"].eq(symbol), ["date", "adj_close", "volume"]].copy()
    if raw.empty:
        raise LookupError(f"{symbol}: empty")
    return raw.rename(columns={"adj_close": "close"}).assign(
        symbol=symbol, adjustment="total-return-like", source="global-offline"
    )[["date", "symbol", "adjustment", "close", "volume", "source"]]

def adapt_a_share(symbol):
    raw = daily.loc[daily["symbol"].eq(symbol), ["date", "close", "volume"]].copy()
    if raw.empty:
        raise LookupError(f"{symbol}: empty")
    return raw.assign(
        symbol=symbol, adjustment="qfq-demo", source="a-share-offline"
    )[["date", "symbol", "adjustment", "close", "volume", "source"]]

frames, status_rows = [], []
for source, symbol, adapter in [
    ("global", "TECH_A", adapt_global),
    ("a_share", "BANK_A", adapt_a_share),
    ("a_share", "MISSING_A", adapt_a_share),
]:
    try:
        result = adapter(symbol)
        frames.append(result)
        status_rows.append({"source": source, "symbol": symbol, "status": "ok", "rows": len(result)})
    except Exception as exc:
        status_rows.append({"source": source, "symbol": symbol, "status": "failed", "rows": 0, "error": str(exc)})

normalized = pd.concat(frames, ignore_index=True)
statuses = pd.DataFrame(status_rows)
display(normalized.head())
display(statuses)
assert normalized.columns.tolist() == ["date", "symbol", "adjustment", "close", "volume", "source"]
assert statuses["status"].tolist() == ["ok", "ok", "failed"]
"""),
        md("""
## 3. SQLite 唯一键与 UPSERT

重复执行同一批次后行数应等于唯一业务键数量，而不是写入次数。
"""),
        code("""
# 建库并把同一批次 UPSERT 两次，验证幂等。
db_path = OUTPUT_DIR / "L3_market_store.sqlite"
if db_path.exists():
    db_path.unlink()
with sqlite3.connect(db_path) as conn:
    conn.execute(\"\"\"
        CREATE TABLE prices(
          date TEXT, symbol TEXT, adjustment TEXT, close REAL, volume INTEGER, source TEXT,
          PRIMARY KEY(symbol,date,adjustment)
        )
    \"\"\")
    sql = \"\"\"INSERT INTO prices VALUES(?,?,?,?,?,?)
             ON CONFLICT(symbol,date,adjustment) DO UPDATE SET
             close=excluded.close, volume=excluded.volume, source=excluded.source\"\"\"
    records = [
        (str(row.date.date()), row.symbol, row.adjustment, row.close, row.volume, row.source)
        for row in normalized.itertuples(index=False)
    ]
    conn.executemany(sql, records)
    conn.executemany(sql, records)
    stored = pd.read_sql_query("SELECT * FROM prices ORDER BY date,symbol", conn, parse_dates=["date"])

print("输入/存储/唯一键:", len(normalized), len(stored), len(normalized.drop_duplicates(["symbol", "date", "adjustment"])))
assert len(stored) == len(normalized)
"""),
        md("""
## 4. 同一结果表驱动指标、图表和清单
"""),
        code("""
# 按资产计算净值、区间收益和最大回撤。
wide = stored.pivot(index="date", columns="symbol", values="close").sort_index()
nav = wide / wide.iloc[0]
drawdown = nav / nav.cummax() - 1
report = pd.DataFrame({
    "start": wide.apply(lambda s: s.first_valid_index()),
    "end": wide.apply(lambda s: s.last_valid_index()),
    "rows": wide.notna().sum(),
    "interval_return": nav.iloc[-1] - 1,
    "max_drawdown": drawdown.min(),
})
report_path = OUTPUT_DIR / "L3_data_report.csv"
report.to_csv(report_path)
display(report)

axis = nav.plot(figsize=(9, 4), title="L3 数据管道标准化净值（模拟数据）")
axis.set(xlabel="日期", ylabel="净值")
axis.grid(alpha=0.2)
axis.figure.tight_layout()
chart_path = OUTPUT_DIR / "L3_data_report.png"
axis.figure.savefig(chart_path, dpi=150)
plt.show()
"""),
        code("""
# 保存输入哈希、配置、逐资产状态和产物路径。
input_path = DATA_DIR / "daily_prices.csv"
manifest = {
    "lab": "L3",
    "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
    "database": db_path.name,
    "report": report_path.name,
    "chart": chart_path.name,
    "statuses": statuses.fillna("").to_dict(orient="records"),
}
manifest_path = OUTPUT_DIR / "L3_data_report.json"
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
assert all(path.exists() for path in [db_path, report_path, chart_path, manifest_path])
print("L3 验收通过")
"""),
        md(end_note("""
- 本实验的两个适配器都读取模拟快照，不代表真实 Yahoo/AkShare 结果。
- 真实系统要增加限流、重试、断点水位、数据授权和一手来源复核。
- 区间收益与回撤只用于验证流水线，不能评价虚构资产。
""")),
    ]
    write_notebook(LABS / "L3_数据获取存储与报告.ipynb", cells)


def build_l4():
    cells = [
        md("""
# L4 综合实验｜防泄漏统计建模

本实验整合第 47–50 课：历史技术特征 → 厚尾风险诊断 → 因子归因 → 时间序列机器学习 → 延迟信号和成本后回测。

- 环境：`pkm-quant`
- 数据：固定模拟行情及由其构造的因子；非真实证券
- 输出：`outputs/L4_model_metrics.csv`、`L4_oof_nav.png`
"""),
        md("""
## 1. 验收原则

1. 所有滚动特征只使用当时及以前数据；
2. 标签明确指向下一日；
3. TimeSeriesSplit 中训练结束早于测试开始；
4. 模型预测只在样本外日期评价；
5. 持仓使用上一期预测并扣除换手成本；
6. 收益同时报告厚尾分位数和因子归因。
"""),
        code(COMMON_SETUP),
        code("""
# 导入统计、因子回归和机器学习工具。
from scipy import stats
import statsmodels.api as sm
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, balanced_accuracy_score
"""),
        md("""
## 2. 构造无未来信息的研究表

技术特征在 t 日收盘后已知，`next_return` 属于 t+1 日标签。删掉 NaN 后仍要保留日期顺序。
"""),
        code("""
# 从模拟价格生成技术特征和下一日标签。
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
prices = daily.pivot(index="date", columns="symbol", values="adj_close").sort_index()
asset_return = prices["TECH_A"].pct_change(fill_method=None)
market_return = prices.pct_change(fill_method=None).mean(axis=1)
research = pd.DataFrame(index=prices.index)
research["ret1"] = asset_return
research["ret5"] = prices["TECH_A"].pct_change(5, fill_method=None)
research["vol20"] = asset_return.rolling(20, min_periods=20).std()
research["ma_gap"] = prices["TECH_A"] / prices["TECH_A"].rolling(20, min_periods=20).mean() - 1
research["market"] = market_return
research["next_return"] = asset_return.shift(-1)
research["label"] = (research["next_return"] > 0).astype(int)
research = research.dropna()
features = ["ret1", "ret5", "vol20", "ma_gap"]
display(research.head())
assert research.index.is_monotonic_increasing
"""),
        md("""
## 3. 风险与因子层先描述样本，再进入预测
"""),
        code("""
# 报告经验尾部与市场模型，不把静态分布当成预测器。
tail = pd.Series({
    "mean": research["ret1"].mean(),
    "std": research["ret1"].std(),
    "1%_quantile": research["ret1"].quantile(0.01),
    "excess_kurtosis": stats.kurtosis(research["ret1"]),
})
factor_sample = research[["ret1", "market"]]
factor_model = sm.OLS(factor_sample["ret1"], sm.add_constant(factor_sample["market"])).fit(
    cov_type="HAC", cov_kwds={"maxlags": 5}
)
factor = pd.Series({
    "alpha_daily": factor_model.params["const"],
    "market_beta": factor_model.params["market"],
    "r_squared": factor_model.rsquared,
})
display(tail.to_frame("value"))
display(factor.to_frame("value"))
"""),
        md("""
## 4. 时序样本外预测与成本后净值
"""),
        code("""
# 每折单独拟合 Pipeline，生成 out-of-fold 概率。
X = research[features]
y = research["label"]
oof = pd.Series(np.nan, index=research.index)
fold_audit = []
for fold, (train_idx, test_idx) in enumerate(TimeSeriesSplit(n_splits=5).split(X), start=1):
    model = Pipeline([
        ("scale", StandardScaler()),
        ("model", LogisticRegression(max_iter=1000, random_state=365)),
    ])
    model.fit(X.iloc[train_idx], y.iloc[train_idx])
    oof.iloc[test_idx] = model.predict_proba(X.iloc[test_idx])[:, 1]
    fold_audit.append((X.index[train_idx[-1]], X.index[test_idx[0]]))

evaluation = research.loc[oof.notna()].copy()
evaluation["prediction"] = (oof.dropna() >= 0.5).astype(int)
evaluation["position"] = evaluation["prediction"].shift(1).fillna(0)
evaluation["turnover"] = evaluation["position"].diff().abs().fillna(evaluation["position"].abs())
evaluation["strategy_return"] = evaluation["position"] * evaluation["ret1"] - 0.001 * evaluation["turnover"]
evaluation["strategy_nav"] = (1 + evaluation["strategy_return"]).cumprod()
evaluation["buy_hold_nav"] = (1 + evaluation["ret1"]).cumprod()

assert all(train_end < test_start for train_end, test_start in fold_audit)
assert evaluation["position"].iloc[1] == evaluation["prediction"].iloc[0]
"""),
        code("""
# 汇总模型、风险和归因指标，并保存图表。
metrics = pd.Series({
    "accuracy": accuracy_score(evaluation["label"], evaluation["prediction"]),
    "balanced_accuracy": balanced_accuracy_score(evaluation["label"], evaluation["prediction"]),
    "positive_rate": evaluation["label"].mean(),
    "strategy_return": evaluation["strategy_nav"].iloc[-1] - 1,
    "buy_hold_return": evaluation["buy_hold_nav"].iloc[-1] - 1,
    "empirical_1pct": tail["1%_quantile"],
    "market_beta": factor["market_beta"],
})
metrics_path = OUTPUT_DIR / "L4_model_metrics.csv"
metrics.to_frame("value").to_csv(metrics_path)
display(metrics.to_frame("value"))

axis = evaluation[["strategy_nav", "buy_hold_nav"]].plot(
    figsize=(9, 4), title="L4 样本外净值（模拟数据）"
)
axis.set(xlabel="日期", ylabel="净值")
axis.grid(alpha=0.2)
axis.figure.tight_layout()
chart_path = OUTPUT_DIR / "L4_oof_nav.png"
axis.figure.savefig(chart_path, dpi=150)
plt.show()
assert metrics_path.exists() and chart_path.exists()
"""),
        md(end_note("""
- 本实验用于验证防泄漏流程，不追求得到正收益。
- 因子模型是区间归因，分类模型是条件预测，两者不能混为因果结论。
- 真实策略还需多标的、跨时期、概率校准、容量、滑点和置信区间。
""")),
    ]
    write_notebook(LABS / "L4_防泄漏统计建模.ipynb", cells)


def main():
    build_43()
    build_44()
    build_45()
    build_46()
    build_47()
    build_48()
    build_49()
    build_50()
    build_l3()
    build_l4()


if __name__ == "__main__":
    main()
