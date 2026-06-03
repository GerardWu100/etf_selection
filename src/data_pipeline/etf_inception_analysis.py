"""
etf_inception_analysis.py
-------------------------
Analyze the inception (birth) year distribution of ETFs in the screened
universe from ``data/raw/volume_screen.csv``.

The volume screen already stores the ``start_date`` column -- the earliest
date with data in the ClickHouse table for each symbol. We treat this as
the ETF's inception date for our purposes.

Outputs:
    - etf_inception_summary.csv   : per-year counts and cumulative counts
    - etf_inception_by_year.png   : bar chart of ETF births per year
    - etf_inception_cumulative.png: line chart of cumulative universe size

Run:
    uv run python data_pipeline/etf_inception_analysis.py
"""

from __future__ import annotations

import pathlib

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

matplotlib.use("Agg")

from data_pipeline.paths import DATA_PIPELINE_OUTPUT_DIR, SCREEN_CSV

OUTPUT_DIR = DATA_PIPELINE_OUTPUT_DIR
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def load_screen() -> pd.DataFrame:
    """
    Load the volume screen CSV and parse the start_date column.

    Returns
    -------
    pd.DataFrame
        Full 500-row universe with ``start_date`` as datetime and a derived
        ``inception_year`` integer column.
    """
    df = pd.read_csv(SCREEN_CSV)
    df["start_date"] = pd.to_datetime(df["start_date"])
    # `inception_year` becomes the grouping key reused by both the summary
    # table and the plots below.
    df["inception_year"] = df["start_date"].dt.year
    return df


