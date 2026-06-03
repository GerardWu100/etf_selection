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
│   └── feature_engineering/
├── integration/
└── data/
```

## Coverage

- `tests/unit/backtesting/test_buy_and_hold.py`
  - exact fixed-share buy-and-hold valuation
  - parseability of `notebooks/01_project_walkthrough/explore_buy_and_hold.ipynb`

- `tests/unit/correlation_analysis/test_log_return_filters.py`
  - log-return threshold semantics
  - average yearly log-return calculations

- `tests/unit/feature_engineering/test_pipeline_components.py`
  - session classification
  - prior-session primitives
  - as-of context joins
  - future-only label generation

## How To Run

- `uv run pytest`
- `uv run pytest tests/unit/backtesting/test_buy_and_hold.py`
- `uv run pytest tests/unit/correlation_analysis/test_log_return_filters.py`
- `uv run pytest tests/unit/feature_engineering/test_pipeline_components.py`
