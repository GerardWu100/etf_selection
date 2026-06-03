"""
Risk-parity allocation method.
"""

import numpy as np

from .allocation_utils import MAX_WEIGHT, run_slsqp_portfolio


def risk_parity(cov: np.ndarray, max_weight: float = MAX_WEIGHT) -> np.ndarray:
    """
    Find the risk-parity portfolio where every asset contributes equally to
    total portfolio volatility.

    The risk contribution of asset i is defined as:
        RC_i = w_i * (Sigma w)_i / sqrt(w^T Sigma w)

    Risk parity sets RC_i = sigma_port / n for all i, where sigma_port
    = sqrt(w^T Sigma w) is total portfolio volatility. This is solved as a
    minimization of squared deviations from the equal target:

        minimize  sum_i (RC_i - sigma_port / n)^2
        subject to  sum(w) = 1,  1e-6 <= w_i <= max_weight

    The tiny positive floor (1e-6) avoids a divide-by-zero inside RC_i
    when a weight collapses to exactly zero during optimization.

    Parameters
    ----------
    cov : np.ndarray, shape (n_assets, n_assets)
        Per-period covariance matrix of log returns.
    max_weight : float, default MAX_WEIGHT
        Upper bound on any individual asset weight.

    Returns
    -------
    np.ndarray
        Weight vector of shape (n_assets,), positive, summing to 1,
        each entry <= max_weight.
    """
    n_assets = cov.shape[0]
    # Every asset should contribute the same fraction of total portfolio risk.
    target_contribution = 1.0 / n_assets

    def objective(weights: np.ndarray) -> float:
        """Measure squared dispersion of asset risk contributions from parity."""
        port_var = float(weights @ cov @ weights)
        if port_var < 1e-16:
            return 0.0
        marginal = cov @ weights
        port_vol = np.sqrt(port_var)
        # Each term is one asset's contribution to total portfolio volatility.
        contributions = weights * marginal / port_vol
        return float(np.sum((contributions - target_contribution * port_vol) ** 2))

    return run_slsqp_portfolio(
        objective,
        n_assets,
        "risk_parity",
        max_weight=max_weight,
        min_weight=1e-6,
        minimize_options={"ftol": 1e-14, "maxiter": 2000},
    )