def build_inception_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a year-level summary of ETF births.

    Parameters
    ----------
    df : pd.DataFrame
        Output of ``load_screen()`` -- must contain ``inception_year``.

    Returns
    -------
    pd.DataFrame
        Columns:
        - inception_year  : calendar year
        - count           : number of ETFs born in that year
        - cumulative      : running total of ETFs available by end of year
        - pct             : percentage of total universe born in that year
        - cumulative_pct  : cumulative percentage
        Sorted ascending by year.
    """
    counts = (
        df["inception_year"].value_counts().sort_index().rename("count").reset_index()
    )
    counts.columns = ["inception_year", "count"]

    total = counts["count"].sum()
    # The cumulative columns are useful for reasoning about how restrictive a
    # full-history cutoff will be in later stages.
    counts["cumulative"] = counts["count"].cumsum()
    counts["pct"] = (counts["count"] / total * 100).round(1)
    counts["cumulative_pct"] = (counts["cumulative"] / total * 100).round(1)

    return counts


def list_etfs_by_year(df: pd.DataFrame) -> dict[int, list[str]]:
    """
    Group ETF tickers by inception year.

    Returns
    -------
    dict[int, list[str]]
        {year: [ticker1, ticker2, ...]} sorted by year ascending, and tickers
        sorted by combined volume descending within each year.
    """
    result: dict[int, list[str]] = {}
    for year, group in df.sort_values("vol_combined", ascending=False).groupby(
        "inception_year"
    ):
        # Keep the within-year order liquidity-ranked so terminal previews show
        # the most tradable launches first.
        result[int(year)] = group["ticker"].tolist()
    return dict(sorted(result.items()))


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

# Colour palette -- professional blues
BAR_COLOR = "#4A90D9"
LINE_COLOR = "#D94A6B"
GRID_COLOR = "#E5E7EB"
BG_COLOR = "#FAFBFC"


def plot_births_per_year(summary: pd.DataFrame) -> pathlib.Path:
    """
    Bar chart of ETFs born per year with count labels on each bar.

    Returns the path to the saved PNG.
    """
    fig, ax = plt.subplots(figsize=(14, 6), constrained_layout=True)
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    bars = ax.bar(
        summary["inception_year"],
        summary["count"],
        color=BAR_COLOR,
        edgecolor="white",
        linewidth=0.5,
    )

    # Count labels on top of each bar
    for bar, count in zip(bars, summary["count"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.5,
            str(count),
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
        )

    ax.set_xlabel("Inception Year", fontsize=12)
    ax.set_ylabel("Number of ETFs", fontsize=12)
    ax.set_title(
        "ETF Births per Year (Top 500 by Volume)",
        fontsize=14,
        fontweight="bold",
    )
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.6)
    ax.set_axisbelow(True)

    # X-axis: show every year
    ax.set_xticks(summary["inception_year"])
    ax.tick_params(axis="x", rotation=45)

    out = OUTPUT_DIR / "etf_inception_by_year.png"
    # Return the path so `main()` can report exactly which artifact was saved.
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def plot_cumulative(summary: pd.DataFrame) -> pathlib.Path:
    """
    Line chart of cumulative ETF universe size over time.

    Returns the path to the saved PNG.
    """
    fig, ax = plt.subplots(figsize=(14, 6), constrained_layout=True)
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    ax.plot(
        summary["inception_year"],
        summary["cumulative"],
        color=LINE_COLOR,
        linewidth=2.5,
        marker="o",
        markersize=5,
    )
    ax.fill_between(
        summary["inception_year"],
        summary["cumulative"],
        alpha=0.15,
        color=LINE_COLOR,
    )

    ax.set_xlabel("Year", fontsize=12)
    ax.set_ylabel("Cumulative ETFs Available", fontsize=12)
    ax.set_title(
        "Cumulative ETF Universe Size (Top 500 by Volume)",
        fontsize=14,
        fontweight="bold",
    )
    ax.grid(color=GRID_COLOR, linewidth=0.6)
    ax.set_axisbelow(True)

    ax.set_xticks(summary["inception_year"])
    ax.tick_params(axis="x", rotation=45)

    out = OUTPUT_DIR / "etf_inception_cumulative.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full inception-year analysis and save all outputs."""
    # Load once, then reuse the same screened universe for the summary, terminal
    # preview, and both charts.
    df = load_screen()
    print(f"Loaded {len(df)} ETFs from {SCREEN_CSV.name}")
    print(
        f"Inception years span: {df['inception_year'].min()} to {df['inception_year'].max()}"
    )

    # -- Summary table --
    summary = build_inception_summary(df)
    summary_csv = OUTPUT_DIR / "etf_inception_summary.csv"
    summary.to_csv(summary_csv, index=False)
    print(f"\nSaved inception summary -> {summary_csv}")

    # -- Print the summary table to terminal --
    print("\n--- ETF Births per Year ---")
    print(
        summary.to_string(
            index=False,
            formatters={
                "pct": lambda x: f"{x:.1f}%",
                "cumulative_pct": lambda x: f"{x:.1f}%",
            },
        )
    )
    print(f"\nTotal ETFs: {summary['count'].sum()}")

    # -- How many would survive the 2016 cutoff? --
    pre_2016 = df[df["start_date"] <= pd.Timestamp("2016-01-01")]
    post_2016 = df[df["start_date"] > pd.Timestamp("2016-01-01")]
    print(f"\nStart date <= 2016-01-01 (survive cutoff): {len(pre_2016)}")
    print(f"Start date >  2016-01-01 (filtered out)   : {len(post_2016)}")

    # -- Top tickers per year --
    by_year = list_etfs_by_year(df)
    print("\n--- Top ETFs by Inception Year (sorted by volume) ---")
    for year, tickers in by_year.items():
        # Show up to 10 tickers per year
        preview = ", ".join(tickers[:10])
        suffix = f" + {len(tickers) - 10} more" if len(tickers) > 10 else ""
        print(f"  {year} ({len(tickers):3d}): {preview}{suffix}")

    # -- Plots --
    png1 = plot_births_per_year(summary)
    print(f"\nSaved bar chart -> {png1}")

    png2 = plot_cumulative(summary)
    print(f"Saved cumulative chart -> {png2}")


if __name__ == "__main__":
    main()
