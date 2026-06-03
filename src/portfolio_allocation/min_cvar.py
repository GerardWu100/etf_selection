"""
Minimum-CVaR allocation method.
"""

import numpy as np
from scipy.optimize import minimize

from .allocation_utils import MAX_WEIGHT, clip_and_renormalize, warn_if_not_converged


def min_cvar(
    returns: np.ndarray,
    alpha: float = 0.95,
    max_weight: float = MAX_WEIGHT,
) -> np.ndarray:
    """
    Find the minimum-CVaR portfolio using the Rockafellar-Uryasev (2000) formulation.

    CVaR at level alpha (e.g. 0.95) is the expected loss in the worst (1-alpha)
    fraction of days. Rockafellar-Uryasev reformulate it as a smooth optimization
    over weights ``w`` and an auxiliary threshold ``zeta`` (the Value-at-Risk
    estimate):

        minimize  zeta + 1 / (T * (1 - alpha)) * sum_t max(-r_t^T w - zeta, 0)
        subject to  sum(w) = 1,  0 <= w_i <= max_weight,  zeta in [-1, 1]

    where ``r_t`` is the vector of asset returns on day t and T is the number
    of observation days. The max() term accumulates losses beyond the VaR
    threshold, so the objective equals CVaR at the optimum.

    The analytic gradient is provided to SLSQP to speed convergence.

    Parameters
    ----------
    returns : np.ndarray, shape (n_obs, n_assets)
        Historical per-period log-return matrix. Rows = time, columns = assets.
    alpha : float, default 0.95
        CVaR confidence level. 0.95 means we target the worst 5% of days.
    max_weight : float, default MAX_WEIGHT
        Upper bound on any individual asset weight.

    Returns
    -------
    np.ndarray
        Weight vector of shape (n_assets,), non-negative, summing to 1,
        each entry <= max_weight.
    """
    n_obs, n_assets = returns.shape
    # Rockafellar-Uryasev rewrites CVaR minimization as a smooth problem in the
    # weights plus an auxiliary VaR-like threshold `zeta`.
    scale = 1.0 / (n_obs * (1.0 - alpha))

    initial = np.zeros(n_assets + 1)
    # The optimization vector is `[weights..., zeta]`, so allocate one extra
    # slot for the auxiliary tail-loss threshold.
    initial[:n_assets] = 1.0 / n_assets
    initial[n_assets] = 0.0

    def objective(x: np.ndarray) -> float:
        """Evaluate Rockafellar-Uryasev CVaR objective at one parameter vector."""
        weights, zeta = x[:n_assets], x[n_assets]
        losses = -(returns @ weights)
        excess = np.maximum(losses - zeta, 0.0)
        return float(zeta + scale * excess.sum())

    def gradient(x: np.ndarray) -> np.ndarray:
        """Return analytic gradient of the CVaR objective with respect to x."""
        weights, zeta = x[:n_assets], x[n_assets]
        losses = -(returns @ weights)
        # Only observations in the tail beyond `zeta` contribute to the CVaR
        # gradient.
        mask = (losses > zeta).astype(float)
        grad = np.empty(n_assets + 1)
        grad[:n_assets] = -scale * (mask[:, None] * returns).sum(axis=0)
        grad[n_assets] = 1.0 - scale * mask.sum()
        return grad

    constraints = [{"type": "eq", "fun": lambda x: x[:n_assets].sum() - 1.0}]
    # Bound the weights long-only and keep `zeta` in a wide but finite range to
    # help SLSQP numerically.
    bounds = [(0.0, max_weight)] * n_assets + [(-1.0, 1.0)]

    result = minimize(
        objective,
        initial,
        jac=gradient,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-12, "maxiter": 2000},
    )

    warn_if_not_converged(result, "min_cvar")
    return clip_and_renormalize(result.x[:n_assets])
