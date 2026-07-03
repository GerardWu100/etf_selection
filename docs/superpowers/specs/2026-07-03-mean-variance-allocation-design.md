# Mean-Variance Allocation Design

## Objective

Add one conventional mean-variance portfolio to the allocation walkthrough.
The investor controls the return-risk trade-off with a risk-aversion setting in
the notebook; no project-level configuration file is required.

## Portfolio objective

For portfolio weights $w$, annualized expected log returns $\mu$, annualized
return covariance matrix $\Sigma$, and risk-aversion coefficient $\lambda$,
maximize:

$$
w^\top \mu - \frac{\lambda}{2} w^\top \Sigma w
$$

The first term rewards expected return. The second penalizes variance. The
coefficient $\lambda$ must be positive: lower values favor expected return and
higher values favor lower variance.

Daily sample means and covariances will both be multiplied by 252 trading days
inside the optimizer so the two terms use consistent annual units.

## Interface and integration

- Add `portfolio_allocation.mean_variance()` beside the existing allocation
  functions.
- Accept daily mean returns, daily covariance, a configurable risk-aversion
  coefficient, and the existing maximum-weight bound.
- Use `3.0` as the function and notebook default for moderate risk aversion.
- Reject non-positive or non-finite risk-aversion values with `ValueError`.
- Export the function through the package strategy registry.
- Add `RISK_AVERSION = 3.0` beside the notebook's existing allocation settings.
- Add one notebook section and include its result in the existing statistics
  table and comparison charts.
- Continue applying the notebook's common minimum- and maximum-weight
  projection after optimization so comparisons use the same feasible set.

## Verification

Unit tests will establish that:

- the weights are non-negative, bounded, and sum to one;
- a higher risk-aversion coefficient reduces portfolio variance on a simple
  deterministic example;
- invalid risk-aversion values are rejected;
- the strategy is available from the package registry.

After unit tests pass, execute the allocation notebook top-to-bottom and run
the full test suite. Update developer and mathematical reference documentation
to match the implemented method.

## Scope exclusions

This change will not add an efficient-frontier sweep, a target-return
constraint, covariance shrinkage, expected-return shrinkage, or a new
`config.toml` file.
