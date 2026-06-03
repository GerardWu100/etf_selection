"""
correlate_kmedoids.py
---------------------
Select N_SELECT ETFs from the volume-screened universe using anchored
k-medoids clustering on the signed Spearman correlation distance matrix.

Method: Anchored k-medoids
--------------------------
K-medoids is a representative-selection clustering method: each cluster is
represented by one actual observed ETF (the medoid) rather than by a synthetic
centroid. That makes it a natural fit for ETF basket construction.

This implementation hard-locks the required anchor ETFs as fixed medoids, then
optimizes the remaining medoids over the survivor universe. The algorithm uses:

1. Greedy furthest-first initialization for the non-anchor medoids.
2. Standard nearest-medoid assignment.
3. Within-cluster medoid updates that minimize total distance to the cluster.

Because the objective is built directly on the signed correlation distance
matrix, the resulting medoids are a diversified set of actual tradable ETFs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from . import correlate_utils as utils
except ImportError:  # pragma: no cover - script execution fallback
    import correlate_utils as utils

OUT_CSV = utils.OUTPUT_DIR / "selected_kmedoids.csv"
OUT_HEATMAP = utils.OUTPUT_DIR / "heatmap_kmedoids.png"

MAX_ITER = 25
TOLERANCE = 1e-12


def _initialize_medoids(
    dist: pd.DataFrame,
    anchor_tickers: list[str],
    n_select: int,
) -> list[int]:
    """Build anchor-fixed initial medoids with shared furthest-first expansion."""
    symbols = dist.index.tolist()
    sym_to_idx = {symbol: idx for idx, symbol in enumerate(symbols)}
    seed_indices = [sym_to_idx[ticker] for ticker in anchor_tickers[:n_select]]
    return utils.furthest_first_indices(dist.values, seed_indices, n_select)


def _assign_clusters(
    distance_values: np.ndarray, medoid_indices: list[int]
) -> np.ndarray:
    """Assign each symbol to its nearest medoid by signed distance."""
    # Slice the full distance matrix down to one column per current medoid, then
    # choose the nearest medoid for each symbol row.
    medoid_distance = distance_values[:, medoid_indices]
    return np.argmin(medoid_distance, axis=1)


def _best_cluster_medoid(
    distance_values: np.ndarray,
    cluster_members: np.ndarray,
    vol_map: dict[str, float],
    symbols: list[str],
) -> int:
    """Choose the lowest-total-distance member of a cluster as its medoid."""
    sub_distance = distance_values[np.ix_(cluster_members, cluster_members)]
    total_distance = sub_distance.sum(axis=1)
    best_value = float(total_distance.min())
    tied = cluster_members[np.abs(total_distance - best_value) < TOLERANCE]
    if len(tied) == 1:
        return int(tied[0])
    return int(max(tied, key=lambda idx: vol_map.get(symbols[int(idx)], 0.0)))


def select_by_kmedoids(
    dist: pd.DataFrame,
    candidates: pd.DataFrame,
    max_iter: int = MAX_ITER,
    n_select: int = utils.N_SELECT,
    anchor_tickers: list[str] | None = None,
) -> tuple[list[str], pd.DataFrame]:
    """
    Run anchored k-medoids on the signed distance matrix.

    Parameters
    ----------
    dist : pd.DataFrame
        Signed distance matrix, index and columns equal to ticker symbols.
    candidates : pd.DataFrame
        Survivor metadata with at least `ticker` and `vol_combined`.
    max_iter : int, default MAX_ITER
        Maximum number of assignment/update iterations.
    n_select : int, default utils.N_SELECT
        Number of medoids (ETFs) to select.
    anchor_tickers : list[str] | None, default None
        Required anchor medoids locked in before optimisation. When None,
        falls back to the module-level constant ``ANCHOR_TICKERS``.

    Returns
    -------
    tuple[list[str], pd.DataFrame]
        Selected tickers in anchor-first order and one row per selected medoid
        with cluster diagnostics.
    """
    symbols = dist.index.tolist()
    n_select = min(n_select, len(symbols))
    # Resolve anchors once
    anchors = utils.resolve_anchor_tickers(
        anchor_tickers, symbols, "k-medoids survivors"
    )
    vol_map = candidates.set_index("ticker")["vol_combined"].to_dict()
    distance_values = dist.values

    # `medoid_indices` is the working state updated by each assignment/update
    # iteration until the set of medoids stabilizes.
    medoid_indices = _initialize_medoids(dist, anchors, n_select)
    fixed_medoid_indices = {
        # Fixed anchor medoids participate in cluster assignment but never move
        # during the update step.
        idx
        for idx in medoid_indices
        if symbols[idx] in set(anchors)
    }

    for iteration in range(max_iter):
        assignments = _assign_clusters(distance_values, medoid_indices)
        # Start from the current medoids, then replace only the medoids whose
        # cluster center actually changes.
        updated_indices = medoid_indices.copy()
        changed = False

        for medoid_position, medoid_idx in enumerate(medoid_indices):
            if medoid_idx in fixed_medoid_indices:
                continue

            cluster_members = np.where(assignments == medoid_position)[0]
            if len(cluster_members) == 0:
                continue

            best_idx = _best_cluster_medoid(
                distance_values=distance_values,
                cluster_members=cluster_members,
                vol_map=vol_map,
                symbols=symbols,
            )
            if best_idx != medoid_idx:
                updated_indices[medoid_position] = best_idx
                changed = True

        medoid_indices = updated_indices
        print(
            f"  k-medoids iteration {iteration + 1:2d}: "
            f"{'updated medoids' if changed else 'converged'}"
        )
        if not changed:
            break

    assignments = _assign_clusters(distance_values, medoid_indices)
    medoid_rows: list[dict[str, float | int | str]] = []
    anchor_set = set(anchors)

    for medoid_position, medoid_idx in enumerate(medoid_indices):
        cluster_members = np.where(assignments == medoid_position)[0]
        medoid_ticker = symbols[medoid_idx]
        cluster_distance = distance_values[
            np.ix_(cluster_members, [medoid_idx])
        ].ravel()
        medoid_rows.append(
            {
                "ticker": medoid_ticker,
                "cluster_size": int(len(cluster_members)),
                "avg_cluster_distance": float(cluster_distance.mean()),
                "is_anchor_medoid": int(medoid_ticker in anchor_set),
            }
        )

    medoid_info = pd.DataFrame(medoid_rows)
    # Split anchors from non-anchors so the ranking step can keep the required
    # core pair ahead of the data-driven medoid ordering.
    non_anchor_info = medoid_info[medoid_info["is_anchor_medoid"] == 0].copy()
    # Larger clusters come first because they represent broader sections of the
    # survivor universe; distance then breaks ties toward tighter representatives.
    non_anchor_info = non_anchor_info.sort_values(
        ["cluster_size", "avg_cluster_distance", "ticker"],
        ascending=[False, True, True],
    )

    ranked_tickers = anchors + non_anchor_info["ticker"].tolist()
    selected = utils.build_anchor_first_selection(
        ranked_tickers=ranked_tickers,
        available_tickers=symbols,
        n_select=n_select,
        anchor_tickers=anchors,
    )

    selection_rank = {ticker: rank for rank, ticker in enumerate(selected, start=1)}
    medoid_info["selection_rank"] = medoid_info["ticker"].map(selection_rank)
    medoid_info = medoid_info.sort_values("selection_rank").reset_index(drop=True)

    print(f"Anchored k-medoids selected {len(selected)} ETFs.")
    print(f"Fixed anchors: {', '.join(anchors)}")

    return selected, medoid_info
