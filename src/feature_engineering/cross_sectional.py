"""
cross_sectional.py
------------------
Cross-sectional feature passes grouped by timestamp.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

# Cross-sectional transforms operate row-wise within each timestamp slice.
CrossSectionalFunction = Callable[[pd.DataFrame, dict[str, Any], str], pd.Series]


def _required_input_column(
    frame: pd.DataFrame,
    feature_name: str,
    config: dict[str, Any],
) -> str:
    """Resolve and validate the configured input column for one transform."""
    input_column = str(config["input_col"])
    if input_column not in frame.columns:
        raise KeyError(
            f"Cross-sectional feature {feature_name!r} needs missing input {input_column!r}."
        )
    return input_column


def _cross_sectional_zscore(
    frame: pd.DataFrame,
    config: dict[str, Any],
    feature_name: str,
) -> pd.Series:
    """Compute within-timestamp z-scores for one feature column.

    The transform is performed cross-sectionally at each timestamp, so every
    value is standardized relative to the active symbol universe at that time.
    """
    input_column = _required_input_column(frame, feature_name, config)
    grouped = frame.groupby("timestamp")[input_column]
    mean = grouped.transform("mean")
    std = grouped.transform("std").replace(0.0, np.nan)
    return (frame[input_column] - mean) / std


def _cross_sectional_percentile_rank(
    frame: pd.DataFrame,
    config: dict[str, Any],
    feature_name: str,
) -> pd.Series:
    """Compute within-timestamp percentile ranks for one feature column."""
    input_column = _required_input_column(frame, feature_name, config)
    return frame.groupby("timestamp")[input_column].rank(pct=True)


def _benchmark_residual(
    frame: pd.DataFrame,
    config: dict[str, Any],
    feature_name: str,
) -> pd.Series:
    """Subtract the benchmark symbol value from each row at matching timestamps."""
    input_column = _required_input_column(frame, feature_name, config)
    benchmark_symbol = str(config["benchmark_symbol"])
    benchmark_series = (
        frame.loc[frame["symbol"] == benchmark_symbol, ["timestamp", input_column]]
        .drop_duplicates(subset=["timestamp"])
        .rename(columns={input_column: "_benchmark_value"})
    )
    merged = frame.merge(benchmark_series, on="timestamp", how="left")
    return merged[input_column] - merged["_benchmark_value"]


def _peer_group_demean(
    frame: pd.DataFrame,
    config: dict[str, Any],
    feature_name: str,
) -> pd.Series:
    """Demean one feature within each timestamp and peer-group partition."""
    input_column = _required_input_column(frame, feature_name, config)
    group_column = str(config.get("group_col", "peer_group"))
    if group_column not in frame.columns:
        raise KeyError(
            f"Cross-sectional feature {feature_name!r} requires peer-group column {group_column!r}."
        )

    peer_mean = frame.groupby(["timestamp", group_column])[input_column].transform(
        "mean"
    )
    return frame[input_column] - peer_mean


CROSS_SECTIONAL_FUNCTIONS: dict[str, CrossSectionalFunction] = {
    "benchmark_residual": _benchmark_residual,
    "peer_group_demean": _peer_group_demean,
    "percentile_rank": _cross_sectional_percentile_rank,
    "zscore": _cross_sectional_zscore,
}


def run_cross_sectional_features(
    feature_frame: pd.DataFrame,
    cross_sectional_configs: list[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply configured cross-sectional transforms and return an audit manifest.

    Parameters
    ----------
    feature_frame : pd.DataFrame
        Per-symbol feature matrix that already contains base time-series
        features and required grouping columns.
    cross_sectional_configs : list[dict[str, Any]]
        Registry-style feature configuration list.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        Enriched feature frame and one-row-per-transform manifest with null-rate
        diagnostics.
    """
    enriched = feature_frame.copy()
    manifest_rows: list[dict[str, Any]] = []

    for config in cross_sectional_configs:
        if not bool(config.get("enabled", True)):
            continue

        feature_name = str(config["name"])
        function_name = str(config["fn"])
        input_column = str(config["input_col"])
        if function_name not in CROSS_SECTIONAL_FUNCTIONS:
            raise ValueError(f"Unsupported cross-sectional function: {function_name}")

        # Resolve the transform once so the loop reads as a short registry
        # runner instead of a growing branch chain.
        transform = CROSS_SECTIONAL_FUNCTIONS[function_name]
        values = transform(enriched, config, feature_name)
        enriched[feature_name] = values.replace([np.inf, -np.inf], np.nan)
        manifest_rows.append(
            {
                "kind": "cross_sectional_feature",
                "name": feature_name,
                "family": "cross_sectional",
                "fn": function_name,
                "timeframe": "base",
                "asof_rule": "same_timestamp_cross_section",
                "lag_rule": "0min",
                "max_staleness_rule": "0min",
                "input_columns": input_column,
                "null_rate": float(enriched[feature_name].isna().mean()),
            }
        )

    return enriched, pd.DataFrame(manifest_rows)
