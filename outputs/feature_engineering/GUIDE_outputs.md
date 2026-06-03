# GUIDE_outputs.md

## Purpose

This folder holds run-local artifacts produced by `feature_engineering/cli.py`.
Unlike root `outputs/`, nothing here is a shared dependency of the ETF
selection pipeline.

## Artifact contract

Each run writes a subfolder named by the configured run name. A typical run
contains:

- `session_primitives.parquet`
  - one row per `(symbol, session_date)`
  - reusable session open/high/low/close, volume, bar counts, prior-session
    values, overnight gap, and next-session close metadata
- `enriched_context.parquet`
  - regular-session minute bars with session primitives and as-of joined
    context columns
- `feature_matrix.parquet`
  - enriched base frame plus per-symbol features, cross-sectional features,
    and labels
- `feature_manifest.csv`
  - one row per feature or label with function name, timeframe, rules, and
    null rate
- `context_join_audit.csv`
  - one row per context source with null rate, stale rate, and effective lag
- `run_audit_log.csv`
  - compact run summary across outputs and feature coverage
- `resolved_config.json`
  - the exact config used after CLI overrides

## Expectations

- Runs are self-describing. If a feature or label exists in the matrix, it
  should also appear in the manifest.
- Context columns with stale data should be nulled before downstream feature
  computation.
- This folder is for generated artifacts only; the tracked file here is this
  guide.
