"""Regression tests for core feature-engineering pipeline components.

These tests validate session classification behavior, leakage-safe context joins,
and forward-looking label construction on compact synthetic fixtures.
"""

from __future__ import annotations
# ruff: noqa: E402

import math
import pathlib
import sys

import pandas as pd

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from feature_engineering.enrich import apply_context_joins
from feature_engineering.labels import run_label_registry
from feature_engineering.sessionize import (
    build_session_primitives,
    classify_market_session,
)


def _ny_timestamp(values: list[str]) -> pd.Series:
    """Build timezone-aware New York timestamps from UTC-like string inputs."""
    return pd.Series(pd.to_datetime(values, utc=True).tz_convert("America/New_York"))


def test_classify_market_session_and_trading_date_roll() -> None:
    timestamps = _ny_timestamp(
        [
            "2025-10-01 07:59:00+00:00",  # 03:59 NY
            "2025-10-01 08:00:00+00:00",  # 04:00 NY
            "2025-10-01 13:30:00+00:00",  # 09:30 NY
            "2025-10-01 20:00:00+00:00",  # 16:00 NY
            "2025-10-02 00:01:00+00:00",  # 20:01 NY previous local date
        ]
    )

    session_date, session_name = classify_market_session(timestamps)

    assert session_name.tolist() == [
        "overnight",
        "premarket",
        "regular",
        "postmarket",
        "overnight",
    ]
    assert pd.Timestamp(session_date.iloc[-1]) == pd.Timestamp("2025-10-02")


def test_session_primitives_compute_prior_session_fields() -> None:
    timestamps = _ny_timestamp(
        [
            "2025-10-01 13:30:00+00:00",  # 09:30 NY
            "2025-10-01 19:59:00+00:00",  # 15:59 NY
            "2025-10-02 13:30:00+00:00",  # 09:30 NY
            "2025-10-02 19:59:00+00:00",  # 15:59 NY
        ]
    )
    primary = pd.DataFrame(
        {
            "symbol": ["SPY"] * 4,
            "timestamp": timestamps,
            "open": [100.0, 101.0, 102.0, 103.0],
            "high": [101.0, 102.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0],
            "close": [101.0, 101.5, 103.0, 104.0],
            "volume": [10.0, 10.0, 10.0, 10.0],
            "trades_count": [1.0, 1.0, 1.0, 1.0],
        }
    )

    _, session_primitives = build_session_primitives(primary)
    day_two = session_primitives.loc[
        session_primitives["session_date"] == pd.Timestamp("2025-10-02")
    ].iloc[0]

    expected_prior_return = 101.5 / 100.0 - 1.0
    expected_gap = 102.0 / 101.5 - 1.0

    assert math.isclose(
        day_two["prior_regular_return"], expected_prior_return, rel_tol=1e-9
    )
    assert math.isclose(day_two["overnight_gap"], expected_gap, rel_tol=1e-9)
    assert day_two["prior_regular_close"] == 101.5


def test_context_join_applies_lag_and_staleness_without_duplicating_symbol() -> None:
    base = pd.DataFrame(
        {
            "symbol": ["SPY", "QQQ"],
            "timestamp": _ny_timestamp(
                [
                    "2025-10-01 14:00:00+00:00",
                    "2025-10-01 14:02:00+00:00",
                ]
            ),
            "close": [100.0, 200.0],
        }
    )
    context = pd.DataFrame(
        {
            "symbol": ["VIX", "VIX"],
            "timestamp": _ny_timestamp(
                [
                    "2025-10-01 14:00:00+00:00",
                    "2025-10-01 14:01:00+00:00",
                ]
            ),
            "ctx_vix_close": [20.0, 21.0],
            "source_name": ["vix_context", "vix_context"],
        }
    )

    enriched, audit = apply_context_joins(
        base_frame=base,
        context_configs=[
            {
                "name": "vix_context",
                "table": "indices",
                "columns": ["ctx_vix_close"],
                "align": "asof",
                "availability": "same_bar",
                "lag": "0min",
                "max_staleness": "1min",
            }
        ],
        normalized_context_frames={"vix_context": context},
    )

    assert "symbol" in enriched.columns
    assert "symbol_x" not in enriched.columns
    assert enriched["ctx_vix_close"].tolist() == [20.0, 21.0]
    assert audit.loc[0, "stale_rate"] == 0.0

    stale_enriched, stale_audit = apply_context_joins(
        base_frame=base.iloc[[1]].copy(),
        context_configs=[
            {
                "name": "vix_context",
                "table": "indices",
                "columns": ["ctx_vix_close"],
                "align": "asof",
                "availability": "same_bar",
                "lag": "0min",
                "max_staleness": "30s",
            }
        ],
        normalized_context_frames={"vix_context": context},
    )

    assert pd.isna(stale_enriched.loc[0, "ctx_vix_close"])
    assert stale_audit.loc[0, "stale_rate"] == 1.0


def test_labels_use_only_future_session_data() -> None:
    feature_frame = pd.DataFrame(
        {
            "symbol": ["SPY"] * 5,
            "session_date": pd.to_datetime(
                ["2025-10-01", "2025-10-01", "2025-10-02", "2025-10-02", "2025-10-02"]
            ),
            "timestamp": _ny_timestamp(
                [
                    "2025-10-01 14:00:00+00:00",
                    "2025-10-01 19:59:00+00:00",
                    "2025-10-02 13:30:00+00:00",
                    "2025-10-02 14:30:00+00:00",
                    "2025-10-02 19:59:00+00:00",
                ]
            ),
            "close": [100.0, 101.0, 110.0, 115.5, 121.0],
            "next_regular_close": [121.0, 121.0, pd.NA, pd.NA, pd.NA],
        }
    )
    session_primitives = pd.DataFrame(
        {
            "symbol": ["SPY", "SPY"],
            "session_date": pd.to_datetime(["2025-10-01", "2025-10-02"]),
            "regular_close": [101.0, 121.0],
            "regular_end_timestamp": _ny_timestamp(
                [
                    "2025-10-01 19:59:00+00:00",
                    "2025-10-02 19:59:00+00:00",
                ]
            ),
        }
    )

    labeled, manifest = run_label_registry(
        feature_frame=feature_frame,
        session_primitives=session_primitives,
        label_configs=[
            {
                "name": "target_next_regular_session_return",
                "fn": "next_regular_session_return",
            },
            {
                "name": "target_next_regular_session_volatility",
                "fn": "next_regular_session_volatility",
            },
        ],
    )

    expected_return = 121.0 / 100.0 - 1.0
    expected_future_vol = pd.Series(
        [
            math.log(115.5 / 110.0),
            math.log(121.0 / 115.5),
        ]
    ).std()

    assert math.isclose(
        labeled.loc[0, "target_next_regular_session_return"],
        expected_return,
        rel_tol=1e-9,
    )
    assert math.isclose(
        labeled.loc[0, "target_next_regular_session_volatility"],
        expected_future_vol,
        rel_tol=1e-9,
    )
    assert set(manifest["kind"]) == {"label"}
