# PROJECT_STRUCTURE.md

```text
etf_selection/
├── README.md
├── GUIDE_ROOT.md
├── GUIDE_OVERVIEW.md
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env.example
├── src/
│   ├── __init__.py
│   ├── src/notebook_support.py
│   ├── data_pipeline/
│   ├── correlation_analysis/
│   ├── feature_engineering/
│   ├── portfolio_allocation/
│   └── backtesting/
├── tests/
│   └── unit/
├── data/
│   ├── raw/
│   ├── external/
│   ├── interim/
│   ├── processed/
│   └── cache/
├── outputs/
│   ├── correlation_analysis/
│   ├── portfolio_allocation/
│   ├── backtesting/
│   ├── feature_engineering/
│   ├── reports/
│   ├── figures/
│   ├── tables/
│   └── runs/
├── notebooks/
│   └── 01_project_walkthrough/
├── docs/
│   ├── user/
│   └── reference/
├── templates/
└── logs/
```
