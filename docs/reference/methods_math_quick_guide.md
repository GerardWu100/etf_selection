# Methods Math Quick Guide

Short reference for the ETF selection and portfolio weighting methods in this
project.

## One-Page Cheat Sheet

### Selection methods

| Method | Core objective | Main advantage | Main risk | Use when | Avoid when |
|---|---|---|---|---|---|
| Ward clustering | One representative per correlation cluster | Stable and interpretable | Not directly optimizing spread | You want simple diversified representatives | You want direct max-distance optimization |
| Greedy maximin | Maximize minimum distance to selected set | Direct diversification spread objective | Can ignore latent factor structure nuance | You want distance-driven diversification | You want factor-representative selection |
| K-medoids | Anchored cluster medoids | Stable, anchor-aware representatives | Requires pre-set cluster count | You want anchor-preserving cluster selection | You want non-cluster methods |
| Max diversification ratio | Greedily maximize equal-weight DR | Directly optimizes portfolio-level diversification | Greedy, not globally optimal | You want financially motivated selection | You want pure distance or factor logic |

### Weighting methods

| Method | Core objective | Main advantage | Main risk | Use when | Avoid when |
|---|---|---|---|---|---|
| Equal weight | $w_i = 1/N$ | Very simple, low model risk | Ignores risk differences | You want robust baseline | You need risk-balanced sleeves |
| Min variance | Minimize $w^\top \Sigma w$ | Strong volatility control | Can underweight growth | Drawdown/vol control first | You need stronger return-seeking tilt |
| Max Sharpe | Maximize return per unit risk | Efficient if estimates are good | Sensitive to return-estimation noise | You trust expected return estimates | Return forecasts are noisy |
| Risk parity | Equalize risk contributions | Balanced risk allocation | Can overweight low-vol sleeves | You want balanced risk sleeves | You have strong directional conviction |
| Max diversification | Maximize diversification ratio | Correlation-aware diversification | Not explicit tail-loss control | You prioritize structural diversification | Tail-risk control is primary goal |
| HRP allocation | Hierarchical inverse-variance bisection | Robust to covariance inversion issues | Tree assumptions can matter | You want practical robust risk allocation | You want very simple optimizer behavior |
| Min CVaR | Minimize expected tail loss | Direct crash/tail control | May reduce upside capture | Tail protection is priority | You only optimize mean-variance |

## Math In Plain English

If you only remember 4 things, remember these:

1. $w$ = how you split money across ETFs (weights add to 100%).
2. $\mu$ = expected return of each ETF.
3. $\Sigma$ = risk + co-movement matrix (volatility and correlation together).
4. Good diversification means low/negative co-movement, not just many ETFs.

Core quick formulas:

- Distance from correlation:
  $$
  D_{ij} = \sqrt{0.5 \left(1 - r_{ij}\right)}
  $$
  - If correlation $r_{ij}$ is high positive, distance is small (similar assets).
  - If correlation is negative, distance is large (better diversifier).
- Portfolio return (annualized, approx):
  $$
  252 \cdot w^\top \mu
  $$
- Portfolio volatility (annualized):
  $$
  \sqrt{252 \cdot w^\top \Sigma w}
  $$
- Sharpe:
  $$
  \frac{\text{annual return} - \text{risk-free rate}}{\text{annual volatility}}
  $$

## ETF Selection Methods

### 1. Ward Clustering (`correlate_ward.py`)

Goal: pick one representative ETF from each cluster.

Math:

1. Build distance matrix $D$ from Spearman correlation.
2. Run Ward hierarchical clustering (minimum increase in within-cluster
   variance per merge).
3. Cut tree into $N_{\text{SELECT}}$ clusters.
4. Choose the cluster medoid, i.e. the ETF with the smallest average
   signed distance to the other names in that cluster.

### 2. Greedy Maximin (`correlate_greedy.py`)

Goal: maximize diversification spread directly.

Math:

At each step, choose:

$$
\text{next} = \arg\max_{c \notin S} \min_{s \in S} D(c, s)
$$

where $S$ is the current selected set.

Interpretation: add the ETF that is farthest from its nearest selected ETF.

### 3. K-Medoids Selection (`correlate_kmedoids.py`)

Goal: select one anchored medoid per cluster.

Math:

1. Build distance matrix from Spearman correlation.
2. Run k-medoids clustering with anchor constraints.
3. Pick the medoid (most central point) from each cluster.
4. Anchors (VOO, VEA) are forced into the selection.

### 4. Max Diversification Ratio (`correlate_maxdiv.py`)

Goal: greedily maximise the equal-weight diversification ratio.

Math:

- Diversification Ratio (Choueifaty & Coignard, 2008):

$$
DR = \frac{w^\top \sigma}{\sqrt{w^\top \Sigma w}}
$$

- Under equal weights $w = 1/N$:

$$
DR_{EW} = \frac{\text{mean}(\sigma_i)}{\sigma_{\text{portfolio}}}
$$

Algorithm:

