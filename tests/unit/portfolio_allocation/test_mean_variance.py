"""Unit tests for conventional mean-variance portfolio allocation."""

import numpy as np
import pytest

import portfolio_allocation as methods


def _two_asset_moments() -> tuple[np.ndarray, np.ndarray]:
    """Return daily moments for a high-return risky and low-return safe asset.

    Returns
    -------
    tuple[numpy.ndarray, numpy.ndarray]
        Daily mean log returns with shape ``(2,)`` and daily covariance with
        shape ``(2, 2)``.
    """
    mean_ret = np.array([0.0010, 0.0002], dtype=float)
    cov = np.array([[0.0004, 0.0], [0.0, 0.000025]], dtype=float)
    return mean_ret, cov


def test_mean_variance_returns_feasible_weights() -> None:
    """Return long-only, fully invested weights within the requested cap."""
    mean_ret, cov = _two_asset_moments()

    weights = methods.mean_variance(
        mean_ret,
        cov,
        risk_aversion=3.0,
        max_weight=0.80,
    )

    assert weights.shape == (2,)
    assert weights.sum() == pytest.approx(1.0)
    assert np.all(weights >= 0.0)
    assert np.all(weights <= 0.80 + 1e-12)


def test_higher_risk_aversion_reduces_portfolio_variance() -> None:
    """Allocate to a lower-variance portfolio when risk aversion increases."""
    mean_ret, cov = _two_asset_moments()

    return_seeking = methods.mean_variance(
        mean_ret,
        cov,
        risk_aversion=0.1,
        max_weight=1.0,
    )
    risk_averse = methods.mean_variance(
        mean_ret,
        cov,
        risk_aversion=20.0,
        max_weight=1.0,
    )

    return_seeking_variance = float(return_seeking @ cov @ return_seeking)
    risk_averse_variance = float(risk_averse @ cov @ risk_averse)
    assert risk_averse_variance < return_seeking_variance


@pytest.mark.parametrize("risk_aversion", [0.0, -1.0, np.nan, np.inf])
def test_mean_variance_rejects_invalid_risk_aversion(risk_aversion: float) -> None:
    """Reject risk-aversion coefficients outside the positive finite range."""
    mean_ret, cov = _two_asset_moments()

    with pytest.raises(ValueError, match="risk_aversion must be finite and > 0"):
        methods.mean_variance(mean_ret, cov, risk_aversion=risk_aversion)


def test_mean_variance_is_registered_as_a_classic_strategy() -> None:
    """Expose mean variance through the public strategy registries."""
    assert "mean_variance" in methods.CLASSIC_STRATEGY_NAMES
    assert methods.STRATEGY_FUNCTIONS["mean_variance"] is methods.mean_variance
