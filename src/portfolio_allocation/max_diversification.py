"""
Maximum-diversification allocation method.
"""

import numpy as np

from .allocation_utils import MAX_WEIGHT, run_slsqp_portfolio


def max_diversification(cov: np.ndarray, max_weight: float = MAX_WEIGHT) -> np.ndarray:
    """
    Find the maximum-diversification portfolio via SLSQP numerical optimization.

    The diversification ratio (DR) compares the weighted sum of standalone asset
    volatilities to actual portfolio volatility:

        DR = (w^T sigma) / sqrt(w^T Sigma w)

    where sigma_i = sqrt(Sigma_ii) is the volatility of asset i. DR = 1
    for a single-asset portfolio (no diversification benefit). DR > 1 indicates
    that correlation between assets reduces total risk below the weighted-average
    standalone risk. This method maximizes DR:

        maximize  (w^T sigma) / sqrt(w^T Sigma w)
        subject to  sum(w) = 1,  0 <= w_i <= max_weight

    Parameters
    ----------
    cov : np.ndarray, shape (n_assets, n_assets)
        Per-period covariance matrix of log returns.
    max_weight : float, default MAX_WEIGHT
        Upper bound on any individual asset weight.

    Returns
    -------
    np.ndarray
        Weight vector of shape (n_assets,), non-negative, summing to 1,
        each entry <= max_weight.
    """
    n_assets = cov.shape[0]
    # Cache standalone volatilities once; they do not depend on the trial weights.
    asset_vols = np.sqrt(np.diag(cov))

    def neg_div_ratio(weights: np.ndarray) -> float:
        """Return the negative diversification ratio for SLSQP minimization."""
        weighted_vol = float(weights @ asset_vols)
        port_vol = float(np.sqrt(weights @ cov @ weights))
        if port_vol < 1e-12:
            return 0.0
        # `minimize` solves a minimization problem, so negate the ratio.
        return -weighted_vol / port_vol

    return run_slsqp_portfolio(
        neg_div_ratio,
        n_assets,
        "max_diversification",
        max_weight=max_weight,
    )
