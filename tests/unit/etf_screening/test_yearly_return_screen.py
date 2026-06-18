"""Tests for the yearly return and weekly volatility ETF screen.

The screen is intentionally small, but the calendar-year logic is easy to get
wrong. These tests use toy prices with known yearly returns so the hurdle and
ranking rules stay explicit.
"""
# ruff: noqa: E402

from __future__ import annotations

import math
import pathlib
import sys

import pandas as pd

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from etf_screening.yearly_return_screen import (
    DEFAULT_MIN_DRAWDOWN,
    DEFAULT_MIN_AVERAGE_YEARLY_RETURN,
    compute_drawdown_metrics,
    compute_weekly_volatility,
    screen_etfs_by_drawdown,
)


def _build_price_rows(
    ticker: str, year_prices: dict[int, tuple[float, float]]
) -> list[dict]:
    """Build two daily close rows per year for a toy ticker."""
    rows = []
    for year, prices in year_prices.items():
        start_price, end_price = prices
        rows.append(
            {
                "ticker": ticker,
                "date": f"{year}-01-02",
                "close_price": start_price,
            }
        )
        rows.append(
            {
                "ticker": ticker,
                "date": f"{year}-12-31",
                "close_price": end_price,
            }
        )
    return rows


def _build_dated_price_rows(ticker: str, dated_prices: dict[str, float]) -> list[dict]:
    """Build daily close rows from explicit date-to-price mappings."""
    rows = []
    for date, close_price in dated_prices.items():
        rows.append(
            {
                "ticker": ticker,
                "date": date,
                "close_price": close_price,
            }
        )
    return rows


def test_default_screen_hurdles_match_current_research_policy() -> None:
    """Default return hurdles should match the documented ETF screen policy."""
    assert math.isclose(DEFAULT_MIN_DRAWDOWN, -0.15)
    assert math.isclose(DEFAULT_MIN_AVERAGE_YEARLY_RETURN, 0.03)


def test_weekly_volatility_uses_calendar_week_last_close() -> None:
    """Weekly volatility should use each calendar week's last observed close."""
    price_frame = pd.DataFrame(
        _build_dated_price_rows(
            "WEEKLY",
            {
                "2024-01-02": 100.0,
                "2024-01-05": 110.0,
                "2024-01-08": 120.0,
                "2024-01-12": 121.0,
                "2024-01-16": 130.0,
                "2024-01-19": 133.1,
            },
        )
    )

    result = compute_weekly_volatility(price_frame)

    expected_returns = pd.Series(
        [
            math.log(121.0 / 110.0),
            math.log(133.1 / 121.0),
        ]
    )
    expected_weekly_volatility = expected_returns.std(ddof=1)

    assert result["ticker"].tolist() == ["WEEKLY"]
    assert math.isclose(
        result.loc[0, "weekly_volatility"],
        expected_weekly_volatility,
    )
    assert result.loc[0, "n_weekly_returns"] == 2


def test_drawdown_metrics_use_weekly_wealth_peak_to_trough_loss() -> None:
    """Maximum drawdown should be measured from weekly wealth peaks."""
    price_frame = pd.DataFrame(
        _build_dated_price_rows(
            "DRAWDOWN",
            {
                "2024-01-05": 100.0,
                "2024-01-12": 120.0,
                "2024-01-19": 90.0,
                "2024-01-26": 108.0,
            },
        )
    )

    result = compute_drawdown_metrics(price_frame)

    assert result["ticker"].tolist() == ["DRAWDOWN"]
    assert math.isclose(result.loc[0, "max_drawdown"], -0.25)


