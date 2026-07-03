# GUIDE_tests.md

## Purpose

This folder holds regression tests for the refactored `src/` layout.

The tests are intentionally focused. They protect numerical behavior and the
walkthrough notebook contract without pretending to be a full end-to-end
pipeline suite.

## Current Layout

```text
tests/
├── GUIDE_tests.md
├── unit/
│   ├── backtesting/
│   ├── correlation_analysis/
│   ├── feature_engineering/
│   └── portfolio_allocation/
├── integration/
│   ├── test_allocation_notebook.py
│   └── test_selection_notebook.py
└── data/
```

## Coverage

- `tests/unit/backtesting/test_buy_and_hold.py`
  - exact fixed-share buy-and-hold valuation
  - parseability of `notebooks/01_project_walkthrough/explore_buy_and_hold.ipynb`

- `tests/unit/correlation_analysis/test_log_return_filters.py`
  - log-return threshold semantics
  - average yearly log-return calculations

- `tests/unit/etf_screening/test_yearly_return_screen.py`
  - calendar-year return summaries
  - weekly volatility from last observed weekly closes
  - weekly maximum-drawdown screen behavior

- `tests/unit/feature_engineering/test_pipeline_components.py`
  - session classification
  - prior-session primitives
  - as-of context joins
  - future-only label generation

- `tests/unit/portfolio_allocation/test_mean_variance.py`
  - feasible long-only mean-variance weights
  - the effect of risk aversion on portfolio variance
  - invalid risk-aversion handling and strategy registration

- `tests/integration/test_allocation_notebook.py`
  - clean top-to-bottom execution of the allocation walkthrough
  - mean-variance source contract
  - embedded Portable Network Graphics (PNG) output for all nine charts

- `tests/integration/test_selection_notebook.py`
  - Jupyter schema validation for the selection walkthrough
  - clean top-to-bottom execution from the repository root

## How To Run

- `uv run pytest`
- `uv run pytest tests/unit/backtesting/test_buy_and_hold.py`
- `uv run pytest tests/unit/correlation_analysis/test_log_return_filters.py`
- `uv run pytest tests/unit/feature_engineering/test_pipeline_components.py`
- `uv run pytest tests/unit/portfolio_allocation/test_mean_variance.py`
- `uv run pytest tests/integration/test_allocation_notebook.py`
