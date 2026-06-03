# GUIDE_portfolio_allocation.md

## Part 1 -- Conceptual Explanation

### Purpose and problem statement

This folder answers the weighting question for a basket that has already been
chosen by the user:

Given a fixed list of ETFs, how do different long-only allocation rules spread
capital across those names?

The current workflow is notebook-first. The notebook builds one return matrix
from the shared daily dataset, then calls the method modules in this folder
directly. There is no active orchestration script in the checked-in source
tree; the notebook is the main human-facing entrypoint.

### Spine of the logic

1. Choose a ticker list in the notebook.
2. Load daily closes through `correlation_analysis.correlate_utils`.
3. Build a daily log-return matrix for that basket.
4. Estimate sample mean returns, covariance, and the raw return panel.
5. Run several long-only weighting methods on the same inputs.
6. Project or cap weights into the same feasible bound regime when needed.
7. Compare the resulting weights with common in-sample summary statistics.

### Allocation methods

The active method modules in the folder are:

- equal weight, created directly in the notebook
- minimum variance
- maximum Sharpe
- risk parity
- maximum diversification
- Hierarchical Risk Parity, or HRP
- minimum Conditional Value at Risk, or minimum CVaR

### Portfolio math

For weights $w$, mean daily log-return vector $\mu$, covariance matrix
$\Sigma$, and annual risk-free rate $R_f$:

$$
R_{\text{ann}} = 252 \cdot w^\top \mu
$$

$$
\sigma_{\text{ann}} = \sqrt{252 \cdot w^\top \Sigma w}
$$

$$
\text{Sharpe} = \frac{R_{\text{ann}} - R_f}{\sigma_{\text{ann}}}
$$

The notebook also reports the diversification ratio:

$$
\text{DR} = \frac{w^\top \sigma}{\sqrt{w^\top \Sigma w}}
$$

where $\sigma$ is the vector of standalone asset volatilities,
$\sigma_i = \sqrt{\Sigma_{ii}}$.

### Bound handling and feasibility

The shared helper `allocation_utils.apply_weight_bounds()` projects raw weight
vectors into a bounded simplex. If there are $N$ assets, feasibility requires:

$$
N \cdot \text{min\_weight} \le 1
$$

and

$$
N \cdot \text{max\_weight} \ge 1
$$

This matters because the notebook often compares multiple optimizers under one
common investability rule.

## Part 2 -- Code Reference

### Folder tree

```text
portfolio_allocation/
├── GUIDE_portfolio_allocation.md   -- This guide.
├── __init__.py                     -- Strategy registry and package exports.
├── allocation_utils.py             -- Shared bound validation and projection.
├── min_variance.py                 -- Minimum-variance optimizer.
├── max_sharpe.py                   -- Maximum-Sharpe optimizer.
├── risk_parity.py                  -- Equal-risk-contribution optimizer.
├── max_diversification.py          -- Diversification-ratio optimizer.
├── hrp.py                          -- Hierarchical Risk Parity weights.
├── min_cvar.py                     -- Minimum-CVaR optimizer.
├── explore_allocation_methods.ipynb -- Notebook entrypoint for comparison.
└── outputs/                        -- Historical charts and CSV artifacts.
```

### `allocation_utils.py`

What it does:
Defines the shared allocation constants and the bounded-simplex projection used
to make weight vectors feasible.

Key items:

- `MIN_WEIGHT`
- `MAX_WEIGHT`
- `RISK_FREE`
- `run_slsqp_portfolio()`
- `validate_weight_bounds()`
- `apply_weight_bounds()`
- `apply_cap()`

### Strategy modules

What they do:
Each module implements one optimizer or allocation rule with a narrow
function-level interface.

Key functions:

- `min_variance.min_variance()`
- `max_sharpe.max_sharpe()`
- `risk_parity.risk_parity()`
- `max_diversification.max_diversification()`
- `hrp.hrp_weights()`
- `min_cvar.min_cvar()`

### `__init__.py`

What it does:
Re-exports the strategy functions and provides the strategy-name registries
used by notebook code.

### `explore_allocation_methods.ipynb`

What it does:
Acts as the main workflow for this folder. The notebook uses a manually edited
ticker list, builds one shared log-return panel, runs each allocation method,
and compares the resulting weights and summary statistics side by side.

## Part 3 -- Short Journal

- 2026-05-19: Documented `run_slsqp_portfolio()` as the shared SLSQP shell used
  by the covariance-based optimizers.
- 2026-04-11: Rewrote the guide to match the current repo: notebook-first
  weighting workflow, method modules only, and no active `allocate.py` or
  `method_lab.py` source files.
