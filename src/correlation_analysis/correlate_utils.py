"""
correlate_utils.py
------------------
Shared utilities for all ETF correlation/selection scripts:
  correlate_greedy.py, correlate_maxdiv.py, correlate_kmedoids.py

This module handles:
  - Loading the candidate ETF universe from the volume screen CSV
  - Applying the full-history start-date screen inside the selection stage
  - Fetching daily closing prices from ClickHouse using argMax(close, ts)
  - Building a daily or weekly log-return matrix with a coverage filter
  - Computing the Spearman correlation matrix
  - Computing the signed distance matrix D = sqrt(0.5 * (1 - r))
  - Computing per-ETF performance statistics for the selected subset
  - Saving a correlation heatmap PNG
  - Saving a results CSV

Key design note -- signed vs absolute distance
----------------------------------------------
We use D = sqrt(0.5 * (1 - r)) instead of D = 1 - |r|.

With absolute distance, r = -0.8 (bonds vs equities) would give D = 0.2,
making them look "similar" -- which is the opposite of what we want for
diversification. With signed distance, r = -1 gives D = 1 (maximum distance),
so negatively correlated assets are correctly treated as ideal diversifiers.

This is the Euclidean distance between unit vectors in return space:
  ||a - b||^2 = 2(1 - r)  when a, b are unit vectors.
So D = sqrt(0.5 * (1 - r)) is geometrically exact.

Daily close convention
----------------------
The firstrate.etfs table contains minute-level OHLCV bars. There is no
guaranteed last-minute bar (no trade may occur in the final minute of the
session). We use:
    argMax(close, ts)   grouped by (symbol, toDate(ts))
This picks the close price of whichever bar has the latest timestamp on each
trading day -- i.e. the last actual traded price of the day, regardless of
what time it occurred. This is robust to days where the final minute has no
trade.
"""

from __future__ import annotations

from pathlib import Path

import clickhouse_connect
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from data_pipeline.clickhouse_client import build_client
from data_pipeline.paths import CORRELATION_OUTPUT_DIR, PRICE_PARQUET, SCREEN_CSV
from data_pipeline.sql_helpers import build_symbols_in_list, exclusive_end_date
from scipy.stats import spearmanr

# ---------------------------------------------------------------------------
# Constants -- shared across all correlation scripts
# ---------------------------------------------------------------------------
N_SELECT = 30  # number of ETFs to select
HISTORY_END = "2025-12-31"  # inclusive
HISTORY_YEARS = 8  # full-history requirement for the selection stage
HISTORY_START = (
    f"{pd.Timestamp(HISTORY_END).year - HISTORY_YEARS + 1}-01-01"  # "2018-01-01"
)
MIN_COVERAGE = 0.80  # drop symbols missing more than 20% of trading days
RISK_FREE = 0.05  # annualised risk-free rate for Sharpe computation
ANCHOR_TICKERS = ("VOO", "VEA")  # required core holdings in every basket
MIN_SELECTION_TOTAL_RETURN = 0.1823  # minimum cumulative log return; ln(1.20) ≈ 0.1823
MIN_ANN_VOL = 0.1  # minimum annualized volatility to remove cash/ultrashort ETFs
MAX_ANN_VOL = 0.60  # maximum annualized volatility to remove leveraged/inverse products
DEFAULT_RETURN_FREQUENCY = "daily"
WEEKLY_PRICE_RULE = "W-FRI"
RETURN_PERIODS_PER_YEAR = {
    "daily": 252,
    "weekly": 52,
}

# Selection artifacts live outside `src/` so notebooks and scripts share one folder.
OUTPUT_DIR = CORRELATION_OUTPUT_DIR
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Use non-interactive backend so matplotlib works without a display
matplotlib.use("Agg")


def normalize_return_frequency(return_frequency: str) -> str:
    """Validate and normalize the return-sampling frequency."""
    # Normalize once up front so every caller can accept mixed-case user input.
    normalized = return_frequency.strip().lower()
    if normalized not in RETURN_PERIODS_PER_YEAR:
        raise ValueError(
            "Unsupported return_frequency="
            f"{return_frequency!r}. Valid options: {sorted(RETURN_PERIODS_PER_YEAR)}"
        )
    return normalized


def get_periods_per_year(return_frequency: str) -> int:
    """Return the annualization factor for the requested return frequency."""
    normalized = normalize_return_frequency(return_frequency)
    return RETURN_PERIODS_PER_YEAR[normalized]


def normalize_analysis_date(date_value: str | pd.Timestamp) -> str:
    """Normalize analysis-window date input to ``YYYY-MM-DD``."""
    timestamp = pd.Timestamp(date_value)
    return timestamp.strftime("%Y-%m-%d")


def resolve_analysis_window(
    start_date: str | pd.Timestamp = HISTORY_START,
    end_date: str | pd.Timestamp = HISTORY_END,
) -> tuple[str, str]:
    """Validate and normalize an inclusive analysis window."""
    normalized_start = normalize_analysis_date(start_date)
    normalized_end = normalize_analysis_date(end_date)
    if pd.Timestamp(normalized_start) > pd.Timestamp(normalized_end):
        raise ValueError(
            f"Analysis window start_date={normalized_start} is after end_date={normalized_end}."
        )
    return normalized_start, normalized_end


# ---------------------------------------------------------------------------
# Anchor helpers
# ---------------------------------------------------------------------------


def get_anchor_tickers() -> list[str]:
    """Return the required ETF anchors in their fixed selection order."""
    return list(ANCHOR_TICKERS)


