"""
Shared helpers for offline notebook exploration.

This module keeps the three exploratory notebooks focused on analysis instead
of repeating the same filesystem, ranking, and overlap logic. It only uses
local CSV/Parquet artifacts so it remains usable when ClickHouse access is not
available.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

from data_pipeline.paths import (
    CORRELATION_OUTPUT_DIR,
    PRICE_PARQUET,
    PROJECT_ROOT,
)

OUTPUT_DIR = PROJECT_ROOT / "outputs"
SELECTION_OUTPUT_DIR = CORRELATION_OUTPUT_DIR
METHOD_SELECTION_CSVS = {
    "greedy": SELECTION_OUTPUT_DIR / "selected_greedy.csv",
    "kmedoids": SELECTION_OUTPUT_DIR / "selected_kmedoids.csv",
    "maxdiv": SELECTION_OUTPUT_DIR / "selected_maxdiv.csv",
}


def bootstrap_notebook(start: Path | None = None) -> Path:
    """Locate the project root and add it to ``sys.path`` for notebook imports."""
    current = (start or Path.cwd()).resolve()
    search_roots = [current, *current.parents]
    for candidate in search_roots:
        if (candidate / "GUIDE_ROOT.md").exists():
            source_root = candidate / "src"
            for path_to_add in [source_root, candidate]:
                if str(path_to_add) not in sys.path:
                    # Inject `src/` first for imports, then the project root for
                    # root-level docs and data path discovery.
                    sys.path.insert(0, str(path_to_add))
            return candidate
    raise FileNotFoundError(
        "Could not locate project root from the current notebook directory."
    )


def ensure_required_artifacts(paths: dict[str, Path]) -> None:
    """Raise a clear error if any local artifact required by a notebook is missing."""
    # `missing` keeps the human-readable label alongside the path so the error
    # message can tell the notebook user exactly what to regenerate.
    missing = {label: path for label, path in paths.items() if not path.exists()}
    if missing:
        # Build the bullet list once and re-use it in the exception text.
        detail = "\n".join(
            f"  - {label}: {path.relative_to(PROJECT_ROOT)}"
            for label, path in missing.items()
        )
        raise FileNotFoundError(
            "Missing local artifacts required for offline notebook exploration.\n"
            f"{detail}\n"
            "Regenerate them from existing outputs or restore them before running notebooks."
        )


def load_local_price_data(columns: list[str] | None = None) -> pd.DataFrame:
    """Load the shared daily parquet used by the notebook-first workflow."""
    ensure_required_artifacts({"daily parquet": PRICE_PARQUET})
    # Default to the columns most notebooks need so they do not read the full
    # parquet unless they are doing something more specialized.
    read_columns = columns or ["ticker", "date", "close_price", "volume"]
    return pd.read_parquet(PRICE_PARQUET, columns=read_columns)


def build_membership_frame(selection_map: dict[str, list[str]]) -> pd.DataFrame:
    """
    Return a wide membership table with per-method ranks and average-rank consensus.

    Missing method ranks are penalized as that method's ``max_rank + 1`` so an
    ETF that appears in only one selector does not outrank a name that is
    consistently near the top across several selectors.
    """
    membership = pd.DataFrame({"ticker": sorted(set().union(*selection_map.values()))})
    missing_rank_penalties: dict[str, float] = {}

    for method_name, selected in selection_map.items():
        # `rank_map` converts one ordered basket into lookup form so the unioned
        # membership table can attach that method's rank to every ticker.
        rank_map = {ticker: rank for rank, ticker in enumerate(selected, start=1)}
        rank_column = f"{method_name}_rank"
        membership[rank_column] = membership["ticker"].map(rank_map)
        # Missing a method is penalized just beyond that method's last explicit
        # rank so partial appearances do not dominate consensus ordering.
        max_rank = len(selected)
        missing_rank_penalties[rank_column] = max_rank + 1

    rank_columns = [column for column in membership.columns if column.endswith("_rank")]
    # `filled_ranks` is the penalized version used for consensus sorting;
    # `membership` keeps the original NaNs for transparency.
    filled_ranks = membership[rank_columns].copy()
    for rank_column, penalty in missing_rank_penalties.items():
        filled_ranks[rank_column] = filled_ranks[rank_column].fillna(float(penalty))

    membership["selection_count"] = membership[rank_columns].notna().sum(axis=1)
    membership["missing_rank_count"] = membership[rank_columns].isna().sum(axis=1)
    membership["average_rank_selected_only"] = membership[rank_columns].mean(
        axis=1,
        skipna=True,
    )
    membership["average_rank"] = filled_ranks.mean(axis=1)
    return membership.sort_values(
        [
            "average_rank",
            "average_rank_selected_only",
            "missing_rank_count",
            "ticker",
        ],
        ascending=[True, True, True, True],
        na_position="last",
    ).reset_index(drop=True)


def build_overlap_matrix(selection_map: dict[str, list[str]]) -> pd.DataFrame:
    """Compute pairwise selection overlap counts."""
    method_names = list(selection_map)
    # Start with an empty square table keyed by method name on both axes.
    overlap = pd.DataFrame(index=method_names, columns=method_names, dtype=int)
    for left_name in method_names:
        for right_name in method_names:
            # Use set intersection so the matrix reflects basket overlap only,
            # not the original ranking positions within each method.
            overlap.loc[left_name, right_name] = len(
                set(selection_map[left_name]) & set(selection_map[right_name])
            )
    return overlap
