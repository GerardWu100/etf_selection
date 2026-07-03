"""Conventional mean-variance portfolio allocation."""

import numpy as np

from .allocation_utils import (
    MAX_WEIGHT,
    TRADING_DAYS_PER_YEAR,
    run_slsqp_portfolio,
)

DEFAULT_RISK_AVERSION = 3.0


def mean_variance(
    mean_ret: np.ndarray,
    cov: np.ndarray,
    risk_aversion: float = DEFAULT_RISK_AVERSION,
    max_weight: float = MAX_WEIGHT,
) -> np.ndarray:
    """Maximize expected return net of a portfolio-variance penalty.

    The optimizer maximizes the conventional Markowitz utility:

        utility = w^T mu_ann - (risk_aversion / 2) * w^T Sigma_ann w

    where ``w`` is the portfolio weight vector, ``mu_ann`` is the annualized
    expected log-return vector, and ``Sigma_ann`` is the annualized covariance
    matrix. Daily moments are multiplied by 252 trading days before evaluating
    both terms so their time units are consistent.

    Parameters
    ----------
    mean_ret : numpy.ndarray, shape (n_assets,)
        Per-period daily mean log returns in decimal units.
    cov : numpy.ndarray, shape (n_assets, n_assets)
        Per-period daily covariance matrix of log returns.
    risk_aversion : float, default 3.0
        Positive variance-penalty coefficient. Lower values favor expected
        return; higher values favor lower portfolio variance.
    max_weight : float, default MAX_WEIGHT
        Upper bound on each individual asset weight.

    Returns
    -------
    numpy.ndarray
        Long-only portfolio weights with shape ``(n_assets,)`` that sum to one
        and do not exceed ``max_weight``.

    Raises
    ------
    ValueError
        If ``risk_aversion`` is not finite and strictly positive.
    """
    if not np.isfinite(risk_aversion) or risk_aversion <= 0.0:
        raise ValueError("risk_aversion must be finite and > 0.")

    annual_mean = np.asarray(mean_ret, dtype=float) * TRADING_DAYS_PER_YEAR
    annual_cov = np.asarray(cov, dtype=float) * TRADING_DAYS_PER_YEAR
    n_assets = annual_mean.shape[0]

    def negative_utility(weights: np.ndarray) -> float:
        """Return negative annualized mean-variance utility for minimization."""
        expected_return = float(weights @ annual_mean)
        portfolio_variance = float(weights @ annual_cov @ weights)
        utility = expected_return - 0.5 * risk_aversion * portfolio_variance
        return -utility

    return run_slsqp_portfolio(
        negative_utility,
        n_assets,
        "mean_variance",
        max_weight=max_weight,
    )