def ensure_anchor_tickers(
    available_tickers: list[str] | pd.Index,
    context: str,
    anchor_tickers: list[str] | None = None,
) -> list[str]:
    """
    Validate that every required anchor ticker is available in the current
    selection universe.

    Parameters
    ----------
    available_tickers : list-like of ticker strings
        The universe currently available to a method after all filters.
    context : str
        Human-readable label used in the error message.
    anchor_tickers : list[str] | None, default None
        Required anchor tickers. When None, falls back to the module-level
        constant ``ANCHOR_TICKERS`` via ``get_anchor_tickers()``.

    Returns
    -------
    list[str]
        The required anchor tickers in fixed order.
    """
    available = {str(ticker) for ticker in available_tickers}
    anchors = anchor_tickers if anchor_tickers is not None else get_anchor_tickers()
    missing = [ticker for ticker in anchors if ticker not in available]
    if missing:
        raise ValueError(
            f"Required anchor ticker(s) missing in {context}: {missing}. "
            "Check the start-date filter, coverage filter, and source data."
        )
    return anchors


def resolve_anchor_tickers(
    anchor_tickers: list[str] | None,
    available_tickers: list[str] | pd.Index,
    context: str,
) -> list[str]:
    """
    Resolve caller-provided anchors and validate they exist in the current universe.

    Returns the anchor list in fixed order after ``ensure_anchor_tickers`` succeeds.
    """
    anchors = anchor_tickers if anchor_tickers is not None else get_anchor_tickers()
    return ensure_anchor_tickers(available_tickers, context, anchors)


def furthest_first_indices(
    distance_values: np.ndarray,
    seed_indices: list[int],
    n_select: int,
) -> list[int]:
    """
    Greedily add row indices that maximize minimum distance to the current set.

    Each new index is the furthest point from the existing medoid/seed set. This
    initializer is shared by k-medoids and mirrors the non-anchor expansion in
    greedy maximin selection.
    """
    selected_indices = list(seed_indices[:n_select])
    if len(selected_indices) >= n_select:
        return selected_indices

    # Track, for every symbol row, the closest distance to any already-selected index.
    min_distance = np.min(
        np.column_stack([distance_values[:, idx] for idx in selected_indices]),
        axis=1,
    )
    while len(selected_indices) < n_select:
        masked = min_distance.copy()
        masked[selected_indices] = -np.inf
        next_idx = int(np.argmax(masked))
        selected_indices.append(next_idx)
        min_distance = np.minimum(min_distance, distance_values[:, next_idx])
    return selected_indices


def build_anchor_first_selection(
    ranked_tickers: list[str],
    available_tickers: list[str] | pd.Index,
    n_select: int,
    anchor_tickers: list[str] | None = None,
) -> list[str]:
    """
    Build a unique selection list with the required anchors forced to the front.

    Parameters
    ----------
    ranked_tickers : list[str]
        Tickers in the method's preferred ranking order.
    available_tickers : list-like of ticker strings
        The universe from which selections may be drawn.
    n_select : int
        Target selection count.
    anchor_tickers : list[str] | None, default None
        Required anchor tickers forced to the front. When None, falls back to
        the module-level constant ``ANCHOR_TICKERS``.

    Returns
    -------
    list[str]
        Unique tickers of length ``min(n_select, len(available_tickers))`` with
        the anchor tickers always included first.
    """
    available = [str(ticker) for ticker in available_tickers]
    available_set = set(available)
    anchors = ensure_anchor_tickers(available, "selection universe", anchor_tickers)

    ordered: list[str] = []
    seen: set[str] = set()
    # Never request more names than actually exist in the current universe.
    target_count = min(n_select, len(available))

    for ticker in anchors + ranked_tickers:
        if ticker not in available_set or ticker in seen:
            continue
        ordered.append(ticker)
        seen.add(ticker)
        if len(ordered) == target_count:
            return ordered

    # If ranked_tickers plus anchors still fall short, fill from the remaining
    # universe in file order so callers always receive a full basket when possible.
    for ticker in available:
        if ticker in seen:
            continue
        ordered.append(ticker)
        if len(ordered) == target_count:
            break

    return ordered


