"""Run the ETF drawdown, yearly-return, and weekly-volatility screen.

The script is intentionally thin. Reusable calculations live in
`src/etf_screening/yearly_return_screen.py`; this file only parses command-line
settings, calls the package function, and writes CSV outputs.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from data_pipeline.paths import PRICE_PARQUET, PROJECT_ROOT
from etf_screening.yearly_return_screen import (
    DEFAULT_MIN_DRAWDOWN,
    DEFAULT_MIN_AVERAGE_YEARLY_RETURN,
    DEFAULT_MIN_TRADING_DAYS_PER_YEAR,
    DEFAULT_MIN_YEARS,
    build_screen_outputs,
)

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "etf_return_vol_screen"
CSV_FLOAT_FORMAT = "%.3f"


def parse_args() -> argparse.Namespace:
    """Parse command-line options for the ETF screen."""
    parser = argparse.ArgumentParser(
        description=(
            "Screen ETFs with enough usable calendar years, a maximum-drawdown "
            "floor, a minimum average calendar-year return, and rank survivors "
            "by weekly log-return volatility."
        )
    )
    parser.add_argument(
        "--price-parquet",
        type=Path,
        default=PRICE_PARQUET,
        help="Path to the daily ETF close parquet file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where screen summary and yearly detail CSVs are written.",
    )
    parser.add_argument(
        "--run-tag",
        default=None,
        help="Output filename tag. Defaults to today's date plus a sequence number.",
    )
    parser.add_argument(
        "--min-drawdown",
        type=float,
        default=DEFAULT_MIN_DRAWDOWN,
        help=(
            "Maximum-drawdown floor. For example, -0.15 keeps ETFs whose "
            "weekly max drawdown is not worse than -15 percent."
        ),
    )
    parser.add_argument(
        "--min-average-yearly-return",
        type=float,
        default=DEFAULT_MIN_AVERAGE_YEARLY_RETURN,
        help="Minimum average simple calendar-year return.",
    )
    parser.add_argument(
        "--min-trading-days-per-year",
        type=int,
        default=DEFAULT_MIN_TRADING_DAYS_PER_YEAR,
        help="Minimum daily close observations required for a ticker-year.",
    )
    parser.add_argument(
        "--min-years",
        type=int,
        default=DEFAULT_MIN_YEARS,
        help=(
            "Minimum number of usable calendar years required for an ETF. "
            "Tickers with longer usable histories are evaluated over full "
            "history."
        ),
    )
    return parser.parse_args()


def next_run_tag(output_dir: Path) -> str:
    """Build a date plus sequence run tag such as `2026-06-17_001`."""
    today = date.today().isoformat()
    existing_tags = sorted(output_dir.glob(f"etf_return_vol_screen_{today}_*.csv"))
    sequence_number = len(existing_tags) + 1
    return f"{today}_{sequence_number:03d}"


def main() -> None:
    """Execute the screen and write summary and per-year detail CSV files."""
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    run_tag = args.run_tag if args.run_tag is not None else next_run_tag(output_dir)

    summary, yearly_returns = build_screen_outputs(
        price_parquet=args.price_parquet,
        min_drawdown=args.min_drawdown,
        min_average_yearly_return=args.min_average_yearly_return,
        min_trading_days_per_year=args.min_trading_days_per_year,
        min_years=args.min_years,
    )

    summary_path = output_dir / f"etf_return_vol_screen_{run_tag}.csv"
    yearly_path = output_dir / f"etf_yearly_returns_{run_tag}.csv"

    summary.to_csv(summary_path, index=False, float_format=CSV_FLOAT_FORMAT)
    yearly_returns.to_csv(yearly_path, index=False, float_format=CSV_FLOAT_FORMAT)

    print(f"Wrote ranked ETF screen: {summary_path}")
    print(f"Wrote yearly return details: {yearly_path}")
    print(f"Passing ETFs: {len(summary)}")


if __name__ == "__main__":
    main()
