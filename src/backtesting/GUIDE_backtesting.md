# GUIDE_backtesting.md

## Part 1 -- Conceptual Explanation

### Purpose and problem statement

This folder is the notebook-facing evaluation layer for a manually chosen ETF
basket. It answers one narrow question:

If you choose a set of tickers and portfolio weights, what exact buy-and-hold
path would that portfolio have produced on the shared daily dataset?

The current folder is intentionally small. It does not implement a large
command-line backtesting framework. Instead, it provides one exact valuation
engine in Python and one notebook that lets you edit a basket manually and
inspect the results.

### Spine of the logic

1. Load the shared daily parquet from `outputs/`.
2. Filter to the requested tickers and date window.
3. Align all tickers to the latest first-valid date so every holding is live at
   the same entry point.
4. Allocate the requested initial capital according to the input weights.
5. Convert those dollar allocations into fixed share counts at the aligned
   entry-date close.
6. Hold those shares constant through the full sample.
7. Revalue the fixed-share portfolio on every trading date.
8. Convert the exact portfolio value path into portfolio log returns:
   $r_{p,t} = \log(V_t / V_{t-1})$.
9. Report annualized log return, annualized log volatility, Sharpe ratio,
   max drawdown, Calmar ratio, and the equity curve.

### Portfolio math

Let:

- $w_i$ = initial portfolio weight of asset $i$
- $B_0$ = initial capital
- $P_{i,0}$ = aligned entry-date close of asset $i$
- $q_i$ = fixed share count bought for asset $i$
- $P_{i,t}$ = close price of asset $i$ on date $t$
- $V_t$ = exact portfolio value on date $t$

Initial dollar allocation:

$$
A_i = B_0 \cdot w_i
$$

Fixed shares:

$$
q_i = \frac{A_i}{P_{i,0}}
$$

Exact buy-and-hold value:

$$
V_t = \sum_i q_i P_{i,t}
$$

Portfolio log return:

$$
r_{p,t} = \log\left(\frac{V_t}{V_{t-1}}\right)
$$

Annualized log return and volatility:

$$
R_{\text{ann}} = 252 \cdot \text{mean}(r_{p,t})
$$

$$
\sigma_{\text{ann}} = \sqrt{252} \cdot \text{std}(r_{p,t})
$$

Sharpe ratio:

$$
\text{Sharpe} = \frac{R_{\text{ann}} - R_f}{\sigma_{\text{ann}}}
$$

where $R_f$ is the annual risk-free rate, kept in log-return units for
consistency with the rest of the repo.

### Inputs and outputs

Inputs:

- `data/raw/daily_close_volume_screened_2016_2025.parquet`
- a manual ticker list from the notebook
- a manual weight vector from the notebook

Outputs produced by the notebook:

- in-memory summary metrics
- an equity curve DataFrame
- notebook plots for portfolio value and drawdown

The checked-in CSV and PNG files under `outputs/backtesting/` are historical
artifacts from earlier runs. The current in-repo workflow is notebook-first.

### Assumptions and invariants

- Long-only weights only
- Weights must sum to 1.0
- No rebalancing after the entry date
- No transaction costs, slippage, taxes, or cash drag
- Prices are daily closes from the shared parquet
- Portfolio valuation is exact from fixed shares, even though reported return
  metrics stay in log-return space

## Part 2 -- Code Reference

### Folder tree

```text
backtesting/
├── GUIDE_backtesting.md         -- This guide.
├── __init__.py                  -- Minimal package marker.
├── buy_and_hold.py              -- Exact fixed-share buy-and-hold engine.
├── explore_buy_and_hold.ipynb   -- Manual notebook for basket evaluation.
├── models/                      -- Reserved artifact folder.
└── outputs/                     -- Historical run artifacts and output guide.
```

### `buy_and_hold.py`

What it does:
Loads the shared parquet, aligns the basket to one common entry date, builds
fixed share counts from the requested weights, revalues the portfolio daily,
and returns summary metrics plus an equity-curve table.

Key functions:

- `load_price_matrix()`
- `run_weighted_backtest()`

### `explore_buy_and_hold.ipynb`

What it does:
Provides the human-in-the-loop interface for this folder. You edit `TICKERS`
and `WEIGHTS`, run the notebook, and inspect the resulting metrics, equity
curve, and drawdown chart.

### `__init__.py`

What it does:
Keeps the package surface minimal so callers import the explicit engine module
directly.

## Part 3 -- Short Journal

- 2026-04-11: Updated the guide to match the current codebase: one exact
  buy-and-hold engine, one notebook entrypoint, and log-return-only reporting.
