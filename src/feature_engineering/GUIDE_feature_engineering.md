# GUIDE_feature_engineering.md

## Part 1 -- Conceptual Explanation

### Purpose and boundary

This folder builds an isolated point-in-time research dataset from minute bars.
It does not replace or feed the existing ETF selection pipeline. The old path

`screen -> shared daily parquet -> correlation selection -> allocation -> backtesting`

still works exactly as before.

This folder exists for a different question:

Given one primary minute-bar universe and several context series, can we build
a leakage-aware feature matrix with explicit as-of, lag, and staleness rules?

### Spine of the logic

1. Load one or more primary minute-bar sources from ClickHouse.
2. Load optional context sources from other tables.
3. Normalize every timestamp into one internal timezone.
4. Derive trading-date and market-session labels:
   - overnight
   - premarket
   - regular
   - postmarket
5. Aggregate reusable session primitives:
   - session open, high, low, close
   - volume and bar counts
   - prior regular-session close, return, and range
   - overnight gap
6. Restrict the feature matrix base to regular-session minute bars.
7. Apply context joins with explicit rules per source:
   - `align`
   - `availability`
   - `lag`
   - `max_staleness`
8. Build per-symbol features from the enriched base frame.
9. Build optional coarser timeframe frames such as `5min` and `15min`, compute
   features there, and as-of join them back to the minute index.
10. Run cross-sectional passes grouped by timestamp.
11. Run a separate label registry that uses only future windows.
12. Export artifacts and audit tables to `outputs/feature_engineering/<run_name>/`.

### Supported source tables

The adapters currently support:

- `firstrate.etfs`
- `firstrate.stocks`
- `firstrate.futures`
- `firstrate.crypto`
- `firstrate.indices`
- `firstrate.options`
- `coinmetrics.perpetual`

The minute-bar tables are harmonized to one OHLCV-like schema. The options
table is summarized to one daily point-in-time row per symbol so it can be
joined like any other context source. Options enrichment is disabled in the
sample config because the current history ends on `2024-12-31`.

### Session model

The folder uses one internal trading-date convention in the internal timezone.

- `04:00` to `09:29` = premarket
- `09:30` to `15:59` = regular
- `16:00` to `19:59` = postmarket
- everything else = overnight

Bars from `20:00` through `23:59` are assigned to the next trading date. This
lets one trading date own its full overnight-to-close context.

### Leakage controls

Three places enforce point-in-time discipline.

First, context joins are `asof` joins with explicit lag and staleness limits.
If a joined value is too old, it is nulled and the stale rate is recorded in
the audit table.

Second, per-symbol and cross-sectional features run only on current or past
data already present on the feature row.

Third, labels live in `labels.py`, not in the feature registry. The default
sample run uses:

- next regular-session return
- next regular-session realized volatility
- an optional quantile label derived from the forward return

### Concrete sample run

The sample `config.toml` uses:

- primary universe: `SPY`, `QQQ`, `IWM`, `TLT`, `XLE`
- context series: `VIX`, `SPY`, `QQQ`, `DXY`, `SR3_Z25`
- timeframe features: `5min`, `15min`
- target window: next regular session

That sample run writes:

- `session_primitives.parquet`
- `enriched_context.parquet`
- `feature_matrix.parquet`
- `feature_manifest.csv`
- `context_join_audit.csv`
- `run_audit_log.csv`
- `resolved_config.json`

### Design decisions

Why keep this stage separate from the ETF flow?

- The ETF selection pipeline is deliberately daily and stable.
- Point-in-time feature work is exploratory and changes faster.
- Mixing them would create avoidable coupling and leakage risk.

Why use minute bars but export a regular-session feature matrix?

- Minute bars are needed to build session primitives and multi-timeframe
  features correctly.
- The regular-session minute index is the cleanest base for intraday research.

Why reuse the ClickHouse client from `correlation_analysis/`?

- It keeps one connection path and one date-window normalization rule.
- It avoids duplicating `.env` parsing in another module.

## Part 2 -- Folder Tree and File Map

```text
feature_engineering/
├── GUIDE_feature_engineering.md -- This folder guide.
├── __init__.py                  -- Package marker.
├── cli.py                       -- End-to-end research pipeline entrypoint.
├── config.toml                  -- Sample research run config.
├── source_adapters.py           -- ClickHouse table adapters and canonical raw schema.
├── normalize.py                 -- Timestamp normalization and source metadata harmonization.
├── sessionize.py                -- Trading-date labels and reusable session primitives.
├── enrich.py                    -- Context as-of joins with lag and staleness audits.
├── features.py                  -- Per-symbol registry and timeframe feature joins.
├── cross_sectional.py           -- Timestamp-grouped cross-sectional transforms.
├── labels.py                    -- Separate target registry.
└── outputs/                     -- Folder-local run artifacts and output guide.
```

## Part 3 -- Code Reference

### `cli.py`

What it does:
Loads config, reuses the shared ClickHouse client, orchestrates every stage,
and writes the final artifacts.

Run:

- `uv run python feature_engineering/cli.py --config feature_engineering/config.toml`

### `source_adapters.py`

What it does:
Defines one supported-table map and converts each source query into one
canonical raw frame with table metadata. Query dispatch is table-driven by
source kind, so the load path stays short even as supported sources grow.

Key items:

- `TABLE_METADATA`
- `load_source_frame()`

### `normalize.py`

What it does:
Converts raw source timestamps into the configured internal timezone while
preserving source timezone metadata.

Key items:

- `normalize_source_frame()`
- `normalize_source_frames()`

### `sessionize.py`

What it does:
Assigns trading dates and market sessions, then builds reusable session-level
primitives used by both features and labels. Repeated "prior regular session"
fields are derived by one explicit loop, which keeps the shared shift rule easy
to inspect.

Key items:

- `classify_market_session()`
- `build_session_primitives()`
- `attach_session_primitives()`

### `enrich.py`

What it does:
Applies context joins with explicit point-in-time rules and returns an audit
table with null rate, stale rate, and effective lag.

Key items:

- `apply_context_joins()`

### `features.py`

What it does:
Builds resampled timeframe frames, runs the per-symbol feature registry, and
records one manifest row per feature.

Key items:

- `build_timeframe_frames()`
- `run_feature_registry()`

### `cross_sectional.py`

What it does:
Computes timestamp-grouped post-pass features such as z-scores, percentile
ranks, benchmark residuals, and peer-group demeaning. Dispatch is registry-
based, matching the style already used in `features.py`.

Key items:

- `run_cross_sectional_features()`

### `labels.py`

What it does:
Builds future-only targets after features are finalized. Label dispatch stays
separate from feature dispatch so the future-only boundary remains obvious in
code.

Key items:

- `run_label_registry()`

## Part 4 -- Short Journal

- 2026-04-16: Simplified the feature-engineering package by replacing small branch chains with registry-style dispatch where the package already used that pattern, and by collapsing repeated prior-session shifts into one shared loop.
