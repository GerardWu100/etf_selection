# GUIDE_scripts.md

## Part 1: Conceptual Explanation

`scripts/` contains thin command-line wrappers for project workflows. Business
logic should stay under `src/`, while scripts should parse inputs, call package
functions, and write outputs.

## Part 2: Code Reference

- `scan_etfs_return_vol.py`
  - runs the calendar-year ETF return screen
  - defaults to at least five usable years, no more than two years below
    2 percent, and at least 4 percent average yearly return
  - writes a ranked summary CSV and a per-year return detail CSV under
    `outputs/etf_return_vol_screen/`

## Part 3: Short Journal

- 2026-06-17: Added the first script wrapper for the yearly return and daily
  volatility ETF screen.
- 2026-06-17: Added the configurable `--max-bad-years` option and changed the
  default minimum history to five usable years.
