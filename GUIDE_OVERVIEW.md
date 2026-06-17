# GUIDE_OVERVIEW.md

## Project Tree

```text
etf_selection/
├── src/
│   ├── data_pipeline/
│   ├── correlation_analysis/
│   ├── feature_engineering/
│   ├── etf_screening/
│   ├── portfolio_allocation/
│   ├── backtesting/
│   └── notebook_support.py
├── scripts/
│   └── scan_etfs_return_vol.py
├── data/
│   ├── raw/
│   ├── external/
│   ├── interim/
│   ├── processed/
│   └── cache/
├── outputs/
│   ├── correlation_analysis/
│   ├── portfolio_allocation/
│   ├── backtesting/
│   └── feature_engineering/
├── notebooks/
│   └── 01_project_walkthrough/
├── docs/
│   ├── user/
│   └── reference/
└── tests/
    └── unit/
```

## Purpose

This project builds a practical ETF research pipeline from market data stored
in ClickHouse.

The main workflow answers:

1. Which ETFs are liquid enough to enter the candidate universe?
2. Which of those ETFs add diversification rather than overlap?
3. Which long-only allocation rules look most reasonable on the selected basket?

There is also a separate point-in-time feature-engineering track for research
on intraday predictors and labels. That track is intentionally isolated from
the current ETF selection workflow.

## Core Data Flow

```text
ClickHouse ETF bars
  -> src/data_pipeline/screen.py
  -> data/raw/volume_screen.csv

ClickHouse ETF bars
  -> src/data_pipeline/export_daily_data.py
  -> data/raw/daily_close_volume_screened_2016_2025.parquet

data/raw/*
  -> src/correlation_analysis/
  -> outputs/correlation_analysis/

outputs/correlation_analysis/selected_merged.csv
  -> src/portfolio_allocation/
  -> outputs/portfolio_allocation/

data/raw/daily_close_volume_screened_2016_2025.parquet
  -> src/etf_screening/
  -> outputs/etf_return_vol_screen/

data/raw/daily_close_volume_screened_2016_2025.parquet
  -> src/backtesting/
  -> outputs/backtesting/

ClickHouse multi-asset minute bars
  -> src/feature_engineering/
  -> outputs/feature_engineering/<run_name>/
```

## Important Assumptions

- The shared data contract now lives in `data/raw/`, not in `outputs/`.
- `VOO` and `VEA` remain required anchors in the selection workflow.
- The selection stage can fall back to the shared local parquet when
  ClickHouse credentials are unavailable.
- Notebooks are consumers of the core modules, not separate implementations.

## Main Components

- `src/data_pipeline/`
  - Builds the candidate universe and the shared daily dataset.

- `src/correlation_analysis/`
  - Builds return matrices, correlations, distance matrices, and diversified
    selection outputs.

- `src/portfolio_allocation/`
  - Computes long-only portfolio weights from the selected basket.

- `src/backtesting/`
  - Evaluates exact fixed-share buy-and-hold outcomes from the shared daily
    parquet.

- `src/feature_engineering/`
  - Builds leakage-aware intraday research datasets with explicit as-of joins
    and label generation.

- `src/etf_screening/`
  - Builds standalone ETF screens from the shared daily parquet, including the
    yearly return hurdle screen ranked by daily volatility.

- `scripts/`
  - Holds thin command-line wrappers that call reusable package logic.

- `src/notebook_support.py`
  - Shared notebook helper for artifact checks and ranking summaries.

## Tradeoffs

- The repository still keeps some historical generated artifacts checked in.
  The structural refactor moved them out of `src/`, but did not delete them.
- The stage package names are preserved instead of forcing a generic
  `analytics/`, `features/`, or `models/` taxonomy. That keeps the domain
  meaning obvious while still matching the thin-root `src/` structure.
