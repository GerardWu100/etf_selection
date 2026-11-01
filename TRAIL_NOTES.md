# Trail notes

## Decisions

- 2026-04-16: Shared pipeline inputs (`volume_screen.csv`, the daily parquet) live in `data/raw/`; `outputs/` holds only derived artifacts. Do not move them back.
- 2026-04-16: `feature_engineering` stays isolated from the ETF selection flow: selection is daily and stable, feature work is exploratory, and coupling them adds leakage risk.
- 2026-10-31: The liquidity screen ranks by volume summed over 2020-2025 (top 500), not one anchor year, so one regime does not dominate. The export keeps all 500; the start-date (full-history) filter runs later, in the selection stage.
- 2026-10-31: Distance is signed, `D = sqrt(0.5 * (1 - rho))` on Spearman correlation, so negatively correlated ETFs count as far apart. `VOO` and `VEA` are required anchors in every selection method.
- 2026-10-31: Active selectors are greedy maximin, anchored k-medoids and max diversification ratio. The selection consensus table ranks by penalized `average_rank` (a missing rank = that method's max rank + 1), not by `method_count`.
- 2026-04-11: Allocation and buy-and-hold backtesting are notebook-first, with no CLI; the old `allocate.py` / `method_lab.py` scripts were removed on purpose.
- 2026-07-03: Mean-variance risk aversion is a notebook setting (`RISK_AVERSION`, default 3.0) because it is an investor preference; no `config.toml`, frontier sweep or shrinkage was in scope.
- 2026-06-18: The return-vol screen keeps ETFs with >= 5 usable years, judged over full usable history, weekly max drawdown no worse than -15% and average yearly return >= 3%, ranked by weekly volatility. It replaced a min-yearly-return / bad-year rule after several 2026-06-17 variants (including a latest-five-years window, reverted).

## Assumptions

- 2026-08-10: Results are in-sample on one fixed 2018-2025 window, with a survivorship-biased universe (funds still trading 2020-2025) and no costs or taxes. Nobody has checked out-of-sample stability; check with a walk-forward or split-sample reselection.

## Gotchas

- 2026-10-31: Daily close is `argMax(close, ts)` (last minute bar of the day), because the minute table does not guarantee a bar at the session close.
- 2026-10-31: Selection hurdles (total return, average yearly return) are in log-return units, even where old labels say percent.
- 2026-11-01: The saved mean-variance output in `explore_allocation_methods.ipynb` still comes from a stray `RISK_AVERSION = 2.0` reset (removed; the setup cell's 3.0 now applies). Rerun with database access before quoting those weights; at 3.0 the bond fund USHY gets more weight and XHB less.
- 2026-08-10: `fillna(median)` before covariance (max-div selection, `correlate_utils`, HRP) shrinks covariance, inflates diversification ratios and understates volatility.
- 2026-08-10: Annualisation uses 252 days regardless of return frequency (a weekly panel is annualised as daily), and `RISK_FREE = 0.05` applies to every year.
- 2026-08-10: Optimiser non-convergence only prints a warning; the failed weights are still used.
- 2026-08-10: Checked-in `outputs/` come from older windows, settings and removed scripts (Ward, PCA, merged selections; allocation CSVs). Do not compare them with fresh runs to infer a code change.
- 2026-08-10: `etf_inception_analysis.ipynb` assumes the working folder is the repo root, and `explore_selection_methods.ipynb` looks only one level up. Run notebooks from the repo root, as the integration tests do.
- 2026-08-10: Feature engineering: every new session-level column must be classified as backward- or forward-looking (`FORWARD_LOOKING_SESSION_COLUMNS`), or labels leak into features. Bars at 20:00 or later roll to the next trading date, so shift only over sessions with regular bars.
- 2026-08-10: `np.select` wrapped in `pd.Series(...)` without `index=` misaligns on assignment and silently yields all-missing values.
- 2026-10-31: The options source history ends 2024-12-31, so options enrichment is off in the sample feature config.

## Failed approaches

## Open blockers

- 2026-10-31: `tests/integration/test_allocation_notebook.py` fails without ClickHouse: the notebook's `BCD` is not in the local parquet, so its empty column makes HRP's linkage raise "must contain only finite values". Next check: add `BCD` to the parquet export, or run with database access.

## Untried ideas

- 2026-10-31: Covariance shrinkage (Ledoit-Wolf) for the allocators. Promising because max-Sharpe and max-div are sensitive to the noisy sample covariance; cost is small (one estimator swap plus a test).
