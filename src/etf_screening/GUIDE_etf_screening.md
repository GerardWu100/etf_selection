# GUIDE_etf_screening.md

## Part 1: Conceptual Explanation

`src/etf_screening/` contains standalone ETF screening logic that does not
belong to the diversification, allocation, or backtesting stages.

The first screen ranks ETFs that satisfy a maturity rule and two return
conditions:

- at least five usable calendar years by default
- no more than two usable calendar years below a 1 percent simple return by
  default
- the average usable calendar-year return must be at least 3 percent by default

Passing ETFs are ranked by daily volatility from lowest to highest. Daily
volatility is the sample standard deviation of daily log returns.

## Part 2: Code Reference

- `yearly_return_screen.py`
  - loads the shared daily close parquet
  - computes per-ticker calendar-year simple returns
  - computes per-ticker daily log-return volatility
  - returns a ranked screen summary and per-year detail table

## Part 3: Short Journal

- 2026-06-17: Added the return-hurdle and daily-volatility ETF screen used by
  `scripts/scan_etfs_return_vol.py`.
- 2026-06-17: Changed the default screen to require at least five usable years
  and allow up to two below-threshold years, reducing the new-ETF bias caused
  by requiring every year to exceed 2 percent.
- 2026-06-17: Lowered the default return hurdles to 1 percent minimum yearly
  return and 3 percent average yearly return.
