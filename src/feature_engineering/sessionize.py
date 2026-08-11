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

# Session-level columns that are NOT knowable while the regular session is still
# running. `regular_close` and friends summarise the whole session, `postmarket_*`
# happens after it, and `next_regular_*` belongs to the following day. Joining any
# of them onto an intraday bar would put the answer in the predictor set, so
# `attach_session_primitives` withholds them. Labels read them straight from the
# session-level table instead.
FORWARD_LOOKING_SESSION_COLUMNS = frozenset(
    {
        "asof_timestamp",
        "regular_close",
        "regular_high",
        "regular_low",
        "regular_volume",
        "regular_trades_count",
        "regular_bar_count",
        "regular_end_timestamp",
        "regular_return",
        "next_regular_close",
        "next_regular_close_timestamp",
        "next_regular_open",
        "next_regular_volume",
    }
    | {f"postmarket_{value_column}" for value_column in SESSION_VALUE_COLUMNS}
)


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
    # `np.select` returns a bare array, so the session-name Series must be given
    # the caller's index explicitly. Without it the two returned Series carry
    # different indexes and the caller's assignment silently produces all-NaN.
    return (
        pd.Series(session_date, index=timestamp.index),
        pd.Series(session_name, index=timestamp.index),
    )


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


def shift_over_regular_sessions(
    session_primitives: pd.DataFrame,
    source_column: str,
    periods: int,
) -> pd.Series:
    """
    Shift one column by whole regular sessions, skipping rows that have none.

    The trading-date roll can create a `session_date` that holds only late
    postmarket bars, for example a Friday 20:00 bar landing on Saturday. Shifting
    over every row would let such a row act as the previous or next regular
    session for its neighbours, wiping out the real value. Shifting over the
    regular-session rows only and reindexing back keeps the neighbours correct.
    """
    has_regular = session_primitives["regular_bar_count"].fillna(0) > 0
    regular_rows = session_primitives.loc[has_regular]
    shifted = regular_rows.groupby("symbol")[source_column].shift(periods)
    return shifted.reindex(session_primitives.index)


def _attach_forward_session_targets(session_primitives: pd.DataFrame) -> pd.DataFrame:
    """Attach next-session close and realized-volatility targets at the session level."""
    enriched = session_primitives.sort_values(["symbol", "session_date"]).copy()
    forward_source_columns = {
        "next_regular_close": "regular_close",
        "next_regular_close_timestamp": "regular_end_timestamp",
        "next_regular_open": "regular_open",
        "next_regular_volume": "regular_volume",
    }
    for target_column, source_column in forward_source_columns.items():
        enriched[target_column] = shift_over_regular_sessions(
            enriched,
            source_column,
            periods=-1,
        )
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

    # These columns all use the same previous-regular-session rule, so a short
    # loop is easier to scan than repeating six near-identical assignments.
    for field_name in PRIOR_REGULAR_FIELDS:
        current_column = f"regular_{field_name}"
        prior_column = f"prior_regular_{field_name}"
        enriched[prior_column] = shift_over_regular_sessions(
            enriched,
            current_column,
            periods=1,
        )
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
    """Join the point-in-time-safe session primitives back onto each classified bar."""
    join_columns = [
        column
        for column in session_primitives.columns
        if column not in FORWARD_LOOKING_SESSION_COLUMNS
    ]
    enriched = classified_bars.merge(
        session_primitives[join_columns],
        on=["symbol", "session_date"],
        how="left",
    )
    return enriched.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
