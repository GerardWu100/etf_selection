# GUIDE_data_pipeline.md

## Part 1 -- Conceptual Explanation

### Purpose and problem statement

This folder builds the two shared data artifacts that the rest of the project
depends on:

1. `data/raw/volume_screen.csv`
2. `data/raw/daily_close_volume_screened_2016_2025.parquet`

The first artifact defines the ETF candidate universe. The second artifact
defines the canonical daily dataset used by notebooks and by downstream
backtesting.

### Spine of the logic

#### `screen.py`

1. Connect to ClickHouse using the root `.env` file.
2. Aggregate ETF share volume by symbol for each calendar year from 2020
   through 2025.
3. Compute the ranking score:
   - `vol_combined = vol_2020 + vol_2021 + vol_2022 + vol_2023 + vol_2024 + vol_2025`
4. Keep the top `TOP_N = 500` symbols by `vol_combined`.
5. Query the earliest available date for each retained symbol.
6. Write the screened universe to `data/raw/volume_screen.csv`.

Why use the full six-year window instead of one anchor year?

- It reduces the chance of selecting a universe that is dominated by one
  temporary regime.
- It gives long-lived liquid ETFs credit across multiple market regimes rather
  than only at two endpoints.

#### `export_daily_data.py`

1. Load the screened universe from `data/raw/volume_screen.csv`.
2. Export all 500 screened ETFs into the shared parquet.
3. Leave the `start_date <= 2016-01-01` full-history rule to the
   correlation-analysis stage.
4. Query ClickHouse minute bars and aggregate them to daily rows:
   - `close_price = argMax(close, ts)`
   - `volume = sum(volume)`
   - This means the daily close is the `close` value from the latest minute bar
     observed on that date, not an average over the day.
5. Ask ClickHouse to emit the result directly as Parquet bytes.
6. Write the bytes to
   `data/raw/daily_close_volume_screened_2016_2025.parquet`.
7. Validate the Parquet magic bytes and print a row/ticker/date summary.

Important:

- The screen is a liquidity ranking only.
- The daily parquet now contains all 500 screened ETFs.
- The full-history rule `start_date <= 2016-01-01` is applied later inside the
  correlation-analysis stage.

### Inputs and outputs

| Item | Type | Meaning |
|---|---|---|
| `firstrate.etfs` | ClickHouse table | Minute-level ETF OHLCV source |
| root `.env` | Environment file | ClickHouse host, port, user, password, and transport flags |
| `data/raw/volume_screen.csv` | CSV | Screened universe with liquidity and first-date metadata |
| `data/raw/daily_close_volume_screened_2016_2025.parquet` | Parquet | Shared daily close/volume dataset for all 500 screened ETFs |

### Math and rules

For symbol $s$:

$$
V^\ast(s) = \sum_{y=2020}^{2025} V_y(s)
$$

where:

- $V_{2020}(s)$ is total traded volume in 2020
- $V_{2021}(s)$ is total traded volume in 2021
- $V_{2022}(s)$ is total traded volume in 2022
- $V_{2023}(s)$ is total traded volume in 2023
- $V_{2024}(s)$ is total traded volume in 2024
- $V_{2025}(s)$ is total traded volume in 2025

The screen keeps the top 500 symbols by $V^\ast(s)$.

For daily export, the project uses:

- `close_price(s, d) = argMax(close, ts)` over all minute bars on date $d$
- `volume(s, d) = sum(volume)` over all minute bars on date $d$

This matters because the minute table does not guarantee a trade in the final
minute of the session. `argMax(close, ts)` recovers the last traded price of
the day rather than assuming a closing bar exists at a fixed timestamp.

### Concrete data examples

`data/raw/volume_screen.csv` rows look like:

| ticker | vol_2020 | vol_2021 | vol_2022 | vol_2023 | vol_2024 | vol_2025 | vol_combined | start_date |
|---|---:|---:|---:|---|
| `TQQQ` | 71,036,712,527 | 33,818,736,998 | 85,012,280,447 | 62,034,735,498 | 27,844,577,926 | 33,643,124,299 | 313,390,167,695 | `2010-02-11` |
| `SPY` | 26,993,012,243 | 15,370,533,205 | 18,832,045,224 | 16,249,663,196 | 10,527,496,649 | 13,108,041,420 | 101,080,791,937 | `2000-01-03` |

The parquet dataset contains:

| ticker | date | close_price | volume |
|---|---|---:|---:|
| `ACWI` | `2016-01-04` | 44.8628 | 6,211,072 |
| `ACWI` | `2016-01-05` | 44.8710 | 3,917,016 |

### Assumptions, constraints, and invariants

- The root `outputs/` folder is the canonical shared artifact location.
- The history window is controlled centrally by the correlation utilities:
  `HISTORY_START = 2016-01-01` and `HISTORY_END = 2025-12-31`.
- The export dataset should contain all 500 liquidity-screened ETFs, including
  later-launch ETFs with partial histories inside 2016-2025.
- The Parquet export is treated as invalid if it fails the `PAR1` header/footer
  check.

## Part 2 -- Folder Tree and File Map

```text
data_pipeline/
├── GUIDE_data_pipeline.md   -- This folder guide.
├── __init__.py              -- Package marker.
├── paths.py                 -- Canonical project paths shared across stages.
├── sql_helpers.py           -- Shared ClickHouse SQL quoting and date-bound helpers.
├── clickhouse_client.py     -- Shared ClickHouse client builder from root `.env`.
├── screen.py                -- Stage-1 liquidity screen and start-date lookup.
└── export_daily_data.py     -- Direct ClickHouse-to-Parquet daily dataset export.
```

## Part 3 -- Code Reference

### `clickhouse_client.py`

What it does:
Builds a ClickHouse HTTP client from the root `.env` file. Both `screen.py`
and `correlation_analysis.correlate_utils` import this helper so connection
logic stays in one place.

Key items:

- `build_client()`

### `screen.py`

What it does:
Builds the top-500 liquid ETF universe from ClickHouse and writes
`data/raw/volume_screen.csv`.

Key items:

- `TOP_N`
- `OUTPUT_CSV`
- `fetch_volume_by_year()`
- `fetch_start_dates()`
- `main()`

Run:

- `uv run python data_pipeline/screen.py`

### `export_daily_data.py`

What it does:
Exports the shared daily close/volume parquet for the full screened top-500
universe without applying the selection-stage history cutoff.

Key items:

- `OUTPUT_PARQUET`
- `_quote_symbol()`
- `_build_daily_query()`
- `_validate_parquet_magic()`
- `main()`

Called by:

- Direct CLI/script execution
- Indirectly supports the notebook-first and backtesting workflows

Run:

- `UV_CACHE_DIR=/tmp/uv-cache uv run python data_pipeline/export_daily_data.py`

### `__init__.py`

What it does:
Marks the folder as an importable package. No runtime logic lives here.

### Short journal

- 2026-05-19: Added `clickhouse_client.py` so pipeline and correlation stages
  share one ClickHouse connection helper.