1. Seed with anchor ETFs.
2. At each step, add the candidate whose inclusion yields the highest DR.
3. Record the marginal DR at each step.

## Portfolio Weighting Methods

All methods are long-only with full investment:

- $w_i \ge 0$
- $\sum_i w_i = 1$

Project-level bounds are enforced after each method:

- $\mathrm{min\_weight} \le w_i \le \mathrm{max\_weight}$

### 1. Equal Weight (`equal_weight.py`)

$$
w_i = \frac{1}{N}
$$

### 2. Minimum Variance (`min_variance.py`)

Minimize:

$$
w^\top \Sigma w
$$

### 3. Maximum Sharpe (`max_sharpe.py`)

Maximize:

$$
\frac{252 \cdot w^\top \mu - R_f}{\sqrt{252 \cdot w^\top \Sigma w}}
$$

### 4. Risk Parity (`risk_parity.py`)

Goal: equalize risk contributions.

- Portfolio volatility: $\sigma_p = \sqrt{w^\top \Sigma w}$
- Risk contribution of asset `i`:
  - $RC_i = \frac{w_i (\Sigma w)_i}{\sigma_p}$

Optimize weights so $RC_i$ values are as equal as possible.

### 5. Maximum Diversification (`max_diversification.py`)

Maximize diversification ratio:

$$
DR(w) = \frac{w^\top \sigma}{\sqrt{w^\top \Sigma w}}
$$

where $\sigma$ is the vector of individual asset volatilities.

### 6. Hierarchical Risk Parity (`hrp.py`)

1. Cluster by distance tree.
2. Quasi-diagonalize covariance by leaf order.
3. Recursively split clusters and allocate inversely to cluster variance.

### 7. Black-Litterman (`black_litterman.py`)

1. Build equilibrium implied returns from market weights.
2. Blend prior with optional views via Bayesian update.
3. Optimize Sharpe using posterior mean and combined covariance.

### 8. Black-Litterman + Momentum (`bl_momentum.py`)

Same as Black-Litterman, but views are built from trailing average returns
(momentum signal).

### 9. Minimum CVaR (`min_cvar.py`)

Uses Rockafellar-Uryasev formulation:

Minimize historical tail loss estimate:

$$
\zeta + \frac{1}{T(1-\alpha)} \sum_t \max(\mathrm{loss}_t - \zeta, 0)
$$

where $\alpha$ is the confidence level (for example, $0.95$).

### 10. Fractional Kelly (`kelly_criterion.py`)

Quadratic approximation for fractional Kelly utility:

$$
\mathbb{E}[g] \approx f \cdot \mu_p - 0.5 \cdot f^2 \cdot \sigma_p^2
$$

where:

- $f$ is the Kelly fraction (in this project typically $0.5$)
- $\mu_p = 252 \cdot w^\top \mu$
- $\sigma_p^2 = 252 \cdot w^\top \Sigma w$

### 11. Robust Mean-Variance (`robust_mean_variance.py`)

Maximizes worst-case utility under mean-estimation uncertainty:

$$
U(w) = \mu_p - \mathrm{estimation\_risk\_penalty} - 0.5 \cdot \lambda \cdot \sigma_p^2
$$

with uncertainty radius scaled by chi-square confidence.

### 12. Shrinkage Sharpe (`shrinkage_sharpe.py`)

1. Shrink sample covariance toward scaled identity (Ledoit-Wolf style).
2. Maximize Sharpe using shrunk covariance.

## Practical Use

- For quick baseline: `equal_weight`, `min_variance`, `max_sharpe`, `risk_parity`
- For tail protection focus: `min_cvar`
- For estimation-noise robustness: `hrp`, `max_diversification`

## Worked Toy Examples + When To Use / Avoid

All examples below are illustrative, not exact optimizer outputs.

### Shared toy setup

Assume 4 ETFs:

- `A`: U.S. equity
- `B`: growth equity
- `C`: intermediate Treasuries
- `D`: gold

Illustrative annual expected returns ($\mu$) and volatilities ($\sigma$):

- $\mu = [8\%, 9\%, 4\%, 6\%]$
- $\sigma = [15\%, 20\%, 7\%, 12\%]$

Illustrative correlations:

- $\mathrm{corr}(A,B)=0.85$, $\mathrm{corr}(A,C)=-0.10$, $\mathrm{corr}(A,D)=0.40$
- $\mathrm{corr}(B,C)=-0.05$, $\mathrm{corr}(B,D)=0.55$, $\mathrm{corr}(C,D)=0.25$

Example signed distance:

$$
D(A,C) = \sqrt{0.5 \left(1 - (-0.10)\right)} = \sqrt{0.55} \approx 0.742
$$

- Interpretation: `A` and `C` are fairly far apart, so good diversifiers.

### Mini by-hand calculations (quick)

1. Sharpe intuition:
- Suppose a portfolio has return `8%`, volatility `12%`, risk-free `4%`.
- Sharpe = $\frac{0.08 - 0.04}{0.12} = 0.33$.
- Higher Sharpe is better (more excess return per unit risk).

