"""Screen ETFs by calendar-year returns and daily volatility.

This module implements a deliberately auditable screen:

1. Convert the long daily close table into per-ticker calendar-year returns.
2. Keep only ETF-years with enough daily observations to count as a usable year.
3. Count how many usable years fall below the minimum yearly return.
4. Keep only ETFs with an acceptable number of below-threshold years.
5. Keep only ETFs whose average calendar-year return clears the average hurdle.
6. Rank the survivors by daily log-return volatility from lowest to highest.

Return convention
-----------------
Calendar-year return is a simple return:

    yearly_return = final_close / first_close - 1

Daily volatility is the sample standard deviation of daily log returns:

    daily_log_return_t = log(close_t / close_{t-1})

The project already uses log returns for daily risk calculations, while simple
calendar-year returns are easier to read for screening hurdles like 2 percent
per year and 4 percent average per year.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from data_pipeline.paths import PRICE_PARQUET

TRADING_DAYS_PER_YEAR = 252
DEFAULT_MIN_YEARLY_RETURN = 0.02
DEFAULT_MIN_AVERAGE_YEARLY_RETURN = 0.04
DEFAULT_MIN_TRADING_DAYS_PER_YEAR = 200
DEFAULT_MIN_YEARS = 5
DEFAULT_MAX_BAD_YEARS = 2

REQUIRED_PRICE_COLUMNS = ("ticker", "date", "close_price")
SCREEN_SUMMARY_COLUMNS = [
    "rank",
    "ticker",
    "start_year",
    "end_year",
    "years_observed",
    "bad_years",
    "bad_year_fraction",
    "min_yearly_return",
    "average_yearly_return",
    "daily_volatility",
    "annualized_volatility",
    "n_daily_returns",
]


def load_price_frame(price_parquet: Path = PRICE_PARQUET) -> pd.DataFrame:
    """Load the daily ETF close table used by the return-volatility screen.

    Parameters
    ----------
    price_parquet : Path, default PRICE_PARQUET
        Parquet file with at least `ticker`, `date`, and `close_price` columns.

    Returns
    -------
    pd.DataFrame
        Long price table with columns `ticker`, `date`, and `close_price`.

    Raises
    ------
    FileNotFoundError
        If the parquet file does not exist.
    """
    if not price_parquet.exists():
        raise FileNotFoundError(f"Price parquet not found: {price_parquet}")

    return pd.read_parquet(price_parquet, columns=list(REQUIRED_PRICE_COLUMNS))


def prepare_price_frame(price_frame: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize a long daily close table.

    Parameters
    ----------
    price_frame : pd.DataFrame
        Long daily close table. Required columns are `ticker`, `date`, and
        `close_price`.

    Returns
    -------
    pd.DataFrame
        Clean table sorted by ticker and date. The table has uppercase tickers,
        datetime dates, positive close prices, and duplicate ticker-date rows
        collapsed to the last observed close.
    """
    missing_columns = [
        column for column in REQUIRED_PRICE_COLUMNS if column not in price_frame.columns
    ]
    if missing_columns:
        raise ValueError(f"Missing required price columns: {missing_columns}")

    clean = price_frame.loc[:, list(REQUIRED_PRICE_COLUMNS)].copy()

    # Normalize symbols once so downstream grouping never treats `voo` and
    # `VOO` as different assets.
    clean["ticker"] = clean["ticker"].astype(str).str.strip().str.upper()
    clean["date"] = pd.to_datetime(clean["date"])
    clean["close_price"] = pd.to_numeric(clean["close_price"], errors="coerce")

    clean = clean.dropna(subset=["ticker", "date", "close_price"])
    clean = clean[clean["ticker"] != ""]
    clean = clean[clean["close_price"] > 0.0]

    if clean.empty:
        raise ValueError("No valid price rows remain after cleaning.")

    clean = clean.sort_values(["ticker", "date"])

    # If a source accidentally contains more than one close for a ticker-date,
    # keep the last row after sorting. The input parquet is daily already, but
    # this makes the boundary behavior explicit.
    clean = clean.drop_duplicates(subset=["ticker", "date"], keep="last")
    return clean.reset_index(drop=True)


