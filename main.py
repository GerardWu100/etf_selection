"""Minimal repository entrypoint.

This module intentionally stays trivial. The actual ETF-selection workflows are
implemented in stage-specific packages such as `data_pipeline`,
`correlation_analysis`, `portfolio_allocation`, `backtesting`, and
`feature_engineering`.

Running this file is mainly a quick environment smoke test.
"""


def main() -> None:
    """Print a short confirmation message for a basic local run check."""
    # Keep the root entrypoint intentionally trivial; the real workflow lives in
    # the stage-specific modules documented in GUIDE_ROOT.md.
    # The print keeps `uv run python main.py` from failing silently in a fresh
    # clone where the user has not picked a specific workflow yet.
    print("Hello from etf-selection!")


if __name__ == "__main__":
    main()
