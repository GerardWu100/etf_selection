# GUIDE_scripts.md

## Part 1: Conceptual Explanation

`scripts/` contains thin command-line wrappers for project workflows. Business
logic should stay under `src/`, while scripts should parse inputs, call package
functions, and write outputs.

## Part 2: Code Reference

- `scan_etfs_return_vol.py`
  - runs the calendar-year ETF return screen
  - defaults to each ETF's latest five usable years, no years below -1 percent
    inside that window, and at least 3 percent average yearly return
  - writes a ranked summary CSV and a per-year return detail CSV under
    `outputs/etf_return_vol_screen/`

## Part 3: Short Journal

- 2026-06-17: Added the first script wrapper for the yearly return and daily
  volatility ETF screen.
- 2026-06-17: Added the configurable `--max-bad-years` option and changed the
  default minimum history to five usable years.
- 2026-06-17: Lowered the default screen thresholds to 1 percent minimum yearly
  return and 3 percent average yearly return.
- 2026-06-17: Switched the screen ranking from daily volatility to weekly
  volatility and tightened the default bad-year allowance back to zero.
- 2026-06-17: Clarified that the return hurdles apply to each ETF's latest
  five usable calendar years.
