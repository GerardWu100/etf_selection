# GUIDE_outputs.md

## Part 1: Conceptual Explanation

This folder stores outputs from `scripts/scan_etfs_return_vol.py`.

The current default screen keeps ETFs that satisfy:

- latest five usable calendar years
- no usable calendar years below a -1 percent simple return inside that latest
  five-year window
- average usable calendar-year simple return of at least 3 percent inside that
  latest five-year window

Passing ETFs are ranked by weekly volatility from lowest to highest. Weekly
volatility is the sample standard deviation of weekly log returns computed from
each ticker's last observed close in consecutive calendar weeks.

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
  - earlier ranked passing ETF summary
  - key columns: `rank`, `ticker`, `years_observed`, `bad_years`,
    `min_yearly_return`, `average_yearly_return`, `daily_volatility`,
    `annualized_volatility`

- `etf_yearly_returns_2026-06-17_002.csv`
  - per-ticker, per-calendar-year detail table used by the earlier screen

- `etf_return_vol_screen_2026-06-17_003.csv`
  - current default ranked passing ETF summary after switching to weekly
    volatility, a -1 percent minimum yearly return, and zero allowed bad years
  - contains 39 passing ETFs
  - key columns: `rank`, `ticker`, `years_observed`, `bad_years`,
    `min_yearly_return`, `average_yearly_return`, `weekly_volatility`,
    `annualized_weekly_volatility`

- `etf_yearly_returns_2026-06-17_003.csv`
  - per-ticker, per-calendar-year detail table used by the current default
    screen

## Part 3: Short Journal

- 2026-06-17: Added the first return-volatility ETF screen output with default
  hurdles of 2 percent minimum yearly return and 4 percent average yearly
  return.
- 2026-06-17: Added a second output using the revised default rule: at least
  five usable years, no more than two years below 2 percent, and at least
  4 percent average yearly return.
- 2026-06-17: Updated the current default output rule to allow up to two years
  below 1 percent and require at least 3 percent average yearly return.
- 2026-06-17: Updated the current default output rule to allow no years below
  -1 percent and rank passing ETFs by weekly volatility.
- 2026-06-17: Clarified that the current output rule evaluates return hurdles
  on each ETF's latest five usable calendar years.
