"""
Hierarchical Risk Parity (HRP) allocation method.
"""

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.spatial.distance import squareform
from correlation_analysis.correlate_utils import (
    correlation_distance_numpy,
    spearman_corr_numpy,
)

from .allocation_utils import MAX_WEIGHT, apply_cap


def hrp_weights(log_ret: pd.DataFrame, max_weight: float = MAX_WEIGHT) -> np.ndarray:
    """
    Compute Hierarchical Risk Parity (HRP) weights from a log-return matrix.

    HRP allocates capital based on the hierarchical structure of pairwise
    correlations rather than inverting the covariance matrix (which is
    numerically unstable for large, correlated baskets).

    Algorithm
    ---------
    1. Build Spearman correlation matrix from ``log_ret``.
    2. Convert to correlation distance: D = sqrt(0.5 * (1 - r)).
    3. Build a hierarchical clustering tree using Ward linkage on ``D``.
    4. Reorder assets by dendrogram leaf order so correlated assets are adjacent.
    5. Recursive bisection: split the portfolio into left/right branches,
       allocate capital in proportion to inverse cluster variance
       (lower-variance branch gets more weight), and recurse until single assets.
    6. Apply a per-asset maximum weight cap via ``apply_cap``.

    Parameters
    ----------
    log_ret : pd.DataFrame
        Wide log-return matrix. Rows = dates, columns = asset tickers.
    max_weight : float, default MAX_WEIGHT
        Maximum allowed weight for any single asset (applied as a post-processing cap).

    Returns
    -------
    np.ndarray
        Weight vector of shape (n_assets,), aligned with ``log_ret.columns``,
        non-negative, summing to 1, each entry <= max_weight.
    """
    symbols = log_ret.columns.tolist()
    n_assets = len(symbols)

    # Fill sparse gaps once so the rank-correlation and covariance calls below
    # operate on a complete panel.
    filled = log_ret.fillna(log_ret.median())
    corr = spearman_corr_numpy(filled.values)

    # HRP clusters on correlation distance rather than covariance directly so
    # the tree reflects relative co-movement structure.
    dist = correlation_distance_numpy(corr)

    condensed = squareform(dist, checks=False)
    # The linkage matrix encodes the full clustering tree that HRP later walks
    # from leaves to root.
    linkage_matrix = linkage(condensed, method="ward")
    leaf_order = leaves_list(linkage_matrix).tolist()

    cov_df = filled.cov()
    ordered_symbols = [symbols[index] for index in leaf_order]
    cov_ordered = cov_df.loc[ordered_symbols, ordered_symbols].values

    weights = np.ones(n_assets) / n_assets

    def cluster_var(indices: list[int]) -> float:
        """Estimate one cluster variance using inverse-variance sub-weights."""
        # Extract the covariance block for one branch of the dendrogram.
        sub_cov = cov_ordered[np.ix_(indices, indices)]
        variances = np.maximum(np.diag(sub_cov), 1e-12)
        inv_var = 1.0 / variances
        inv_var_weights = inv_var / inv_var.sum()
        return float(inv_var_weights @ sub_cov @ inv_var_weights)

    def recursive_bisect(indices: list[int]) -> None:
        """Recursively split a cluster and rebalance branch weights by variance."""
        if len(indices) <= 1:
            return
        mid = len(indices) // 2
        left, right = indices[:mid], indices[mid:]
        var_left, var_right = cluster_var(left), cluster_var(right)
        total = var_left + var_right
        # Lower-variance clusters receive the larger share of portfolio weight.
        alpha = (1.0 - var_left / total) if total > 0 else 0.5

        current_total = weights[indices].sum()
        weights[left] *= alpha * current_total / weights[left].sum()
        weights[right] *= (1.0 - alpha) * current_total / weights[right].sum()

        recursive_bisect(left)
        recursive_bisect(right)

    recursive_bisect(list(range(n_assets)))
    weights /= weights.sum()

    # `reordered` converts the dendrogram-order weights back to original ticker
    # order before the shared cap helper is applied.
    reordered = np.zeros(n_assets)
    for ordered_idx, original_idx in enumerate(leaf_order):
        # Undo the dendrogram leaf ordering so callers get weights aligned with
        # the original column order of `log_ret`.
        reordered[original_idx] = weights[ordered_idx]

    return apply_cap(reordered, max_weight)
