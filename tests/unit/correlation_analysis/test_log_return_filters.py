"""Regression tests for log-return selection filter semantics.

These tests pin down the repo convention that selection hurdles are expressed
in log-return units, not simple-return percentages.
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

from correlation_analysis import correlate_utils as utils


def _candidate_frame(tickers: list[str]) -> pd.DataFrame:
    """Build the minimal candidate metadata table needed by the filters."""
    return pd.DataFrame(
        {
            "ticker": tickers,
            "vol_combined": [1.0] * len(tickers),
            "start_date": ["2010-01-01"] * len(tickers),
        }
    )


def test_filter_min_total_return_interprets_threshold_in_log_units() -> None:
    """A 0.20 hurdle should compare against cumulative log return directly."""
    dates = pd.to_datetime(["2020-01-03", "2020-01-10"])
    log_ret = pd.DataFrame(
        {
            # 0.19 log return is below the 0.20 log hurdle.
            "ALMOST": [0.10, 0.09],
            # 0.21 log return is above the 0.20 log hurdle.
            "PASS": [0.10, 0.11],
        },
        index=dates,
    )

    filtered_log_ret, filtered_candidates = utils.filter_min_total_return(
        log_ret=log_ret,
        candidates=_candidate_frame(["ALMOST", "PASS"]),
        min_total_return=0.20,
        anchor_tickers=[],
    )

    assert filtered_log_ret.columns.tolist() == ["PASS"]
    assert filtered_candidates["ticker"].tolist() == ["PASS"]


def test_compute_average_yearly_returns_returns_calendar_year_log_means() -> None:
    """Average yearly return should be the mean of annual log-return sums."""
    dates = pd.to_datetime(
        [
            "2020-01-31",
            "2020-12-31",
            "2021-01-31",
            "2021-12-31",
        ]
    )
    yearly_log_return = math.log(1.10)
    log_ret = pd.DataFrame(
        {
            "ETF": [yearly_log_return, 0.0, yearly_log_return, 0.0],
        },
        index=dates,
    )

    average_yearly_return = utils.compute_average_yearly_returns(log_ret)

    assert math.isclose(
        average_yearly_return["ETF"],
        yearly_log_return,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
