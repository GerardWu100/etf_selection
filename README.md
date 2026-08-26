# etf_selection

Quantitative ETF research pipeline. It screens a liquid ETF universe from
ClickHouse market data, selects a diversified basket, compares long-only
portfolio-weighting rules on that basket, and evaluates exact buy-and-hold
outcomes.

## What it does

- `src/data_pipeline/` ranks ETFs by six-year traded volume (2020-2025) in
  ClickHouse and exports a shared daily close/volume parquet
  (`data/raw/daily_close_volume_screened_2016_2025.parquet`).
- `src/correlation_analysis/` builds a Spearman correlation / signed-distance
  matrix on that universe and runs three diversified-selection methods, each
  anchored on `VOO` and `VEA`: greedy maximin, anchored k-medoids, and max
  diversification ratio (Choueifaty & Coignard, 2008).
- `src/portfolio_allocation/` computes long-only weights for a chosen basket:
  equal weight, minimum variance, mean-variance, maximum Sharpe, risk parity,
  maximum diversification, Hierarchical Risk Parity (HRP), and minimum CVaR
  (Rockafellar-Uryasev).
- `src/backtesting/` runs an exact fixed-share buy-and-hold valuation of a
  chosen basket and weight vector: no rebalancing, transaction costs, or
  slippage.
- `src/etf_screening/` is a standalone screen that ranks ETFs by weekly
  return volatility after a maturity, drawdown, and average-return hurdle.
- `src/feature_engineering/` is a separate, exploratory track that builds a
  leakage-aware intraday feature and label dataset from ClickHouse minute
  bars. It does not feed the ETF selection pipeline above.

The selection and allocation workflow is notebook-first; see
`notebooks/01_project_walkthrough/`.

## Requirements

- Python >=3.13
- A ClickHouse server reachable with the credentials in `.env` (template in
  `.env.example`): `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT`, `CLICKHOUSE_USER`,
  `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_SECURE`, `CLICKHOUSE_VERIFY`.
- ClickHouse table `firstrate.etfs`. The feature-engineering track can also
  read `firstrate.stocks`, `firstrate.futures`, `firstrate.crypto`,
  `firstrate.indices`, `firstrate.options`, and `coinmetrics.perpetual`.
- The correlation-analysis and backtesting stages fall back to the local
  `data/raw/*.parquet` file when ClickHouse credentials are unavailable.

## Setup

```
uv sync
```

## Usage

```bash
# Build the shared liquidity screen and daily dataset
uv run python -m data_pipeline.screen
uv run python -m data_pipeline.export_daily_data

# Run one ETF selection method against the shared dataset
uv run python -m correlation_analysis.correlate_greedy
uv run python -m correlation_analysis.correlate_kmedoids
uv run python -m correlation_analysis.correlate_maxdiv

# Standalone yearly-return / weekly-volatility screen
uv run python scripts/scan_etfs_return_vol.py

# Point-in-time feature-engineering sample run
uv run python -m feature_engineering.cli --config src/feature_engineering/config.toml

# Test suite
uv run pytest
```

Portfolio allocation and buy-and-hold backtesting have no standalone scripts;
run them from `notebooks/01_project_walkthrough/explore_allocation_methods.ipynb`
and `explore_buy_and_hold.ipynb`.

## Configuration

`src/feature_engineering/config.toml` controls the feature-engineering sample
run: the primary minute-bar universe and symbols, context sources with their
`align` / `availability` / `lag` / `max_staleness` join rules, and the output
directory.

## Layout

```text
src/                  importable package code, one folder per pipeline stage
scripts/              thin CLI wrappers (currently scan_etfs_return_vol.py)
notebooks/            walkthrough notebooks; the main selection/allocation entrypoint
data/raw/             shared screened universe and daily parquet
outputs/              generated CSVs, PNGs, and run artifacts per stage
docs/reference/       ClickHouse notes and a methods/math quick guide
tests/                unit and integration tests
```

## Output

- `outputs/correlation_analysis/selected_*.csv` and `heatmap_*.png` — per-method
  selection results.
- `outputs/etf_return_vol_screen/` — ranked screen and per-year return detail CSVs.
- `outputs/feature_engineering/<run_name>/` — feature matrix, manifest, and
  audit tables.
- `outputs/backtesting/`, `outputs/portfolio_allocation/` — artifacts from
  earlier notebook runs; current allocation and backtest results are mostly
  inspected in-notebook.

## Where to start

Read [GUIDE_ROOT.md](./GUIDE_ROOT.md) and [GUIDE_OVERVIEW.md](./GUIDE_OVERVIEW.md)
for the folder map and data flow. Method-level math is in
[docs/reference/methods_math_quick_guide.md](./docs/reference/methods_math_quick_guide.md).
