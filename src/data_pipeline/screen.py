"""
screen.py
---------
Screen the top ETFs by combined 2020-2025 trading volume from the
firstrate.etfs ClickHouse table.

Output
------
data/raw/volume_screen.csv  --  columns:
    ticker       : ETF symbol
    vol_2020     : total share volume traded in calendar year 2020
    vol_2021     : total share volume traded in calendar year 2021
    vol_2022     : total share volume traded in calendar year 2022
    vol_2023     : total share volume traded in calendar year 2023
    vol_2024     : total share volume traded in calendar year 2024
    vol_2025     : total share volume traded in calendar year 2025
    vol_combined : total six-year volume from 2020 through 2025
    start_date   : earliest date with data in the entire table for that symbol

The top `TOP_N` rows by vol_combined are saved. This CSV feeds directly into
the correlation-analysis stage as the candidate universe.
"""

from __future__ import annotations

import os

import pandas as pd

from data_pipeline.clickhouse_client import build_client
from data_pipeline.paths import RAW_DATA_DIR
from data_pipeline.sql_helpers import build_symbols_in_list

# Config -- change TOP_N to screen more or fewer candidates
TOP_N = 500  # number of ETFs to keep after volume screening
SCREEN_YEARS = tuple(range(2020, 2026))
VOLUME_COLUMNS = [f"vol_{year}" for year in SCREEN_YEARS]

# Shared raw-data directory at project root; all pipeline stages use the same path.
OUTPUT_DIR = RAW_DATA_DIR
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_CSV = OUTPUT_DIR / "volume_screen.csv"


def fetch_volume_by_year(client) -> pd.DataFrame:
    """
    Query ClickHouse for per-symbol volume summed over 2020 through 2025.

    The query groups by (symbol, year) and returns one row per
    (symbol, year) pair. We then pivot to wide format so each symbol
    has a single row with one volume column per screen year.

    Returns
    -------
    pd.DataFrame
        Wide DataFrame indexed by symbol with columns:
        vol_2020 ... vol_2025, vol_combined.
        Sorted descending by vol_combined.
    """
    years_sql = ", ".join(str(year) for year in SCREEN_YEARS)

    # Sum volume for each symbol across the full 2020-2025 screen window.
    query = """
        SELECT
            symbol,
            toYear(ts)      AS year,
            sum(volume)     AS total_vol
        FROM firstrate.etfs
        WHERE toYear(ts) IN ({years_sql})
        GROUP BY symbol, year
        ORDER BY symbol, year
    """.format(years_sql=years_sql)
    print("Querying ClickHouse: per-symbol volume for 2020 through 2025 ...")
    result = client.query(query)

    df_long = pd.DataFrame(result.result_rows, columns=result.column_names)

    # Pivot to one row per symbol; missing years become zero volume.
    df_wide = df_long.pivot(index="symbol", columns="year", values="total_vol").fillna(
        0
    )

    df_wide.columns.name = None
    rename_map = {
        year: f"vol_{year}" for year in SCREEN_YEARS if year in df_wide.columns
    }
    df_wide = df_wide.rename(columns=rename_map)

    for col in VOLUME_COLUMNS:
        if col not in df_wide.columns:
            df_wide[col] = 0.0

    df_wide = df_wide[VOLUME_COLUMNS]
    df_wide["vol_combined"] = df_wide[VOLUME_COLUMNS].sum(axis=1)
    df_wide = df_wide.sort_values("vol_combined", ascending=False)

    return df_wide


def fetch_start_dates(client, symbols: list[str]) -> pd.Series:
    """
    For each symbol, fetch the earliest trading date in firstrate.etfs.

    Parameters
    ----------
    client  : connected ClickHouse client
    symbols : list of ETF ticker strings to look up

    Returns
    -------
    pd.Series
        Index = symbol (str), values = start_date (date string, "YYYY-MM-DD").
    """
    symbols_sql = build_symbols_in_list(symbols)

    query = f"""
        SELECT
            symbol,
            toDate(min(ts)) AS start_date
        FROM firstrate.etfs
        WHERE symbol IN ({symbols_sql})
        GROUP BY symbol
    """
    print(f"Querying ClickHouse: start dates for {len(symbols)} symbols ...")
    result = client.query(query)

    df = pd.DataFrame(result.result_rows, columns=result.column_names)
    return df.set_index("symbol")["start_date"]


def main() -> None:
    """
    Full screening pipeline:
      1. Connect to ClickHouse.
      2. Fetch per-year volume for all symbols in 2020 through 2025.
      3. Rank by combined volume, keep top TOP_N.
      4. Fetch start dates for the top TOP_N symbols.
      5. Save to data/raw/volume_screen.csv.
      6. Print the top 20 rows for a quick sanity check.
    """
    client = build_client()
    print(f"Connected to ClickHouse at {os.environ['CLICKHOUSE_HOST']}")

    df_vol = fetch_volume_by_year(client)
    print(f"Total symbols with data in the 2020-2025 screen window: {len(df_vol)}")

    df_top = df_vol.head(TOP_N).copy()
    print(f"Top {TOP_N} symbols selected.")

    top_symbols = df_top.index.tolist()
    start_dates = fetch_start_dates(client, top_symbols)

    df_top["start_date"] = start_dates.map(str)

    df_top.index.name = "ticker"
    df_top = df_top.reset_index()
    df_top = df_top[["ticker", *VOLUME_COLUMNS, "vol_combined", "start_date"]]

    if OUTPUT_CSV.exists():
        OUTPUT_CSV.unlink()

    df_top.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved {len(df_top)} rows -> {OUTPUT_CSV}")

    print("\nTop 20 by combined 2020-2025 volume:")
    print("-" * 72)
    preview = df_top.head(20).copy()
    for col in [*VOLUME_COLUMNS, "vol_combined"]:
        preview[col] = preview[col].apply(lambda value: f"{value:,.0f}")
    print(preview.to_string(index=False))
    print("-" * 72)


if __name__ == "__main__":
    main()
