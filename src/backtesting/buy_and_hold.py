"""
backtesting/buy_and_hold.py
---------------------------
Weighted long-only buy-and-hold backtesting utilities.

Given a list of tickers and corresponding weights, this module buys fixed
shares on the aligned entry date, revalues those shares each day, and then
summarises the exact portfolio path using log-return metrics throughout.

Metrics
-------
- ann_return    : mean(log_ret) * 252 -- annualised log return
- ann_vol       : std(log_ret) * sqrt(252) -- annualised log volatility
- sharpe        : (ann_return - risk_free) / ann_vol
- max_drawdown  : peak-to-trough drawdown on the wealth path exp(cumsum(log_ret))
- calmar        : ann_return / max_drawdown
- total_log_return : sum of all daily portfolio log returns over the window

The equity curve is the exact marked-to-market value of those fixed shares.
Portfolio log returns are then derived from that portfolio-value series:
    port_log_ret_t = log(V_t / V_{t-1})

This keeps reporting in log-return space while preserving exact buy-and-hold
mechanics.

Usage
-----
    from backtesting.buy_and_hold import run_weighted_backtest

    metrics, equity = run_weighted_backtest(
        tickers=["VOO", "TLT", "IAU"],
        weights=[0.60, 0.30, 0.10],
        start_date="2018-01-01",
        end_date="2025-12-31",
    )
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

from data_pipeline.paths import PRICE_PARQUET
from portfolio_allocation.allocation_utils import RISK_FREE, TRADING_DAYS_PER_YEAR

matplotlib.use("Agg")


def load_price_matrix(
    tickers: list[str],
    start_date: str,
    end_date: str,
    price_parquet: Path = PRICE_PARQUET,
) -> pd.DataFrame:
    """
    Build a wide close-price matrix indexed by trading date.

    Loads prices from the shared parquet, filters by ticker and date range,
    forward-fills intra-window gaps, and aligns all tickers to the latest
    first-valid date so the portfolio starts with a complete basket.

    Parameters
    ----------
    tickers       : ordered list of ticker strings
    start_date    : inclusive start date (YYYY-MM-DD)
    end_date      : inclusive end date (YYYY-MM-DD)
    price_parquet : path to the shared daily close parquet

    Returns
    -------
    pd.DataFrame
        Wide price matrix: rows = trading dates (DatetimeIndex),
        columns = tickers in input order.
    """
    if not price_parquet.exists():
        raise FileNotFoundError(f"Price parquet not found: {price_parquet}")

    raw = pd.read_parquet(price_parquet, columns=["ticker", "date", "close_price"])
    raw["ticker"] = raw["ticker"].astype(str).str.upper()
    raw["date"] = pd.to_datetime(raw["date"])

    tickers_upper = [t.strip().upper() for t in tickers]
    available = set(raw["ticker"].unique())
    missing = [t for t in tickers_upper if t not in available]
    if missing:
        raise ValueError(f"Tickers not found in parquet: {missing}")

    subset = raw[
        raw["ticker"].isin(tickers_upper)
        & (raw["date"] >= pd.Timestamp(start_date))
        & (raw["date"] <= pd.Timestamp(end_date))
    ].copy()

    if subset.empty:
        raise ValueError("No rows remain after date and ticker filtering.")

    price_wide = subset.pivot(index="date", columns="ticker", values="close_price")
    price_wide = price_wide.sort_index().reindex(columns=tickers_upper)

    # Align start to the latest first-valid date so every ticker is live
    first_valid = price_wide.apply(pd.Series.first_valid_index)
    if first_valid.isna().any():
        raise ValueError(
            f"No valid prices for: {first_valid[first_valid.isna()].index.tolist()}"
        )

    aligned_start = pd.to_datetime(first_valid.max())
    price_wide = price_wide[price_wide.index >= aligned_start]
    price_wide = price_wide.ffill().dropna(how="any")

    if len(price_wide) < 2:
        raise ValueError(
            "Fewer than 2 trading rows after alignment -- cannot compute returns."
        )

    return price_wide


def run_weighted_backtest(
    tickers: list[str],
    weights: list[float],
    start_date: str,
    end_date: str,
    initial_capital: float = 30_000,
    risk_free: float = RISK_FREE,
    price_parquet: Path = PRICE_PARQUET,
) -> tuple[dict, pd.DataFrame]:
    """
    Compute exact buy-and-hold performance metrics for a weighted portfolio.

    The function allocates the requested initial capital across the aligned
    entry-date prices, keeps the resulting share counts fixed, revalues the
    portfolio on each subsequent trading day, and computes portfolio log
    returns from that exact value path:
        port_log_ret_t = log(V_t / V_{t-1})

    All reported return metrics remain in log-return space, but the portfolio
    path itself is valued exactly from fixed shares instead of using an asset-
    level weighted log-return approximation.

    Parameters
    ----------
    tickers         : ordered ticker list
    weights         : weight for each ticker (must sum to 1.0, all >= 0)
    start_date      : inclusive backtest start date (YYYY-MM-DD)
    end_date        : inclusive backtest end date (YYYY-MM-DD)
    initial_capital : starting capital in USD (for equity curve display only)
    risk_free       : annualised log risk-free rate (default 0.05)
    price_parquet   : path to the shared price parquet

    Returns
    -------
    metrics : dict
        Keys: start_date, end_date, n_trading_days, ann_return, ann_vol,
              sharpe, max_drawdown, calmar, total_log_return, final_value,
              initial_capital.
    equity : pd.DataFrame
        Columns: date, log_return, portfolio_value, drawdown.
        portfolio_value is in USD. drawdown is expressed as a positive fraction
        (e.g. 0.15 = 15% drawdown from peak).
    """
    weights_arr = np.asarray(weights, dtype=float)

    if len(weights_arr) != len(tickers):
        raise ValueError("len(weights) must equal len(tickers).")
    if not np.isclose(weights_arr.sum(), 1.0, atol=1e-4):
        raise ValueError(f"Weights must sum to 1.0, got {weights_arr.sum():.6f}.")
    if weights_arr.min() < 0.0:
        raise ValueError("Negative weights are not allowed (long-only portfolio).")

    prices = load_price_matrix(tickers, start_date, end_date, price_parquet)

    # Convert the requested starting weights into fixed share counts at the
    # aligned entry date. This is the defining mechanics of buy-and-hold.
    entry_prices = prices.iloc[0].to_numpy(dtype=float)
    if np.any(entry_prices <= 0.0):
        raise ValueError(
            "Entry prices must be strictly positive for buy-and-hold valuation."
        )

    initial_allocations = initial_capital * weights_arr
    share_counts = initial_allocations / entry_prices

    # Mark the fixed shares to market on every trading date, then derive the
    # portfolio log-return path from the exact portfolio values.
    portfolio_values = prices.to_numpy(dtype=float) @ share_counts
    portfolio_value_series = pd.Series(
        portfolio_values,
        index=prices.index,
        dtype=float,
    )
    portfolio_log_returns = np.log(
        portfolio_value_series / portfolio_value_series.shift(1)
    ).fillna(0.0)
    return_periods = portfolio_log_returns.iloc[1:]

    n_trading_days = len(prices)
    ann_return = float(return_periods.mean()) * TRADING_DAYS_PER_YEAR
    ann_vol = float(return_periods.std(ddof=1)) * np.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe = (ann_return - risk_free) / ann_vol if ann_vol > 1e-12 else np.nan

    # The portfolio value path is exact. Wealth is simply value normalized by
    # the initial capital, and total log return is log(V_T / V_0).
    wealth = portfolio_value_series / initial_capital
    total_log_return = float(np.log(wealth.iloc[-1]))

    # Drawdown: fraction of wealth lost from running peak
    running_max = portfolio_value_series.cummax()
    drawdowns = 1.0 - portfolio_value_series / running_max
    max_dd = float(drawdowns.max())

    calmar = ann_return / max_dd if max_dd > 1e-12 else np.nan
    final_value = float(portfolio_value_series.iloc[-1])

    metrics = {
        "start_date": str(prices.index[0].date()),
        "end_date": str(prices.index[-1].date()),
        "n_trading_days": n_trading_days,
        "initial_capital": initial_capital,
        "final_value": round(final_value, 2),
        "total_log_return": round(total_log_return, 4),
        "ann_return": round(ann_return, 4),
        "ann_vol": round(ann_vol, 4),
        "sharpe": round(float(sharpe), 4) if not np.isnan(sharpe) else float("nan"),
        "max_drawdown": round(max_dd, 4),
        "calmar": round(float(calmar), 4) if not np.isnan(calmar) else float("nan"),
    }

    equity = pd.DataFrame(
        {
            "date": prices.index,
            "log_return": portfolio_log_returns.to_numpy(dtype=float),
            "portfolio_value": portfolio_value_series.to_numpy(dtype=float),
            # Drawdown is a positive fraction so the notebook can plot it
            # directly without sign flips.
            "drawdown": drawdowns.to_numpy(dtype=float),
        }
    )

    return metrics, equity
