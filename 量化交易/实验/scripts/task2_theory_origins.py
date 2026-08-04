"""Task2：用模拟验证随机游走与凯利仓位的核心推论。

实验只依赖 NumPy、pandas 和 Matplotlib，不访问外部行情接口。

运行：
    conda activate pkm-quant
    python 实验/scripts/task2_theory_origins.py

输出：
    实验/outputs/task2_bachelier_random_walk.png
    实验/outputs/task2_thorp_kelly.png
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_DIR / "outputs"
CACHE_DIR = Path(tempfile.gettempdir()) / "pkm-quant-cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(CACHE_DIR / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(CACHE_DIR))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SEED = 82


def bachelier_experiment() -> tuple[pd.DataFrame, pd.Series]:
    """验证布朗运动的独立增量、零均值和方差时间缩放。"""

    rng = np.random.default_rng(SEED)
    path_count = 20_000
    step_count = 252
    daily_sigma = 1.0

    increments = rng.normal(
        loc=0.0,
        scale=daily_sigma,
        size=(path_count, step_count),
    )
    cumulative_change = np.cumsum(increments, axis=1)
    terminal_change = cumulative_change[:, -1]

    horizons = np.array([1, 5, 20, 60, 252])
    variance_rows = []
    for horizon in horizons:
        empirical_variance = cumulative_change[:, horizon - 1].var(ddof=1)
        theoretical_variance = horizon * daily_sigma**2
        variance_rows.append(
            {
                "horizon": horizon,
                "empirical_variance": empirical_variance,
                "theoretical_variance": theoretical_variance,
                "variance_ratio": empirical_variance / theoretical_variance,
            }
        )
    variance_table = pd.DataFrame(variance_rows)

    current_increment = increments[:, :-1].ravel()
    next_increment = increments[:, 1:].ravel()
    lag1_correlation = np.corrcoef(current_increment, next_increment)[0, 1]

    summary = pd.Series(
        {
            "path_count": path_count,
            "step_count": step_count,
            "increment_mean": increments.mean(),
            "increment_std": increments.std(ddof=1),
            "lag1_correlation": lag1_correlation,
            "same_direction_rate": np.mean(current_increment * next_increment > 0),
            "terminal_mean": terminal_change.mean(),
            "terminal_std": terminal_change.std(ddof=1),
            "terminal_theoretical_std": daily_sigma * np.sqrt(step_count),
            "terminal_positive_rate": np.mean(terminal_change > 0),
        },
        name="value",
    )

    figure, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    days = np.arange(step_count + 1)
    displayed_paths = np.column_stack(
        [np.full(50, 100.0), 100 + cumulative_change[:50]]
    )
    axes[0].plot(days, displayed_paths.T, alpha=0.35, linewidth=0.8)
    axes[0].axhline(100, color="black", linewidth=1, linestyle="--")
    axes[0].set_title("50 Bachelier paths")
    axes[0].set_xlabel("Step")
    axes[0].set_ylabel("Price index")

    axes[1].plot(
        variance_table["horizon"],
        variance_table["empirical_variance"],
        "o-",
        label="Empirical variance",
    )
    axes[1].plot(
        variance_table["horizon"],
        variance_table["theoretical_variance"],
        "--",
        label="h × daily variance",
    )
    axes[1].set_title("Variance grows linearly with time")
    axes[1].set_xlabel("Horizon")
    axes[1].set_ylabel("Variance")
    axes[1].legend()

    axes[2].hist(
        terminal_change,
        bins=60,
        density=True,
        alpha=0.6,
        label="Simulated terminal change",
    )
    x = np.linspace(terminal_change.min(), terminal_change.max(), 400)
    theoretical_std = daily_sigma * np.sqrt(step_count)
    normal_density = np.exp(-0.5 * (x / theoretical_std) ** 2) / (
        theoretical_std * np.sqrt(2 * np.pi)
    )
    axes[2].plot(x, normal_density, linewidth=2, label="Normal benchmark")
    axes[2].set_title("Terminal distribution")
    axes[2].set_xlabel("Cumulative price change")
    axes[2].set_ylabel("Density")
    axes[2].legend()

    figure.suptitle("Bachelier experiment: implications of Brownian motion")
    figure.tight_layout()
    figure.savefig(
        OUTPUT_DIR / "task2_bachelier_random_walk.png",
        dpi=160,
        bbox_inches="tight",
    )
    plt.close(figure)

    return variance_table, summary


def expected_log_growth(fraction: np.ndarray | float, p: float, b: float) -> np.ndarray:
    """二项下注每次的理论期望对数增长率。"""

    fraction_array = np.asarray(fraction, dtype=float)
    q = 1 - p
    return p * np.log1p(b * fraction_array) + q * np.log1p(-fraction_array)


def thorp_experiment() -> tuple[pd.DataFrame, pd.Series]:
    """比较不同仓位下的算术期望、典型复利结果和下行风险。"""

    rng = np.random.default_rng(SEED + 1)
    p = 0.52
    q = 1 - p
    b = 1.0
    bet_count = 1_000
    path_count = 50_000
    kelly_fraction = (b * p - q) / b

    strategies = {
        "no_bet": 0.00,
        "half_kelly": 0.02,
        "full_kelly": kelly_fraction,
        "double_kelly": 0.08,
        "overbet_10pct": 0.10,
    }

    wins = rng.binomial(bet_count, p, size=path_count)
    rows = []
    for name, fraction in strategies.items():
        log_terminal_wealth = (
            wins * np.log1p(b * fraction)
            + (bet_count - wins) * np.log1p(-fraction)
        )
        terminal_wealth = np.exp(log_terminal_wealth)
        expected_multiplier_per_bet = 1 + fraction * (b * p - q)
        rows.append(
            {
                "strategy": name,
                "fraction": fraction,
                "arithmetic_edge_per_bet": fraction * (b * p - q),
                "expected_log_growth": float(expected_log_growth(fraction, p, b)),
                "theoretical_expected_wealth": expected_multiplier_per_bet**bet_count,
                "simulated_median_wealth": np.median(terminal_wealth),
                "simulated_mean_wealth": terminal_wealth.mean(),
                "p05_wealth": np.quantile(terminal_wealth, 0.05),
                "p95_wealth": np.quantile(terminal_wealth, 0.95),
                "probability_below_initial": np.mean(terminal_wealth < 1),
            }
        )
    result_table = pd.DataFrame(rows)

    fair_game_growth = float(expected_log_growth(kelly_fraction, 0.50, b))
    summary = pd.Series(
        {
            "win_probability": p,
            "net_odds": b,
            "kelly_fraction": kelly_fraction,
            "full_kelly_log_growth": float(
                expected_log_growth(kelly_fraction, p, b)
            ),
            "fair_game_growth_at_4pct": fair_game_growth,
            "bet_count": bet_count,
            "terminal_simulation_paths": path_count,
        },
        name="value",
    )

    fraction_grid = np.linspace(0, 0.20, 401)
    growth_grid = expected_log_growth(fraction_grid, p, b)

    band_path_count = 3_000
    outcomes = rng.random((band_path_count, bet_count)) < p
    cumulative_wins = np.cumsum(outcomes, axis=1)
    periods = np.arange(1, bet_count + 1)

    figure, axes = plt.subplots(1, 3, figsize=(17, 4.8))
    axes[0].plot(fraction_grid, growth_grid)
    axes[0].axhline(0, color="black", linewidth=1)
    axes[0].axvline(
        kelly_fraction,
        color="tab:red",
        linestyle="--",
        label=f"Kelly = {kelly_fraction:.2%}",
    )
    axes[0].scatter(
        [kelly_fraction],
        [expected_log_growth(kelly_fraction, p, b)],
        color="tab:red",
    )
    axes[0].set_title("Expected log growth")
    axes[0].set_xlabel("Fraction of wealth bet")
    axes[0].set_ylabel("Expected log growth per bet")
    axes[0].legend()

    band_strategies = {
        "Half Kelly (2%)": 0.02,
        "Full Kelly (4%)": kelly_fraction,
        "Overbet (10%)": 0.10,
    }
    colors = ["tab:blue", "tab:green", "tab:red"]
    for (label, fraction), color in zip(band_strategies.items(), colors):
        log_wealth = (
            cumulative_wins * np.log1p(b * fraction)
            + (periods - cumulative_wins) * np.log1p(-fraction)
        )
        p05, median, p95 = np.quantile(log_wealth, [0.05, 0.50, 0.95], axis=0)
        axes[1].plot(periods, median, label=label, color=color)
        axes[1].fill_between(periods, p05, p95, color=color, alpha=0.12)
    axes[1].axhline(0, color="black", linewidth=1)
    axes[1].set_title("Typical path and 5%–95% range")
    axes[1].set_xlabel("Number of bets")
    axes[1].set_ylabel("Log wealth")
    axes[1].legend()

    x_positions = np.arange(len(result_table))
    width = 0.36
    axes[2].bar(
        x_positions - width / 2,
        result_table["theoretical_expected_wealth"],
        width,
        label="Expected wealth",
    )
    axes[2].bar(
        x_positions + width / 2,
        result_table["simulated_median_wealth"],
        width,
        label="Median wealth",
    )
    axes[2].set_yscale("log")
    axes[2].set_xticks(x_positions)
    axes[2].set_xticklabels(
        ["0%", "2%", "4%", "8%", "10%"],
        rotation=0,
    )
    axes[2].set_title("Mean expectation can hide typical loss")
    axes[2].set_xlabel("Fraction bet")
    axes[2].set_ylabel("Terminal wealth after 1,000 bets (log scale)")
    axes[2].legend()

    figure.suptitle("Thorp experiment: edge, sizing and compound growth")
    figure.tight_layout()
    figure.savefig(
        OUTPUT_DIR / "task2_thorp_kelly.png",
        dpi=160,
        bbox_inches="tight",
    )
    plt.close(figure)

    return result_table, summary


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    variance_table, bachelier_summary = bachelier_experiment()
    kelly_table, thorp_summary = thorp_experiment()

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 180)
    pd.set_option("display.float_format", lambda value: f"{value:.6f}")

    print("\n=== Bachelier summary ===")
    print(bachelier_summary.to_string())
    print("\n=== Variance scaling ===")
    print(variance_table.to_string(index=False))
    print("\n=== Thorp / Kelly summary ===")
    print(thorp_summary.to_string())
    print("\n=== Position sizing comparison ===")
    print(kelly_table.to_string(index=False))
    print(f"\nFigures written to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
