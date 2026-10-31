# AGENTS.md

## Goal

Build a practical, long-term ETF portfolio from market data: screen a liquid ETF universe, select ETFs that add diversification rather than overlap (anchored on `VOO` and `VEA`), and compare long-only weighting rules on that basket with exact buy-and-hold evaluation.

## Principles

- Logic lives in `src/`; notebooks and `scripts/` only call it. Notebooks must run top to bottom from a fresh kernel.
- Stay point-in-time and leakage-aware, especially in `feature_engineering`, which stays separate from the selection flow.
- Blog posts in `content/post/` are published: keep them evidence-backed and do not rewrite them unasked.
- This repository is public: never commit `.env`, credentials, machine paths or server details.
- Read `TRAIL_NOTES.md` before changing settled choices.

## Commands

```bash
uv sync
uv run pytest tests/unit          # fast, no database needed
uv run pytest                     # also executes two walkthrough notebooks
```

Data refresh needs ClickHouse credentials in `.env` (see `.env.example`); the README lists the pipeline commands.
