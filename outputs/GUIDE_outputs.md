# GUIDE_outputs.md

## Part 1: Conceptual Explanation

This folder stores generated artifacts. The important structural rule is that
shared pipeline inputs no longer live here; they now live in `data/raw/`.

That split is deliberate:

- `data/raw/` contains reusable pipeline inputs.
- `outputs/` contains derived artifacts, charts, reports, and saved runs.

## Part 2: Code Reference

- `outputs/correlation_analysis/`
  - selection CSVs and correlation diagnostics

- `outputs/portfolio_allocation/`
  - allocation tables and charts

- `outputs/backtesting/`
  - backtest CSVs, charts, and logs

- `outputs/feature_engineering/`
  - run-specific research artifacts

- `outputs/reports/`, `outputs/figures/`, `outputs/tables/`, `outputs/runs/`
  - root-level scaffolding for future artifact consolidation

- `outputs/runs/2026-06-17_001_main_smoke/`
  - archived smoke-test run containing a copy of `main.py`, captured standard
    output, captured standard error, and the process exit code

## Part 3: Short Journal

- 2026-04-16: Shared datasets were moved out of `outputs/` and into `data/raw/` so generated artifacts no longer mix with base inputs.
- 2026-06-17: Added the first root-level run archive under `outputs/runs/` to
  preserve both the executed script and its terminal output.