2. Maximin intuition:
- If current selected set is `{A, C}` and candidate distances to nearest
  selected ETF are:
  - $B \rightarrow 0.22$
  - $D \rightarrow 0.48$
- Greedy maximin picks `D` (because `0.48` is larger).

3. CVaR intuition:
- If worst 5% daily losses are `[-2.0%, -1.8%, -1.6%, -1.5%, -1.4%]`,
  then CVaR(95%) is their average:
  $$
  \frac{-2.0 - 1.8 - 1.6 - 1.5 - 1.4}{5} = -1.66\%
  $$
- Min-CVaR tries to make this tail average less negative.

## Selection Methods: Example + Decision Rule

### Ward Clustering

Example:

- Tree forms 3 clusters: `{A,B}`, `{C}`, `{D}`
- If selecting 3 ETFs: pick 1 per cluster (for `{A,B}`, pick higher-liquidity one)

Use when:

- You want stable, interpretable “one-per-cluster” diversification.

Avoid when:

- You want direct optimization of “maximum minimum distance” (Greedy is better for that).

### Greedy Maximin

Example:

- Seed with liquid ETF `A`
- Next choose ETF farthest from `A` (likely `C`)
- Next choose ETF with largest minimum distance to `{A,C}` (often `D`)

Use when:

- You want a direct diversification spread objective.

Avoid when:

- You care more about representativeness of latent factors than pairwise distance.

### K-Medoids Selection

Example:

- With 30 clusters, K-medoids finds the most central ETF in each cluster.
- Anchors (VOO, VEA) are guaranteed inclusion.
- Output: one medoid per cluster, with anchors replacing the natural medoid
  when an anchor is present in that cluster.

Use when:

- You want stable, anchor-aware cluster representatives.

Avoid when:

- You want non-cluster-based selection (distance or factor methods).

### Max Diversification Ratio

Example:

- Start with anchors `{VOO, VEA}`, DR = 1.05.
- Add `GLD` (low equity correlation), DR jumps to 1.15.
- Add `TLT` (rates diversifier), DR reaches 1.22.
- Later additions show diminishing DR improvement.

Use when:

- You want financially motivated selection that accounts for the full covariance structure.

Avoid when:

- You want pure factor or pure distance-only selection logic.

## Weighting Methods: Example + Decision Rule

### Equal Weight

Example:

- 4 ETFs -> `[25%, 25%, 25%, 25%]`

Use when:

- You want simplicity and low model risk.

Avoid when:

- Asset volatilities differ a lot and you want risk-balanced exposure.

### Minimum Variance

Example:

- Possible output: `[15%, 10%, 45%, 30%]` (tilts to low-vol assets)

Use when:

- Drawdown and volatility control are top priority.

Avoid when:

- You need higher return-seeking behavior.

### Maximum Sharpe

Example:

- Possible output: `[35%, 30%, 20%, 15%]`

Use when:

- You trust expected-return estimates and want return/risk efficiency.

Avoid when:

- Return estimates are noisy/unstable (common in practice).

### Risk Parity

Example:

- Capital weights may be `[22%, 16%, 38%, 24%]` so each contributes similar risk.

Use when:

- You want balanced risk contributions across sleeves.

Avoid when:

- You strongly believe one sleeve should dominate by conviction.

### Maximum Diversification

Example:

- Output tends to overweight assets with strong diversification ratio impact,
  e.g. `[20%, 15%, 40%, 25%]`.

Use when:

- You prioritize correlation structure diversification.

Avoid when:

- You need explicit tail-loss control (use CVaR methods).

### Hierarchical Risk Parity (Allocation)

Example:

- Cluster split first `{A,B}` vs `{C,D}` then recursive inverse-variance split.
- Typical output can resemble `[24%, 14%, 36%, 26%]`.

Use when:

- You want robust risk allocation with less covariance inversion fragility.

Avoid when:

- You need a simple transparent linear optimizer output.

### Black-Litterman

Example:

- Start with market-implied prior, add mild views, output may shift from
  `[25,25,25,25]` to `[28,24,30,18]`.

Use when:

- You want disciplined blending of prior + views.

Avoid when:

- You do not have credible views/prior assumptions.

### Black-Litterman + Momentum

Example:

- If trailing momentum favors `A` and `D`, posterior may tilt toward them.

Use when:

- You want a systematic view model without manual discretionary views.

Avoid when:

- You dislike trend exposure / are in mean-reversion regime assumptions.

### Minimum CVaR

Example:

- At $\alpha = 95\%$, the optimizer minimizes the average worst 5% loss scenarios.
- Possible output: `[12%, 8%, 50%, 30%]`.

Use when:

- Tail-risk and crash behavior matter more than average volatility.

Avoid when:

- You only care about mean-variance metrics.

## Fast Personal-Finance Defaults

If you want a practical default stack:

1. Selection: `Greedy` or `MaxDiv`
2. Weighting: `Risk Parity` or `HRP`
3. Constraints: `min_weight=5%`, `max_weight=20%`, around 10 ETFs
4. Validate: run both math validators before live testing
