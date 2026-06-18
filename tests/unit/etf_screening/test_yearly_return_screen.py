"""Tests for the yearly return and daily volatility ETF screen.

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
    DEFAULT_MAX_BAD_YEARS,
    DEFAULT_MIN_AVERAGE_YEARLY_RETURN,
    DEFAULT_MIN_YEARLY_RETURN,
    screen_etfs_by_yearly_return,
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


def test_default_screen_hurdles_match_current_research_policy() -> None:
    """Default return hurdles should match the documented ETF screen policy."""
    assert math.isclose(DEFAULT_MIN_YEARLY_RETURN, 0.01)
    assert math.isclose(DEFAULT_MIN_AVERAGE_YEARLY_RETURN, 0.03)
    assert DEFAULT_MAX_BAD_YEARS == 2


def test_screen_keeps_only_etfs_meeting_each_year_and_average_return_hurdles() -> None:
    """An ETF must pass every yearly hurdle and the average yearly hurdle."""
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
            "BADYEAR",
            {
                2020: (100.0, 101.0),
                2021: (100.0, 110.0),
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

    result = screen_etfs_by_yearly_return(
        price_frame=price_frame,
        min_yearly_return=0.02,
        min_average_yearly_return=0.04,
        min_trading_days_per_year=2,
        min_years=1,
        max_bad_years=0,
    )

    assert result["ticker"].tolist() == ["LOWVOL", "HIGHVOL"]
    assert result["years_observed"].tolist() == [2, 2]
    assert math.isclose(result.loc[0, "min_yearly_return"], 0.04)
    assert math.isclose(result.loc[0, "average_yearly_return"], 0.045)
    assert result.loc[0, "daily_volatility"] < result.loc[1, "daily_volatility"]


def test_screen_can_allow_limited_bad_years_after_minimum_history() -> None:
    """A mature ETF may pass with limited bad years when its average return is high."""
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
            "TOO_MANY_BAD",
            {
                2020: (100.0, 110.0),
                2021: (100.0, 101.0),
                2022: (100.0, 101.0),
                2023: (100.0, 101.0),
                2024: (100.0, 120.0),
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

    result = screen_etfs_by_yearly_return(
        price_frame=price_frame,
        min_yearly_return=0.02,
        min_average_yearly_return=0.04,
        min_trading_days_per_year=2,
        min_years=5,
        max_bad_years=2,
    )

    assert result["ticker"].tolist() == ["MATURE"]
    assert result.loc[0, "bad_years"] == 2
    assert math.isclose(result.loc[0, "bad_year_fraction"], 0.4)
