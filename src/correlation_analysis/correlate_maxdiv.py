"""
correlate_maxdiv.py
-------------------
Select N_SELECT ETFs by greedily maximising the equal-weight Diversification
Ratio (DR) of the growing basket.

Method: Maximum Diversification Ratio (greedy forward selection)
----------------------------------------------------------------
The Diversification Ratio (Choueifaty & Coignard, 2008) measures how much
portfolio-level volatility is reduced relative to the simple average of
individual asset volatilities:

    DR = (sum of individual vols) / (portfolio vol)
       = (w^T * sigma) / sqrt(w^T * Sigma * w)

Under equal weights w = 1/N, this simplifies to:

    DR_EW = mean(sigma_i) / sqrt((1/N^2) * 1^T Sigma 1)

DR = 1 means the assets are perfectly correlated (no diversification benefit).
DR > 1 means there is a diversification benefit. Higher is better.

Unlike the other selection methods:
  - Ward / K-Medoids group assets by similarity, then pick representatives.
  - Greedy Maximin maximises the minimum pairwise distance (geometry only).

This method directly optimises a portfolio-level objective: it asks "which ETF,
when added to my current basket under equal weighting, produces the largest
diversification benefit?" This is the most financially motivated selection
criterion because it accounts for the full covariance structure, not just
pairwise distances.

Algorithm
---------
1. Seed with the required anchor ETFs.
2. For each remaining slot:
   a. For every candidate c not yet selected, compute the DR of the current
      basket + c, all under equal weights.
   b. Pick the candidate that gives the highest DR.
3. Record the marginal DR at each step (useful for deciding how many ETFs add
   meaningful diversification).

Computational note: the inner loop recomputes DR for n_candidates trial
baskets per step, for n_steps steps. For ~300 candidates and 30 selections,
this is ~300 * 30 = 9000 small matrix operations (each on N x N matrices
with N <= 30). This runs in well under a second.

Reference
---------
Choueifaty, Y. & Coignard, Y. (2008). "Toward Maximum Diversification."
Journal of Portfolio Management, 35(1), 40-51.

Pipeline
--------
1. Load candidates, drop tickers that started after the full-history cutoff.
2. Fetch daily closes from ClickHouse.
3. Build log-return matrix, apply coverage filter.
4. Compute Spearman correlation and signed distance matrix.
5. Compute sample covariance matrix from log returns.
6. Run greedy max-DR selection.
7. Compute per-ETF stats for the selected set.
8. Save outputs.

Outputs
-------
outputs/correlation_analysis/selected_maxdiv.csv           -- N_SELECT ETFs with stats
outputs/correlation_analysis/heatmap_maxdiv.png            -- correlation heatmap
outputs/correlation_analysis/maxdiv_marginal_dr.png        -- marginal DR curve
"""

import pathlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from . import correlate_utils as utils
except ImportError:  # pragma: no cover - script execution fallback
    import correlate_utils as utils

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
OUT_CSV = utils.OUTPUT_DIR / "selected_maxdiv.csv"
OUT_HEATMAP = utils.OUTPUT_DIR / "heatmap_maxdiv.png"
OUT_CURVE = utils.OUTPUT_DIR / "maxdiv_marginal_dr.png"


# ---------------------------------------------------------------------------
# Diversification ratio helpers
# ---------------------------------------------------------------------------


def _equal_weight_dr(cov_sub: np.ndarray, vols_sub: np.ndarray) -> float:
    """
    Compute the equal-weight diversification ratio for a subset of assets.

    Called by: select_by_maxdiv()

    Parameters
    ----------
    cov_sub  : (k, k) covariance matrix of the k selected assets
    vols_sub : (k,) individual annualised volatilities of the k assets

    Returns
    -------
    float
        DR = mean(sigma_i) / sigma_portfolio_EW.
        Returns 1.0 if the portfolio vol is zero or near-zero (degenerate).
    """
    n = len(vols_sub)
    # Equal weights
    w = np.ones(n) / n
    # Portfolio volatility: sqrt(w^T Sigma w)
    port_var = w @ cov_sub @ w
    port_vol = np.sqrt(max(port_var, 0.0))
    if port_vol < 1e-14:
        return 1.0
    # DR = mean(sigma_i) / sigma_portfolio
    avg_vol = vols_sub.mean()
    return avg_vol / port_vol


# ---------------------------------------------------------------------------
# Greedy max-DR selection
# ---------------------------------------------------------------------------


