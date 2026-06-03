"""
export_daily_data.py
--------------------
Export daily ETF close/volume data for the screened ETF universe to Parquet.

This script is designed for the exact workflow used in this repository:

1. Stage 1 has already produced `data/raw/volume_screen.csv` (top 500 by
   combined 2020-2025 volume).
2. We export daily history for all 500 screened ETFs.
3. The full-history start-date screen is applied later by the
   correlation-analysis stage, not here.
4. For the screened ETFs, we query ClickHouse minute bars and aggregate to one
   row per (ticker, date):
      - `close_price`: `argMax(close, ts)` (last traded close of the day)
      - `volume`: `sum(volume)` (total shares traded during that day)
5. We request query output directly in ClickHouse `Parquet` format and write
   bytes to a local `.parquet` file.

Run:
    UV_CACHE_DIR=/tmp/uv-cache uv run python -m data_pipeline.export_daily_data
"""

from __future__ import annotations

from correlation_analysis import correlate_utils as utils
from data_pipeline.clickhouse_client import build_client
from data_pipeline.paths import PRICE_PARQUET
from data_pipeline.sql_helpers import build_symbols_in_list, exclusive_end_date

OUTPUT_PARQUET = PRICE_PARQUET


def _build_daily_query(symbols: list[str], start_date: str, end_date: str) -> str:
    """
    Build the ClickHouse query that returns one daily row per ticker.

    Args:
        symbols: ETF ticker list from the top-500 liquidity screen.
        start_date: Inclusive lower bound in YYYY-MM-DD.
        end_date: Inclusive upper bound in YYYY-MM-DD.

    Returns:
        SQL query string for Parquet export.
    """
    history_end_exclusive = exclusive_end_date(end_date)
    symbols_sql = build_symbols_in_list(symbols)

    return f"""
        SELECT
            symbol              AS ticker,
            toDate(ts)          AS date,
            argMax(close, ts)   AS close_price,
            sum(volume)         AS volume
        FROM firstrate.etfs
        WHERE symbol IN ({symbols_sql})
          AND ts >= '{start_date}'
          AND ts <  '{history_end_exclusive}'
        GROUP BY ticker, date
        ORDER BY ticker, date
    """


def _validate_parquet_magic(path) -> None:
    """
    Validate basic Parquet file magic bytes.

    A Parquet file starts with `PAR1` and ends with `PAR1`. This is a quick
    sanity check that the export did not write a truncated or wrong-format file.
    """
    with path.open("rb") as handle:
        head = handle.read(4)
        handle.seek(-4, 2)
        tail = handle.read(4)

    if head != b"PAR1" or tail != b"PAR1":
        raise ValueError(
            f"Parquet magic-byte validation failed for {path}. "
            f"head={head!r}, tail={tail!r}"
        )


def main() -> None:
    """Run the full export pipeline and write the Parquet artifact."""
    candidates = utils.load_screened_universe()
    symbols = candidates["ticker"].astype(str).tolist()

    print(
        "Screened universe size before the correlation-stage start-date filter: "
        f"{len(symbols)} ETFs"
    )

    query = _build_daily_query(
        symbols=symbols,
        start_date=utils.HISTORY_START,
        end_date=utils.HISTORY_END,
    )

    client = build_client()
    print(
        f"Connected to ClickHouse. Exporting daily close+volume for "
        f"{len(symbols)} ETFs ({utils.HISTORY_START} to {utils.HISTORY_END}) ..."
    )
    parquet_bytes = client.raw_query(query, fmt="Parquet")

    if OUTPUT_PARQUET.exists():
        OUTPUT_PARQUET.unlink()

    OUTPUT_PARQUET.write_bytes(parquet_bytes)
    _validate_parquet_magic(OUTPUT_PARQUET)

    file_size_mb = OUTPUT_PARQUET.stat().st_size / (1024 * 1024)
    print(f"Saved Parquet -> {OUTPUT_PARQUET}")
    print(f"File size: {file_size_mb:.2f} MB")

    summary_query = f"""
        SELECT
            count(*)            AS rows,
            uniqExact(ticker)   AS tickers,
            min(date)           AS min_date,
            max(date)           AS max_date
        FROM (
            {query}
        )
    """
    summary = client.query(summary_query)
    rows, tickers, min_date, max_date = summary.result_rows[0]

    print(
        "Verification summary: "
        f"rows={rows:,}, tickers={tickers}, "
        f"date_range=[{min_date}, {max_date}]"
    )


if __name__ == "__main__":
    main()
