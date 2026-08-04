"""Lesson-specific notebook cells for P1.

Each entry is a list of ``(heading, explanation, code)`` tuples.  The build
script wraps these cells with common course positioning and boundary sections.
"""

from __future__ import annotations


CODE_LESSONS = {*range(4, 25), *range(26, 30)}


FORMULAS = {
    4: "归一化净值：I_t = P_t / P_0。只有统一起点后，价格路径才可比较。",
    5: "简单收益 R_t=P_t/P_(t-1)-1；对数收益 r_t=ln(P_t)-ln(P_(t-1))；累计收益 ∏(1+R_t)-1。",
    6: "FV=PV(1+r)^N；NPV(r)=Σ CF_t/(1+r)^t；IRR 是使 NPV=0 的折现率。",
    7: "样本方差 s²=Σ(R_t-R̄)²/(n-1)；年化波动率 σ_ann=s_daily√252。",
    8: "Cov(X,Y)=E[(X-μx)(Y-μy)]；ρ=Cov(X,Y)/(σxσy)；组合方差 w'Σw。",
    9: "R_strategy=α+βR_market+ε；β=Cov(R_strategy,R_market)/Var(R_market)。",
    10: "Z=(X-μ)/σ；正态密度由均值 μ 和标准差 σ 决定。",
    11: "超额峰度 κ=E[((X-μ)/σ)^4]-3；厚尾表现为远端分位数和极端概率高于正态基准。",
    12: "√n(X̄-μ)/σ 在经典条件下依分布收敛到 N(0,1)。",
    13: "t=(R̄-μ0)/(s/√n)；p 值是在原假设成立时得到当前或更极端统计量的概率。",
    14: "R²=1-SSE/SST；样本外 R² 使用测试集误差与测试集均值基准比较。",
    15: "弱平稳要求均值、方差和只依赖滞后的协方差稳定；ADF 检验原假设为存在单位根。",
    16: "ρ_k=Corr(R_t,R_(t-k))；Ljung–Box 联合检验前若干阶自相关是否为零。",
    17: "蒙特卡洛估计 E[g(X)]≈(1/M)Σg(X_m)，标准误通常按 1/√M 下降。",
    18: "GBM：dS/S=μdt+σdW；离散精确步进 S_(t+Δ)=S_t exp[(μ-σ²/2)Δ+σ√ΔZ]。",
    19: "一周期二叉树风险中性概率 q=(e^(rΔt)-d)/(u-d)；价格=e^(-rΔt)E_Q[payoff]。",
    20: "欧式看涨：C=S N(d1)-K e^(-rT)N(d2)。",
    21: "Delta=∂V/∂S，Gamma=∂²V/∂S²，Theta=∂V/∂t，Vega=∂V/∂σ。",
    22: "中间价=(best bid+best ask)/2；价差=best ask-best bid；不平衡=(bid depth-ask depth)/(bid depth+ask depth)。",
    23: "成本后收益=毛收益-费用-价差成本-滑点-市场冲击；冲击通常随成交规模非线性增加。",
    24: "连续竞价通常先按价格排序，再按同价位进入时间排序；成交量=min(买方剩余量,卖方剩余量)。",
    26: "数据契约不是公式，而是 source、as_of、timezone、frequency、adjustment、schema 和许可的共同约束。",
    27: "总回报复权因子需同时反映拆股与现金分红；研究收益和成交回放必须保留不同价格列。",
    28: "OHLCV 聚合：Open=first，High=max，Low=min，Close=last，Volume=sum。",
    29: "净策略收益=持仓×下一期资产收益-换手×单位成本；所有指标必须与同频基准对齐。",
}


