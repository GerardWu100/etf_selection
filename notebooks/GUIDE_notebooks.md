# GUIDE_notebooks.md

## Part 1: Conceptual Explanation

The notebooks are walkthrough consumers of the core modules under `src/`.
They are not meant to duplicate business logic.

The active walkthrough set lives under `notebooks/01_project_walkthrough/`.

## Part 2: Code Reference

- `explore_selection_methods.ipynb`
  - Offline review of the selection stage from local artifacts.
  - Imports shared paths from `data_pipeline.paths` and executes from the
    repository root without relying on saved kernel state.

- `explore_allocation_methods.ipynb`
  - Manual comparison of eight long-only allocation rules using the shared
    local price parquet when ClickHouse credentials are unavailable.
  - Exposes the mean-variance risk-aversion coefficient as `RISK_AVERSION`
    beside the notebook's other tunable settings.
  - Restores Jupyter's inline Matplotlib backend after importing shared
    script-oriented utilities, so its nine charts remain visible in both an
    interactive kernel and an executed notebook.

- `explore_buy_and_hold.ipynb`
  - Buy-and-hold evaluation of a chosen basket.

- `etf_inception_analysis.ipynb`
  - Screening-universe inception analysis.

- `data_pipeline_test.ipynb`
  - Small parquet sanity-check notebook.

## Part 3: Short Journal

- 2026-07-03: Added conventional mean-variance allocation with a configurable
  notebook-level risk-aversion coefficient and expanded the comparison to
  eight strategies and nine charts.
- 2026-04-16: The notebooks were centralized under a root `notebooks/` tree so the source folders stay code-focused.
- 2026-07-02: The allocation walkthrough now overrides the shared headless
  plotting backend inside Jupyter so `plt.show()` embeds charts instead of
  emitting non-interactive-backend warnings.
- 2026-07-02: The selection walkthrough's stale, schema-invalid outputs were
  discarded and regenerated from a clean top-to-bottom execution.
