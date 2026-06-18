# ETF Selection

Quantitative ETF research project for screening a liquid ETF universe,
selecting diversified baskets, comparing long-only allocation rules, and
evaluating simple buy-and-hold outcomes. The repository also contains a
separate point-in-time feature-engineering research track.

## Goal

The main workflow answers three portfolio-construction questions:

1. Which ETFs are liquid enough and old enough to belong in the candidate universe?
2. Which subset is genuinely diversified rather than redundant?
3. Given a selected basket, how do several long-only allocation rules compare?

The feature-engineering stage is exploratory. It does not feed the current ETF
selection pipeline directly.

## Current Layout

```text
etf_selection/
├── README.md
├── GUIDE_ROOT.md
├── GUIDE_OVERVIEW.md
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env.example
├── src/
│   ├── __init__.py
│   ├── src/notebook_support.py
│   ├── data_pipeline/
│   ├── correlation_analysis/
│   ├── etf_screening/
│   ├── feature_engineering/
│   ├── portfolio_allocation/
│   └── backtesting/
├── scripts/
│   └── scan_etfs_return_vol.py
├── tests/
│   ├── GUIDE_tests.md
│   └── unit/
├── data/
│   ├── raw/
│   ├── external/
│   ├── interim/
│   ├── processed/
│   └── cache/
├── outputs/
│   ├── backtesting/
│   ├── correlation_analysis/
│   ├── feature_engineering/
│   ├── reports/
│   ├── figures/
│   ├── tables/
│   └── runs/
├── notebooks/
│   └── 01_project_walkthrough/
├── docs/
│   ├── user/
│   └── reference/
├── templates/
└── logs/
```

## Important Inputs And Outputs

- Shared raw inputs:
  - `data/raw/volume_screen.csv`
  - `data/raw/daily_close_volume_screened_2016_2025.parquet`
- Selection artifacts:
  - `outputs/correlation_analysis/selected_*.csv`
  - `outputs/correlation_analysis/selected_merged.csv`
- Allocation artifacts:
  - `outputs/portfolio_allocation/allocation_*.csv`
  - `outputs/portfolio_allocation/allocation_*.png`
- Backtesting artifacts:
  - `outputs/backtesting/buy_and_hold_*`
- ETF return-volatility screen artifacts:
  - `outputs/etf_return_vol_screen/etf_return_vol_screen_*.csv`
  - `outputs/etf_return_vol_screen/etf_yearly_returns_*.csv`
- Feature-engineering run artifacts:
  - `outputs/feature_engineering/<run_name>/...`

## How To Run

Set up the environment:

```bash
uv sync
```

Screen the ETF universe and export the shared daily dataset:

```bash
uv run python -m data_pipeline.screen
UV_CACHE_DIR=/tmp/uv-cache uv run python -m data_pipeline.export_daily_data
```

Run the point-in-time feature-engineering sample:

```bash
uv run python -m feature_engineering.cli --config src/feature_engineering/config.toml
```

Run the ETF return-volatility screen:

```bash
uv run python scripts/scan_etfs_return_vol.py
```

By default this screen requires at least five usable calendar years, evaluates
all usable years for ETFs with longer histories, allows no years below a -1
percent simple return, requires at least 3 percent average yearly return, and
ranks passing ETFs by lowest weekly log-return volatility. Generated CSV files
format floating-point values to three decimal places.

Execute the walkthrough notebooks from the repository root:

```bash
MPLCONFIGDIR=/tmp/mpl IPYTHONDIR=/tmp/ipython UV_CACHE_DIR=/tmp/uv-cache \
  uv run python -m nbconvert --ExecutePreprocessor.shutdown_kernel=immediate --to notebook --execute --inplace \
  notebooks/01_project_walkthrough/explore_selection_methods.ipynb

MPLCONFIGDIR=/tmp/mpl IPYTHONDIR=/tmp/ipython UV_CACHE_DIR=/tmp/uv-cache \
  uv run python -m nbconvert --ExecutePreprocessor.shutdown_kernel=immediate --to notebook --execute --inplace \
  notebooks/01_project_walkthrough/explore_allocation_methods.ipynb

MPLCONFIGDIR=/tmp/mpl IPYTHONDIR=/tmp/ipython UV_CACHE_DIR=/tmp/uv-cache \
  uv run python -m nbconvert --ExecutePreprocessor.shutdown_kernel=immediate --to notebook --execute --inplace \
  notebooks/01_project_walkthrough/explore_buy_and_hold.ipynb
```

Run the test suite:

```bash
uv run pytest
```

## Where To Start

- Read [GUIDE_ROOT.md](/home/ai4000/projects/etf_selection/GUIDE_ROOT.md) for repository navigation.
- Read [GUIDE_OVERVIEW.md](/home/ai4000/projects/etf_selection/GUIDE_OVERVIEW.md) for the end-to-end architecture.
- Open the walkthrough notebooks under [notebooks/01_project_walkthrough](</home/ai4000/projects/etf_selection/notebooks/01_project_walkthrough>) for the offline analysis flow.

## Next Useful Improvements

- Add a small root-level orchestration CLI so the main stages can be invoked from one command surface.
- Separate truly current artifacts from historical checked-in outputs if the repo should become lighter.
- Add integration tests that execute the notebook contract against the new root `notebooks/` layout.
