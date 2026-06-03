# GUIDE_outputs.md

## Part 1 -- Conceptual Explanation

### Purpose and problem statement

This folder stores timestamped artifacts produced by two backtesting workflows:

- `backtesting/buy_and_hold.py` through `save_result_files()`
- `backtesting/yearly_ticker_metrics.py` through `save_yearly_ticker_report()`

Unlike root `outputs/`, these files are local to the backtesting module and are
meant to preserve individual runs rather than act as shared pipeline inputs.

### Artifact patterns

- `buy_and_hold_metrics_<timestamp>.csv`
  - One summary row per run
  - Key fields:
    - `start_date`
    - `end_date`
    - `n_assets`
    - `n_trading_days`
    - `initial_capital`
    - `final_value`
    - `total_return`
    - `cagr`
    - `annualized_return`
    - `annualized_volatility`
    - `sharpe_ratio`
    - `sortino_ratio`
    - `max_drawdown`
    - `calmar_ratio`
    - `risk_free_rate`

- `buy_and_hold_equity_curve_<timestamp>.csv`
  - One row per trading day
  - Schema:
    - `date`
    - `portfolio_value`
    - `daily_return`
    - `cumulative_return`
    - `drawdown`

- `buy_and_hold_allocation_<timestamp>.csv`
  - One row per ticker
  - Schema:
    - `ticker`
    - `entry_price`
    - `shares`
    - `initial_allocation_usd`
    - `initial_weight`
    - `final_price`
    - `final_value_usd`
    - `final_weight`

- `buy_and_hold_chart_<timestamp>.png`
  - Two-panel chart showing portfolio value and drawdown

- `buy_and_hold_run_<timestamp>.log`
  - Text log with run tag, tickers, input file path, date filters, realized
    start/end dates, and summary metrics

- `ticker_yearly_metrics_<timestamp>.csv`
  - One row per `(ticker, year)`
  - Schema:
    - `ticker`
    - `year`
    - `start_date`
    - `end_date`
    - `n_price_days`
    - `n_return_days`
    - `start_price`
    - `end_price`
    - `total_return`
    - `annualized_return`
    - `annualized_volatility`
    - `sharpe_ratio`

- `ticker_yearly_total_return_<timestamp>.csv`
  - Wide pivot table
  - Row = ticker
  - Column = calendar year
  - Cell = simple total return for that ticker-year

- `ticker_yearly_sharpe_<timestamp>.csv`
  - Wide pivot table
  - Row = ticker
  - Column = calendar year
  - Cell = yearly Sharpe ratio for that ticker-year

- `ticker_yearly_report_<timestamp>.log`
  - Text log with run tag, tickers, parquet path, date filters, and output file
    names for one saved yearly-report run

### Current snapshot

The current folder snapshot contains several buy-and-hold runs plus one saved
single-ticker yearly report from March 15, 2026. These files are examples of
the naming pattern, not special-cased outputs.

## Part 2 -- Folder Tree and File Map

```text
outputs/backtesting/
├── GUIDE_outputs.md                         -- This folder guide.
├── buy_and_hold_metrics_20260301_055753.csv -- Metrics snapshot for one run.
├── buy_and_hold_metrics_20260301_063524.csv -- Metrics snapshot for one run.
├── buy_and_hold_metrics_20260301_063653.csv -- Metrics snapshot for one run.
├── buy_and_hold_equity_curve_20260301_055753.csv -- Daily equity path.
├── buy_and_hold_equity_curve_20260301_063524.csv -- Daily equity path.
├── buy_and_hold_equity_curve_20260301_063653.csv -- Daily equity path.
├── buy_and_hold_allocation_20260301_055753.csv -- Per-ticker holdings table.
├── buy_and_hold_allocation_20260301_063524.csv -- Per-ticker holdings table.
├── buy_and_hold_allocation_20260301_063653.csv -- Per-ticker holdings table.
├── buy_and_hold_chart_20260301_055753.png   -- Value/drawdown chart.
├── buy_and_hold_chart_20260301_063524.png   -- Value/drawdown chart.
├── buy_and_hold_chart_20260301_063653.png   -- Value/drawdown chart.
├── buy_and_hold_run_20260301_055753.log     -- Text run log.
├── buy_and_hold_run_20260301_063524.log     -- Text run log.
├── buy_and_hold_run_20260301_063653.log     -- Text run log.
├── ticker_yearly_metrics_20260315_notebook20.csv -- Long per-ticker yearly metrics table.
├── ticker_yearly_total_return_20260315_notebook20.csv -- Wide yearly return pivot.
├── ticker_yearly_sharpe_20260315_notebook20.csv -- Wide yearly Sharpe pivot.
└── ticker_yearly_report_20260315_notebook20.log -- Saved-report run log.
```

## Part 3 -- Code Reference

### Producing functions

- `backtesting.buy_and_hold.save_result_files()`
  - writes the metrics CSV, equity-curve CSV, allocation CSV, chart, and log

- `backtesting.buy_and_hold.save_charts()`
  - creates the PNG chart used by `save_result_files()`

- `backtesting.yearly_ticker_metrics.save_yearly_ticker_report()`
  - writes the long yearly table, return pivot, Sharpe pivot, and report log

### Consuming workflows

- `backtesting/cli.py`
  - direct producer of these files

- `notebooks/01_project_walkthrough/explore_buy_and_hold.ipynb`
  - can be used to create additional runs or compare baskets interactively

- `backtesting/explore_single_ticker_metrics.ipynb`
  - interactive notebook for displaying one return and one Sharpe ratio per
    ticker-year without constructing a portfolio
