# GUIDE_correlation_analysis.md

## Part 1 -- Conceptual Explanation

### Purpose and problem statement

This folder is the diversified-universe engine of the project. It starts from
the liquidity-screened ETF universe and asks a harder question:

Which ETFs add distinct risk exposures rather than duplicating one another?

It answers that question by building one common return/correlation pipeline and
running four different selection methods on top of it.

### Spine of the logic

1. Load `data/raw/volume_screen.csv`.
2. Apply the full-history screen and drop ETFs whose `start_date` is later
   than the active analysis start date. In the notebook this is driven by the
   same `ANALYSIS_START` constant that slices the price history.
3. Fetch daily closes from ClickHouse with `argMax(close, ts)`, or fall back to
   the shared parquet when ClickHouse credentials are unavailable.
4. Pivot into a wide price matrix and compute daily or weekly log returns.
5. Apply a minimum coverage rule:
   - `MIN_COVERAGE = 0.80`
6. Apply the notebook-only manual blacklist when configured:
   - `BLACKLIST_TICKERS` in the notebook currently excludes
     `GLD`, `ASHR`, `ELV`, `KSA`, `EWZ`, `UGL`, `VNM`, and `ECH`
     before any statistical hurdle is evaluated.
7. Apply the shared total-return hurdle:
   - `MIN_TOTAL_RETURN_HURDLE` in the notebook controls this as a cumulative
     log-return threshold —
     passed as `min_total_return` to `apply_shared_selection_filters()`.
   - `MIN_SELECTION_TOTAL_RETURN = 0.1823` in `correlate_utils.py` is the
     standalone-script default.
8. Apply the notebook-only average yearly return hurdle when configured:
   - `MIN_AVERAGE_YEARLY_RETURN` in the notebook (default `0.00`) removes ETFs
     whose mean calendar-year log return is negative.
9. Apply the volatility band filter:
   - `MIN_ANN_VOL` in the notebook (default `0.10`) removes cash/ultrashort ETFs.
   - `MAX_ANN_VOL` in the notebook (default `0.60`) removes leveraged/inverse products.
10. Compute the Spearman correlation matrix.
11. Transform correlation into a signed distance matrix.
12. Run one of four selection methods, each anchored on `VOO` and `VEA`:
   - Ward clustering
   - Greedy maximin
   - Anchored k-medoids
   - Maximum diversification ratio
13. Save method-specific CSVs and diagnostics.
14. Validate the matrix math and method invariants with synthetic data in
    `validate_selection_math.py`.

### Core formulas

For daily close price $P_t$:

$$
r_t = \ln\left(\frac{P_t}{P_{t-1}}\right)
$$

For ETFs $i$ and $j$, let $\rho_{ij}$ be Spearman rank correlation. The project
uses:

$$
D_{ij} = \sqrt{0.5 \cdot (1 - \rho_{ij})}
$$

Interpretation:

- $\rho = 1 \Rightarrow D = 0$
- $\rho = 0 \Rightarrow D \approx 0.707$
- $\rho = -1 \Rightarrow D = 1$

This signed distance is the central design choice in the folder. It ensures
negatively correlated assets are treated as far apart, which is what a
diversification search should want.

For wealth path $W_t = \exp\left(\sum_{k \le t} r_k\right)$, drawdown is:

$$
\text{drawdown}_t = 1 - \frac{W_t}{\max_{k \le t} W_k}
$$

### Method-level logic

Ward clustering:
Keep `VOO` and `VEA` inside the full signed-distance matrix, cut the
full survivor universe into 15 Ward clusters, and take one representative per
cluster. If a cluster contains `VOO` or `VEA`, that anchor becomes the
cluster representative. Otherwise the representative is the cluster medoid:
the ETF whose average signed distance to the other members of that cluster is
smallest.

Why that creates a low-correlation basket:
If two ETFs are highly positively correlated, their signed distance is small,
so Ward tends to place them in the same cluster. When the dendrogram is cut
into `N_SELECT` clusters, the method keeps only one representative from each
cluster. That removes near-duplicates such as multiple broad-equity ETFs that
move together and forces the final basket to spread across distinct correlation
groups. The method therefore lowers within-basket correlation by construction,
even though it does not compute portfolio weights.

Plain-language example:
If `SPY`, `IVV`, and `VOO` all move almost identically, Ward will usually place
them in the same cluster because their pairwise distances are close to zero.
The cluster still keeps `VOO` as its representative, even if `SPY` or `IVV`
trade more volume. In a non-anchor cluster such as `AGG`, `BND`, and `LQD`,
the method keeps the ETF closest to the middle of that cluster's distance
geometry, not the one with the largest turnover. Repeating that logic across
all 15 clusters produces a
basket that spans different risk groups rather than one crowded theme.