def compute_yearly_returns(
    price_frame: pd.DataFrame,
    min_trading_days_per_year: int = DEFAULT_MIN_TRADING_DAYS_PER_YEAR,
) -> pd.DataFrame:
    """Compute simple calendar-year returns for each ticker.

    Parameters
    ----------
    price_frame : pd.DataFrame
        Clean or raw long daily close table with `ticker`, `date`, and
        `close_price` columns.
    min_trading_days_per_year : int, default 200
        Minimum number of observed daily closes required for a ticker-year to
        count as a usable year. This avoids treating short partial years as
        full annual records.

    Returns
    -------
    pd.DataFrame
        One row per usable ticker-year with columns:
        `ticker`, `year`, `n_price_days`, `start_date`, `end_date`,
        `start_price`, `end_price`, and `yearly_return`.
    """
    if min_trading_days_per_year < 2:
        raise ValueError("min_trading_days_per_year must be at least 2.")

    clean = prepare_price_frame(price_frame)
    clean["year"] = clean["date"].dt.year

    yearly_rows = []
    for (ticker, year), group in clean.groupby(["ticker", "year"], sort=True):
        # Each group is already sorted by date because `prepare_price_frame`
        # sorted the full table by ticker and date.
        n_price_days = len(group)
        if n_price_days < min_trading_days_per_year:
            continue

        start_row = group.iloc[0]
        end_row = group.iloc[-1]
        start_price = float(start_row["close_price"])
        end_price = float(end_row["close_price"])
        yearly_return = end_price / start_price - 1.0

        yearly_rows.append(
            {
                "ticker": ticker,
                "year": int(year),
                "n_price_days": int(n_price_days),
                "start_date": start_row["date"],
                "end_date": end_row["date"],
                "start_price": start_price,
                "end_price": end_price,
                "yearly_return": yearly_return,
            }
        )

    return pd.DataFrame(yearly_rows)


def compute_daily_volatility(price_frame: pd.DataFrame) -> pd.DataFrame:
    """Compute daily and annualized log-return volatility for each ticker.

    Parameters
    ----------
    price_frame : pd.DataFrame
        Clean or raw long daily close table with `ticker`, `date`, and
        `close_price` columns.

    Returns
    -------
    pd.DataFrame
        One row per ticker with `ticker`, `daily_volatility`,
        `annualized_volatility`, and `n_daily_returns`.
    """
    clean = prepare_price_frame(price_frame)
    price_wide = clean.pivot(index="date", columns="ticker", values="close_price")
    price_wide = price_wide.sort_index()

    # Log returns make multi-day compounding additive and match the rest of the
    # project risk convention. Missing observations are left as missing rather
    # than filled, so volatility is computed only from observed adjacent closes.
    log_returns = np.log(price_wide / price_wide.shift(1))

    daily_volatility = log_returns.std(axis=0, ddof=1)
    n_daily_returns = log_returns.count(axis=0)

    volatility = pd.DataFrame(
        {
            "ticker": daily_volatility.index.astype(str),
            "daily_volatility": daily_volatility.to_numpy(dtype=float),
            "annualized_volatility": daily_volatility.to_numpy(dtype=float)
            * np.sqrt(TRADING_DAYS_PER_YEAR),
            "n_daily_returns": n_daily_returns.to_numpy(dtype=int),
        }
    )
    return volatility.dropna(subset=["daily_volatility"]).reset_index(drop=True)


