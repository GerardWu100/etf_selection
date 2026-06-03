"""
source_adapters.py
------------------
Load raw source tables into one canonical point-in-time schema.

The adapters deliberately keep table-specific SQL close to the source so the
rest of the pipeline can work with one normalized frame:

- minute-bar sources expose `timestamp`, `symbol`, and OHLCV-like columns
- the options source is summarized to one daily point-in-time row per symbol
- table metadata carries timezone and source-kind information for later audits
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import clickhouse_connect
import pandas as pd

from correlation_analysis.correlate_utils import resolve_analysis_window
from data_pipeline.sql_helpers import build_symbols_in_list

# Canonical columns define the normalized schema expected by downstream stages.
CANONICAL_COLUMNS = [
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trades_count",
    "call_volume",
    "put_volume",
    "total_open_interest",
    "call_iv_mid",
    "put_iv_mid",
    "put_call_volume_ratio",
]


@dataclass(frozen=True)
class TableMetadata:
    """Static metadata for each supported source table."""

    database: str
    table: str
    source_kind: str
    source_timezone: str
    has_volume: bool
    has_trades_count: bool


TABLE_METADATA: dict[tuple[str, str], TableMetadata] = {
    ("firstrate", "etfs"): TableMetadata(
        database="firstrate",
        table="etfs",
        source_kind="minute_bars",
        source_timezone="America/New_York",
        has_volume=True,
        has_trades_count=False,
    ),
    ("firstrate", "stocks"): TableMetadata(
        database="firstrate",
        table="stocks",
        source_kind="minute_bars",
        source_timezone="America/New_York",
        has_volume=True,
        has_trades_count=False,
    ),
    ("firstrate", "futures"): TableMetadata(
        database="firstrate",
        table="futures",
        source_kind="minute_bars",
        source_timezone="America/New_York",
        has_volume=True,
        has_trades_count=False,
    ),
    ("firstrate", "crypto"): TableMetadata(
        database="firstrate",
        table="crypto",
        source_kind="minute_bars",
        source_timezone="UTC",
        has_volume=True,
        has_trades_count=False,
    ),
    ("firstrate", "indices"): TableMetadata(
        database="firstrate",
        table="indices",
        source_kind="minute_bars",
        source_timezone="America/New_York",
        has_volume=False,
        has_trades_count=False,
    ),
    ("firstrate", "options"): TableMetadata(
        database="firstrate",
        table="options",
        source_kind="options_summary",
        source_timezone="America/New_York",
        has_volume=True,
        has_trades_count=False,
    ),
    ("coinmetrics", "perpetual"): TableMetadata(
        database="coinmetrics",
        table="perpetual",
        source_kind="minute_bars",
        source_timezone="UTC",
        has_volume=True,
        has_trades_count=True,
    ),
}


def get_table_metadata(source_config: dict[str, Any]) -> TableMetadata:
    """Return the supported metadata entry for one source configuration."""
    key = (str(source_config["database"]), str(source_config["table"]))
    if key not in TABLE_METADATA:
        supported = sorted(TABLE_METADATA)
        raise ValueError(
            f"Unsupported source table {key}. Supported tables: {supported}"
        )
    return TABLE_METADATA[key]


def _build_symbol_filter(symbols: list[str]) -> str:
    """Build a ClickHouse `IN (...)` filter for one symbol list."""
    if not symbols:
        raise ValueError("Each source must define at least one symbol.")
    return f"symbol IN ({build_symbols_in_list(symbols)})"


def _empty_canonical_frame() -> pd.DataFrame:
    """Return an empty frame with the canonical source columns."""
    return pd.DataFrame(columns=CANONICAL_COLUMNS)


def _coerce_canonical_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Ensure every canonical column exists even when the source omits it."""
    normalized = frame.copy()
    for column in CANONICAL_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = pd.NA
    ordered = ["symbol", "timestamp"] + [
        column for column in CANONICAL_COLUMNS if column not in {"symbol", "timestamp"}
    ]
    return normalized[ordered].copy()


def _run_query(
    client: clickhouse_connect.driver.Client,
    query: str,
) -> pd.DataFrame:
    """Execute SQL and return a Pandas DataFrame with driver-provided columns."""
    result = client.query(query)
    if not result.result_rows:
        return _empty_canonical_frame()
    return pd.DataFrame(result.result_rows, columns=result.column_names)