Greedy maximin:
Start from `VOO` and `VEA`, then repeatedly add the ETF whose minimum
distance to the selected set is largest.

Anchored k-medoids:
Treat `VOO` and `VEA` as fixed medoids, then optimize the remaining
medoids directly on the signed distance matrix.

Maximum diversification ratio:
Greedily add the ETF that maximises the equal-weight diversification ratio
of the growing basket. Unlike the other methods, this directly optimises a
portfolio-level diversification metric using the full covariance structure
rather than pairwise distances or cluster membership. Reference: Choueifaty
& Coignard (2008), "Toward Maximum Diversification."

### Inputs and outputs

Inputs:

- `data/raw/volume_screen.csv`
- ClickHouse minute bars from `firstrate.etfs`
- `data/raw/daily_close_volume_screened_2016_2025.parquet` for the notebook path
  and for local access to the full top-500 screened universe

Primary outputs:

- `outputs/correlation_analysis/selected_ward.csv`
- `outputs/correlation_analysis/selected_greedy.csv`
- `outputs/correlation_analysis/selected_pca.csv`
- `outputs/correlation_analysis/selected_kmedoids.csv`
- `outputs/correlation_analysis/selected_maxdiv.csv`
- `outputs/correlation_analysis/heatmap_*.png`
- `outputs/correlation_analysis/dendrogram_ward.png`
- `outputs/correlation_analysis/greedy_marginal_diversity.png`
- `outputs/correlation_analysis/pca_variance_explained.png`
- `outputs/correlation_analysis/pca_loadings.csv`
- `outputs/correlation_analysis/heatmap_kmedoids.png`

### Concrete data example

Method CSVs share a common core schema:

| ticker | ann_return | ann_vol | sharpe | max_drawdown | avg_abs_corr | vol_combined | start_date |
|---|---:|---:|---:|---:|---:|---:|---|
| `GLD` | 0.1343 | 0.1487 | 0.5668 | 0.2180 | 0.1474 | 4,852,932,226 | `2004-11-18` |

### Edge cases and invariants

- ETFs that start after `HISTORY_START` are dropped before any return analysis.
- ETFs with insufficient data coverage are dropped before correlation
  computation.
- If fewer than `N_SELECT = 30` symbols survive, the methods proceed with the
  survivors rather than failing.
- Method CSVs should use the same global return statistics because they are all
  computed from the same return matrix.
- Selection hurdles are interpreted in log-return units, even if older prose or
  artifacts still use percentage-style labels.

## Part 2 -- Folder Tree and File Map

```text
correlation_analysis/
├── GUIDE_correlation_analysis.md   -- This folder guide.
├── __init__.py                     -- Package marker.
├── correlate_utils.py              -- Shared data-loading, return-matrix, stats, and plotting utilities.
├── correlate_ward.py               -- Ward clustering selection and dendrogram export.
├── correlate_greedy.py             -- Greedy maximin selection and marginal-diversity chart.
├── correlate_pca.py                -- Standalone PCA factor-representation experiment.
├── correlate_kmedoids.py           -- Anchored k-medoids representative selection.
├── correlate_maxdiv.py             -- Greedy max diversification ratio selection.
├── validate_selection_math.py      -- Synthetic-data validation suite for selection math.
├── outputs/                        -- Method CSVs and diagnostics.
└── explore_selection_methods.ipynb -- Notebook focused on greedy, k-medoids, and MaxDiv comparisons.
```

## Part 3 -- Code Reference

### `correlate_utils.py`

What it does:
Defines the shared constants, data loading, return-matrix construction,
correlation/distance computation, stat computation, and common output writers.

Key constants:

- `N_SELECT`
- `HISTORY_START`
- `HISTORY_END`
- `MIN_COVERAGE`
- `RISK_FREE`
- `MIN_ANN_VOL`
- `MAX_ANN_VOL`

Key functions:

- `build_client()`
- `load_daily_closes()`
- `load_candidates()`
- `fetch_daily_closes()`
- `load_daily_closes_from_parquet()`
- `build_return_matrix()`
- `compute_spearman_corr()`
- `compute_distance_matrix()`
- `apply_shared_selection_filters()`
- `compute_stats()`
- `save_heatmap()`
- `save_results()`

### `correlate_ward.py`

What it does:
Runs Ward linkage on the signed distance matrix, picks one ETF per cluster, and
saves the selected ETF stats plus the full dendrogram.

Key functions:

- `select_by_ward()`
- `save_dendrogram()`
- `main()`

Run:

- `uv run python correlation_analysis/correlate_ward.py`

