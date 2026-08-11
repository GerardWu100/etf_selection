# Mean-Variance Allocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tested mean-variance allocation method with notebook-configurable risk aversion and include it in the walkthrough comparison.

**Architecture:** A focused `mean_variance.py` module will use the existing Sequential Least Squares Programming optimizer shell. The package registry will expose it, while the notebook will provide a single `RISK_AVERSION` setting and one strategy cell. Existing guide and reference files will document the implemented behavior.

**Tech Stack:** Python 3.12, NumPy, SciPy, pytest, Jupyter/nbconvert

---

### Task 1: Mean-variance optimizer

**Files:**
- Create: `tests/unit/portfolio_allocation/test_mean_variance.py`
- Create: `src/portfolio_allocation/mean_variance.py`
- Modify: `src/portfolio_allocation/__init__.py`

- [x] **Step 1: Write failing behavioral and registry tests**

Add tests using a two-asset deterministic example. Assert valid bounded weights,
lower variance at higher risk aversion, rejection of zero/negative/non-finite
risk aversion, and registration under `mean_variance`.

- [x] **Step 2: Verify the tests fail for the missing feature**

Run:

```bash
uv run pytest tests/unit/portfolio_allocation/test_mean_variance.py -v
```

Expected: collection fails because `portfolio_allocation.mean_variance` does not
exist.

- [x] **Step 3: Implement the optimizer**

Create a fully typed function with default `risk_aversion=3.0` that minimizes
the negative annualized utility:

```python
annual_mean = mean_ret * TRADING_DAYS_PER_YEAR
annual_cov = cov * TRADING_DAYS_PER_YEAR
objective = -(
    weights @ annual_mean - 0.5 * risk_aversion * weights @ annual_cov @ weights
)
```

Validate that risk aversion is finite and strictly positive, then call
`run_slsqp_portfolio`. Export the function and add it to the classic strategy
names and function registry.

- [x] **Step 4: Verify the focused tests pass**

Run:

```bash
uv run pytest tests/unit/portfolio_allocation/test_mean_variance.py -v
```

Expected: all tests pass.

### Task 2: Notebook integration

**Files:**
- Modify: `notebooks/01_project_walkthrough/explore_allocation_methods.ipynb`
- Test: `tests/integration/test_allocation_notebook.py`

- [x] **Step 1: Strengthen the notebook integration test first**

Require `mean_variance` in the executed notebook source/output contract and
increase the expected embedded chart count from eight to nine.

- [x] **Step 2: Verify the integration test fails**

Run:

```bash
uv run pytest tests/integration/test_allocation_notebook.py -v
```

Expected: failure because the notebook does not yet produce the mean-variance
allocation and ninth chart.

- [x] **Step 3: Add the notebook setting and strategy cell**

Add `RISK_AVERSION = 3.0` beside the weight settings. Insert a documented
mean-variance section after minimum variance and call:

```python
raw = methods.mean_variance(
    mean_ret,
    cov,
    risk_aversion=RISK_AVERSION,
    max_weight=MAX_WEIGHT,
)
w = allocation_utils.apply_weight_bounds(raw, MIN_WEIGHT, MAX_WEIGHT)
_show(w, "mean_variance")
```

Update the introductory strategy count and list.

- [x] **Step 4: Execute and verify the notebook**

Run:

```bash
MPLCONFIGDIR=/tmp/mpl IPYTHONDIR=/tmp/ipython UV_CACHE_DIR=/tmp/uv-cache uv run python -m nbconvert --ExecutePreprocessor.shutdown_kernel=immediate --to notebook --execute --inplace notebooks/01_project_walkthrough/explore_allocation_methods.ipynb
```

Then rerun the integration test and expect it to pass.

### Task 3: Documentation and complete verification

**Files:**
- Modify: `src/portfolio_allocation/GUIDE_portfolio_allocation.md`
- Modify: `notebooks/GUIDE_notebooks.md`
- Modify: `docs/reference/methods_math_quick_guide.md`

- [x] **Step 1: Update documentation from implemented code**

Define the mean-variance objective, every symbol, annualization convention,
risk-aversion behavior, default value, module, notebook setting, and the
return-estimation limitation. Correct the notebook strategy count.

- [x] **Step 2: Run the full test suite**

Run:

```bash
uv run pytest
```

Expected: all tests pass.

- [x] **Step 3: Inspect the final diff and commit all workspace changes**

Run standalone `git diff`, `git status`, `git add .`, and `git commit` commands.
Preserve the user's pre-existing notebook changes and include them as required
by the repository instruction to finish with `git add .` and a commit.