def test_screen_keeps_only_etfs_meeting_drawdown_and_average_return_hurdles() -> None:
    """An ETF must pass the drawdown floor and average yearly return hurdle."""
    price_frame = pd.DataFrame(
        _build_price_rows(
            "LOWVOL",
            {
                2020: (100.0, 105.0),
                2021: (100.0, 104.0),
            },
        )
        + _build_price_rows(
            "HIGHVOL",
            {
                2020: (100.0, 106.0),
                2021: (100.0, 105.0),
            },
        )
        + _build_price_rows(
            "BIG_DRAWDOWN",
            {
                2020: (100.0, 120.0),
                2021: (100.0, 90.0),
            },
        )
        + _build_price_rows(
            "BADAVG",
            {
                2020: (100.0, 102.0),
                2021: (100.0, 103.0),
            },
        )
    )

    result = screen_etfs_by_drawdown(
        price_frame=price_frame,
        min_drawdown=-0.20,
        min_average_yearly_return=0.04,
        min_trading_days_per_year=2,
        min_years=2,
    )

    assert result["ticker"].tolist() == ["LOWVOL", "HIGHVOL"]
    assert result["years_observed"].tolist() == [2, 2]
    assert math.isclose(result.loc[0, "min_yearly_return"], 0.04)
    assert math.isclose(result.loc[0, "average_yearly_return"], 0.045)
    assert result.loc[0, "weekly_volatility"] < result.loc[1, "weekly_volatility"]


def test_screen_requires_minimum_history_and_average_return() -> None:
    """An ETF must have enough usable years and clear the average return hurdle."""
    price_frame = pd.DataFrame(
        _build_price_rows(
            "MATURE",
            {
                2020: (100.0, 110.0),
                2021: (100.0, 101.0),
                2022: (100.0, 115.0),
                2023: (100.0, 101.0),
                2024: (100.0, 120.0),
            },
        )
        + _build_price_rows(
            "LOW_AVERAGE_RETURN",
            {
                2020: (100.0, 101.0),
                2021: (100.0, 101.0),
                2022: (100.0, 101.0),
                2023: (100.0, 101.0),
                2024: (100.0, 101.0),
            },
        )
        + _build_price_rows(
            "TOO_YOUNG",
            {
                2023: (100.0, 110.0),
                2024: (100.0, 120.0),
            },
        )
    )

    result = screen_etfs_by_drawdown(
        price_frame=price_frame,
        min_drawdown=-0.50,
        min_average_yearly_return=0.04,
        min_trading_days_per_year=2,
        min_years=5,
    )

    assert result["ticker"].tolist() == ["MATURE"]
    assert math.isclose(result.loc[0, "min_yearly_return"], 0.01)


def test_screen_uses_full_history_after_minimum_years() -> None:
    """Older usable years should still affect mature ETFs after the minimum history."""
    price_frame = pd.DataFrame(
        _build_price_rows(
            "FULL_PASS",
            {
                2019: (100.0, 104.0),
                2020: (100.0, 105.0),
                2021: (100.0, 104.0),
                2022: (100.0, 105.0),
                2023: (100.0, 106.0),
                2024: (100.0, 107.0),
                2025: (100.0, 108.0),
            },
        )
        + _build_price_rows(
            "OLDER_FAIL",
            {
                2019: (100.0, 50.0),
                2020: (100.0, 50.0),
                2021: (100.0, 104.0),
                2022: (100.0, 105.0),
                2023: (100.0, 106.0),
                2024: (100.0, 107.0),
                2025: (100.0, 108.0),
            },
        )
        + _build_price_rows(
            "RECENT_FAIL",
            {
                2019: (100.0, 120.0),
                2020: (100.0, 120.0),
                2021: (100.0, 104.0),
                2022: (100.0, 105.0),
                2023: (100.0, 98.0),
                2024: (100.0, 107.0),
                2025: (100.0, 108.0),
            },
        )
    )

    result = screen_etfs_by_drawdown(
        price_frame=price_frame,
        min_drawdown=-0.15,
        min_average_yearly_return=0.03,
        min_trading_days_per_year=2,
        min_years=5,
    )

    assert result["ticker"].tolist() == ["FULL_PASS"]
    assert result.loc[0, "start_year"] == 2019
    assert result.loc[0, "end_year"] == 2025
    assert result.loc[0, "years_observed"] == 7
    assert math.isclose(result.loc[0, "min_yearly_return"], 0.04)