### `correlate_greedy.py`

What it does:
Runs the furthest-first maximin heuristic and saves both the selected ETF CSV
and the marginal-diversity curve.

Key functions:

- `select_by_greedy()`
- `save_marginal_diversity_curve()`
- `main()`

Run:

- `uv run python correlation_analysis/correlate_greedy.py`

### `correlate_pca.py`

What it does:
Runs a standalone PCA factor-representation experiment on the shared survivor
universe, keeping the required anchors first and then selecting the highest
absolute-loading ETF for each remaining principal-component slot.

This script is retained for direct experimentation, but it is not part of the
active notebook workflow.

Key functions:

- `run_pca()`
- `select_by_pca()`
- `save_scree_plot()`
- `save_loadings_csv()`
- `main()`

Run:

- `uv run python correlation_analysis/correlate_pca.py`

### `correlate_maxdiv.py`

What it does:
Greedily adds ETFs that maximise the equal-weight diversification ratio
of the growing basket. Uses the full covariance structure rather than
pairwise distances.

Key functions:

- `select_by_maxdiv()`
- `main()`

Run:

- `uv run python correlation_analysis/correlate_maxdiv.py`

### `correlate_kmedoids.py`

What it does:
Runs anchored k-medoids on the signed distance matrix, forcing `VOO`, `VEA`,
to remain in the basket while optimizing the remaining medoid
representatives.

Key functions:

- `select_by_kmedoids()`
- `main()`

Run:

- `uv run python correlation_analysis/correlate_kmedoids.py`

### `validate_selection_math.py`

What it does:
Checks matrix symmetry, bounds, selection count/uniqueness, anchor handling,
and diversification-quality sanity conditions on synthetic returns.

Run:

- `uv run python correlation_analysis/validate_selection_math.py`

### `explore_selection_methods.ipynb`

What it does:
Runs the notebook-focused selection methods from local artifacts without
requiring a live database query. The notebook is structured as shared
preprocessing followed by one Markdown-plus-code pair for greedy maximin,
anchored k-medoids, and maximum diversification ratio, then a final overlap
and summary cell. Ward and PCA remain available as standalone scripts but are
not executed inside the notebook. Each explanatory Markdown cell includes one
simple display equation so the method logic is visible before the code runs.

The setup cell defines ten tunable notebook constants and wires all of
them to the underlying filter and selector functions:

| Constant | Default | Controls |
|---|---|---|
| `TOP_N` | 30 | Basket size — passed as `n_select` to the three notebook selector functions. |
| `ANALYSIS_START` | `"20160101"` | Inclusive analysis-window start. Also used as the start-date eligibility cutoff, so ETFs that start after this date are dropped before return construction. |
| `ANALYSIS_END` | `"20251231"` | Inclusive analysis-window end used when slicing the local price history. |
| `ANCHOR_TICKERS` | `("VOO", "VEA")` | Required core holdings seeded before any method optimises. Passed to all filters and selectors. |
| `RETURN_FREQUENCY` | `"weekly"` | Return sampling frequency passed to `build_return_matrix()`, the pre-selection audit, and `compute_stats()`. Use `"weekly"` to resample to Friday closes. |
| `MIN_TOTAL_RETURN_HURDLE` | 0.20 | Cumulative log-return hurdle passed as `min_total_return` to the notebook filter sequence. |
| `MIN_AVERAGE_YEARLY_RETURN` | 0.00 | Mean calendar-year log-return hurdle applied after the total-return hurdle. |
| `MIN_ANN_VOL` | 0.10 | Minimum annualised volatility passed to `apply_shared_selection_filters()`. |
| `MAX_ANN_VOL` | 0.60 | Maximum annualised volatility passed to `apply_shared_selection_filters()`. |
| `BLACKLIST_TICKERS` | `["GLD", "ASHR", "ELV", "KSA", "EWZ", "UGL", "VNM", "ECH"]` | Manual exclusions applied before any statistical filter. |

All three notebook selector functions (`select_by_greedy`,
`select_by_kmedoids`, `select_by_maxdiv`) accept an explicit `n_select`
kwarg so the notebook constant actually takes effect rather than being
silently ignored.

The setup cell now also renders a pre-selection audit table with counts before
and after each hurdle for the manual blacklist, total-return hurdle,
average-yearly-return hurdle, minimum volatility hurdle, and maximum
volatility hurdle. That audit is notebook-only; the standalone scripts still
just print filter summaries.

The final notebook summary keeps one consensus table ranked by penalized
`average_rank`, not by `method_count`. A missing method rank is filled with
that method's `max_rank + 1`, which penalizes one-off picks while still using
the actual per-method ordering information.