def screen_etfs_by_yearly_return(
    price_frame: pd.DataFrame,
    min_yearly_return: float = DEFAULT_MIN_YEARLY_RETURN,
    min_average_yearly_return: float = DEFAULT_MIN_AVERAGE_YEARLY_RETURN,
    min_trading_days_per_year: int = DEFAULT_MIN_TRADING_DAYS_PER_YEAR,
    min_years: int = DEFAULT_MIN_YEARS,
    max_bad_years: int = DEFAULT_MAX_BAD_YEARS,
) -> pd.DataFrame:
    """Screen ETFs by yearly return hurdles and rank by daily volatility.

    Parameters
    ----------
    price_frame : pd.DataFrame
        Long daily close table with `ticker`, `date`, and `close_price`.
    min_yearly_return : float, default 0.02
        Simple return threshold used to count bad years. A value of 0.02 means
        2 percent.
    min_average_yearly_return : float, default 0.04
        Minimum average simple calendar-year return. A value of 0.04 means
        4 percent.
    min_trading_days_per_year : int, default 200
        Minimum number of daily close observations needed for a ticker-year to
        count as a usable calendar year.
    min_years : int, default 5
        Minimum number of usable calendar years required for an ETF to pass.
    max_bad_years : int, default 2
        Maximum number of usable calendar years allowed below
        `min_yearly_return`. Set to 0 for the strict rule that every usable
        year must clear the yearly threshold.

    Returns
    -------
    pd.DataFrame
        Passing ETFs ranked from lowest to highest daily volatility. Columns:
        `rank`, `ticker`, `start_year`, `end_year`, `years_observed`,
        `bad_years`, `bad_year_fraction`, `min_yearly_return`,
        `average_yearly_return`, `daily_volatility`, `annualized_volatility`,
        and `n_daily_returns`.
    """
    if min_years < 1:
        raise ValueError("min_years must be at least 1.")
    if max_bad_years < 0:
        raise ValueError("max_bad_years must be at least 0.")

    yearly_returns = compute_yearly_returns(
        price_frame=price_frame,
        min_trading_days_per_year=min_trading_days_per_year,
    )
    if yearly_returns.empty:
        return pd.DataFrame(columns=SCREEN_SUMMARY_COLUMNS)

    yearly_summary = (
        yearly_returns.groupby("ticker")
        .agg(
            start_year=("year", "min"),
            end_year=("year", "max"),
            years_observed=("year", "count"),
            bad_years=(
                "yearly_return",
                lambda returns: int((returns < min_yearly_return).sum()),
            ),
            min_yearly_return=("yearly_return", "min"),
            average_yearly_return=("yearly_return", "mean"),
        )
        .reset_index()
    )
    yearly_summary["bad_year_fraction"] = (
        yearly_summary["bad_years"] / yearly_summary["years_observed"]
    )

    passing = yearly_summary[
        (yearly_summary["years_observed"] >= min_years)
        & (yearly_summary["bad_years"] <= max_bad_years)
        & (yearly_summary["average_yearly_return"] >= min_average_yearly_return)
    ].copy()

    if passing.empty:
        return pd.DataFrame(columns=SCREEN_SUMMARY_COLUMNS)

    volatility = compute_daily_volatility(price_frame)
    result = passing.merge(volatility, on="ticker", how="inner")
    result = result.sort_values(
        ["daily_volatility", "average_yearly_return", "ticker"],
        ascending=[True, False, True],
    ).reset_index(drop=True)

    # Use one-based ranks because this CSV is meant to be read directly by a
    # human, not only consumed by code.
    result.insert(0, "rank", np.arange(1, len(result) + 1))
    return result


def build_screen_outputs(
    price_parquet: Path = PRICE_PARQUET,
    min_yearly_return: float = DEFAULT_MIN_YEARLY_RETURN,
    min_average_yearly_return: float = DEFAULT_MIN_AVERAGE_YEARLY_RETURN,
    min_trading_days_per_year: int = DEFAULT_MIN_TRADING_DAYS_PER_YEAR,
    min_years: int = DEFAULT_MIN_YEARS,
    max_bad_years: int = DEFAULT_MAX_BAD_YEARS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load prices and build both summary and per-year screen outputs.

    Parameters
    ----------
    price_parquet : Path, default PRICE_PARQUET
        Parquet file containing daily close prices.
    min_yearly_return : float, default 0.02
        Simple calendar-year return threshold used to count bad years.
    min_average_yearly_return : float, default 0.04
        Minimum average simple calendar-year return.
    min_trading_days_per_year : int, default 200
        Minimum daily close observations required for a usable ticker-year.
    min_years : int, default 5
        Minimum number of usable calendar years required for an ETF to pass.
    max_bad_years : int, default 2
        Maximum number of usable years allowed below `min_yearly_return`.

    Returns
    -------
    summary : pd.DataFrame
        Ranked passing ETF summary.
    yearly_returns : pd.DataFrame
        Per-ticker, per-calendar-year return details used by the screen.
    """
    prices = load_price_frame(price_parquet)
    yearly_returns = compute_yearly_returns(
        price_frame=prices,
        min_trading_days_per_year=min_trading_days_per_year,
    )
    summary = screen_etfs_by_yearly_return(
        price_frame=prices,
        min_yearly_return=min_yearly_return,
        min_average_yearly_return=min_average_yearly_return,
        min_trading_days_per_year=min_trading_days_per_year,
        min_years=min_years,
        max_bad_years=max_bad_years,
    )
    return summary, yearly_returns
