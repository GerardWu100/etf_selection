"""
Shared constants and helpers for flattened allocation modules.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from scipy.optimize import minimize

from correlation_analysis import correlate_utils as utils

# Default lower/upper bounds used across all strategies.
MIN_WEIGHT = 0.05
MAX_WEIGHT = 0.20

# Annualized trading-day count and risk-free rate shared across all methods.
TRADING_DAYS_PER_YEAR = 252
RISK_FREE = utils.RISK_FREE


def clip_and_renormalize(raw: np.ndarray) -> np.ndarray:
    """
    Clip small negative solver artefacts and renormalize weights to sum to 1.

    Numerical optimizers (SLSQP) can return tiny negative values at
    zero-bound constraints. Clipping at zero and renormalizing is the
    standard post-processing step before using weights downstream.

    Parameters
    ----------
    raw : np.ndarray, shape (n_assets,)
        Raw weight vector from the optimizer.

    Returns
    -------
    np.ndarray
        Non-negative weights summing to 1.
    """
    weights = np.maximum(raw, 0.0)
    weights /= weights.sum()
    return weights


def run_slsqp_portfolio(
    objective: Callable[[np.ndarray], float],
    n_assets: int,
    method_name: str,
    *,
    max_weight: float = MAX_WEIGHT,
    min_weight: float = 0.0,
    minimize_options: dict | None = None,
) -> np.ndarray:
    """
    Run the shared long-only fully-invested SLSQP shell used by most allocators.

    Parameters
    ----------
    objective : callable
        Scalar objective evaluated on a weight vector of length ``n_assets``.
    n_assets : int
        Number of assets in the basket.
    method_name : str
        Label passed to ``warn_if_not_converged`` when the solver fails.
    max_weight : float, default MAX_WEIGHT
        Upper bound on each asset weight.
    min_weight : float, default 0.0
        Lower bound on each asset weight (risk parity uses a tiny positive floor).
    minimize_options : dict | None, default None
        Optional ``scipy.optimize.minimize`` options override.

    Returns
    -------
    np.ndarray
        Non-negative weights summing to 1 after ``clip_and_renormalize``.
    """
    initial = np.ones(n_assets) / n_assets
    constraints = [{"type": "eq", "fun": lambda weights: weights.sum() - 1.0}]
    bounds = [(min_weight, max_weight)] * n_assets
    options = minimize_options or {"ftol": 1e-12, "maxiter": 1000}

    result = minimize(
        objective,
        initial,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options=options,
    )

    warn_if_not_converged(result, method_name)
    return clip_and_renormalize(result.x)


def warn_if_not_converged(result: object, method_name: str) -> None:
    """Print a warning when a scipy optimizer does not converge.

    Parameters
    ----------
    result : scipy OptimizeResult
        Return value from ``scipy.optimize.minimize``.
    method_name : str
        Human-readable name of the allocation method (for the message).
    """
    if not result.success:  # type: ignore[union-attr]
        print(
            f"  WARNING: {method_name} optimiser did not converge: {result.message}"  # type: ignore[union-attr]
        )


def validate_weight_bounds(
    n_assets: int,
    min_weight: float,
    max_weight: float,
    tol: float = 1e-12,
) -> None:
    """
    Validate whether per-asset bounds are feasible for the given asset count.

    The feasibility conditions for long-only fully-invested weights are:
      n_assets * min_weight <= 1
      n_assets * max_weight >= 1
    """
    if min_weight < 0.0:
        raise ValueError("min_weight must be >= 0.")
    if max_weight <= 0.0:
        raise ValueError("max_weight must be > 0.")
    if min_weight > max_weight:
        raise ValueError("min_weight cannot be greater than max_weight.")
    if n_assets * min_weight > 1.0 + tol:
        raise ValueError(
            f"Infeasible bounds: {n_assets} * min_weight ({min_weight:.2%}) > 100%."
        )
    if n_assets * max_weight < 1.0 - tol:
        raise ValueError(
            f"Infeasible bounds: {n_assets} * max_weight ({max_weight:.2%}) < 100%."
        )


def apply_weight_bounds(
    weights: np.ndarray,
    min_weight: float = MIN_WEIGHT,
    max_weight: float = MAX_WEIGHT,
    max_iter: int = 100,
) -> np.ndarray:
    """
    Enforce per-asset lower/upper bounds while preserving weight preferences.

    This function projects a raw weight vector into a feasible bounded simplex:
      - each weight in [min_weight, max_weight]
      - all weights non-negative
      - total sum equals 1

    The projection uses proportional redistribution with iterative clipping:
      1) assign the lower bound to every asset
      2) distribute remaining mass in proportion to the original weight signal
      3) clip assets that hit max_weight and redistribute leftover mass
    """
    raw = np.asarray(weights, dtype=float).copy()
    # Normalize the input to a flat float vector before doing any feasibility
    # checks or redistribution.
    if raw.ndim != 1:
        raise ValueError("weights must be a 1D vector.")

    n_assets = raw.shape[0]
    validate_weight_bounds(n_assets, min_weight, max_weight)

    # Use the raw optimizer output as preference weights. Invalid values are
    # treated as zero so a numerical glitch does not break the allocation pass.
    pref = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)
    pref = np.maximum(pref, 0.0)
    if pref.sum() <= 1e-12:
        # Fall back to equal preference if the optimizer returned an unusable
        # vector; the bounds projection should still produce a valid portfolio.
        pref = np.ones(n_assets) / n_assets
    else:
        pref /= pref.sum()

    bounded = np.full(n_assets, min_weight, dtype=float)
    remaining = 1.0 - n_assets * min_weight
    if remaining <= 1e-12:
        return bounded

    capacity = np.full(n_assets, max_weight - min_weight, dtype=float)
    # `active` tracks the indices still eligible to receive additional weight.
    active = [idx for idx in range(n_assets) if capacity[idx] > 1e-12]

    for _ in range(max_iter):
        if remaining <= 1e-12 or not active:
            break

        active_arr = np.array(active, dtype=int)
        active_pref = pref[active_arr]
        # `denom` is the total remaining preference mass over still-active
        # assets only.
        denom = active_pref.sum()

        if denom <= 1e-12:
            tentative = np.full(
                len(active_arr), remaining / len(active_arr), dtype=float
            )
        else:
            tentative = remaining * active_pref / denom

        overflow = tentative - capacity[active_arr]
        hit_mask = overflow > 1e-12

        if hit_mask.any():
            hit_indices = active_arr[hit_mask]
            for idx in hit_indices:
                # Lock capped assets in place, then redistribute only across the
                # remaining names that still have spare capacity.
                add_amt = capacity[idx]
                bounded[idx] += add_amt
                remaining -= add_amt
                capacity[idx] = 0.0
            active = [idx for idx in active if capacity[idx] > 1e-12]
            continue

        bounded[active_arr] += tentative
        remaining = 0.0
        break

    if remaining > 1e-8:
        raise ValueError(
            "Weight bound projection did not converge. "
            "Try less restrictive min/max bounds."
        )

    bounded = np.clip(bounded, min_weight, max_weight)
    bounded /= bounded.sum()
    return bounded


def apply_cap(weights: np.ndarray, cap: float, max_iter: int = 50) -> np.ndarray:
    """
    Iteratively clip overweight positions and redistribute excess to uncapped assets.

    Parameters
    ----------
    weights : np.ndarray
        Raw weight vector that should sum to approximately 1.
    cap : float
        Maximum allowed per-position weight.
    max_iter : int, default 50
        Safety bound on redistribution iterations.

    Returns
    -------
    np.ndarray
        Capped, non-negative weights summing to 1.
    """
    # A pure cap is just the general bounded-simplex projection with a zero
    # lower bound.
    return apply_weight_bounds(
        weights=weights,
        min_weight=0.0,
        max_weight=cap,
        max_iter=max_iter,
    )