def _subset_selection_universe(
    log_ret: pd.DataFrame,
    candidates: pd.DataFrame,
    passing_tickers: list[str] | pd.Index,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the return matrix and candidate table restricted to one ticker set."""
    passing_list = [str(ticker) for ticker in passing_tickers]
    filtered_log_ret = log_ret.loc[:, passing_list].copy()
    filtered_candidates = candidates[candidates["ticker"].isin(passing_list)].copy()
    filtered_candidates = filtered_candidates.sort_values(
        "vol_combined",
        ascending=False,
    ).reset_index(drop=True)
    return filtered_log_ret, filtered_candidates


def _filter_by_metric_hurdle(
    log_ret: pd.DataFrame,
    candidates: pd.DataFrame,
    metric: pd.Series,
    min_allowed: float,
    *,
    dropped_message: str,
    validation_context: str,
    anchor_tickers: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Keep tickers whose ``metric`` value is at least ``min_allowed``.

    The helper prints a short preview of the worst failures, subsets the
    universe, and re-validates that required anchors survived the cut.
    """
    passing = metric[metric >= min_allowed].index.tolist()
    dropped = metric[metric < min_allowed].sort_values()

    if not dropped.empty:
        print(dropped_message.format(count=len(dropped)))
        preview = dropped.head(15).index.tolist()
        print(f"Top 15 dropped: {preview}")

    filtered_log_ret, filtered_candidates = _subset_selection_universe(
        log_ret,
        candidates,
        passing,
    )
    ensure_anchor_tickers(
        filtered_log_ret.columns.tolist(),
        validation_context,
        anchor_tickers,
    )
    return filtered_log_ret, filtered_candidates


def compute_total_log_returns(log_ret: pd.DataFrame) -> pd.Series:
    """Sum log returns over the full window to get cumulative log return per ticker."""
    return log_ret.sum(axis=0, skipna=True)


def compute_average_yearly_returns(log_ret: pd.DataFrame) -> pd.Series:
    """
    Compute each ticker's mean calendar-year log return over the sample.

    For each calendar year ``y`` we sum the daily log returns within that year
    to get the annual log return, then average those annual log returns across
    all observed years. All values are in log-return space (continuous compounding).
    """
    if not isinstance(log_ret.index, pd.DatetimeIndex):
        raise TypeError("log_ret index must be a DatetimeIndex for yearly aggregation")

    yearly_log_returns = log_ret.groupby(log_ret.index.year).sum()
    return yearly_log_returns.mean(axis=0, skipna=True)


def compute_annualized_volatility(
    log_ret: pd.DataFrame,
    return_frequency: str = DEFAULT_RETURN_FREQUENCY,
) -> pd.Series:
    """Compute annualised volatility from the sampled-period log-return panel."""
    annualization_periods = get_periods_per_year(return_frequency)
    return log_ret.std(axis=0) * np.sqrt(annualization_periods)


def filter_blacklisted_tickers(
    log_ret: pd.DataFrame,
    candidates: pd.DataFrame,
    blacklist_tickers: list[str] | tuple[str, ...] | None = None,
    anchor_tickers: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Drop manually blacklisted symbols before the statistical hurdles are applied.

    Parameters
    ----------
    log_ret : pd.DataFrame
        Wide log-return matrix after the coverage filter.
    candidates : pd.DataFrame
        Candidate metadata containing at least `ticker` and `vol_combined`.
    blacklist_tickers : list[str] | tuple[str, ...] | None, default None
        Symbols to exclude manually before any return or volatility filtering.
    anchor_tickers : list[str] | None, default None
        Required anchor tickers validated after filtering. When None, falls back
        to the module-level constant ``ANCHOR_TICKERS``.
    """
    anchors = anchor_tickers if anchor_tickers is not None else get_anchor_tickers()
    blacklist = [str(ticker) for ticker in (blacklist_tickers or [])]
    blacklist_set = set(blacklist)
    conflicting_anchors = sorted(set(anchors) & blacklist_set)
    if conflicting_anchors:
        raise ValueError(
            "Blacklist conflicts with required anchors: "
            f"{conflicting_anchors}. Remove them from blacklist_tickers."
        )

    if not blacklist_set:
        return _subset_selection_universe(log_ret, candidates, log_ret.columns.tolist())

    dropped = [ticker for ticker in log_ret.columns if ticker in blacklist_set]
    if dropped:
        print(
            "Manual blacklist dropped "
            f"{len(dropped)} symbols before the statistical filters: {dropped}"
        )

    passing = [ticker for ticker in log_ret.columns if ticker not in blacklist_set]
    filtered_log_ret, filtered_candidates = _subset_selection_universe(
        log_ret,
        candidates,
        passing,
    )
    ensure_anchor_tickers(
        filtered_log_ret.columns.tolist(),
        "blacklist-filtered survivor universe",
        anchors,
    )
    return filtered_log_ret, filtered_candidates


def filter_min_total_return(
    log_ret: pd.DataFrame,
    candidates: pd.DataFrame,
    min_total_return: float = MIN_SELECTION_TOTAL_RETURN,
    start_date: str | pd.Timestamp = HISTORY_START,
    end_date: str | pd.Timestamp = HISTORY_END,
    anchor_tickers: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Drop symbols whose total price return over the analysis window is below a
    minimum hurdle.

    The filter uses the cumulative log return over the full analysis sample
    from ``HISTORY_START`` to ``HISTORY_END``. A symbol passes only if:

        sum_t r_t >= min_total_return   (log return threshold)

    Parameters
    ----------
    log_ret : pd.DataFrame
        Wide log-return matrix after the coverage filter.
    candidates : pd.DataFrame
        Candidate metadata containing at least `ticker` and `vol_combined`.
    min_total_return : float, default MIN_SELECTION_TOTAL_RETURN
        Minimum cumulative log return required over the full sample window.
    start_date : str | pd.Timestamp, default HISTORY_START
        Inclusive analysis-window start date used in status messages.
    end_date : str | pd.Timestamp, default HISTORY_END
        Inclusive analysis-window end date used in status messages.
    anchor_tickers : list[str] | None, default None
        Required anchor tickers validated after filtering. When None, falls back
        to the module-level constant ``ANCHOR_TICKERS``.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        Filtered log-return matrix and matching candidate metadata.
    """
    window_start, window_end = resolve_analysis_window(start_date, end_date)
    # Cumulative log return is the sum of daily log returns over the full window.
    total_log_return = compute_total_log_returns(log_ret)
    return _filter_by_metric_hurdle(
        log_ret,
        candidates,
        total_log_return,
        min_total_return,
        dropped_message=(
            "Total-return hurdle dropped {count} symbols below "
            f"{min_total_return:.4f} log total return "
            f"({window_start} to {window_end})."
        ),
        validation_context="minimum-total-return-filtered survivor universe",
        anchor_tickers=anchor_tickers,
    )


def filter_min_average_yearly_return(
    log_ret: pd.DataFrame,
    candidates: pd.DataFrame,
    min_average_yearly_return: float,
    anchor_tickers: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Drop symbols whose mean calendar-year log return is below a hurdle.

    For ticker ``i`` and calendar year ``y``, the notebook computes
    ``R_log[i, y] = sum_t r[i, t]`` over that year, then keeps ticker ``i``
    only if ``mean_y R_log[i, y] >= min_average_yearly_return``.
    """
    average_yearly_return = compute_average_yearly_returns(log_ret)
    return _filter_by_metric_hurdle(
        log_ret,
        candidates,
        average_yearly_return,
        min_average_yearly_return,
        dropped_message=(
            "Average calendar-year log-return hurdle dropped {count} symbols below "
            f"{min_average_yearly_return:.4f}."
        ),
        validation_context="minimum-average-yearly-return-filtered survivor universe",
        anchor_tickers=anchor_tickers,
    )


def apply_shared_selection_filters(
    log_ret: pd.DataFrame,
    candidates: pd.DataFrame,
    min_ann_vol: float = MIN_ANN_VOL,
    max_ann_vol: float = MAX_ANN_VOL,
    min_total_return: float = MIN_SELECTION_TOTAL_RETURN,
    min_average_yearly_return: float | None = None,
    return_frequency: str = DEFAULT_RETURN_FREQUENCY,
    start_date: str | pd.Timestamp = HISTORY_START,
    end_date: str | pd.Timestamp = HISTORY_END,
    blacklist_tickers: list[str] | tuple[str, ...] | None = None,
    anchor_tickers: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Apply the shared selection-universe filters used across the method scripts.

    The current workflow uses one common survivor universe for cross-method
    comparison: the coverage-filtered panel, further restricted to ETFs whose
    total full-window cumulative log return is at least ``min_total_return``, whose
    mean calendar-year log return is at least
    ``min_average_yearly_return`` when provided, and whose annualized
    volatility falls within [min_ann_vol, max_ann_vol].

    Parameters
    ----------
    log_ret : pd.DataFrame
        Wide log-return matrix after the coverage filter.
    candidates : pd.DataFrame
        Candidate metadata with at least `ticker` and `vol_combined`.
    min_ann_vol : float, default MIN_ANN_VOL
        Minimum annualised volatility; removes cash/ultrashort ETFs.
    max_ann_vol : float, default MAX_ANN_VOL
        Maximum annualised volatility; removes leveraged/inverse products.
    min_total_return : float, default MIN_SELECTION_TOTAL_RETURN
        Minimum cumulative log return over the study window.
    min_average_yearly_return : float | None, default None
        Optional minimum arithmetic mean of calendar-year log returns.
    return_frequency : {"daily", "weekly"}, default DEFAULT_RETURN_FREQUENCY
        Sampling frequency used to build ``log_ret``. This controls the
        annualization factor used by the volatility filters.
    start_date : str | pd.Timestamp, default HISTORY_START
        Inclusive analysis-window start date used in status messages.
    end_date : str | pd.Timestamp, default HISTORY_END
        Inclusive analysis-window end date used in status messages.
    blacklist_tickers : list[str] | tuple[str, ...] | None, default None
        Optional manual blacklist applied before the statistical filters.
    anchor_tickers : list[str] | None, default None
        Required anchor tickers that are always kept regardless of the vol
        filters and validated at the end. When None, falls back to the
        module-level constant ``ANCHOR_TICKERS``.
    """
    # Resolve anchors once so the same list is used for both the vol-bypass
    # guard and the final validation check.
    anchors = anchor_tickers if anchor_tickers is not None else get_anchor_tickers()

    filtered_log_ret, filtered_candidates = filter_blacklisted_tickers(
        log_ret,
        candidates,
        blacklist_tickers=blacklist_tickers,
        anchor_tickers=anchors,
    )

    filtered_log_ret, filtered_candidates = filter_min_total_return(
        filtered_log_ret,
        filtered_candidates,
        min_total_return=min_total_return,
        start_date=start_date,
        end_date=end_date,
        anchor_tickers=anchors,
    )

    if min_average_yearly_return is not None:
        filtered_log_ret, filtered_candidates = filter_min_average_yearly_return(
            filtered_log_ret,
            filtered_candidates,
            min_average_yearly_return=min_average_yearly_return,
            anchor_tickers=anchors,
        )

    ann_vols = compute_annualized_volatility(
        filtered_log_ret,
        return_frequency=return_frequency,
    )

    # One mask keeps symbols inside the annualized-vol band; anchors bypass the cut.
    vol_mask = (ann_vols >= min_ann_vol) & (ann_vols <= max_ann_vol)
    dropped_low_vol = ann_vols[~vol_mask & (ann_vols < min_ann_vol)]
    if not dropped_low_vol.empty:
        print(
            f"Minimum volatility hurdle (<{min_ann_vol:.1%}) dropped "
            f"{len(dropped_low_vol)} symbols."
        )
        preview = dropped_low_vol.sort_values().head(15).index.tolist()
        print(f"Top 15 lowest vol dropped: {preview}")

    dropped_high_vol = ann_vols[~vol_mask & (ann_vols > max_ann_vol)].index.tolist()
    if dropped_high_vol:
        print(
            f"Maximum volatility hurdle (>{max_ann_vol:.0%}) dropped "
            f"{len(dropped_high_vol)} symbols: {dropped_high_vol}"
        )

    passing_vol = vol_mask[vol_mask].index.tolist()
    for anchor in anchors:
        if anchor in filtered_log_ret.columns and anchor not in passing_vol:
            passing_vol.append(anchor)

    filtered_log_ret, filtered_candidates = _subset_selection_universe(
        filtered_log_ret,
        filtered_candidates,
        passing_vol,
    )

    ensure_anchor_tickers(
        filtered_log_ret.columns.tolist(),
        "final shared selection universe",
        anchors,
    )

    return filtered_log_ret, filtered_candidates


# ---------------------------------------------------------------------------
# Candidate universe
# ---------------------------------------------------------------------------


def load_screened_universe() -> pd.DataFrame:
    """
    Load the full liquidity-screened ETF universe from the shared screen CSV.

    Returns
    -------
    pd.DataFrame
        Columns include ticker (str), one `vol_<year>` column for each screen
        year from 2020 through 2025, vol_combined (float), and start_date
        (str "YYYY-MM-DD").
        Sorted descending by vol_combined as written by the screen stage.
    """
    df = pd.read_csv(SCREEN_CSV)
    df["start_date"] = pd.to_datetime(df["start_date"]).dt.strftime("%Y-%m-%d")
    return df.reset_index(drop=True)


def apply_start_date_filter(
    candidates: pd.DataFrame,
    start_date: str | pd.Timestamp = HISTORY_START,
) -> pd.DataFrame:
    """
    Keep only ETFs whose first available date is on or before ``start_date``.

    We require ETF start_date <= analysis start_date so that every surviving ETF has a
    full history covering the entire analysis window. ETFs that started later
    (e.g. TSLL from 2022, IBIT from 2024) are dropped inside the correlation
    stage before return analysis begins.

    Returns
    -------
    pd.DataFrame
        Columns include ticker (str), one `vol_<year>` column for each screen
        year from 2020 through 2025, vol_combined (float), and start_date
        (str "YYYY-MM-DD").
        Sorted descending by vol_combined.
        Only tickers with start_date <= ``start_date`` are included.
    """
    df = candidates.copy()
    normalized_start = normalize_analysis_date(start_date)

    # Convert start_date strings to date objects for comparison
    df["start_date"] = pd.to_datetime(df["start_date"]).dt.date

    # Hard drop: any ticker that started after the analysis start has incomplete
    # history and cannot be used in the full-window analysis
    cutoff = pd.to_datetime(normalized_start).date()
    before = len(df)
    df = df[df["start_date"] <= cutoff].copy()
    after = len(df)

    print(
        f"Candidates after start_date filter (<= {normalized_start}): "
        f"{after} / {before} (dropped {before - after})"
    )

    # Convert start_date back to string for clean display
    df["start_date"] = df["start_date"].astype(str)

    return df.reset_index(drop=True)


def load_candidates(
    start_date: str | pd.Timestamp = HISTORY_START,
) -> pd.DataFrame:
    """
    Load the screened ETF universe and apply the selection-stage start-date filter.

    This wrapper preserves the historical API used by the method scripts and
    notebooks while making the stage boundary explicit: the data pipeline
    produces the full top-500 parquet, and correlation analysis decides which
    ETFs are old enough for the full study window.
    """
    return apply_start_date_filter(load_screened_universe(), start_date=start_date)


# ---------------------------------------------------------------------------
# ClickHouse data fetch
# ---------------------------------------------------------------------------


def fetch_daily_closes(
    client: clickhouse_connect.driver.Client,
    symbols: list[str],
    start_date: str | pd.Timestamp = HISTORY_START,
    end_date: str | pd.Timestamp = HISTORY_END,
) -> pd.DataFrame:
    """
    Fetch daily closing prices for the given symbols from ClickHouse.

    Uses argMax(close, ts) grouped by (symbol, date) to get the last traded
    price of each day. This is robust to the case where no trade occurs in
    the final minute of the session -- we simply take whatever the last bar
    was, regardless of time.

    The query covers ``start_date`` to ``end_date`` (inclusive on both ends).
    We use ``end_date + 1 day`` as the exclusive upper bound because ts is a DateTime64 and a date
    comparison like ts <= '2025-12-31' would miss bars after midnight.

    Parameters
    ----------
    client  : connected ClickHouse client
    symbols : list of ticker strings to fetch

    Returns
    -------
    pd.DataFrame
        Long-format: columns = [symbol (str), date (date), close_price (float)].
        Sorted by (symbol, date).
    """
    window_start, window_end = resolve_analysis_window(start_date, end_date)

    symbols_sql = build_symbols_in_list(symbols)
    history_end_exclusive = exclusive_end_date(window_end)

    query = f"""
        SELECT
            symbol,
            toDate(ts)          AS date,
            argMax(close, ts)   AS close_price
        FROM firstrate.etfs
        WHERE symbol IN ({symbols_sql})
          AND ts >= '{window_start}'
          AND ts <  '{history_end_exclusive}'
        GROUP BY symbol, date
        ORDER BY symbol, date
    """

    print(
        f"Fetching daily closes for {len(symbols)} symbols "
        f"({window_start} to {window_end}) ..."
    )
    result = client.query(query)

    df = pd.DataFrame(result.result_rows, columns=result.column_names)

    # Ensure correct dtypes -- ClickHouse may return date as a Python date
    # object or as a string depending on driver version
    df["date"] = pd.to_datetime(df["date"])
    df["close_price"] = df["close_price"].astype(float)

    print(
        f"Fetched {len(df):,} rows "
        f"({df['symbol'].nunique()} symbols, "
        f"{df['date'].nunique()} unique dates)"
    )

    return df


def load_daily_closes_from_parquet(
    symbols: list[str],
    start_date: str | pd.Timestamp = HISTORY_START,
    end_date: str | pd.Timestamp = HISTORY_END,
) -> pd.DataFrame:
    """Load daily close history for the given symbols from the shared parquet."""
    if not PRICE_PARQUET.exists():
        raise FileNotFoundError(
            "ClickHouse credentials are unavailable and the shared parquet "
            f"fallback does not exist: {PRICE_PARQUET}"
        )

    # The parquet fallback keeps notebook and validation workflows independent
    # of database access, but it still enforces the same date window.
    print(
        "ClickHouse credentials unavailable. "
        f"Falling back to local parquet -> {PRICE_PARQUET}"
    )
    parquet_df = pd.read_parquet(
        PRICE_PARQUET,
        columns=["ticker", "date", "close_price"],
    )
    parquet_df["ticker"] = parquet_df["ticker"].astype(str)
    parquet_df["date"] = pd.to_datetime(parquet_df["date"])

    window_start, window_end = resolve_analysis_window(start_date, end_date)
    history_start = pd.Timestamp(window_start)
    history_end = pd.Timestamp(window_end)
    filtered = parquet_df[
        parquet_df["ticker"].isin(symbols)
        & (parquet_df["date"] >= history_start)
        & (parquet_df["date"] <= history_end)
    ].copy()

    if filtered.empty:
        raise ValueError(
            "The shared parquet did not contain any requested symbol history "
            f"for {len(symbols)} symbols."
        )

    filtered = filtered.rename(columns={"ticker": "symbol"})
    filtered = filtered.sort_values(["symbol", "date"]).reset_index(drop=True)

    print(
        f"Loaded {len(filtered):,} rows from local parquet "
        f"({filtered['symbol'].nunique()} symbols, "
        f"{filtered['date'].nunique()} unique dates)"
    )
    return filtered


def load_daily_closes(
    symbols: list[str],
    start_date: str | pd.Timestamp = HISTORY_START,
    end_date: str | pd.Timestamp = HISTORY_END,
) -> pd.DataFrame:
    """Load daily closes from ClickHouse when possible, else from local parquet."""
    try:
        client = build_client()
    except KeyError, FileNotFoundError:
        # Missing env vars are expected in offline mode, so fall back cleanly
        # instead of treating that as a hard failure.
        return load_daily_closes_from_parquet(
            symbols,
            start_date=start_date,
            end_date=end_date,
        )
    return fetch_daily_closes(
        client,
        symbols,
        start_date=start_date,
        end_date=end_date,
    )


# ---------------------------------------------------------------------------
# Return matrix construction
# ---------------------------------------------------------------------------


def build_return_matrix(
    prices_long: pd.DataFrame,
    candidates: pd.DataFrame,
    return_frequency: str = DEFAULT_RETURN_FREQUENCY,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Pivot close prices to a wide matrix, optionally resample to weekly closes,
    apply a coverage filter, and compute log returns.

    Steps
    -----
    1. Pivot: rows = dates, columns = symbols, values = close_price.
    2. Optionally resample to weekly closes using the last observed price in
       each Friday-ending week.
    3. Coverage filter: drop symbols where non-NaN periods / total periods
       < MIN_COVERAGE. This is a secondary guard -- most symbols should pass
       because we pre-filtered by start_date.
    4. Log returns: ln(P_t / P_{t-1}). The first row becomes NaN and is dropped.
    5. Drop any remaining all-NaN columns (shouldn't happen after step 3 but
       defensive).

    Parameters
    ----------
    prices_long : long-format DataFrame with columns [symbol, date, close_price]
    candidates  : DataFrame with columns [ticker, vol_combined, ...] used to
                  look up liquidity rank after filtering
    return_frequency : {"daily", "weekly"}, default DEFAULT_RETURN_FREQUENCY
        Sampling frequency for the return matrix.

    Returns
    -------
    log_ret : pd.DataFrame
        Wide log-return matrix. rows = dates (DatetimeIndex),
        cols = surviving symbol strings.
        Shape approximately (2500, 200+).
    survivors : pd.DataFrame
        Subset of candidates DataFrame containing only the symbols that
        survived the coverage filter. Sorted descending by vol_combined.
    """
    # --- Step 1: pivot to wide price matrix ---
    # rows = dates, cols = symbols, values = close_price
    # Dates with no data for a symbol become NaN (forward fill is NOT applied
    # here -- gaps remain as NaN so the coverage filter can detect them)
    price_wide = prices_long.pivot(index="date", columns="symbol", values="close_price")
    price_wide.index = pd.to_datetime(price_wide.index)
    price_wide = price_wide.sort_index()
    # Normalize the frequency label once so the same value drives both
    # resampling logic and user-facing log messages.
    normalized_frequency = normalize_return_frequency(return_frequency)

    if normalized_frequency == "weekly":
        price_wide = price_wide.resample(WEEKLY_PRICE_RULE).last().dropna(how="all")
        print(f"Resampled daily closes to weekly closes using {WEEKLY_PRICE_RULE}.")

    total_periods = len(price_wide)
    print(
        f"Price matrix shape before coverage filter: {price_wide.shape} "
        f"({total_periods} {normalized_frequency} periods)"
    )

    # --- Step 2: coverage filter ---
    # Count non-NaN observations per symbol; divide by total sampled periods
    coverage = price_wide.notna().sum() / total_periods

    # Keep only symbols meeting the minimum coverage threshold
    passing = coverage[coverage >= MIN_COVERAGE].index.tolist()
    dropped = [s for s in price_wide.columns if s not in passing]
    if dropped:
        print(
            f"Coverage filter dropped {len(dropped)} symbols "
            f"(< {MIN_COVERAGE:.0%} of trading days): {dropped}"
        )
    price_wide = price_wide[passing]

    # Warn if fewer than N_SELECT symbols survived
    if len(passing) < N_SELECT:
        print(
            f"WARNING: only {len(passing)} symbols passed coverage filter "
            f"(need {N_SELECT}). Proceeding with all {len(passing)}."
        )

    # --- Step 3: log returns ---
    # ln(P_t / P_{t-1}) = log(P_t) - log(P_{t-1})
    # This is the continuously compounded sampled-period return.
    # NaN gaps in the price series propagate to NaN returns -- that is correct
    # behaviour; we do not forward-fill prices.
    log_ret = np.log(price_wide / price_wide.shift(1))

    # Drop the first row (all NaN because there is no P_{t-1})
    log_ret = log_ret.iloc[1:]

    # Drop any column that is entirely NaN (defensive)
    log_ret = log_ret.dropna(axis=1, how="all")

    print(f"{normalized_frequency.title()} log-return matrix shape: {log_ret.shape}")

    # --- Step 4: build survivors DataFrame ---
    # Keep only the candidates that are in the surviving column set
    survivors = candidates[candidates["ticker"].isin(log_ret.columns)].copy()
    survivors = survivors.sort_values("vol_combined", ascending=False).reset_index(
        drop=True
    )

    return log_ret, survivors


# ---------------------------------------------------------------------------
# Correlation and distance matrices
# ---------------------------------------------------------------------------


def spearman_corr_numpy(log_ret_values: np.ndarray) -> np.ndarray:
    """
    Compute a Spearman correlation matrix from a 2-D observation array.

    Parameters
    ----------
    log_ret_values : np.ndarray
        Shape ``(n_observations, n_variables)`` with NaNs already handled by caller.

    Returns
    -------
    np.ndarray
        Symmetric correlation matrix of shape ``(n_variables, n_variables)``.
    """
    result = spearmanr(log_ret_values)
    corr = np.array(result.statistic)
    if corr.ndim == 0:
        # Spearman on a single asset returns a scalar statistic, not a matrix.
        corr = np.array([[1.0, float(corr)], [float(corr), 1.0]])
    return corr


def correlation_distance_numpy(corr: np.ndarray) -> np.ndarray:
    """
    Convert a correlation matrix to signed distance ``D = sqrt(0.5 * (1 - r))``.

    Values are clipped to ``[0, 1]`` and the diagonal is set to zero exactly.
    """
    dist = np.sqrt(0.5 * (1.0 - corr))
    np.clip(dist, 0.0, 1.0, out=dist)
    np.fill_diagonal(dist, 0.0)
    return dist


def compute_spearman_corr(log_ret: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the pairwise Spearman rank correlation matrix for all columns
    (symbols) in the log-return matrix.

    Spearman rank correlation is used instead of Pearson because:
    - ETF daily returns exhibit fat tails (leptokurtosis) and occasional
      extreme outliers (circuit breakers, flash crashes, ETF mispricings).
    - Spearman is robust to outliers; it correlates the *ranks* of returns
      rather than the raw values, so no single extreme day dominates.
    - It captures monotonic (not just linear) relationships.

    NaN values in log_ret are handled by filling each column with its median
    before ranking and correlation.

    Parameters
    ----------
    log_ret : pd.DataFrame
        Wide log-return matrix. rows = dates, cols = symbols.

    Returns
    -------
    pd.DataFrame
        Symmetric (n_symbols x n_symbols) Spearman correlation matrix.
        Diagonal = 1.0. Index and columns = symbol strings.
    """
    print("Computing Spearman correlation matrix ...")

    # scipy.stats.spearmanr returns a SpearmanrResult with .statistic attribute
    # that is the full correlation matrix when given a 2-D array.
    # We drop NaNs pairwise by filling with the column median before ranking --
    # this is a pragmatic choice: gaps are rare (coverage >= 0.80) so filling
    # with median preserves the rank structure without distorting it.
    filled = log_ret.fillna(log_ret.median())
    corr_array = spearman_corr_numpy(filled.values)

    corr_df = pd.DataFrame(
        corr_array,
        index=log_ret.columns,
        columns=log_ret.columns,
    )

    print(f"Correlation matrix shape: {corr_df.shape}")
    return corr_df


def compute_distance_matrix(corr: pd.DataFrame) -> pd.DataFrame:
    """
    Convert a Spearman correlation matrix to a signed distance matrix using:

        D(i, j) = sqrt(0.5 * (1 - r(i, j)))

    Properties:
    - r = +1  ->  D = 0    (identical time series, zero distance)
    - r =  0  ->  D = 0.707 (uncorrelated)
    - r = -1  ->  D = 1    (perfectly anticorrelated, maximum distance)

    This is geometrically exact: it equals the Euclidean distance between
    unit vectors whose dot product is r. Negatively correlated assets are
    treated as FAR apart, which is correct for diversification -- a bond ETF
    negatively correlated with equities is an ideal diversifier, not a
    "similar" asset.

    Parameters
    ----------
    corr : pd.DataFrame
        Symmetric Spearman correlation matrix. Index and columns = symbols.

    Returns
    -------
    pd.DataFrame
        Symmetric distance matrix. Same index/columns as corr.
        Values in [0, 1].
    """
    dist = correlation_distance_numpy(corr.values)
    return pd.DataFrame(dist, index=corr.index, columns=corr.columns)


# ---------------------------------------------------------------------------
# Per-ETF performance statistics
# ---------------------------------------------------------------------------


def compute_stats(
    selected: list[str],
    log_ret: pd.DataFrame,
    candidates: pd.DataFrame,
    return_frequency: str = DEFAULT_RETURN_FREQUENCY,
    anchor_tickers: list[str] | None = None,
) -> pd.DataFrame:
    """
    Compute per-ETF performance statistics for the selected ticker list.

    Statistics computed over the full HISTORY_START to HISTORY_END window:

    - ann_return   : annualised log return = mean(period log ret) * periods_per_year
    - ann_vol      : annualised volatility = std(period log ret) * sqrt(periods_per_year)
    - sharpe       : (ann_return - RISK_FREE) / ann_vol
    - max_drawdown : maximum peak-to-trough drawdown on cumulative wealth
                     series `W_t = exp(cumulative_log_return_t)` (expressed as
                     a positive fraction, e.g. 0.35 = 35%)
    - avg_abs_corr : average absolute Spearman correlation of this ETF with
                     the other selected ETFs. Lower = better diversifier.
    - vol_combined : from the candidates CSV (liquidity proxy)
    - start_date   : from the candidates CSV
    - is_anchor    : 1 if ticker is one of the mandatory core holdings

    Parameters
    ----------
    selected   : list of ticker strings
    log_ret    : wide log-return matrix (all surviving symbols, not just selected)
    candidates : full candidates DataFrame with vol_combined and start_date
    return_frequency : {"daily", "weekly"}, default DEFAULT_RETURN_FREQUENCY
        Sampling frequency used to build ``log_ret``.
    anchor_tickers : list[str] | None, default None
        Tickers marked as anchors in the ``is_anchor`` column. When None,
        falls back to the module-level constant ``ANCHOR_TICKERS``.

    Returns
    -------
    pd.DataFrame
        One row per selected ticker. Sorted descending by sharpe.
        Columns: ticker, ann_return, ann_vol, sharpe, max_drawdown,
                 avg_abs_corr, vol_combined, start_date.
    """
    # Resolve the anchor set used for the is_anchor flag
    anchor_set = (
        set(anchor_tickers) if anchor_tickers is not None else set(ANCHOR_TICKERS)
    )
    annualization_periods = get_periods_per_year(return_frequency)

    # Subset log returns to only the selected tickers
    # `ret_sel` is the exact return panel used for every per-ETF metric below.
    ret_sel = log_ret[selected]

    # Spearman correlation among the selected ETFs only
    # Use the same median-fill approach as in compute_spearman_corr
    filled_sel = ret_sel.fillna(ret_sel.median())
    corr_sel_result = spearmanr(filled_sel.values)
    corr_sel = np.array(corr_sel_result.statistic)
    # corr_sel is (N_SELECT x N_SELECT); diagonal = 1.0

    rows = []
    for i, ticker in enumerate(selected):
        r = ret_sel[ticker].dropna()

        # Annualised return: scale mean sampled-period log return to annual
        ann_ret = r.mean() * annualization_periods

        # Annualised volatility: scale sampled-period std to annual
        ann_vol = r.std() * np.sqrt(annualization_periods)

        # Sharpe ratio: excess return over risk-free divided by volatility
        sharpe = (ann_ret - RISK_FREE) / ann_vol if ann_vol > 0 else np.nan

        # Maximum drawdown from cumulative wealth series.
        # Cumulative log return at time t: sum of daily log returns up to t.
        cum = r.cumsum()
        wealth = np.exp(cum)
        running_max = wealth.cummax()
        drawdown = 1.0 - (wealth / running_max)
        max_dd = drawdown.max()  # maximum drawdown in [0, 1]

        # Average absolute Spearman correlation with the other selected ETFs
        # corr_sel[i, :] is the i-th row; exclude the diagonal (self)
        abs_corrs = np.abs(corr_sel[i, :])
        # Zero out self-correlation on diagonal before averaging
        abs_corrs[i] = 0.0
        avg_abs_corr = abs_corrs.sum() / (len(selected) - 1)

        rows.append(
            {
                "ticker": ticker,
                "ann_return": round(ann_ret, 4),
                "ann_vol": round(ann_vol, 4),
                "sharpe": round(sharpe, 4),
                "max_drawdown": round(max_dd, 4),
                "avg_abs_corr": round(avg_abs_corr, 4),
                "is_anchor": int(ticker in anchor_set),
            }
        )

    stats_df = pd.DataFrame(rows)

    # Merge in vol_combined and start_date from candidates
    meta = candidates[["ticker", "vol_combined", "start_date"]].copy()
    # Merge liquidity and start-date metadata late so the numerical metrics stay
    # computed only from the cleaned return panel.
    stats_df = stats_df.merge(meta, on="ticker", how="left")

    # Sort by Sharpe descending -- best risk-adjusted performers first
    stats_df = stats_df.sort_values("sharpe", ascending=False).reset_index(drop=True)

    return stats_df


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def save_heatmap(
    corr: pd.DataFrame,
    selected: list[str],
    output_path: Path,
    title: str = "Spearman Correlation -- Selected ETFs",
) -> None:
    """
    Save a correlation heatmap for the selected ETFs as a PNG file.

    The heatmap shows the Spearman correlation matrix of the N_SELECT selected
    ETFs only (not the full 200+ symbol matrix). Colour scale: -1 (blue) to
    +1 (red). White = uncorrelated.

    Parameters
    ----------
    corr        : full correlation matrix (all surviving symbols)
    selected    : list of selected ticker strings (subset of corr's index)
    output_path : Path where the PNG will be saved
    title       : chart title string
    """
    # Subset correlation matrix to selected tickers only
    corr_sel = corr.loc[selected, selected]

    n = len(selected)
    # Scale the canvas with basket size because the selected count can vary
    # across methods and filters.
    # Scale figure size with number of tickers so labels stay readable
    fig_size = max(14, n * 0.55)
    fig, ax = plt.subplots(figsize=(fig_size, fig_size * 0.85))

    # Draw the heatmap using imshow
    im = ax.imshow(corr_sel.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Spearman r", fontsize=11)

    # Tick labels -- use ticker names on both axes
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(corr_sel.columns, rotation=90, fontsize=8)
    ax.set_yticklabels(corr_sel.index, fontsize=8)

    # Annotate each cell with the correlation value
    for i in range(n):
        for j in range(n):
            val = corr_sel.values[i, j]
            # Use white text on dark cells, black on light cells for readability
            text_color = "white" if abs(val) > 0.6 else "black"
            ax.text(
                j,
                i,
                f"{val:.2f}",
                ha="center",
                va="center",
                fontsize=6,
                color=text_color,
            )

    ax.set_title(title, fontsize=13, pad=12)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Heatmap saved -> {output_path}")


def save_results(stats_df: pd.DataFrame, output_path: Path) -> None:
    """
    Save the per-ETF statistics DataFrame to a CSV file.

    Parameters
    ----------
    stats_df    : DataFrame returned by compute_stats()
    output_path : Path where the CSV will be written
    """
    stats_df.to_csv(output_path, index=False)
    print(f"Results saved -> {output_path}")
    # Print a readable summary table to stdout
    print("\nSelected ETFs (sorted by Sharpe ratio):")
    print("-" * 80)
    print(stats_df.to_string(index=False))
    print("-" * 80)
