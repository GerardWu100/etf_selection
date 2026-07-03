# GUIDE_notebooks.md

## Part 1: Conceptual Explanation

The notebooks are walkthrough consumers of the core modules under `src/`.
They are not meant to duplicate business logic.

The active walkthrough set lives under `notebooks/01_project_walkthrough/`.

## Part 2: Code Reference

- `explore_selection_methods.ipynb`
  - Offline review of the selection stage from local artifacts.

- `explore_allocation_methods.ipynb`
  - Manual comparison of seven long-only allocation rules using the shared
    local price parquet when ClickHouse credentials are unavailable.
  - Restores Jupyter's inline Matplotlib backend after importing shared
    script-oriented utilities, so its eight charts remain visible in both an
    interactive kernel and an executed notebook.

- `explore_buy_and_hold.ipynb`
  - Buy-and-hold evaluation of a chosen basket.

- `etf_inception_analysis.ipynb`
  - Screening-universe inception analysis.

- `data_pipeline_test.ipynb`
  - Small parquet sanity-check notebook.

## Part 3: Short Journal

- 2026-04-16: The notebooks were centralized under a root `notebooks/` tree so the source folders stay code-focused.
- 2026-07-02: The allocation walkthrough now overrides the shared headless
  plotting backend inside Jupyter so `plt.show()` embeds charts instead of
  emitting non-interactive-backend warnings.
