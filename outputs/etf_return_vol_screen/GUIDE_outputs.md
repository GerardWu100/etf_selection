# GUIDE_outputs.md

## Part 1: Conceptual Explanation

This folder stores outputs from `scripts/scan_etfs_return_vol.py`.

The current default screen keeps ETFs that satisfy:

- at least five usable calendar years
- no more than two usable calendar years below a 2 percent simple return
- average usable calendar-year simple return of at least 4 percent

Passing ETFs are ranked by daily volatility from lowest to highest. Daily
volatility is the sample standard deviation of daily log returns.

## Part 2: File Map

- `etf_return_vol_screen_2026-06-17_001.csv`
  - strict original screen output
  - required every usable calendar year to clear 2 percent, with no minimum
    age beyond one usable year

- `etf_yearly_returns_2026-06-17_001.csv`
  - per-ticker, per-calendar-year detail table used by the screen
  - key columns: `ticker`, `year`, `n_price_days`, `start_price`, `end_price`,
    `yearly_return`

- `etf_return_vol_screen_2026-06-17_002.csv`
  - current default ranked passing ETF summary
  - key columns: `rank`, `ticker`, `years_observed`, `bad_years`,
    `min_yearly_return`, `average_yearly_return`, `daily_volatility`,
    `annualized_volatility`

- `etf_yearly_returns_2026-06-17_002.csv`
  - per-ticker, per-calendar-year detail table used by the current default
    screen

## Part 3: Short Journal

- 2026-06-17: Added the first return-volatility ETF screen output with default
  hurdles of 2 percent minimum yearly return and 4 percent average yearly
  return.
- 2026-06-17: Added a second output using the revised default rule: at least
  five usable years, no more than two years below 2 percent, and at least
  4 percent average yearly return.
