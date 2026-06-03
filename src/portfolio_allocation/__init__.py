"""
Portfolio allocation methods exposed at the package root.

This flattened layout matches the `correlation_analysis` folder: one module per
allocation method plus shared utilities in `allocation_utils.py`. Notebooks can
import methods directly from `portfolio_allocation`.
"""

from .hrp import hrp_weights
from .max_diversification import max_diversification
from .max_sharpe import max_sharpe
from .min_cvar import min_cvar
from .min_variance import min_variance
from .risk_parity import risk_parity

# Separate the strategies into "classic" versus "advanced" buckets so the CLI
# and notebooks can expose simpler defaults without hardcoding names twice.
CLASSIC_STRATEGY_NAMES = [
    "min_variance",
    "max_sharpe",
    "risk_parity",
    "max_diversification",
    "hrp",
]

ADVANCED_STRATEGY_NAMES = [
    "min_cvar",
]

ALL_STRATEGY_NAMES = CLASSIC_STRATEGY_NAMES + ADVANCED_STRATEGY_NAMES

# Central registry used by orchestration code and notebooks to look up a
# concrete optimizer from a stable strategy name.
STRATEGY_FUNCTIONS = {
    "min_variance": min_variance,
    "max_sharpe": max_sharpe,
    "risk_parity": risk_parity,
    "max_diversification": max_diversification,
    "hrp": hrp_weights,
    "min_cvar": min_cvar,
}

__all__ = [
    # Re-export the canonical strategy names so callers do not have to know the
    # individual module layout.
    "ADVANCED_STRATEGY_NAMES",
    "ALL_STRATEGY_NAMES",
    "CLASSIC_STRATEGY_NAMES",
    "STRATEGY_FUNCTIONS",
    "hrp_weights",
    "max_diversification",
    "max_sharpe",
    "min_cvar",
    "min_variance",
    "risk_parity",
]
