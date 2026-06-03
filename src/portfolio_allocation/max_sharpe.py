"""
Maximum-Sharpe allocation method.
"""

import numpy as np

from .allocation_utils import (
    MAX_WEIGHT,
    RISK_FREE,
    TRADING_DAYS_PER_YEAR,
    run_slsqp_portfolio,
)


def max_sharpe(
    mean_ret: np.ndarray,
    cov: np.ndarray,
    risk_free: float = RISK_FREE,
    max_weight: float = MAX_WEIGHT,
) -> np.ndarray:
    """
    Find the maximum-Sharpe portfolio via SLSQP numerical optimization.

    Solves:
        maximize  (w^T mu_ann - rf) / sqrt(w^T Sigma_ann w)
        subject to  sum(w) = 1,  0 <= w_i <= max_weight

    where mu_ann = mean_ret * 252 and Sigma_ann = cov * 252 are the
    annualized mean return vector and covariance matrix. The risk-free
    rate ``rf`` is also annualized.

    Parameters
    ----------
    mean_ret : np.ndarray, shape (n_assets,)
        Per-period (daily) mean log returns.
    cov : np.ndarray, shape (n_assets, n_assets)
        Per-period (daily) covariance matrix of log returns.
    risk_free : float, default RISK_FREE
        Annualized log risk-free rate used in the Sharpe numerator.
    max_weight : float, default MAX_WEIGHT
        Upper bound on any individual asset weight.

    Returns
    -------
    np.ndarray
        Weight vector of shape (n_assets,), non-negative, summing to 1,
        each entry <= max_weight.
    """
    n_assets = len(mean_ret)

    def neg_sharpe(weights: np.ndarray) -> float:
        """Return negative annualized Sharpe ratio for one weight vector."""
        # Convert daily moments to annualized units inside the objective.
        annual_return = float(weights @ mean_ret) * TRADING_DAYS_PER_YEAR
        annual_vol = float(np.sqrt(weights @ cov @ weights * TRADING_DAYS_PER_YEAR))
        if annual_vol < 1e-12:
            return 0.0
        return -(annual_return - risk_free) / annual_vol

    return run_slsqp_portfolio(
        neg_sharpe,
        n_assets,
        "max_sharpe",
        max_weight=max_weight,
    )