def select_by_maxdiv(
    log_ret: pd.DataFrame,
    candidates: pd.DataFrame,
    n_select: int = utils.N_SELECT,
    anchor_tickers: list[str] | None = None,
) -> tuple[list[str], list[float]]:
    """
    Greedily select ETFs to maximise the equal-weight diversification ratio.

    At each step, the candidate whose addition produces the highest DR for the
    new (N+1)-asset basket under equal weights is selected. This considers the
    full covariance structure, not just pairwise distances.

    Parameters
    ----------
    log_ret    : daily log-return matrix (dates x symbols), columns are tickers
    candidates : DataFrame with at least columns 'ticker' and 'vol_combined'
    n_select   : int, default utils.N_SELECT
                 Number of ETFs to select.
    anchor_tickers : list[str] | None, default None
                 Required anchor tickers seeded before greedy expansion. When
                 None, falls back to the module-level constant ``ANCHOR_TICKERS``.

    Returns
    -------
    selected : list[str]
        Ordered list of selected tickers (anchors first, then greedy picks).
    marginal_drs : list[float]
        The DR of the basket after each selection step. Length = len(selected).
        marginal_drs[0] is NaN (only one asset), marginal_drs[k] is the DR
        of the basket after step k+1.
    """
    symbols = log_ret.columns.tolist()
    symbol_set = set(symbols)
    # Resolve anchors once
    anchors = utils.resolve_anchor_tickers(
        anchor_tickers, symbols, "max diversification survivors"
    )

    # Compute the sample covariance matrix (daily, not annualised -- the DR
    # ratio cancels the annualisation factor, so it doesn't matter)
    cov_full = log_ret.fillna(log_ret.median()).cov().values
    # Individual daily volatilities (standard deviations)
    vols = np.sqrt(np.maximum(np.diag(cov_full), 0.0))

    # Symbol-to-index mapping
    # This lets the selection loop move cheaply between ticker labels and the
    # covariance/vol arrays.
    sym_to_idx = {s: i for i, s in enumerate(symbols)}

    # Volume tiebreaker lookup
    vol_lookup = dict(
        zip(
            candidates["ticker"].astype(str),
            candidates["vol_combined"],
            strict=False,
        )
    )

    # Seed with anchors
    selected_syms: list[str] = []
    selected_idx: list[int] = []
    for anchor in anchors:
        if anchor in symbol_set and anchor not in selected_syms:
            selected_syms.append(anchor)
            selected_idx.append(sym_to_idx[anchor])
    if len(selected_syms) < len(anchors):
        missing = set(anchors) - set(selected_syms)
        print(f"  WARNING: anchors missing from return matrix: {missing}")

    # DR after adding each anchor
    marginal_drs: list[float] = []
    for step in range(len(selected_idx)):
        if step == 0:
            marginal_drs.append(float("nan"))
        else:
            idx_arr = np.array(selected_idx[: step + 1])
            sub_cov = cov_full[np.ix_(idx_arr, idx_arr)]
            sub_vols = vols[idx_arr]
            marginal_drs.append(_equal_weight_dr(sub_cov, sub_vols))

    print(f"  Anchors seeded: {', '.join(selected_syms)}")

    # --- Greedy forward selection ---
    selected_set = set(selected_idx)
    candidate_indices = [
        sym_to_idx[s] for s in symbols if sym_to_idx[s] not in selected_set
    ]

    while len(selected_idx) < min(n_select, len(symbols)):
        best_dr = -np.inf
        best_idx = -1
        best_ties: list[int] = []

        # Current basket indices as array (for slicing)
        current_arr = np.array(selected_idx)

        for c_idx in candidate_indices:
            # Trial basket = current + candidate
            trial_arr = np.append(current_arr, c_idx)
            sub_cov = cov_full[np.ix_(trial_arr, trial_arr)]
            sub_vols = vols[trial_arr]
            # Score each candidate on the full basket-level DR, not just on its
            # pairwise relationship with the current holdings.
            dr = _equal_weight_dr(sub_cov, sub_vols)

            if dr > best_dr + 1e-12:
                best_dr = dr
                best_idx = c_idx
                best_ties = [c_idx]
            elif abs(dr - best_dr) < 1e-12:
                best_ties.append(c_idx)

        # Tiebreak by vol_combined (prefer more liquid)
        if len(best_ties) > 1:
            best_idx = max(
                best_ties,
                key=lambda idx: vol_lookup.get(symbols[idx], 0.0),
            )

        # Commit the pick
        selected_idx.append(best_idx)
        selected_set.add(best_idx)
        selected_syms.append(symbols[best_idx])
        # Persist the achieved basket DR after the new name is included so the
        # output curve can be read as "portfolio quality vs basket size".
        marginal_drs.append(best_dr)

        # Remove from candidates
        candidate_indices = [i for i in candidate_indices if i != best_idx]

        step_num = len(selected_idx)
        if step_num <= 10 or step_num % 5 == 0:
            # Print densely at the start, then only every fifth step once the
            # basket is large enough that the log would otherwise get noisy.
            print(f"  Step {step_num:>3d}: {symbols[best_idx]:<6s}  DR = {best_dr:.4f}")

    print(f"Max-DR selected {len(selected_syms)} ETFs.")
    return selected_syms, marginal_drs


# ---------------------------------------------------------------------------
# Marginal DR curve
# ---------------------------------------------------------------------------


def save_marginal_dr_curve(
    selected: list[str],
    marginal_drs: list[float],
    output_path: pathlib.Path,
) -> None:
    """
    Save a line chart showing how the diversification ratio grows as ETFs
    are added to the basket.

    Called by: main()

    Parameters
    ----------
    selected    : ordered list of selected tickers
    marginal_drs : DR value after each step (first entry is NaN)
    output_path : where to write the PNG
    """
    # Skip the first value (NaN for single-asset basket)
    steps = list(range(2, len(marginal_drs) + 1))
    dr_values = marginal_drs[1:]

    fig, ax = plt.subplots(figsize=(10, 4), constrained_layout=True)
    ax.plot(steps, dr_values, marker="o", linewidth=1.8, color="#2f4b7c")
    ax.set_title("Greedy Max-DR: diversification ratio vs basket size")
    ax.set_xlabel("Number of ETFs in basket")
    ax.set_ylabel("Diversification Ratio (higher = better)")
    ax.grid(alpha=0.3)

    # Annotate the flattening zone -- when marginal improvement < 1%
    for i in range(1, len(dr_values)):
        if dr_values[i] / max(dr_values[i - 1], 1e-12) - 1.0 < 0.01:
            ax.axvline(
                steps[i],
                color="red",
                linestyle="--",
                alpha=0.5,
                label=f"<1% marginal gain from step {steps[i]}",
            )
            ax.legend(fontsize=9)
            break

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Marginal DR curve saved -> {output_path}")


# ---------------------------------------------------------------------------
# Standalone pipeline
# ---------------------------------------------------------------------------
