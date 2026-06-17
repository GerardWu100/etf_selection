# GUIDE_outputs.md

## Part 1: Conceptual Explanation

This folder stores outputs from `scripts/scan_etfs_return_vol.py`.

The screen keeps ETFs that clear both return hurdles:

- each usable calendar year has a simple total return of at least 2 percent by
  default
- the average usable calendar-year simple return is at least 4 percent by
  default

Passing ETFs are ranked by daily volatility from lowest to highest. Daily
volatility is the sample standard deviation of daily log returns.

## Part 2: File Map

- `etf_return_vol_screen_2026-06-17_001.csv`
  - ranked passing ETF summary
  - key columns: `rank`, `ticker`, `years_observed`, `min_yearly_return`,
    `average_yearly_return`, `daily_volatility`, `annualized_volatility`

- `etf_yearly_returns_2026-06-17_001.csv`
  - per-ticker, per-calendar-year detail table used by the screen
  - key columns: `ticker`, `year`, `n_price_days`, `start_price`, `end_price`,
    `yearly_return`

## Part 3: Short Journal

- 2026-06-17: Added the first return-volatility ETF screen output with default
  hurdles of 2 percent minimum yearly return and 4 percent average yearly
  return.
