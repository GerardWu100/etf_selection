# GUIDE_etf_screening.md

## Part 1: Conceptual Explanation

`src/etf_screening/` contains standalone ETF screening logic that does not
belong to the diversification, allocation, or backtesting stages.

The first screen ranks ETFs that satisfy two calendar-year return hurdles:

- every usable calendar year must have at least a 2 percent simple return by
  default
- the average usable calendar-year return must be at least 4 percent by default

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
