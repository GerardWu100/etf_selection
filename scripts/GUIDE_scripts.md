# GUIDE_scripts.md

## Part 1: Conceptual Explanation

`scripts/` contains thin command-line wrappers for project workflows. Business
logic should stay under `src/`, while scripts should parse inputs, call package
functions, and write outputs.

## Part 2: Code Reference

- `scan_etfs_return_vol.py`
  - runs the drawdown, calendar-year return, and weekly-volatility ETF screen
  - defaults to at least five usable years, full usable history for older ETFs,
    weekly maximum drawdown no worse than -15 percent, and at least 3 percent
    average yearly return
  - writes a ranked summary CSV and a per-year return detail CSV under
    `outputs/etf_return_vol_screen/`
  - writes floating-point CSV values to three decimal places

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
- 2026-06-17: Reverted the return hurdle window to full usable history for
  ETFs with more than five usable years and rounded CSV floats to three
  decimals.
- 2026-06-18: Replaced `--min-yearly-return` and `--max-bad-years` with
  `--min-drawdown`.
