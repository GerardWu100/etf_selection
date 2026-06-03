"""
normalize.py
------------
Normalize raw source frames into one internal timezone and one column contract.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


# These fields are coerced uniformly so downstream math sees stable dtypes.
NUMERIC_COLUMNS = [
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


def _normalize_timestamp_column(
    frame: pd.DataFrame,
    internal_timezone: str,
) -> pd.DataFrame:
    """Convert source timestamps to UTC first, then into the internal timezone."""
    normalized = frame.copy()
    if normalized.empty:
        normalized["timestamp_utc"] = pd.Series(dtype="datetime64[ns, UTC]")
        normalized["timestamp"] = pd.Series(
            dtype=f"datetime64[ns, {internal_timezone}]"
        )
        return normalized

    timestamp_utc = pd.to_datetime(normalized["timestamp"], utc=True)
    normalized["timestamp_utc"] = timestamp_utc
    normalized["timestamp"] = timestamp_utc.dt.tz_convert(internal_timezone)
    return normalized


def _ensure_numeric_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Coerce numeric-like columns while keeping missing values nullable."""
    normalized = frame.copy()
    for column in NUMERIC_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = pd.NA
            continue
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    return normalized


def normalize_source_frame(
    frame: pd.DataFrame,
    source_config: dict[str, Any],
    internal_timezone: str,
) -> pd.DataFrame:
    """
    Normalize one raw source frame.

    The normalized contract preserves the original table metadata while making
    timestamps comparable across US market data and UTC-native crypto sources.
    """
    normalized = frame.copy()
    for column in ["symbol", "timestamp"]:
        if column not in normalized.columns:
            normalized[column] = pd.Series(dtype="object")
    normalized["symbol"] = normalized["symbol"].astype(str)
    normalized = _normalize_timestamp_column(normalized, internal_timezone)
    normalized = _ensure_numeric_columns(normalized)
    normalized["source_name"] = str(source_config["name"])
    normalized["feature_timezone"] = internal_timezone
    normalized["is_primary_source"] = bool(
        source_config.get("is_primary_source", False)
    )
    normalized["source_alias"] = str(source_config.get("alias", source_config["name"]))
    normalized = normalized.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    return normalized


def normalize_source_frames(
    raw_frames: dict[str, pd.DataFrame],
    source_configs: list[dict[str, Any]],
    internal_timezone: str,
) -> dict[str, pd.DataFrame]:
    """Normalize a batch of source frames keyed by config name."""
    normalized_frames: dict[str, pd.DataFrame] = {}
    for source_config in source_configs:
        source_name = str(source_config["name"])
        normalized_frames[source_name] = normalize_source_frame(
            raw_frames[source_name],
            source_config=source_config,
            internal_timezone=internal_timezone,
        )
    return normalized_frames
