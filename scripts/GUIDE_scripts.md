# GUIDE_scripts.md

## Part 1: Conceptual Explanation

`scripts/` contains thin command-line wrappers for project workflows. Business
logic should stay under `src/`, while scripts should parse inputs, call package
functions, and write outputs.

## Part 2: Code Reference

- `scan_etfs_return_vol.py`
  - runs the calendar-year ETF return screen
  - writes a ranked summary CSV and a per-year return detail CSV under
    `outputs/etf_return_vol_screen/`

## Part 3: Short Journal

- 2026-06-17: Added the first script wrapper for the yearly return and daily
  volatility ETF screen.