def _build_minute_bar_query(
    source_config: dict[str, Any],
    metadata: TableMetadata,
    start_date: str,
    end_date: str,
) -> str:
    """Build one canonical OHLCV-like query for a supported minute-bar table."""
    history_end_exclusive = (pd.Timestamp(end_date) + pd.Timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    volume_expr = "volume" if metadata.has_volume else "CAST(NULL AS Nullable(Float64))"
    trades_expr = (
        "trades_count"
        if metadata.has_trades_count
        else "CAST(NULL AS Nullable(UInt32))"
    )
    symbol_filter = _build_symbol_filter(
        [str(symbol) for symbol in source_config["symbols"]]
    )

    return f"""
        SELECT
            symbol,
            ts AS timestamp,
            open,
            high,
            low,
            close,
            {volume_expr} AS volume,
            {trades_expr} AS trades_count
        FROM {metadata.database}.{metadata.table}
        WHERE {symbol_filter}
          AND ts >= '{start_date}'
          AND ts < '{history_end_exclusive}'
        ORDER BY symbol, timestamp
    """


def _build_options_summary_query(
    source_config: dict[str, Any],
    metadata: TableMetadata,
    start_date: str,
    end_date: str,
) -> str:
    """Build a daily options summary query aligned to the market close timestamp."""
    symbol_filter = _build_symbol_filter(
        [str(symbol) for symbol in source_config["symbols"]]
    )
    return f"""
        SELECT
            symbol,
            toDateTime(trade_date, '{metadata.source_timezone}') + toIntervalHour(16) AS timestamp,
            CAST(NULL AS Nullable(Float64)) AS open,
            CAST(NULL AS Nullable(Float64)) AS high,
            CAST(NULL AS Nullable(Float64)) AS low,
            CAST(NULL AS Nullable(Float64)) AS close,
            toFloat64(sum(volume)) AS volume,
            CAST(NULL AS Nullable(UInt32)) AS trades_count,
            toFloat64(sumIf(volume, option_type = 'c')) AS call_volume,
            toFloat64(sumIf(volume, option_type = 'p')) AS put_volume,
            toFloat64(sum(open_interest)) AS total_open_interest,
            avgIf((bid_iv + ask_iv) / 2.0, option_type = 'c' AND bid_iv > 0 AND ask_iv > 0) AS call_iv_mid,
            avgIf((bid_iv + ask_iv) / 2.0, option_type = 'p' AND bid_iv > 0 AND ask_iv > 0) AS put_iv_mid,
            toFloat64(sumIf(volume, option_type = 'p')) / nullIf(toFloat64(sumIf(volume, option_type = 'c')), 0.0) AS put_call_volume_ratio
        FROM {metadata.database}.{metadata.table}
        WHERE {symbol_filter}
          AND trade_date >= toDate('{start_date}')
          AND trade_date <= toDate('{end_date}')
        GROUP BY symbol, trade_date
        ORDER BY symbol, timestamp
    """


QUERY_BUILDERS = {
    "minute_bars": _build_minute_bar_query,
    "options_summary": _build_options_summary_query,
}


def load_source_frame(
    client: clickhouse_connect.driver.Client,
    source_config: dict[str, Any],
    start_date: str | pd.Timestamp,
    end_date: str | pd.Timestamp,
) -> pd.DataFrame:
    """
    Load one source into a canonical long-form frame.

    Parameters
    ----------
    client
        Connected ClickHouse client.
    source_config
        One source entry from the feature-engineering config.
    start_date, end_date
        Inclusive analysis window.

    Returns
    -------
    pd.DataFrame
        Canonical source frame sorted by `(symbol, timestamp)`.
    """
    metadata = get_table_metadata(source_config)
    window_start, window_end = resolve_analysis_window(start_date, end_date)

    if metadata.source_kind not in QUERY_BUILDERS:
        raise ValueError(f"Unsupported source kind: {metadata.source_kind}")

    # The metadata selects one focused SQL builder so the main load path stays
    # small even as supported source kinds grow.
    query_builder = QUERY_BUILDERS[metadata.source_kind]
    query = query_builder(source_config, metadata, window_start, window_end)

    frame = _run_query(client, query)
    frame = _coerce_canonical_columns(frame)
    frame["source_name"] = str(source_config["name"])
    frame["source_database"] = metadata.database
    frame["source_table"] = metadata.table
    frame["source_kind"] = metadata.source_kind
    frame["source_timezone"] = metadata.source_timezone
    frame["source_symbol_count"] = len(source_config["symbols"])
    return frame.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
