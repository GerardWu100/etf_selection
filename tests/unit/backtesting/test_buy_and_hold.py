"""Regression tests for backtesting buy-and-hold behavior.

These tests protect the exact portfolio-valuation path used by the notebook
workflow and ensure the checked-in notebook file remains parseable JSON.
"""
# ruff: noqa: E402

from __future__ import annotations

import json
import math
import pathlib
import sys

import pandas as pd

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backtesting.buy_and_hold import run_weighted_backtest


def test_run_weighted_backtest_uses_exact_buy_and_hold_valuation(
    tmp_path: pathlib.Path,
) -> None:
    """Portfolio values should come from fixed shares, not weighted log-return sums."""
    price_parquet = tmp_path / "prices.parquet"

    # Two offsetting assets make the approximation error obvious.
    price_frame = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "AAA", "BBB", "AAA", "BBB"],
            "date": pd.to_datetime(
                [
                    "2020-01-01",
                    "2020-01-01",
                    "2020-01-02",
                    "2020-01-02",
                    "2020-01-03",
                    "2020-01-03",
                ]
            ),
            "close_price": [100.0, 100.0, 110.0, 90.0, 121.0, 81.0],
        }
    )
    price_frame.to_parquet(price_parquet, index=False)

    metrics, equity = run_weighted_backtest(
        tickers=["AAA", "BBB"],
        weights=[0.5, 0.5],
        start_date="2020-01-01",
        end_date="2020-01-03",
        initial_capital=100.0,
        price_parquet=price_parquet,
    )

    expected_total_log_return = math.log(1.01)

    assert metrics["start_date"] == "2020-01-01"
    assert metrics["end_date"] == "2020-01-03"
    assert metrics["final_value"] == 101.0
    assert math.isclose(
        metrics["total_log_return"],
        round(expected_total_log_return, 4),
        rel_tol=0.0,
        abs_tol=1e-12,
    )

    # The equity curve should include the entry date with initial capital and
    # then the exact fixed-share path through time.
    assert equity["date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2020-01-01",
        "2020-01-02",
        "2020-01-03",
    ]
    assert equity["portfolio_value"].tolist() == [100.0, 100.0, 101.0]
    assert equity["drawdown"].tolist() == [0.0, 0.0, 0.0]
    assert math.isclose(
        equity.loc[2, "log_return"],
        expected_total_log_return,
        rel_tol=0.0,
        abs_tol=1e-12,
    )


def test_backtesting_notebook_is_valid_json() -> None:
    """Notebook automation depends on the checked-in backtesting notebook parsing."""
    notebook_path = (
        PROJECT_ROOT
        / "notebooks"
        / "01_project_walkthrough"
        / "explore_buy_and_hold.ipynb"
    )
    notebook_payload = notebook_path.read_text()

    json.loads(notebook_payload)
