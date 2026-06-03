"""
labels.py
---------
Leakage-safe label registry kept separate from predictor features.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# Labels are computed after feature construction to keep forward targets isolated.


def _label_next_regular_session_return(frame: pd.DataFrame) -> pd.Series:
    """Compute the forward close-to-current-bar return to the next regular close."""
    return frame["next_regular_close"] / frame["close"] - 1.0


def _label_next_regular_session_volatility(frame: pd.DataFrame) -> pd.Series:
    """Expose next-session realized volatility precomputed at session level."""
    return frame["next_session_realized_volatility"].astype(float)


def _label_quantile(
    frame: pd.DataFrame,
    config: dict[str, Any],
    label_name: str,
) -> pd.Series:
    """Bucket one forward target into timestamp-wise quantiles."""
    target_column = str(config["target_col"])
    n_quantiles = int(config.get("n_quantiles", 5))

    if target_column not in frame.columns:
        raise KeyError(
            f"Label {label_name!r} requires missing target column {target_column!r}."
        )

    # Rank inside each timestamp so the label only compares symbols that are
    # simultaneously visible at that point in time.
    rank = frame.groupby("timestamp")[target_column].rank(pct=True)
    return np.ceil(rank * n_quantiles).clip(lower=1, upper=n_quantiles)


def _attach_next_session_realized_volatility(
    session_primitives: pd.DataFrame,
    regular_bars: pd.DataFrame,
) -> pd.DataFrame:
    """Attach next-session realized volatility to each current session row.

    Realized volatility is estimated within each (symbol, session_date) regular
    session using the standard deviation of intraday log returns, then shifted
    by one session so labels remain strictly forward-looking.
    """
    realized_vol = (
        regular_bars.assign(
            bar_log_return=regular_bars.groupby(["symbol", "session_date"])[
                "close"
            ].transform(lambda series: np.log(series / series.shift(1)))
        )
        .groupby(["symbol", "session_date"], sort=False)["bar_log_return"]
        .std()
        .rename("session_realized_volatility")
        .reset_index()
    )
    merged = session_primitives.merge(
        realized_vol, on=["symbol", "session_date"], how="left"
    )
    merged["next_session_realized_volatility"] = merged.groupby("symbol")[
        "session_realized_volatility"
    ].shift(-1)
    return merged


def _build_label_series(
    label_frame: pd.DataFrame,
    config: dict[str, Any],
    label_name: str,
) -> pd.Series:
    """Dispatch one configured label without growing the main loop."""
    function_name = str(config["fn"])
    if function_name == "next_regular_session_return":
        return _label_next_regular_session_return(label_frame)
    if function_name == "next_regular_session_volatility":
        return _label_next_regular_session_volatility(label_frame)
    if function_name == "quantile_label":
        return _label_quantile(label_frame, config, label_name)
    raise ValueError(f"Unsupported label function: {function_name}")


def run_label_registry(
    feature_frame: pd.DataFrame,
    session_primitives: pd.DataFrame,
    label_configs: list[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build configured labels after feature construction is complete.

    Parameters
    ----------
    feature_frame : pd.DataFrame
        Final feature matrix used as the left side for label joins.
    session_primitives : pd.DataFrame
        Session-level primitives used to derive forward volatility labels.
    label_configs : list[dict[str, Any]]
        Label registry configuration entries.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        Label-augmented frame and label manifest table with null-rate stats.
    """
    working_primitives = _attach_next_session_realized_volatility(
        session_primitives=session_primitives,
        regular_bars=feature_frame,
    )
    label_frame = feature_frame.merge(
        working_primitives[
            ["symbol", "session_date", "next_session_realized_volatility"]
        ],
        on=["symbol", "session_date"],
        how="left",
    )

    manifest_rows: list[dict[str, Any]] = []
    for config in label_configs:
        if not bool(config.get("enabled", True)):
            continue

        label_name = str(config["name"])
        function_name = str(config["fn"])
        # Keep the registry loop linear: compute the series once, assign it
        # once, then record the manifest row.
        label_frame[label_name] = _build_label_series(
            label_frame,
            config,
            label_name,
        )

        manifest_rows.append(
            {
                "kind": "label",
                "name": label_name,
                "family": "target",
                "fn": function_name,
                "timeframe": "future",
                "asof_rule": "future_window_only",
                "lag_rule": "n/a",
                "max_staleness_rule": "n/a",
                "input_columns": str(config.get("target_col", "next_regular_close")),
                "null_rate": float(label_frame[label_name].isna().mean()),
            }
        )

    if "next_session_realized_volatility" in label_frame.columns:
        label_frame = label_frame.drop(columns=["next_session_realized_volatility"])
    return label_frame, pd.DataFrame(manifest_rows)