def lesson_cells(number: int) -> list[tuple[str, str, str]]:
    """Return lesson-specific teaching cells."""

    cells: dict[int, list[tuple[str, str, str]]] = {
        4: [
            (
                "从价格表得到可比净值",
                "先查看长表字段，再把 `date × symbol` 重排为价格矩阵。归一化只改变比较基准，不改变单期收益。",
                """
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
print("原始长表字段:", daily.columns.tolist())
display(daily.head(8))

close = daily.pivot(index="date", columns="symbol", values="adj_close").sort_index()
normalized = close.divide(close.iloc[0], axis="columns")

assert np.allclose(normalized.iloc[0], 1.0)
display(normalized.head())
""",
            ),
            (
                "比较资产路径",
                "`axis='columns'` 表示每一列除以该列自己的首日价格。图中比较的是模拟资产的相对路径，不是价格高低。",
                """
ax = normalized.plot(figsize=(9, 4), title="Normalized simulated asset paths")
ax.set_ylabel("Wealth index (start = 1)")
ax.set_xlabel("Date")
plt.tight_layout()
plt.show()
""",
            ),
        ],
        5: [
            (
                "用三个价格手算两种收益",
                "简单收益先做价格比再减 1；对数收益先取自然对数再做差。小数组用于核对运算顺序。",
                """
prices_small = np.array([100.0, 105.0, 102.0])
simple_small = prices_small[1:] / prices_small[:-1] - 1.0
log_small = np.log(prices_small[1:]) - np.log(prices_small[:-1])

print("简单收益:", np.round(simple_small, 6))
print("对数收益:", np.round(log_small, 6))
assert np.isclose(np.prod(1.0 + simple_small) - 1.0, 102.0 / 100.0 - 1.0)
""",
            ),
            (
                "在完整行情上核对累计收益",
                "Pandas 保留日期和资产标签；累计简单收益用连乘，对数收益用累加后再指数还原，两者应一致。",
                """
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
close = daily.pivot(index="date", columns="symbol", values="adj_close").sort_index()
simple = close.pct_change(fill_method=None)
log_ret = np.log(close).diff()

cum_simple = (1.0 + simple).prod() - 1.0
cum_log = np.exp(log_ret.sum()) - 1.0
np.testing.assert_allclose(cum_simple, cum_log, rtol=1e-10)
display(pd.DataFrame({"simple_compounded": cum_simple, "log_reconstructed": cum_log}))
""",
            ),
        ],
        6: [
            (
                "复利与贴现是一对逆运算",
                "同一利率和期限下，先复利再贴现应回到原始本金。",
                """
present_value = 10_000.0
annual_rate = 0.08
years = 10

future_value = present_value * (1.0 + annual_rate) ** years
discounted_back = future_value / (1.0 + annual_rate) ** years

print(f"10 年后价值: {future_value:,.2f}")
print(f"贴现回今天: {discounted_back:,.2f}")
assert np.isclose(discounted_back, present_value)
""",
            ),
            (
                "NPV 使用外部折现率，IRR 由现金流反求",
                "现金流第 0 期为投入。这里用 `brentq` 在给定区间寻找使 NPV 为零的根；区间和现金流符号变化都会影响是否有解。",
                """
from scipy.optimize import brentq

cashflows = np.array([-1_000.0, 380.0, 420.0, 460.0])

def npv(rate, flows):
    periods = np.arange(len(flows))
    return np.sum(flows / (1.0 + rate) ** periods)

required_return = 0.06
project_npv = npv(required_return, cashflows)
project_irr = brentq(lambda rate: npv(rate, cashflows), -0.99, 2.0)

print(f"NPV @ 6%: {project_npv:.2f}")
print(f"IRR: {project_irr:.2%}")
assert abs(npv(project_irr, cashflows)) < 1e-8
""",
            ),
        ],
        7: [
            (
                "从日收益得到方差、波动和回撤",
                "样本标准差使用 `ddof=1`。年化波动假设收益频率稳定且近似独立；最大回撤从累计净值的历史峰值计算。",
                """
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
market = daily.loc[daily["symbol"] == "SIM_MARKET"].set_index("date")["adj_close"]
returns = market.pct_change(fill_method=None).dropna()

daily_variance = returns.var(ddof=1)
annual_volatility = returns.std(ddof=1) * np.sqrt(252)
nav = (1.0 + returns).cumprod()
drawdown = nav / nav.cummax() - 1.0

print(f"日方差: {daily_variance:.8f}")
print(f"年化波动: {annual_volatility:.2%}")
print(f"最大回撤: {drawdown.min():.2%}")
""",
            ),
            (
                "滚动波动随市场状态变化",
                "20 日窗口只使用当日及之前的 20 个观测；它是历史估计，不是未来波动承诺。",
                """
rolling_volatility = returns.rolling(window=20, min_periods=20).std(ddof=1) * np.sqrt(252)
ax = rolling_volatility.plot(figsize=(9, 3.8), title="20-day annualized volatility")
ax.set_ylabel("Annualized volatility")
plt.tight_layout()
plt.show()
""",
            ),
        ],
        8: [
            (
                "协方差、相关性和组合方差",
                "先用 Pandas 按日期与资产标签得到收益矩阵，再进入矩阵运算。`weights @ covariance @ weights` 是二次型。",
                """
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
close = daily.pivot(index="date", columns="symbol", values="adj_close").sort_index()
returns = close.pct_change(fill_method=None).dropna()

covariance = returns.cov()
pearson = returns.corr(method="pearson")
spearman = returns.corr(method="spearman")
weights = pd.Series(1.0 / returns.shape[1], index=returns.columns)
portfolio_variance = float(weights @ covariance @ weights)

print(f"等权组合日方差: {portfolio_variance:.8f}")
display(pearson.round(3))
display((spearman - pearson).round(3).head())
""",
            ),
        ],
        9: [
            (
                "用市场收益解释策略收益",
                "`add_constant` 增加截距 α；Beta 是市场收益系数。稳健标准误只修正推断，不改变 OLS 点估计。",
                """
import statsmodels.api as sm

daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
close = daily.pivot(index="date", columns="symbol", values="adj_close").sort_index()
returns = close.pct_change(fill_method=None).dropna()

y = returns["SIM_GROWTH"]
X = sm.add_constant(returns[["SIM_MARKET"]])
model = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 5})

result = pd.Series({
    "alpha_daily": model.params["const"],
    "beta_market": model.params["SIM_MARKET"],
    "r_squared": model.rsquared,
    "alpha_pvalue_hac": model.pvalues["const"],
})
display(result)
""",
            ),
        ],
        10: [
            (
                "把正态分布当作基准而不是事实",
                "使用样本均值和标准差构造同参数正态基准，再比较偏度、峰度与正态性检验。",
                """
from scipy import stats

daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
market = daily.loc[daily["symbol"] == "SIM_MARKET"].set_index("date")["adj_close"]
returns = market.pct_change(fill_method=None).dropna()

mu, sigma = returns.mean(), returns.std(ddof=1)
jb = stats.jarque_bera(returns)
diagnostics = pd.Series({
    "mean": mu,
    "std": sigma,
    "skew": stats.skew(returns, bias=False),
    "excess_kurtosis": stats.kurtosis(returns, fisher=True, bias=False),
    "jarque_bera_pvalue": jb.pvalue,
})
display(diagnostics)
""",
            ),
            (
                "比较经验直方图与正态密度",
                "横轴是日收益，纵轴是密度；拟合曲线只说明中心区域的基准形状。",
                """
x = np.linspace(returns.quantile(0.001), returns.quantile(0.999), 300)
fig, ax = plt.subplots(figsize=(8, 4))
ax.hist(returns, bins=40, density=True, alpha=0.55, label="Observed")
ax.plot(x, stats.norm.pdf(x, mu, sigma), label="Normal benchmark")
ax.set(title="Return distribution vs normal benchmark", xlabel="Daily return", ylabel="Density")
ax.legend()
plt.tight_layout()
plt.show()
""",
            ),
        ],
        11: [
            (
                "比较正态与 t 分布的尾部",
                "同一组收益分别拟合正态和 Student-t。用高分位阈值比较模型给出的双尾概率。",
                """
from scipy import stats

daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
market = daily.loc[daily["symbol"] == "SIM_MARKET"].set_index("date")["adj_close"]
returns = market.pct_change(fill_method=None).dropna()

normal_params = stats.norm.fit(returns)
t_params = stats.t.fit(returns)
threshold = 2.5 * returns.std(ddof=1)
normal_tail = 2.0 * stats.norm.sf(threshold, *normal_params)
t_tail = stats.t.cdf(-threshold, *t_params) + stats.t.sf(threshold, *t_params)
empirical_tail = np.mean(np.abs(returns - returns.mean()) > threshold)

display(pd.Series({
    "empirical_tail": empirical_tail,
    "normal_tail": normal_tail,
    "student_t_tail": t_tail,
    "excess_kurtosis": stats.kurtosis(returns, fisher=True, bias=False),
}))
""",
            ),
        ],
        12: [
            (
                "观察样本均值分布的收敛",
                "底层收益使用偏斜分布；对不同样本量重复抽样，比较样本均值的标准化偏度和峰度。",
                """
from scipy import stats

rng = np.random.default_rng(365)
sample_sizes = [5, 20, 100]
rows = []

for n in sample_sizes:
    samples = rng.lognormal(mean=0.0, sigma=0.7, size=(5_000, n))
    means = samples.mean(axis=1)
    standardized = (means - means.mean()) / means.std(ddof=1)
    rows.append({
        "sample_size": n,
        "skew": stats.skew(standardized, bias=False),
        "excess_kurtosis": stats.kurtosis(standardized, fisher=True, bias=False),
        "std_of_mean": means.std(ddof=1),
    })

display(pd.DataFrame(rows))
""",
            ),
        ],
        13: [
            (
                "同时报告均值、区间和 p 值",
                "检验原假设为平均日收益等于 0。95% 置信区间描述估计不确定性，不是未来单日收益区间。",
                """
from scipy import stats

daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
close = daily.pivot(index="date", columns="symbol", values="adj_close").sort_index()
strategy = close["SIM_VALUE"].pct_change(fill_method=None).dropna()

test = stats.ttest_1samp(strategy, popmean=0.0)
mean = strategy.mean()
se = stats.sem(strategy)
interval = stats.t.interval(0.95, df=len(strategy) - 1, loc=mean, scale=se)

display(pd.Series({
    "mean_daily_return": mean,
    "effect_bps_per_day": mean * 10_000,
    "ci95_low": interval[0],
    "ci95_high": interval[1],
    "pvalue": test.pvalue,
    "observations": len(strategy),
}))
""",
            ),
        ],
        14: [
            (
                "比较样本内和样本外 R²",
                "按时间顺序切分，不能随机打乱。特征只使用昨天及更早的信息，目标是下一日收益。",
                """
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
close = daily.pivot(index="date", columns="symbol", values="adj_close").sort_index()
market = close["SIM_MARKET"].pct_change(fill_method=None)
dataset = pd.DataFrame({
    "lag1": market.shift(1),
    "lag2": market.shift(2),
    "target": market,
}).dropna()

split = int(len(dataset) * 0.7)
train, test = dataset.iloc[:split], dataset.iloc[split:]
model = LinearRegression().fit(train[["lag1", "lag2"]], train["target"])

train_r2 = model.score(train[["lag1", "lag2"]], train["target"])
test_pred = model.predict(test[["lag1", "lag2"]])
test_r2 = r2_score(test["target"], test_pred)

display(pd.Series({"train_r2": train_r2, "test_r2": test_r2, "test_observations": len(test)}))
""",
            ),
        ],
        15: [
            (
                "分别检验价格水平和收益率",
                "ADF 原假设是存在单位根。这里比较对数价格与其一阶差分，p 值不能单独证明经济关系。",
                """
from statsmodels.tsa.stattools import adfuller

daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
market = daily.loc[daily["symbol"] == "SIM_MARKET"].set_index("date")["adj_close"]
log_price = np.log(market)
log_return = log_price.diff().dropna()

price_adf = adfuller(log_price, autolag="AIC")
return_adf = adfuller(log_return, autolag="AIC")
display(pd.DataFrame({
    "series": ["log_price", "log_return"],
    "adf_stat": [price_adf[0], return_adf[0]],
    "pvalue": [price_adf[1], return_adf[1]],
    "used_lags": [price_adf[2], return_adf[2]],
}))
""",
            ),
        ],
        16: [
            (
                "ACF 与 Ljung–Box 联合诊断",
                "ACF 单独看每个滞后，Ljung–Box 检查多个滞后是否整体为零。统计显著仍需成本后验证。",
                """
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.stattools import acf

daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
market = daily.loc[daily["symbol"] == "SIM_MARKET"].set_index("date")["adj_close"]
returns = market.pct_change(fill_method=None).dropna()

acf_values = acf(returns, nlags=10, fft=True)
ljung_box = acorr_ljungbox(returns, lags=[5, 10], return_df=True)

print("ACF lag 0–10:", np.round(acf_values, 4))
display(ljung_box)
""",
            ),
        ],
        17: [
            (
                "模拟终值分布并检查蒙特卡洛误差",
                "参数是模型输入而不是历史真相。增加路径数应使终值均值更稳定，但不会修复错误分布假设。",
                """
rng = np.random.default_rng(365)
spot, mu, sigma, years, steps = 100.0, 0.06, 0.20, 1.0, 252
dt = years / steps

def simulate_terminal(path_count):
    shocks = rng.standard_normal((steps, path_count))
    log_steps = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * shocks
    return spot * np.exp(log_steps.sum(axis=0))

terminal_1k = simulate_terminal(1_000)
terminal_10k = simulate_terminal(10_000)
display(pd.DataFrame({
    "paths": [1_000, 10_000],
    "mean_terminal": [terminal_1k.mean(), terminal_10k.mean()],
    "p05": [np.quantile(terminal_1k, 0.05), np.quantile(terminal_10k, 0.05)],
    "p95": [np.quantile(terminal_1k, 0.95), np.quantile(terminal_10k, 0.95)],
}))
""",
            ),
        ],
        18: [
            (
                "用 GBM 精确离散式生成路径",
                "代码中的 `mu` 是真实世界漂移假设；风险中性定价时应替换为适当的风险中性漂移。",
                """
rng = np.random.default_rng(365)
spot, mu, sigma = 100.0, 0.06, 0.22
steps, paths = 252, 200
dt = 1.0 / steps
z = rng.standard_normal((steps, paths))
log_increments = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * z
prices = spot * np.exp(np.vstack([np.zeros(paths), np.cumsum(log_increments, axis=0)]))

assert prices.shape == (steps + 1, paths)
print("一年终值中位数:", round(float(np.median(prices[-1])), 2))

fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(prices[:, :20], alpha=0.45)
ax.set(title="GBM paths under fixed assumptions", xlabel="Trading day", ylabel="Simulated price")
plt.tight_layout()
plt.show()
""",
            ),
        ],
        19: [
            (
                "一周期二叉树风险中性定价",
                "先检查 `d < exp(rΔt) < u`，否则存在简单无套利冲突。风险中性 q 用于贴现复制，不是上涨预测。",
                """
spot, strike = 100.0, 100.0
up, down = 1.20, 0.85
rate, dt = 0.03, 1.0

growth = np.exp(rate * dt)
assert down < growth < up
q = (growth - down) / (up - down)

payoff_up = max(spot * up - strike, 0.0)
payoff_down = max(spot * down - strike, 0.0)
option_price = np.exp(-rate * dt) * (q * payoff_up + (1.0 - q) * payoff_down)

display(pd.Series({"risk_neutral_q": q, "payoff_up": payoff_up, "payoff_down": payoff_down, "call_price": option_price}))
""",
            ),
        ],
        20: [
            (
                "计算 Black–Scholes 欧式看涨价格",
                "单位要一致：期限以年、波动率和利率用小数。模型价格是给定假设下的无套利基准。",
                """
from src.quant_core import black_scholes_call

inputs = {"spot": 100.0, "strike": 105.0, "maturity": 0.5, "rate": 0.02, "volatility": 0.25}
call_price = black_scholes_call(**inputs)
print("输入:", inputs)
print(f"欧式看涨价格: {call_price:.4f}")
assert 0.0 < call_price < inputs["spot"]
""",
            ),
            (
                "观察波动率敏感性",
                "其他输入固定时，看涨期权价格通常随波动率上升；这不是对未来方向的预测。",
                """
vol_grid = np.linspace(0.10, 0.60, 11)
prices = [black_scholes_call(100.0, 105.0, 0.5, 0.02, vol) for vol in vol_grid]
display(pd.DataFrame({"volatility": vol_grid, "call_price": prices}))
""",
            ),
        ],
        21: [
            (
                "同一合约的四个局部敏感度",
                "Theta 以每天计，Vega 以波动率变化 1 个百分点计；不同资料的单位定义可能不同。",
                """
from src.quant_core import black_scholes_greeks

greeks = black_scholes_greeks(
    spot=100.0,
    strike=100.0,
    maturity=0.5,
    rate=0.02,
    volatility=0.25,
)
display(pd.Series(greeks))
""",
            ),
            (
                "Delta 和 Gamma 随现价变化",
                "这是局部风险曲线。大幅价格变化时应重新计算，而不能用初始 Delta 线性外推。",
                """
spots = np.linspace(70.0, 130.0, 61)
surface = pd.DataFrame([
    {"spot": spot, **black_scholes_greeks(spot, 100.0, 0.5, 0.02, 0.25)}
    for spot in spots
])
ax = surface.plot(x="spot", y=["delta", "gamma"], secondary_y="gamma", figsize=(8, 4), title="Delta and Gamma by spot")
plt.tight_layout()
plt.show()
""",
            ),
        ],
        22: [
            (
                "从 L2 快照计算价差、深度和不平衡",
                "先按买卖方向分别找最优价；深度使用前 5 档可见数量，不能代表隐藏流动性。",
                """
book = pd.read_csv(DATA_DIR / "order_book.csv")
display(book)

bids = book.loc[book["side"] == "bid"].sort_values("price", ascending=False)
asks = book.loc[book["side"] == "ask"].sort_values("price", ascending=True)
best_bid = bids.iloc[0]["price"]
best_ask = asks.iloc[0]["price"]
mid = (best_bid + best_ask) / 2.0
spread_bps = (best_ask - best_bid) / mid * 10_000
imbalance = (bids["quantity"].sum() - asks["quantity"].sum()) / book["quantity"].sum()

display(pd.Series({"best_bid": best_bid, "best_ask": best_ask, "mid": mid, "spread_bps": spread_bps, "depth_imbalance": imbalance}))
""",
            ),
        ],
        23: [
            (
                "按档位穿透计算买入均价",
                "市价买入从最低卖价开始消耗数量。成交均价与决策时中间价的差构成实现滑点的一部分。",
                """
book = pd.read_csv(DATA_DIR / "order_book.csv")
asks = book.loc[book["side"] == "ask"].sort_values("price")
best_bid = book.loc[book["side"] == "bid", "price"].max()
best_ask = asks["price"].min()
mid = (best_bid + best_ask) / 2.0

def market_buy_vwap(quantity):
    remaining = quantity
    cost = 0.0
    filled = 0
    for row in asks.itertuples():
        take = min(remaining, int(row.quantity))
        cost += take * row.price
        filled += take
        remaining -= take
        if remaining == 0:
            break
    if remaining:
        raise ValueError("可见卖盘深度不足")
    return cost / filled

sizes = [100, 600, 1_500]
rows = []
for size in sizes:
    vwap = market_buy_vwap(size)
    rows.append({"quantity": size, "vwap": vwap, "slippage_bps_vs_mid": (vwap / mid - 1.0) * 10_000})
display(pd.DataFrame(rows))
""",
            ),
        ],
        24: [
            (
                "用价格—时间优先匹配限价单",
                "示例只实现买卖限价单。买方按高价优先、同价早到优先；卖方相反。",
                """
orders = [
    {"id": "S1", "side": "sell", "price": 100.20, "qty": 300, "time": 1},
    {"id": "S2", "side": "sell", "price": 100.20, "qty": 200, "time": 2},
    {"id": "S3", "side": "sell", "price": 100.30, "qty": 400, "time": 3},
    {"id": "B1", "side": "buy", "price": 100.25, "qty": 450, "time": 4},
]

sell_book = sorted([o.copy() for o in orders if o["side"] == "sell"], key=lambda o: (o["price"], o["time"]))
buy = [o.copy() for o in orders if o["id"] == "B1"][0]
trades = []

for sell in sell_book:
    if buy["qty"] == 0 or buy["price"] < sell["price"]:
        break
    matched = min(buy["qty"], sell["qty"])
    trades.append({"buy_id": buy["id"], "sell_id": sell["id"], "price": sell["price"], "qty": matched})
    buy["qty"] -= matched
    sell["qty"] -= matched

display(pd.DataFrame(trades))
print("B1 未成交数量:", buy["qty"])
assert [trade["sell_id"] for trade in trades] == ["S1", "S2"]
""",
            ),
        ],
        26: [
            (
                "把三种供应商字段映射到统一 schema",
                "示例是离线构造的供应商风格数据，不是实时接口结果。适配后统一为 `date/symbol/open/high/low/close/volume`。",
                """
yfinance_style = pd.DataFrame({
    "Date": ["2025-01-02"], "Ticker": ["SIM_A"], "Open": [10.0],
    "High": [10.5], "Low": [9.9], "Close": [10.3], "Volume": [100_000],
})
akshare_style = pd.DataFrame({
    "日期": ["2025-01-02"], "代码": ["SIM_A"], "开盘": [10.0],
    "最高": [10.5], "最低": [9.9], "收盘": [10.3], "成交量": [100_000],
})
tushare_style = pd.DataFrame({
    "trade_date": ["20250102"], "ts_code": ["SIM_A"], "open": [10.0],
    "high": [10.5], "low": [9.9], "close": [10.3], "vol": [100_000],
})

def normalize_frame(frame, mapping, source):
    normalized = frame.rename(columns=mapping).copy()
    normalized["date"] = pd.to_datetime(normalized["date"])
    normalized["source"] = source
    return normalized[["date", "symbol", "open", "high", "low", "close", "volume", "source"]]

frames = [
    normalize_frame(yfinance_style, {"Date":"date","Ticker":"symbol","Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"}, "yfinance_style"),
    normalize_frame(akshare_style, {"日期":"date","代码":"symbol","开盘":"open","最高":"high","最低":"low","收盘":"close","成交量":"volume"}, "akshare_style"),
    normalize_frame(tushare_style, {"trade_date":"date","ts_code":"symbol","vol":"volume"}, "tushare_style"),
]
display(pd.concat(frames, ignore_index=True))
""",
            ),
        ],
        27: [
            (
                "拆股日同时保留原始价与复权研究价",
                "2 拆 1 会让原始价格机械减半，但持有者股数翻倍。复权价用于连续收益，原始价用于当时成交回放。",
                """
actions = pd.read_csv(DATA_DIR / "corporate_actions.csv", parse_dates=["date"])
raw = pd.Series(
    [100.0, 102.0, 51.5, 52.0],
    index=pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"]),
    name="raw_close",
)
split_date = actions.loc[actions["action"] == "split", "date"].iloc[0]
split_ratio = actions.loc[actions["action"] == "split", "value"].iloc[0]

adjusted = raw.copy()
adjusted.loc[adjusted.index < split_date] = adjusted.loc[adjusted.index < split_date] / split_ratio
comparison = pd.concat([raw, adjusted.rename("split_adjusted_close")], axis=1)
comparison["raw_return"] = comparison["raw_close"].pct_change(fill_method=None)
comparison["adjusted_return"] = comparison["split_adjusted_close"].pct_change(fill_method=None)
display(comparison)
""",
            ),
        ],
        28: [
            (
                "把逐笔样例聚合为 1 分钟 OHLCV",
                "`label='right', closed='right'` 表示时间标签是区间右端；这直接影响信号何时可得。",
                """
ticks = pd.read_csv(DATA_DIR / "intraday_ticks.csv", parse_dates=["timestamp"]).set_index("timestamp")
one_minute = ticks.resample("1min", label="right", closed="right").agg(
    open=("price", "first"),
    high=("price", "max"),
    low=("price", "min"),
    close=("price", "last"),
    volume=("quantity", "sum"),
).dropna()

display(ticks.head(10))
display(one_minute.head())
assert (one_minute["high"] >= one_minute[["open", "close"]].max(axis=1)).all()
assert (one_minute["low"] <= one_minute[["open", "close"]].min(axis=1)).all()
""",
            ),
        ],
        29: [
            (
                "定义无未来信息的信号和下一日持仓",
                "均线在收盘后形成，因此使用 `signal.shift(1)` 表示最早下一交易日持有。换手在持仓变化时发生。",
                """
from src.quant_core import performance_summary

daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
close = daily.pivot(index="date", columns="symbol", values="adj_close").sort_index()
asset = close["SIM_GROWTH"]
benchmark = close["SIM_MARKET"].pct_change(fill_method=None)

fast = asset.rolling(20, min_periods=20).mean()
slow = asset.rolling(60, min_periods=60).mean()
signal = (fast > slow).astype(float)
position = signal.shift(1).fillna(0.0)
asset_return = asset.pct_change(fill_method=None)
turnover = position.diff().abs().fillna(position.abs())
cost_per_turnover = 0.0005
strategy = position * asset_return - turnover * cost_per_turnover

metrics = performance_summary(strategy, benchmark)
display(metrics.to_frame("value"))
""",
            ),
            (
                "生成包含策略与基准的研究报告",
                "报告记录模拟数据身份、信号时点和成本假设。它是方法演示，不是投资建议或未来收益承诺。",
                """
aligned = pd.concat([strategy.rename("strategy"), benchmark.rename("benchmark")], axis=1).dropna()
nav = (1.0 + aligned).cumprod()
ax = nav.plot(figsize=(9, 4), title="Strategy vs benchmark (simulated data)")
ax.set_ylabel("Wealth index")
plt.tight_layout()
figure_path = OUTPUT_DIR / "29_strategy_vs_benchmark.png"
plt.savefig(figure_path, dpi=150)
plt.show()

report_rows = "".join(
    f"<tr><th>{key}</th><td>{value:.6f}</td></tr>" if isinstance(value, (float, np.floating))
    else f"<tr><th>{key}</th><td>{value}</td></tr>"
    for key, value in metrics.items()
)
report_html = f\"\"\"<!doctype html><meta charset='utf-8'>
<title>P1 strategy research report</title>
<h1>策略研究报告：双均线教学样例</h1>
<p><strong>数据：</strong>固定种子模拟日线，不是真实证券。</p>
<p><strong>假设：</strong>中期趋势持续性可能带来成本后收益；20/60 日均线仅作教学规则。</p>
<p><strong>执行：</strong>收盘形成信号，下一交易日持仓；单边换手成本 5 bps。</p>
<h2>收益、风险与基准</h2><table>{report_rows}</table>
<h2>边界</h2><p>未进行参数搜索、滚动样本外、容量、税费和模拟盘验证，不构成收益承诺。</p>
\"\"\"
report_path = OUTPUT_DIR / "29_strategy_report.html"
report_path.write_text(report_html, encoding="utf-8")
print("已生成:", report_path)
""",
            ),
        ],
    }
    return cells[number]

