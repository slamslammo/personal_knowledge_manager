"""Code cells for the six P1 module labs."""

from __future__ import annotations


def lab_cells(lab_id: str) -> list[tuple[str, str, str]]:
    cells = {
        "L1": [
            (
                "把交易想法改写为研究假设卡",
                "一张有效假设卡至少包含资产、机制、可观察预测、反证条件、持有周期和执行约束。",
                """
hypothesis = pd.Series({
    "research_question": "SIM_GROWTH 的中期趋势是否能在成本后优于 SIM_MARKET？",
    "asset_universe": "SIM_GROWTH；基准 SIM_MARKET",
    "mechanism": "投资者反应不足可能导致信息逐步进入价格",
    "observable_prediction": "过去 60 日趋势为正时，下一月超额收益均值较高",
    "falsifier": "样本外超额收益不为正，或成本后优势消失",
    "holding_period": "20 个交易日",
    "execution": "收盘形成信号，下一交易日成交",
    "data_identity": "固定种子模拟行情，仅用于方法演示",
})
display(hypothesis.to_frame("内容"))
""",
            ),
        ],
        "L2": [
            (
                "建立收益—风险账本",
                "账本同时保存资产收益、基准、组合权重、成本口径和风险指标，避免只展示一个年化数字。",
                """
from src.quant_core import annualized_return, annualized_volatility, max_drawdown

daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
close = daily.pivot(index="date", columns="symbol", values="adj_close").sort_index()
returns = close.pct_change(fill_method=None).dropna()

assets = ["SIM_VALUE", "SIM_GROWTH", "SIM_DEFENSIVE"]
weights = pd.Series([0.35, 0.35, 0.30], index=assets)
portfolio = returns[assets].mul(weights, axis="columns").sum(axis=1)
covariance = returns[assets].cov()
variance_matrix = float(weights @ covariance @ weights)

ledger = pd.Series({
    "annual_return": annualized_return(portfolio),
    "annual_volatility": annualized_volatility(portfolio),
    "max_drawdown": max_drawdown(portfolio),
    "daily_variance_from_matrix": variance_matrix,
    "daily_variance_from_series": portfolio.var(ddof=1),
})
np.testing.assert_allclose(ledger["daily_variance_from_matrix"], ledger["daily_variance_from_series"])
display(ledger.to_frame("value"))
""",
            ),
        ],
        "L3": [
            (
                "按时间切分统计证据",
                "同一信号同时检查效应大小、t 检验、市场 Beta 和样本外方向；不把一个 p 值当作结论。",
                """
import statsmodels.api as sm
from scipy import stats

daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
close = daily.pivot(index="date", columns="symbol", values="adj_close").sort_index()
returns = close.pct_change(fill_method=None)
signal = close["SIM_GROWTH"].pct_change(20).shift(1)
strategy = np.sign(signal) * returns["SIM_GROWTH"]
dataset = pd.concat([
    strategy.rename("strategy"),
    returns["SIM_MARKET"].rename("market"),
], axis=1).dropna()

split = int(len(dataset) * 0.7)
train, test = dataset.iloc[:split], dataset.iloc[split:]
test_result = stats.ttest_1samp(test["strategy"], 0.0)
model = sm.OLS(test["strategy"], sm.add_constant(test[["market"]])).fit(cov_type="HAC", cov_kwds={"maxlags": 5})

audit = pd.Series({
    "train_mean_bps": train["strategy"].mean() * 10_000,
    "test_mean_bps": test["strategy"].mean() * 10_000,
    "test_pvalue": test_result.pvalue,
    "test_beta": model.params["market"],
    "test_alpha_bps": model.params["const"] * 10_000,
    "test_observations": len(test),
})
display(audit.to_frame("value"))
""",
            ),
        ],
        "L4": [
            (
                "分开真实世界情景与风险中性定价",
                "左侧使用主观漂移模拟未来现价，右侧使用风险中性 Black–Scholes 价格；两种概率不能混称。",
                """
from src.quant_core import black_scholes_call, black_scholes_greeks

rng = np.random.default_rng(365)
spot, mu, sigma, maturity = 100.0, 0.06, 0.25, 0.5
terminal = spot * np.exp((mu - 0.5 * sigma**2) * maturity + sigma * np.sqrt(maturity) * rng.standard_normal(20_000))
strike = 105.0
physical_exercise_probability = np.mean(terminal > strike)
model_price = black_scholes_call(spot, strike, maturity, 0.02, sigma)
greeks = black_scholes_greeks(spot, strike, maturity, 0.02, sigma)

display(pd.Series({
    "physical_exercise_probability_under_mu": physical_exercise_probability,
    "risk_neutral_bs_price": model_price,
    **greeks,
}))
""",
            ),
        ],
        "L5": [
            (
                "从订单簿得到规模相关成本",
                "对多个下单量穿透卖盘，计算 VWAP 和相对中间价滑点，再判断毛信号是否覆盖成本。",
                """
book = pd.read_csv(DATA_DIR / "order_book.csv")
bids = book.loc[book["side"] == "bid"].sort_values("price", ascending=False)
asks = book.loc[book["side"] == "ask"].sort_values("price")
mid = (bids.iloc[0]["price"] + asks.iloc[0]["price"]) / 2.0

def execute_buy(quantity):
    remaining, notional = quantity, 0.0
    for row in asks.itertuples():
        take = min(remaining, int(row.quantity))
        notional += take * row.price
        remaining -= take
        if remaining == 0:
            return notional / quantity
    return np.nan

gross_alpha_bps = 18.0
fee_bps = 2.0
rows = []
for quantity in [100, 500, 1_000, 1_800]:
    vwap = execute_buy(quantity)
    slippage_bps = (vwap / mid - 1.0) * 10_000 if np.isfinite(vwap) else np.nan
    rows.append({
        "quantity": quantity,
        "vwap": vwap,
        "slippage_bps": slippage_bps,
        "net_alpha_bps": gross_alpha_bps - fee_bps - slippage_bps,
    })
display(pd.DataFrame(rows))
""",
            ),
        ],
        "L6": [
            (
                "生成最终报告所需的统一证据表",
                "报告同时使用策略、基准、风险、成本和数据契约。缺少任一字段时应视为未完成，而不是留空交付。",
                """
from src.quant_core import performance_summary

daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
close = daily.pivot(index="date", columns="symbol", values="adj_close").sort_index()
asset_return = close["SIM_VALUE"].pct_change(fill_method=None)
benchmark = close["SIM_MARKET"].pct_change(fill_method=None)
signal = (close["SIM_VALUE"].rolling(20).mean() > close["SIM_VALUE"].rolling(60).mean()).astype(float)
position = signal.shift(1).fillna(0.0)
turnover = position.diff().abs().fillna(position.abs())
strategy = position * asset_return - turnover * 0.0005

metrics = performance_summary(strategy, benchmark)
contract = {
    "identity": "synthetic",
    "frequency": "1 business day",
    "timezone": "Asia/Shanghai (teaching convention)",
    "adjustment": "simulated adjusted close",
    "signal_time": "close t",
    "earliest_position_time": "t+1",
    "cost_per_turnover": 0.0005,
}

required_metric_fields = {
    "strategy_annual_return", "benchmark_annual_return",
    "strategy_annual_volatility", "max_drawdown", "beta",
}
assert required_metric_fields.issubset(metrics.index)
assert all(contract.values())
display(metrics.to_frame("value"))
display(pd.Series(contract).to_frame("value"))
""",
            ),
            (
                "写出可归档策略报告",
                "HTML 文件是阶段产物；能力矩阵用于指出仍未通过的实盘、稳健性和工程要求。",
                """
metric_rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in metrics.items())
contract_rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in contract.items())
html = f\"\"\"<!doctype html><meta charset='utf-8'>
<title>P1 策略研究报告</title>
<h1>P1 策略研究报告</h1>
<h2>研究假设</h2><p>模拟价值资产的中期趋势是否产生基准和成本后的收益。</p>
<h2>数据契约</h2><table>{contract_rows}</table>
<h2>收益、风险与基准</h2><table>{metric_rows}</table>
<h2>执行与成本</h2><p>收盘形成信号，下一交易日持仓；单位换手成本 5 bps。</p>
<h2>方法边界</h2><p>固定种子模拟行情；未完成参数稳健性、容量、税费、模拟盘和实盘风控。</p>
\"\"\"
path = OUTPUT_DIR / "L6_p1_strategy_report.html"
path.write_text(html, encoding="utf-8")
print("已生成:", path)
""",
            ),
        ],
    }
    return cells[lab_id]

