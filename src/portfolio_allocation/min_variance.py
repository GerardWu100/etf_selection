"""
Minimum-variance allocation method.
"""

import numpy as np

from .allocation_utils import MAX_WEIGHT, run_slsqp_portfolio


def min_variance(cov: np.ndarray, max_weight: float = MAX_WEIGHT) -> np.ndarray:
    """
    Find the global minimum-variance portfolio via SLSQP numerical optimization.

    Solves the classic Markowitz minimum-variance problem:
        minimize  w^T Sigma w
        subject to  sum(w) = 1,  0 <= w_i <= max_weight

    where Sigma is the covariance matrix. This ignores expected returns
    entirely, concentrating purely on risk reduction.

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

    def objective(weights: np.ndarray) -> float:
        """Return portfolio variance for one candidate weight vector."""
        # Long-only minimum variance is the pure quadratic form `w^T Σ w`.
        return float(weights @ cov @ weights)

    return run_slsqp_portfolio(
        objective,
        n_assets,
        "min_variance",
        max_weight=max_weight,
    )
