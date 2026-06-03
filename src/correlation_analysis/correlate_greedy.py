"""
correlate_greedy.py
-------------------
Select N_SELECT ETFs from the volume-screened universe using a Greedy Maximin
(furthest-first) algorithm on a signed Spearman correlation distance matrix.

Method: Greedy Maximin (furthest-first traversal)
--------------------------------------------------
The algorithm directly optimises the objective we care about: at each step,
we add the ETF that maximises the minimum distance to all already-selected ETFs.

Formally, let S be the current selected set. At step k+1 we pick:

    next = argmax_{c not in S}  min_{s in S}  D(c, s)

where D(i, j) = sqrt(0.5 * (1 - r(i, j))) is the signed Spearman distance.

This is the "p-dispersion" or "Maximin" heuristic. It does not guarantee the
globally optimal set (that is NP-hard), but it is the best known polynomial-
time greedy approximation and gives excellent practical results.

Tiebreaker: if two candidates have identical min-distance scores (very rare),
we prefer the one with higher vol_combined (more liquid).

Seed: the algorithm is seeded with the required anchor tickers. Those
anchor names are hard constraints and are always part of the
final basket before the maximin expansion begins.

Pipeline
--------
1. Load candidates (volume_screen.csv), drop tickers that started after the
   full-history cutoff.
2. Fetch daily closes from ClickHouse (argMax per day, robust to missing last bar).
3. Build log-return matrix, apply coverage filter (>= 80% of trading days).
4. Compute Spearman correlation matrix.
5. Compute signed distance D = sqrt(0.5*(1-r)).
6. Run Greedy Maximin:
   a. Seed with the required anchors.
   b. Maintain a min_dist vector: for each candidate c, min_dist[c] is the
      minimum distance from c to any already-selected ticker.
   c. Each step: pick argmax(min_dist), update min_dist vector.
7. Compute per-ETF stats for the selected set.
8. Save outputs/correlation_analysis/selected_greedy.csv and
   outputs/correlation_analysis/heatmap_greedy.png.
9. Save outputs/correlation_analysis/greedy_marginal_diversity.png -- the
   marginal minimum distance added at each step. When this curve flattens,
   further picks add little diversity -- useful for deciding how many ETFs you
   actually need.

Outputs
-------
outputs/correlation_analysis/selected_greedy.csv           -- N_SELECT ETFs with performance stats
outputs/correlation_analysis/heatmap_greedy.png            -- correlation heatmap of selected ETFs
outputs/correlation_analysis/greedy_marginal_diversity.png -- marginal diversity curve
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
OUT_CSV = utils.OUTPUT_DIR / "selected_greedy.csv"
OUT_HEATMAP = utils.OUTPUT_DIR / "heatmap_greedy.png"
OUT_CURVE = utils.OUTPUT_DIR / "greedy_marginal_diversity.png"


# ---------------------------------------------------------------------------
# Greedy Maximin selection logic
# ---------------------------------------------------------------------------


def select_by_greedy(
    dist: pd.DataFrame,
    candidates: pd.DataFrame,
    n_select: int = utils.N_SELECT,
    anchor_tickers: list[str] | None = None,
) -> tuple[list[str], list[float]]:
    """
    Run the Greedy Maximin algorithm to select ``n_select`` maximally diverse ETFs.

    At each step, the ETF that is furthest (in signed distance) from the
    closest already-selected ETF is added to the selected set. This directly
    maximises the minimum pairwise distance in the selected set.

    The algorithm maintains a min_dist vector of length n_candidates:
      min_dist[c] = min over all selected s of D(c, s)

    This makes each greedy step O(n_candidates) rather than O(n_candidates^2)
    by updating only the new distances introduced by the most recently added
    ETF, instead of recomputing all pairwise minimums from scratch.

    Parameters
    ----------
    dist       : signed distance matrix (n_symbols x n_symbols).
                 Index and columns = symbol strings.
    candidates : DataFrame with columns [ticker, vol_combined, ...].
                 Must be sorted descending by vol_combined.
    n_select   : int, default utils.N_SELECT
                 Target number of ETFs to select.
    anchor_tickers : list[str] | None, default None
                 Required anchor tickers seeded before greedy expansion. When
                 None, falls back to the module-level constant ``ANCHOR_TICKERS``.

    Returns
    -------
    selected      : list of n_select ticker strings in selection order
    marginal_mins : list of n_select floats -- the min_dist value at the time
                    each ETF was added. selected[0] has no meaningful value
                    (seeded), so marginal_mins[0] = NaN.
    """
    symbols = dist.index.tolist()
    n = len(symbols)
    n_select = min(n_select, n)
    # Resolve anchors once; used for seeding and the final anchor-first ordering
    anchors = utils.resolve_anchor_tickers(
        anchor_tickers, symbols, "greedy maximin survivors"
    )

    sym_to_idx = {s: i for i, s in enumerate(symbols)}

    # Distance matrix as a numpy array for fast column/row access
    D = dist.values  # shape (n, n)

    # vol_combined lookup for tiebreaking when min-distance scores tie
    vol_map = candidates.set_index("ticker")["vol_combined"].to_dict()

    anchor_tickers_resolved = anchors
    # `seed_tickers` is the fixed starting basket before any greedy expansion.
    seed_tickers = anchor_tickers_resolved[:n_select]
    selected_idx = [sym_to_idx[ticker] for ticker in seed_tickers]
    selected_tickers = seed_tickers.copy()

    # Initialise min_dist against the current anchor set. For each candidate,
    # min_dist[i] is the minimum distance to any already-selected anchor.
    anchor_distances = np.column_stack([D[:, idx] for idx in selected_idx])
    min_dist = anchor_distances.min(axis=1)

    marginal_mins: list[float] = [float("nan")]
    for position in range(1, len(selected_idx)):
        current_idx = selected_idx[position]
        previous_indices = selected_idx[:position]
        # For seeded anchors, record the distance to the closest earlier anchor
        # so the output curve has a consistent one-value-per-selection shape.
        anchor_min_distance = float(D[current_idx, previous_indices].min())
        marginal_mins.append(anchor_min_distance)

    print(f"Greedy Maximin: fixed anchors = {', '.join(seed_tickers)}")
    print(f"Selecting {n_select} ETFs ...")

    if len(selected_idx) >= n_select:
        return selected_tickers, marginal_mins[:n_select]

    for step in range(len(selected_idx), n_select):
        # --- Find the candidate with the highest min_dist ---
        # Exclude already-selected indices by setting their min_dist to -inf
        # so they are never re-selected.
        # We do this non-destructively using a masked maximum.
        min_dist_masked = min_dist.copy()
        min_dist_masked[selected_idx] = -np.inf

        # argmax gives the index of the best remaining candidate.
        # If there are ties in min_dist_masked, we break by vol_combined.
        best_val = min_dist_masked.max()

        # Find all indices tied at the best value (within floating point tol)
        tied_indices = np.where(np.abs(min_dist_masked - best_val) < 1e-12)[0].tolist()

        if len(tied_indices) == 1:
            # No tie -- take the unique best
            next_idx = tied_indices[0]
        else:
            # Tie: pick the tied candidate with the highest vol_combined
            next_idx = max(
                tied_indices,
                key=lambda i: vol_map.get(symbols[i], 0.0),
            )

        # Convert the chosen matrix index back to the public ticker label before
        # appending to the human-readable selection list.
        next_ticker = symbols[next_idx]
        selected_idx.append(next_idx)
        selected_tickers.append(next_ticker)
        marginal_mins.append(float(best_val))

        # --- Update min_dist ---
        # For each remaining candidate c, min_dist[c] may decrease now that
        # next_idx is in the selected set. Specifically:
        #   new_min_dist[c] = min(min_dist[c], D[c, next_idx])
        # We update in-place -- this is the key efficiency trick.
        min_dist = np.minimum(min_dist, D[:, next_idx])

        print(
            f"  Step {step + 1:2d}: added {next_ticker:8s}  "
            f"(marginal min-dist = {best_val:.4f})"
        )

    return utils.build_anchor_first_selection(
        # Re-run the anchor-first helper so any future change to the seeding
        # logic still guarantees the public output contract.
        ranked_tickers=selected_tickers,
        available_tickers=symbols,
        n_select=n_select,
        anchor_tickers=anchors,
    ), marginal_mins


def save_marginal_diversity_curve(
    selected: list[str],
    marginal_mins: list[float],
    output_path: pathlib.Path,
) -> None:
    """
    Save a line chart showing the marginal minimum distance added at each
    greedy selection step.

    The y-axis shows the minimum distance from the newly added ETF to the
    closest already-selected ETF (the "marginal diversity contribution").
    When this curve flattens, adding more ETFs provides diminishing returns
    in diversification -- this is a useful visual guide for deciding how
    many ETFs to actually hold.

    Parameters
    ----------
    selected      : list of ticker strings in selection order
    marginal_mins : list of min_dist values at selection time (index 0 = NaN)
    output_path   : where to save the PNG
    """
    # Step indices 1..N_SELECT (skip the seed at index 0 which has NaN)
    steps = list(range(2, len(selected) + 1))
    values = marginal_mins[1:]  # drop the NaN seed entry

    fig, ax = plt.subplots(figsize=(12, 5))

    ax.plot(steps, values, marker="o", markersize=5, linewidth=1.8, color="steelblue")

    # Annotate the last few tickers for context
    for i, (step, val, ticker) in enumerate(
        zip(steps[-5:], values[-5:], selected[-5:])
    ):
        ax.annotate(
            ticker,
            xy=(step, val),
            xytext=(step - 0.5, val + 0.005),
            fontsize=7,
            color="dimgray",
        )

    ax.set_xlabel("Selection step (ETF #)", fontsize=11)
    ax.set_ylabel("Marginal min-distance to selected set", fontsize=11)
    ax.set_title(
        "Greedy Maximin: marginal diversity added at each step\n"
        "(flattening curve = diminishing diversification returns)",
        fontsize=12,
    )
    ax.grid(True, linestyle="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Marginal diversity curve saved -> {output_path}")
