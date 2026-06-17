# GUIDE_ROOT.md

## Part 1: Conceptual Explanation

The repository root is now a coordination layer rather than the place where
implementation code lives.

The design is intentionally simple:

- `src/` holds runnable Python code.
- `data/raw/` holds the shared pipeline inputs that downstream stages reuse.
- `outputs/` holds generated artifacts.
- `notebooks/` holds walkthrough notebooks.
- `docs/reference/` holds human-readable technical notes.
- `tests/` holds regression tests.

That split matters because the project has two different classes of files:

1. **Stable code and configuration** that should be easy to browse and import.
2. **Mutable data and generated artifacts** that should stay out of `src/`.

High-level flow:

```text
ClickHouse + .env
  -> src/data_pipeline/
  -> data/raw/
  -> src/correlation_analysis/
  -> outputs/correlation_analysis/
  -> src/portfolio_allocation/
  -> outputs/portfolio_allocation/
  -> src/backtesting/
  -> outputs/backtesting/

ClickHouse + .env
  -> src/feature_engineering/
  -> outputs/feature_engineering/
```

## Part 2: Code Reference

- `.env`
  - Local ClickHouse credentials used by the data and selection stages.

- `.env.example`
  - Non-secret environment template for a fresh setup.

- `pyproject.toml`
  - Dependency and packaging configuration.
  - The source tree is now package-based through `src/`.

- `README.md`
  - User-facing runbook and current layout summary.

- `GUIDE_OVERVIEW.md`
  - Conceptual architecture guide for the full project.

- `PROJECT_STRUCTURE.md`
  - Snapshot-style structure note for quick scanning.

- `src/`
  - Main implementation code.
  - Start with:
    - [src/data_pipeline](/home/ai4000/projects/etf_selection/src/data_pipeline)
    - [src/correlation_analysis](/home/ai4000/projects/etf_selection/src/correlation_analysis)
    - [src/portfolio_allocation](/home/ai4000/projects/etf_selection/src/portfolio_allocation)
    - [src/backtesting](/home/ai4000/projects/etf_selection/src/backtesting)
    - [src/feature_engineering](/home/ai4000/projects/etf_selection/src/feature_engineering)
    - [src/etf_screening](/home/ai4000/projects/etf_selection/src/etf_screening)

- `data/`
  - Shared raw and staged data folders. The active shared pipeline inputs now
    live in `data/raw/`.

- `scripts/`
  - Thin command-line wrappers for package workflows.

- `outputs/`
  - Generated artifacts grouped outside the source tree.

- `notebooks/`
  - Walkthrough notebooks under `notebooks/01_project_walkthrough/`.

- `docs/`
  - Reference notes under `docs/reference/`.

- `tests/`
  - Unit-style regression coverage under `tests/unit/`.

Where to start:

- Read [README.md](/home/ai4000/projects/etf_selection/README.md).
- Then read [GUIDE_OVERVIEW.md](/home/ai4000/projects/etf_selection/GUIDE_OVERVIEW.md).
- Then open the relevant source folder under `src/`.

## Part 3: Short Journal

- 2026-04-16: The repository was reshaped so implementation lives under `src/`, shared pipeline inputs live under `data/raw/`, and notebooks live in a root `notebooks/` tree.
- 2026-06-17: Added `scripts/` and `src/etf_screening/` for a yearly return
  hurdle screen ranked by daily volatility.
