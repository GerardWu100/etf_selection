"""
enrich.py
---------
Apply explicit as-of context joins with lag and staleness audits.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

# Context joins are applied with explicit availability lag and staleness checks.


def _parse_timedelta(value: str | None) -> pd.Timedelta | None:
    """Parse optional timedelta config values, preserving empty-as-None semantics."""
    if value is None or str(value).strip() == "":
        return None
    return pd.Timedelta(str(value))


def _as_utc_ns(series: pd.Series) -> pd.Series:
    """Normalize datetimes to UTC nanosecond precision for stable as-of joins."""
    return pd.to_datetime(series, utc=True).astype("datetime64[ns, UTC]")


def _context_value_columns(
    context_frame: pd.DataFrame,
    source_name: str,
    config_columns: list[str],
    rename_map: dict[str, str],
) -> list[str]:
    """Validate and resolve output column names carried from one context source."""
    selected: list[str] = []
    for column in config_columns:
        if not context_frame.empty and column not in context_frame.columns:
            raise KeyError(
                f"Context source {source_name!r} does not contain column {column!r}."
            )
        selected.append(column)
    return [rename_map.get(column, column) for column in selected]


def _merge_asof_context(
    base_frame: pd.DataFrame,
    context_frame: pd.DataFrame,
    context_config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Merge one context source onto the base frame and return one audit row."""
    source_name = str(context_config["name"])
    rename_map = {
        str(original): str(renamed)
        for original, renamed in context_config.get("rename", {}).items()
    }
    requested_columns = [
        str(column) for column in context_config.get("columns", ["close"])
    ]
    join_on_symbol = bool(context_config.get("join_on_symbol", False))
    lag = _parse_timedelta(context_config.get("lag", "0min")) or pd.Timedelta(0)
    max_staleness = _parse_timedelta(context_config.get("max_staleness"))
    align = str(context_config.get("align", "asof")).lower()

    output_columns = _context_value_columns(
        context_frame,
        source_name=source_name,
        config_columns=requested_columns,
        rename_map=rename_map,
    )
    context_subset = context_frame.copy()
    context_subset["context_timestamp"] = context_subset["timestamp"]
    context_subset["available_timestamp"] = context_subset["timestamp"] + lag
    context_subset = context_subset.rename(columns=rename_map)

    merge_columns = ["available_timestamp", "context_timestamp"] + output_columns
    if join_on_symbol:
        merge_columns.append("symbol")
    context_subset = context_subset[merge_columns].copy()

    left = base_frame.copy()
    left["_row_id"] = range(len(left))
    left["_merge_timestamp"] = _as_utc_ns(left["timestamp"])
    context_subset["_merge_available_timestamp"] = _as_utc_ns(
        context_subset["available_timestamp"]
    )

    if align == "asof":
        if join_on_symbol:
            left = left.sort_values(["symbol", "_merge_timestamp"]).reset_index(
                drop=True
            )
            right = context_subset.sort_values(
                ["symbol", "_merge_available_timestamp"]
            ).reset_index(drop=True)
            merged = pd.merge_asof(
                left,
                right,
                left_on="_merge_timestamp",
                right_on="_merge_available_timestamp",
                by="symbol",
                direction="backward",
            )
        else:
            left = left.sort_values("_merge_timestamp").reset_index(drop=True)
            right = context_subset.sort_values(
                "_merge_available_timestamp"
            ).reset_index(drop=True)
            merged = pd.merge_asof(
                left,
                right,
                left_on="_merge_timestamp",
                right_on="_merge_available_timestamp",
                direction="backward",
            )
    elif align == "exact":
        right = context_subset.rename(
            columns={"_merge_available_timestamp": "_merge_timestamp"}
        )
        merge_keys = (
            ["_merge_timestamp", "symbol"] if join_on_symbol else ["_merge_timestamp"]
        )
        merged = left.merge(right, on=merge_keys, how="left")
    else:
        raise ValueError(f"Unsupported context align rule: {align!r}")

    context_time_col = f"{source_name}_context_timestamp"
    merged = merged.rename(columns={"context_timestamp": context_time_col})
    drop_columns = [
        column
        for column in [
            "available_timestamp",
            "_merge_timestamp",
            "_merge_available_timestamp",
        ]
        if column in merged.columns
    ]
    if drop_columns:
        merged = merged.drop(columns=drop_columns)

    age_minutes = (
        merged["timestamp"] - merged[context_time_col]
    ).dt.total_seconds() / 60.0
    stale_mask = pd.Series(False, index=merged.index)
    if max_staleness is not None:
        stale_mask = merged[context_time_col].notna() & (
            (merged["timestamp"] - merged[context_time_col]) > max_staleness
        )
        for column in output_columns:
            merged.loc[stale_mask, column] = pd.NA

    merged[f"{source_name}_effective_lag_minutes"] = age_minutes
    merged[f"{source_name}_is_stale"] = stale_mask
    merged = (
        merged.sort_values("_row_id").drop(columns=["_row_id"]).reset_index(drop=True)
    )

    null_rates = [float(merged[column].isna().mean()) for column in output_columns]
    audit_row = {
        "context_name": source_name,
        "source_table": str(context_config["table"]),
        "align": align,
        "availability": str(context_config.get("availability", "same_timestamp")),
        "lag": str(context_config.get("lag", "0min")),
        "max_staleness": str(context_config.get("max_staleness", "")),
        "join_on_symbol": join_on_symbol,
        "rows": int(len(merged)),
        "null_rate": float(max(null_rates) if null_rates else 1.0),
        "stale_rate": float(stale_mask.mean()),
        "mean_effective_lag_minutes": float(age_minutes.dropna().mean())
        if age_minutes.notna().any()
        else pd.NA,
        "max_effective_lag_minutes": float(age_minutes.dropna().max())
        if age_minutes.notna().any()
        else pd.NA,
    }
    return merged, audit_row


def apply_context_joins(
    base_frame: pd.DataFrame,
    context_configs: list[dict[str, Any]],
    normalized_context_frames: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply enabled context joins sequentially and collect join-quality audits."""
    enriched = base_frame.copy()
    audit_rows: list[dict[str, Any]] = []
    for context_config in context_configs:
        if not bool(context_config.get("enabled", True)):
            continue
        source_name = str(context_config["name"])
        enriched, audit_row = _merge_asof_context(
            enriched,
            normalized_context_frames[source_name],
            context_config=context_config,
        )
        audit_rows.append(audit_row)
    return enriched, pd.DataFrame(audit_rows)
