"""
sessionize.py
-------------
Derive reusable market-session primitives from normalized minute bars.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Session boundary constants are minutes-from-midnight in the internal timezone.
SESSION_ORDER = ["overnight", "premarket", "regular", "postmarket"]
SESSION_START_MINUTE = 4 * 60
REGULAR_START_MINUTE = 9 * 60 + 30
REGULAR_END_MINUTE = 16 * 60
POSTMARKET_END_MINUTE = 20 * 60
SESSION_VALUE_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trades_count",
    "bar_count",
    "start_timestamp",
    "end_timestamp",
]
PRIOR_REGULAR_FIELDS = [
    "close",
    "open",
    "high",
    "low",
    "volume",
    "return",
]


def classify_market_session(timestamp: pd.Series) -> tuple[pd.Series, pd.Series]:
    """
    Classify each normalized timestamp into one trading-date and one session.

    Trading-date convention:
    - `20:00` through `23:59` belongs to the next regular session date
    - `00:00` through `03:59` belongs to the current calendar date
    """
    naive_timestamp = timestamp.dt.tz_localize(None)
    clock_minutes = naive_timestamp.dt.hour * 60 + naive_timestamp.dt.minute

    session_name = np.select(
        [
            (clock_minutes >= SESSION_START_MINUTE)
            & (clock_minutes < REGULAR_START_MINUTE),
            (clock_minutes >= REGULAR_START_MINUTE)
            & (clock_minutes < REGULAR_END_MINUTE),
            (clock_minutes >= REGULAR_END_MINUTE)
            & (clock_minutes < POSTMARKET_END_MINUTE),
        ],
        ["premarket", "regular", "postmarket"],
        default="overnight",
    )

    session_date = naive_timestamp.dt.normalize()
    next_day_mask = clock_minutes >= POSTMARKET_END_MINUTE
    session_date = session_date + pd.to_timedelta(next_day_mask.astype(int), unit="D")
    return pd.Series(session_date), pd.Series(session_name)


def _aggregate_one_session(
    classified_bars: pd.DataFrame,
    session_name: str,
) -> pd.DataFrame:
    """Aggregate one named market session to one row per symbol and trading date."""
    session_bars = classified_bars[
        classified_bars["market_session"] == session_name
    ].copy()
    if session_bars.empty:
        return pd.DataFrame(columns=["symbol", "session_date"])

    aggregated = (
        session_bars.groupby(["symbol", "session_date"], sort=False)
        .agg(
            session_open=("open", "first"),
            session_high=("high", "max"),
            session_low=("low", "min"),
            session_close=("close", "last"),
            session_volume=("volume", "sum"),
            session_trades_count=("trades_count", "sum"),
            session_bar_count=("timestamp", "size"),
            session_start_timestamp=("timestamp", "min"),
            session_end_timestamp=("timestamp", "max"),
        )
        .reset_index()
    )

    rename_map = {
        column: f"{session_name}_{column.removeprefix('session_')}"
        for column in aggregated.columns
        if column not in {"symbol", "session_date"}
    }
    return aggregated.rename(columns=rename_map)


def _attach_forward_session_targets(session_primitives: pd.DataFrame) -> pd.DataFrame:
    """Attach next-session close and realized-volatility targets at the session level."""
    enriched = session_primitives.sort_values(["symbol", "session_date"]).copy()
    enriched["next_regular_close"] = enriched.groupby("symbol")["regular_close"].shift(
        -1
    )
    enriched["next_regular_close_timestamp"] = enriched.groupby("symbol")[
        "regular_end_timestamp"
    ].shift(-1)
    enriched["next_regular_open"] = enriched.groupby("symbol")["regular_open"].shift(-1)
    enriched["next_regular_volume"] = enriched.groupby("symbol")[
        "regular_volume"
    ].shift(-1)
    return enriched


def _ensure_session_columns(session_primitives: pd.DataFrame) -> pd.DataFrame:
    """Guarantee a stable per-session column set even when some sessions are absent."""
    enriched = session_primitives.copy()
    for session_name in SESSION_ORDER:
        for value_column in SESSION_VALUE_COLUMNS:
            column_name = f"{session_name}_{value_column}"
            if column_name not in enriched.columns:
                enriched[column_name] = pd.NA
    return enriched


def _attach_prior_regular_fields(session_primitives: pd.DataFrame) -> pd.DataFrame:
    """Shift prior regular-session fields through one explicit loop."""
    enriched = session_primitives.copy()
    grouped = enriched.groupby("symbol")

    # These columns all use the same previous-regular-session rule, so a short
    # loop is easier to scan than repeating six near-identical assignments.
    for field_name in PRIOR_REGULAR_FIELDS:
        current_column = f"regular_{field_name}"
        prior_column = f"prior_regular_{field_name}"
        enriched[prior_column] = grouped[current_column].shift(1)
    return enriched


def build_session_primitives(
    normalized_primary_bars: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build both bar-level session labels and session-level primitives.

    Returns
    -------
    classified_bars
        Original bars with `session_date` and `market_session`.
    session_primitives
        One row per `(symbol, session_date)` with cross-session context.
    """
    classified_bars = normalized_primary_bars.copy()
    session_date, session_name = classify_market_session(classified_bars["timestamp"])
    classified_bars["session_date"] = pd.to_datetime(session_date)
    classified_bars["market_session"] = session_name
    classified_bars = classified_bars.sort_values(["symbol", "timestamp"]).reset_index(
        drop=True
    )

    aggregates = [
        _aggregate_one_session(classified_bars, session_name=value)
        for value in SESSION_ORDER
    ]
    session_primitives = aggregates[0]
    for aggregated in aggregates[1:]:
        session_primitives = session_primitives.merge(
            aggregated,
            on=["symbol", "session_date"],
            how="outer",
        )

    session_primitives = _ensure_session_columns(session_primitives)
    session_primitives = session_primitives.sort_values(
        ["symbol", "session_date"]
    ).reset_index(drop=True)
    session_primitives["regular_return"] = (
        session_primitives["regular_close"] / session_primitives["regular_open"] - 1.0
    )
    session_primitives["premarket_return"] = (
        session_primitives["premarket_close"] / session_primitives["premarket_open"]
        - 1.0
    )

    session_primitives = _attach_prior_regular_fields(session_primitives)
    session_primitives["prior_regular_range"] = (
        session_primitives["prior_regular_high"]
        - session_primitives["prior_regular_low"]
    ) / session_primitives["prior_regular_close"]
    session_primitives["overnight_gap"] = (
        session_primitives["regular_open"] / session_primitives["prior_regular_close"]
        - 1.0
    )
    session_primitives["asof_timestamp"] = session_primitives[
        "regular_end_timestamp"
    ].fillna(session_primitives["postmarket_end_timestamp"])
    session_primitives["has_regular_session"] = (
        session_primitives["regular_bar_count"].fillna(0) > 0
    )

    session_primitives = _attach_forward_session_targets(session_primitives)
    return classified_bars, session_primitives


def attach_session_primitives(
    classified_bars: pd.DataFrame,
    session_primitives: pd.DataFrame,
) -> pd.DataFrame:
    """Join session-level primitives back onto each classified bar."""
    join_columns = [
        column
        for column in session_primitives.columns
        if column not in {"asof_timestamp"}
    ]
    enriched = classified_bars.merge(
        session_primitives[join_columns],
        on=["symbol", "session_date"],
        how="left",
    )
    return enriched.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
