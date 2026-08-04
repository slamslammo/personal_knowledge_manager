"""Transparent, small-scope calculations shared by P1 lessons.

The notebooks still derive every financial formula before calling these helpers.
This module exists to keep the full-data examples and the capstone report
consistent, not to hide the research assumptions.
"""

from __future__ import annotations

from math import exp, log, sqrt
from statistics import NormalDist

import numpy as np
import pandas as pd


TRADING_DAYS = 252


def simple_returns(prices: pd.Series | pd.DataFrame) -> pd.Series | pd.DataFrame:
    """Return P_t / P_(t-1) - 1 without forward filling missing values."""

    return prices.pct_change(fill_method=None)


def log_returns(prices: pd.Series | pd.DataFrame) -> pd.Series | pd.DataFrame:
    """Return log(P_t) - log(P_(t-1)). Prices must be strictly positive."""

    if (prices <= 0).any().any() if isinstance(prices, pd.DataFrame) else (prices <= 0).any():
        raise ValueError("Log returns require strictly positive prices.")
    return np.log(prices).diff()


def wealth_index(returns: pd.Series, initial: float = 1.0) -> pd.Series:
    """Compound simple returns into an explicitly based wealth index."""

    clean = returns.dropna()
    compounded = (1.0 + clean).cumprod() * initial
    base_index = clean.index[:1]
    if len(base_index) == 0:
        return compounded
    start = pd.Series([initial], index=[base_index[0] - pd.Timedelta(days=1)])
    return pd.concat([start, compounded])


def max_drawdown(returns: pd.Series) -> float:
    """Return the minimum peak-to-trough drawdown of a simple-return series."""

    nav = (1.0 + returns.dropna()).cumprod()
    drawdown = nav / nav.cummax() - 1.0
    return float(drawdown.min())


def annualized_return(returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    """Compound observed returns and annualize over the observed period count."""

    clean = returns.dropna()
    if clean.empty:
        return float("nan")
    total = float((1.0 + clean).prod())
    return total ** (periods / len(clean)) - 1.0


def annualized_volatility(
    returns: pd.Series, periods: int = TRADING_DAYS
) -> float:
    """Annualize sample standard deviation with sqrt(periods)."""

    return float(returns.dropna().std(ddof=1) * sqrt(periods))


def performance_summary(
    strategy: pd.Series,
    benchmark: pd.Series,
    periods: int = TRADING_DAYS,
) -> pd.Series:
    """Create a small, explicit performance summary on aligned dates."""

    aligned = pd.concat(
        [strategy.rename("strategy"), benchmark.rename("benchmark")],
        axis=1,
        join="inner",
    ).dropna()
    excess = aligned["strategy"] - aligned["benchmark"]
    covariance = aligned.cov(ddof=1)
    beta = covariance.loc["strategy", "benchmark"] / covariance.loc[
        "benchmark", "benchmark"
    ]
    return pd.Series(
        {
            "strategy_annual_return": annualized_return(
                aligned["strategy"], periods
            ),
            "benchmark_annual_return": annualized_return(
                aligned["benchmark"], periods
            ),
            "strategy_annual_volatility": annualized_volatility(
                aligned["strategy"], periods
            ),
            "max_drawdown": max_drawdown(aligned["strategy"]),
            "beta": float(beta),
            "mean_daily_excess": float(excess.mean()),
            "observations": int(len(aligned)),
        }
    )


def black_scholes_call(
    spot: float,
    strike: float,
    maturity: float,
    rate: float,
    volatility: float,
) -> float:
    """European call price under the Black–Scholes assumptions."""

    if min(spot, strike, maturity, volatility) <= 0:
        raise ValueError("spot, strike, maturity and volatility must be positive")
    normal = NormalDist()
    d1 = (
        log(spot / strike)
        + (rate + 0.5 * volatility**2) * maturity
    ) / (volatility * sqrt(maturity))
    d2 = d1 - volatility * sqrt(maturity)
    return spot * normal.cdf(d1) - strike * exp(-rate * maturity) * normal.cdf(
        d2
    )


def black_scholes_greeks(
    spot: float,
    strike: float,
    maturity: float,
    rate: float,
    volatility: float,
) -> dict[str, float]:
    """Delta, Gamma, Theta per calendar day, and Vega per volatility point."""

    normal = NormalDist()
    d1 = (
        log(spot / strike)
        + (rate + 0.5 * volatility**2) * maturity
    ) / (volatility * sqrt(maturity))
    d2 = d1 - volatility * sqrt(maturity)
    pdf_d1 = normal.pdf(d1)
    delta = normal.cdf(d1)
    gamma = pdf_d1 / (spot * volatility * sqrt(maturity))
    theta_year = (
        -(spot * pdf_d1 * volatility) / (2.0 * sqrt(maturity))
        - rate * strike * exp(-rate * maturity) * normal.cdf(d2)
    )
    vega_one_point = spot * pdf_d1 * sqrt(maturity) / 100.0
    return {
        "delta": delta,
        "gamma": gamma,
        "theta_per_day": theta_year / 365.0,
        "vega_per_vol_point": vega_one_point,
    }

