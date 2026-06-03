"""
features.py
-----------
Per-symbol feature registry with explicit timeframe handling.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd


# Registry functions share one callable signature for config-driven execution.
FeatureFunction = Callable[[pd.DataFrame, dict[str, Any]], pd.Series]


def _required_column(frame: pd.DataFrame, column: str, feature_name: str) -> pd.Series:
    """Return one required column or raise a feature-specific error."""
    if column not in frame.columns:
        raise KeyError(f"Feature {feature_name!r} requires missing column {column!r}.")
    return frame[column]


def build_timeframe_frames(
    regular_bars: pd.DataFrame,
    timeframe_configs: list[dict[str, Any]],
) -> dict[str, pd.DataFrame]:
    """Resample regular-session minute bars to coarser OHLCV frames."""
    timeframe_frames: dict[str, pd.DataFrame] = {}
    base_columns = [
        "timestamp",
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "trades_count",
    ]
    resample_input = regular_bars[base_columns].copy()

    for timeframe_config in timeframe_configs:
        if not bool(timeframe_config.get("enabled", True)):
            continue
        frequency = str(timeframe_config["frequency"])
        parts: list[pd.DataFrame] = []
        for symbol, symbol_frame in resample_input.groupby("symbol", sort=False):
            symbol_frame = symbol_frame.sort_values("timestamp").set_index("timestamp")
            resampled = (
                symbol_frame.resample(
                    frequency,
                    label="right",
                    closed="right",
                )
                .agg(
                    {
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum",
                        "trades_count": "sum",
                    }
                )
                .dropna(subset=["close"])
                .reset_index()
            )
            resampled["symbol"] = symbol
            parts.append(resampled)

        timeframe_frames[frequency] = (
            pd.concat(parts, ignore_index=True)
            .sort_values(["symbol", "timestamp"])
            .reset_index(drop=True)
            if parts
            else pd.DataFrame(columns=base_columns)
        )
    return timeframe_frames


def feature_log_return(frame: pd.DataFrame, config: dict[str, Any]) -> pd.Series:
    """Compute grouped log returns on one close-like column."""
    close_col = str(config.get("close_col", "close"))
    window = int(config.get("window", 1))
    close_series = _required_column(frame, close_col, str(config["name"]))
    return close_series.groupby(frame["symbol"]).transform(
        lambda series: np.log(series / series.shift(window))
    )


def feature_level(frame: pd.DataFrame, config: dict[str, Any]) -> pd.Series:
    """Expose an existing column as a named feature."""
    input_col = str(config.get("input_col", config.get("close_col", "close")))
    return _required_column(frame, input_col, str(config["name"])).astype(float)


def feature_overnight_gap(frame: pd.DataFrame, _config: dict[str, Any]) -> pd.Series:
    """Return the precomputed overnight gap feature."""
    return frame["overnight_gap"].astype(float)


def feature_prior_session_return(
    frame: pd.DataFrame, _config: dict[str, Any]
) -> pd.Series:
    """Return the previous regular-session return already stored in primitives."""
    return frame["prior_regular_return"].astype(float)


def feature_prior_session_range(
    frame: pd.DataFrame, _config: dict[str, Any]
) -> pd.Series:
    """Return the previous regular-session range normalized by the prior close."""
    return frame["prior_regular_range"].astype(float)


def feature_session_return_from_open(
    frame: pd.DataFrame, config: dict[str, Any]
) -> pd.Series:
    """Measure the live regular-session move from the current session open."""
    close_col = str(config.get("close_col", "close"))
    close_series = _required_column(frame, close_col, str(config["name"]))
    return close_series / frame["regular_open"] - 1.0


def feature_realized_volatility(
    frame: pd.DataFrame, config: dict[str, Any]
) -> pd.Series:
    """Rolling realized volatility from grouped log returns."""
    close_col = str(config.get("close_col", "close"))
    window = int(config.get("window", 30))
    returns = feature_log_return(
        frame, {"name": config["name"], "close_col": close_col, "window": 1}
    )
    return returns.groupby(frame["symbol"]).transform(
        lambda series: series.rolling(window=window, min_periods=window).std()
    )


def feature_rolling_range(frame: pd.DataFrame, config: dict[str, Any]) -> pd.Series:
    """Rolling mean of normalized bar ranges."""
    high_col = str(config.get("high_col", "high"))
    low_col = str(config.get("low_col", "low"))
    close_col = str(config.get("close_col", "close"))
    window = int(config.get("window", 30))
    high = _required_column(frame, high_col, str(config["name"]))
    low = _required_column(frame, low_col, str(config["name"]))
    close = _required_column(frame, close_col, str(config["name"]))
    intrabar_range = (high - low) / close.replace(0.0, np.nan)
    return intrabar_range.groupby(frame["symbol"]).transform(
        lambda series: series.rolling(window=window, min_periods=window).mean()
    )


def feature_relative_return(frame: pd.DataFrame, config: dict[str, Any]) -> pd.Series:
    """Return the asset log return minus the benchmark log return."""
    close_col = str(config.get("close_col", "close"))
    benchmark_col = str(config["benchmark_close_col"])
    window = int(config.get("window", 1))
    own_return = feature_log_return(
        frame, {"name": config["name"], "close_col": close_col, "window": window}
    )
    benchmark_return = feature_log_return(
        frame,
        {"name": config["name"], "close_col": benchmark_col, "window": window},
    )
    return own_return - benchmark_return


def feature_beta_residual(frame: pd.DataFrame, config: dict[str, Any]) -> pd.Series:
    """Rolling beta residual versus a benchmark close series."""
    close_col = str(config.get("close_col", "close"))
    benchmark_col = str(config["benchmark_close_col"])
    window = int(config.get("window", 60))
    own_return = feature_log_return(
        frame, {"name": config["name"], "close_col": close_col, "window": 1}
    )
    benchmark_return = feature_log_return(
        frame,
        {"name": config["name"], "close_col": benchmark_col, "window": 1},
    )

    output = pd.Series(index=frame.index, dtype=float)
    for _, index in frame.groupby("symbol", sort=False).groups.items():
        symbol_index = pd.Index(index)
        symbol_returns = own_return.loc[symbol_index]
        symbol_benchmark = benchmark_return.loc[symbol_index]
        covariance = symbol_returns.rolling(window=window, min_periods=window).cov(
            symbol_benchmark
        )
        variance = symbol_benchmark.rolling(window=window, min_periods=window).var()
        beta = covariance / variance.replace(0.0, np.nan)
        output.loc[symbol_index] = symbol_returns - beta * symbol_benchmark
    return output


def feature_liquidity_surprise(
    frame: pd.DataFrame, config: dict[str, Any]
) -> pd.Series:
    """Volume surprise relative to the recent rolling mean."""
    volume_col = str(config.get("volume_col", "volume"))
    window = int(config.get("window", 60))
    volume = _required_column(frame, volume_col, str(config["name"]))
    rolling_mean = volume.groupby(frame["symbol"]).transform(
        lambda series: series.rolling(window=window, min_periods=window).mean()
    )
    return volume / rolling_mean.replace(0.0, np.nan) - 1.0


def feature_rsi(frame: pd.DataFrame, config: dict[str, Any]) -> pd.Series:
    """Simple rolling RSI on one close-like column."""
    close_col = str(config.get("close_col", "close"))
    window = int(config.get("window", 14))
    close = _required_column(frame, close_col, str(config["name"]))
    output = pd.Series(index=frame.index, dtype=float)
    for _, index in frame.groupby("symbol", sort=False).groups.items():
        symbol_close = close.loc[index]
        delta = symbol_close.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        mean_gain = gain.rolling(window=window, min_periods=window).mean()
        mean_loss = loss.rolling(window=window, min_periods=window).mean()
        rs = mean_gain / mean_loss.replace(0.0, np.nan)
        output.loc[index] = 100.0 - (100.0 / (1.0 + rs))
    return output


FEATURE_FUNCTIONS: dict[str, FeatureFunction] = {
    "beta_residual": feature_beta_residual,
    "level": feature_level,
    "liquidity_surprise": feature_liquidity_surprise,
    "log_return": feature_log_return,
    "overnight_gap": feature_overnight_gap,
    "prior_session_range": feature_prior_session_range,
    "prior_session_return": feature_prior_session_return,
    "range": feature_rolling_range,
    "realized_volatility": feature_realized_volatility,
    "relative_return": feature_relative_return,
    "rsi": feature_rsi,
    "session_return_from_open": feature_session_return_from_open,
}


def _merge_timeframe_feature(
    base_frame: pd.DataFrame,
    timeframe_frame: pd.DataFrame,
    feature_name: str,
) -> pd.DataFrame:
    """As-of join one timeframe feature back to the base regular bars."""
    left = base_frame.copy()
    left["_row_id"] = range(len(left))
    parts: list[pd.DataFrame] = []

    for symbol, left_part in left.groupby("symbol", sort=False):
        right_part = timeframe_frame.loc[
            timeframe_frame["symbol"] == symbol,
            ["timestamp", feature_name],
        ].copy()
        left_part = left_part.sort_values("timestamp").copy()
        left_part["_merge_timestamp"] = pd.to_datetime(
            left_part["timestamp"], utc=True
        ).astype("datetime64[ns, UTC]")
        right_part["_merge_timestamp"] = pd.to_datetime(
            right_part["timestamp"], utc=True
        ).astype("datetime64[ns, UTC]")
        right_part = right_part.sort_values("_merge_timestamp")

        merged_part = pd.merge_asof(
            left_part,
            right_part[["_merge_timestamp", feature_name]],
            on="_merge_timestamp",
            direction="backward",
        )
        parts.append(merged_part)

    merged = pd.concat(parts, ignore_index=True)
    return (
        merged.sort_values("_row_id")
        .drop(columns=["_row_id", "_merge_timestamp"])
        .reset_index(drop=True)
    )


def run_feature_registry(
    base_frame: pd.DataFrame,
    timeframe_frames: dict[str, pd.DataFrame],
    feature_configs: list[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the per-symbol feature registry and return a manifest of outputs."""
    feature_frame = base_frame.copy()
    manifest_rows: list[dict[str, Any]] = []

    for feature_config in feature_configs:
        if not bool(feature_config.get("enabled", True)):
            continue

        feature_name = str(feature_config["name"])
        function_name = str(feature_config["fn"])
        timeframe = str(feature_config.get("timeframe", "base"))
        if function_name not in FEATURE_FUNCTIONS:
            raise ValueError(f"Unsupported feature function: {function_name}")

        feature_function = FEATURE_FUNCTIONS[function_name]
        if timeframe == "base":
            feature_frame[feature_name] = feature_function(
                feature_frame, feature_config
            )
        else:
            if timeframe not in timeframe_frames:
                raise KeyError(
                    f"Feature {feature_name!r} requested missing timeframe {timeframe!r}."
                )
            working_frame = timeframe_frames[timeframe].copy()
            working_frame[feature_name] = feature_function(
                working_frame, feature_config
            )
            feature_frame = _merge_timeframe_feature(
                feature_frame, working_frame, feature_name
            )

        manifest_rows.append(
            {
                "kind": "feature",
                "name": feature_name,
                "family": str(feature_config.get("family", "unspecified")),
                "fn": function_name,
                "timeframe": timeframe,
                "asof_rule": str(feature_config.get("asof", "current_bar")),
                "lag_rule": str(feature_config.get("lag", "0min")),
                "max_staleness_rule": str(feature_config.get("max_staleness", "0min")),
                "input_columns": ",".join(
                    str(value)
                    for key, value in feature_config.items()
                    if key.endswith("_col") or key == "input_col"
                ),
                "null_rate": float(feature_frame[feature_name].isna().mean()),
            }
        )

    return feature_frame, pd.DataFrame(manifest_rows)
