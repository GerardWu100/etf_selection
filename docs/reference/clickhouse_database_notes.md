# ClickHouse Database Notes

Reference document for the `firstrate` ClickHouse database: schema, statistics, compression analysis,
and codec recommendations. Captures findings from exploratory analysis conducted 2026-02-27.

---

## 1. Database Overview

Database name: `firstrate`

All tables use `MergeTree` engine, partitioned by month (`toYYYYMM`), ordered by `(symbol, ts)` or
equivalent. All tables share the same schema pattern: `symbol`, timestamp, OHLCV columns.

### Table Summary

| Table     | Symbols | Date Range  | Total Rows | Compressed | Uncompressed | Overall Ratio |
|-----------|---------|-------------|-----------|-----------|--------------|---------------|
| `stocks`  | 7,783   | 2000–2026   | 4.0B      | 77.8 GiB  | 186 GiB      | 2.4x          |
| `options` | —       | —           | 3.2B      | 150 GiB   | 305 GiB      | 2.0x          |
| `etfs`    | 4,293   | —           | 812M      | 18.1 GiB  | 37.5 GiB     | 2.1x          |
| `futures` | 14,503  | 2007–2025   | 549M      | 4.3 GiB   | 14.4 GiB     | 3.4x          |
| `indices` | —       | —           | 195M      | 2.7 GiB   | 5.1 GiB      | 1.9x          |
| `crypto`  | 75      | 2013–2026   | 159M      | 3.5 GiB   | 5.8 GiB      | 1.7x          |

---

## 2. Schemas

### `stocks` and `etfs`

```sql
symbol  LowCardinality(String)
ts      DateTime64(3, 'America/New_York')  CODEC(DoubleDelta, ZSTD(1))
open    Float64                            CODEC(Gorilla(8), ZSTD(1))
high    Float64                            CODEC(Gorilla(8), ZSTD(1))
low     Float64                            CODEC(Gorilla(8), ZSTD(1))
close   Float64                            CODEC(Gorilla(8), ZSTD(1))
volume  Float64                            CODEC(ZSTD(1))
```

Sort key: `(symbol, ts)`. Partition: `toYYYYMM(ts)`.

### `futures`

Same as stocks/etfs except `volume` is `UInt32` instead of `Float64`.

### `crypto`

Same as stocks/etfs but `ts` timezone is `UTC`.

### `indices`

Same as stocks/etfs but no `volume` column.

### `options`

```sql
symbol        LowCardinality(String)
trade_date    Date                    CODEC(DoubleDelta, ZSTD(1))
strike_price  Float64                 CODEC(Gorilla(8), ZSTD(1))
expiry_date   Date                    CODEC(DoubleDelta, ZSTD(1))
option_type   Enum8('c'=1, 'p'=2)
last_price    Float64                 CODEC(Gorilla(8), ZSTD(1))
bid           Float64                 CODEC(Gorilla(8), ZSTD(1))
ask           Float64                 CODEC(Gorilla(8), ZSTD(1))
bid_iv        Float64                 CODEC(Gorilla(8), ZSTD(1))
ask_iv        Float64                 CODEC(Gorilla(8), ZSTD(1))
open_interest UInt32                  CODEC(ZSTD(1))
volume        UInt32                  CODEC(ZSTD(1))
delta         Float64                 CODEC(Gorilla(8), ZSTD(1))
gamma         Float64                 CODEC(Gorilla(8), ZSTD(1))
vega          Float64                 CODEC(Gorilla(8), ZSTD(1))
theta         Float64                 CODEC(Gorilla(8), ZSTD(1))
rho           Float64                 CODEC(Gorilla(8), ZSTD(1))
```

Sort key: `(symbol, trade_date, expiry_date, option_type, strike_price)`.

---

## 3. Per-Column Compression Analysis

### stocks (minute OHLCV, 7,783 symbols, avg 516,641 rows/symbol)

| Column   | Compressed | Uncompressed | Ratio |
|----------|-----------|--------------|-------|
| `symbol` | 46 MiB    | 6.2 GiB      | 138x  |
| `ts`     | 2.3 GiB   | 29.6 GiB     | 12.9x |
| `volume` | 7.4 GiB   | 29.6 GiB     | 4.0x  |
| `open`   | 16.9 GiB  | 29.6 GiB     | 1.76x |
| `high`   | 16.5 GiB  | 29.6 GiB     | 1.79x |
| `low`    | 16.5 GiB  | 29.6 GiB     | 1.79x |
| `close`  | 17.1 GiB  | 29.6 GiB     | 1.74x |

### etfs (minute OHLCV, 4,293 symbols)

| Column   | Compressed | Uncompressed | Ratio |
|----------|-----------|--------------|-------|
| `symbol` | 9.9 MiB   | 1.12 GiB     | 116x  |
| `ts`     | 644 MiB   | 5.75 GiB     | 9.1x  |
| `volume` | 1.5 GiB   | 5.75 GiB     | 3.8x  |
| `open`   | 3.79 GiB  | 5.75 GiB     | 1.52x |
| `high`   | 3.75 GiB  | 5.75 GiB     | 1.53x |
| `low`    | 3.77 GiB  | 5.75 GiB     | 1.53x |
| `close`  | 3.83 GiB  | 5.75 GiB     | 1.50x |

### futures (minute OHLCV, 14,503 symbols, avg 37,869 rows/symbol)

| Column   | Compressed | Uncompressed | Ratio |
|----------|-----------|--------------|-------|
| `symbol` | 5.3 MiB   | 662 MiB      | 125x  |
| `ts`     | 352 MiB   | 3.94 GiB     | 11.5x |
| `volume` | 619 MiB   | 1.97 GiB     | 3.3x  |
| `open`   | 1.12 GiB  | 3.94 GiB     | 3.54x |
| `high`   | 1.10 GiB  | 3.94 GiB     | 3.57x |
| `low`    | 1.10 GiB  | 3.94 GiB     | 3.57x |
| `close`  | 1.13 GiB  | 3.94 GiB     | 3.50x |

### crypto (minute OHLCV, 75 symbols, avg 2,118,918 rows/symbol)

| Column   | Compressed | Uncompressed | Ratio |
|----------|-----------|--------------|-------|
| `symbol` | 898 KiB   | 148 MiB      | 168x  |
| `ts`     | 37 MiB    | 1.15 GiB     | 31.6x |
| `volume` | 809 MiB   | 1.15 GiB     | 1.45x |
| `open`   | 678 MiB   | 1.15 GiB     | 1.73x |
| `high`   | 668 MiB   | 1.15 GiB     | 1.76x |
| `low`    | 668 MiB   | 1.15 GiB     | 1.76x |
| `close`  | 685 MiB   | 1.15 GiB     | 1.72x |

### indices (minute OHLC, no volume)

| Column   | Compressed | Uncompressed | Ratio |
|----------|-----------|--------------|-------|
| `symbol` | 1.2 MiB   | 160 MiB      | 133x  |
| `ts`     | 5.8 MiB   | 1.25 GiB     | 219x  |
| `open`   | 682 MiB   | 1.25 GiB     | 1.87x |
| `high`   | 663 MiB   | 1.25 GiB     | 1.92x |
| `low`    | 663 MiB   | 1.25 GiB     | 1.92x |
| `close`  | 681 MiB   | 1.25 GiB     | 1.87x |

Note: the `ts` ratio of 219x on indices is anomalously high, likely due to sparse bars
(e.g. daily-only or regular-hours-only data with very uniform timestamp deltas).

### options (daily snapshots, greeks + prices)

| Column          | Compressed | Uncompressed | Ratio |
|-----------------|-----------|--------------|-------|
| `trade_date`    | 39 MiB    | 5.90 GiB     | 155x  |
| `symbol`        | 33 MiB    | 5.00 GiB     | 156x  |
| `expiry_date`   | 125 MiB   | 5.90 GiB     | 49x   |
| `strike_price`  | 675 MiB   | 23.62 GiB    | 36x   |
| `option_type`   | 402 MiB   | 2.95 GiB     | 7.5x  |
| `open_interest` | 1.14 GiB  | 11.81 GiB    | 10.3x |
| `volume`        | 1.00 GiB  | 11.80 GiB    | 12.1x |
| `bid`           | 7.72 GiB  | 23.62 GiB    | 3.1x  |
| `ask`           | 8.37 GiB  | 23.62 GiB    | 2.8x  |
| `bid_iv`        | 12.07 GiB | 23.62 GiB    | 2.0x  |
| `last_price`    | 12.25 GiB | 23.62 GiB    | 1.9x  |
| `vega`          | 13.44 GiB | 23.62 GiB    | 1.76x |
| `gamma`         | 13.14 GiB | 23.62 GiB    | 1.8x  |
| `theta`         | 17.38 GiB | 23.62 GiB    | 1.36x |
| `rho`           | 20.25 GiB | 23.62 GiB    | 1.17x |
| `delta`         | 19.76 GiB | 23.62 GiB    | 1.20x |
| `ask_iv`        | 21.76 GiB | 23.62 GiB    | 1.09x |

---

## 4. Compression Analysis and Codec Recommendations

### How the current codecs work

**Gorilla(8):** XOR delta encoding designed for time-series float data. Works by encoding the
XOR between consecutive float64 bit-patterns. Extremely efficient when consecutive values are
close (small XOR). Fails when consecutive values jump significantly — large XOR means many bits
must be stored. The parameter `8` sets the block size (default).

**DoubleDelta:** Encodes the delta-of-deltas of integer values. Works perfectly for regular
timestamps (e.g. every minute = constant delta -> delta-of-delta is zero -> near-zero entropy).

**ZSTD(n):** General-purpose block compressor. Finds byte-level repetition and patterns across
a larger window than Gorilla. Less sensitive to value smoothness. Level `n` controls compression
effort at write time; decompression speed is nearly flat across all levels (~1,400-1,500 MB/s).

The codec stack `Gorilla(8), ZSTD(1)` means: first Gorilla-transform the data, then
ZSTD-compress the Gorilla output. If Gorilla produces noisy output (many large XOR values),
ZSTD has less structure to exploit — potentially worse than plain ZSTD on raw floats.

### Why Gorilla underperforms on mixed-symbol OHLCV tables

The sort order `(symbol, ts)` means within a partition, all bars for symbol A are stored
contiguously, then all bars for symbol B, etc. Gorilla's XOR chain breaks at every symbol
boundary. With thousands of symbols per partition (4,293 ETFs, 7,783 stocks), there are
thousands of boundary breaks per monthly partition where prices reset to a completely different
magnitude — destroying Gorilla's efficiency.

Example of what Gorilla sees at a symbol boundary:

```
AAPL:  185.2, 185.3, 185.1, ...  <- small XOR, Gorilla efficient
  -> boundary jump ->
ZVZZT:   0.41,  0.40,  0.42, ...  <- large XOR vs prior value, Gorilla inefficient
```

### Why futures compresses better (3.5x vs ~1.75x for stocks/ETFs)

Futures contracts expire. Each contract symbol has a short contiguous block of bars
(avg 37,869 rows/symbol vs 516,641 for stocks). Within that short block, prices are smooth
and Gorilla's XOR chain stays efficient. Symbol boundaries still exist but the in-boundary
compression gain dominates because contract prices stay within a tight range for the life
of the contract.

### Why crypto compresses poorly despite only 75 symbols

With only 75 symbols and 2M+ rows each, there are almost no boundary breaks — Gorilla should
work well. But crypto prices span enormous magnitude ranges (BTC ~$90k, micro-caps at
$0.000001) and are highly volatile at the minute level. The float64 exponent bits vary
significantly even within a single symbol's series, producing large XOR deltas. Gorilla
fails on volatile data regardless of boundary count.

### Why options Greeks compress worst of all (1.1–1.4x)

Greeks (delta, gamma, vega, theta, rho) and implied volatility (bid_iv, ask_iv) are highly
non-linear functions of multiple inputs. Consecutive rows in the sort order
`(symbol, trade_date, expiry_date, option_type, strike_price)` — e.g. adjacent strikes —
produce wildly different greek values. The XOR deltas are large and essentially random from
Gorilla's perspective. These columns account for ~100 GiB compressed out of ~150 GiB total
for the options table.

### Codec recommendations

| Table / Column       | Current Codec          | Recommended          | Reason |
|----------------------|------------------------|----------------------|--------|
| `stocks` OHLC        | `Gorilla(8), ZSTD(1)` | `ZSTD(1)`            | Mixed-symbol table; Gorilla adds overhead without benefit |
| `etfs` OHLC          | `Gorilla(8), ZSTD(1)` | `ZSTD(1)`            | Same as stocks |
| `crypto` OHLC        | `Gorilla(8), ZSTD(1)` | `ZSTD(1)`            | High volatility kills Gorilla even with few symbols |
| `indices` OHLC       | `Gorilla(8), ZSTD(1)` | `ZSTD(1)`            | Mixed symbols, Gorilla not helping |
| `futures` OHLC       | `Gorilla(8), ZSTD(1)` | keep or `ZSTD(1)`    | Already 3.5x — Gorilla may be helping; benchmark first |
| `options` Greeks/IV  | `Gorilla(8), ZSTD(1)` | `ZSTD(1)`            | Non-linear values, Gorilla is worst-case scenario |
| `options strike_price`| `Gorilla(8), ZSTD(1)`| keep                 | Already 36x — round tick values suit Gorilla perfectly |
| All `ts` columns     | `DoubleDelta, ZSTD(1)`| keep                 | Excellent (9–220x) — regular timestamps ideal for DoubleDelta |
| All `symbol` columns | `LowCardinality(String)`| keep               | Excellent (116–168x) |

### ZSTD level guidance

ZSTD level controls write-time compression effort only. Decompression speed is nearly flat
across all levels — query time is not materially affected by the level chosen.

| Level | Ratio gain vs level 1 | Write speed penalty | Recommendation |
|-------|-----------------------|--------------------:|----------------|
| 1     | baseline              | none                | Default — right choice for most financial data |
| 3     | +5–15%                | ~2-3x slower        | ZSTD library default; marginal gain |
| 6     | +10–25%               | ~5x slower          | Only if storage-constrained and writes are infrequent |
| 9+    | diminishing           | very slow           | Rarely worth it |

The gain from switching codec (Gorilla -> plain ZSTD) will be larger than any ZSTD level
tuning. Fix the codec first; only tune the level if storage is critically constrained.

### Query time impact

```
query_time = io_time + decompress_time + compute_time

io_time         proportional to compressed_size  (smaller = faster disk reads)
decompress_time  proportional to uncompressed_size (flat across ZSTD levels)
```

- Higher ZSTD levels do not slow queries — decompression speed is level-independent.
- Better compression ratio helps query time indirectly: fewer bytes read from disk.
- The benefit is larger on HDD or network-attached storage than on NVMe.
- Dropping Gorilla from underperforming columns is a small query-time win: one fewer
  decode pass, and potentially less data to decompress if plain ZSTD achieves better ratio.
- Write time is where the ZSTD level tradeoff is felt: level 3 is ~2-3x slower to compress
  than level 1, level 6 is ~5x slower.

---

## 5. Useful Queries

### Per-column compression breakdown for any table

```sql
SELECT
    column,
    type,
    formatReadableSize(sum(column_data_compressed_bytes))   AS compressed,
    formatReadableSize(sum(column_data_uncompressed_bytes)) AS uncompressed,
    round(sum(column_data_uncompressed_bytes) / sum(column_data_compressed_bytes), 2) AS ratio
FROM system.parts_columns
WHERE database = 'firstrate' AND table = 'stocks' AND active = 1
GROUP BY column, type
ORDER BY sum(column_data_uncompressed_bytes) DESC
```

### Table-level totals across all tables

```sql
SELECT
    table,
    formatReadableSize(sum(data_compressed_bytes))   AS compressed,
    formatReadableSize(sum(data_uncompressed_bytes)) AS uncompressed,
    round(sum(data_uncompressed_bytes) / sum(data_compressed_bytes), 2) AS ratio
FROM system.parts
WHERE database = 'firstrate' AND active = 1
GROUP BY table
ORDER BY sum(data_uncompressed_bytes) DESC
```

### Symbol and row counts per table

```sql
SELECT
    count(DISTINCT symbol) AS symbol_count,
    min(ts)                AS earliest,
    max(ts)                AS latest,
    count()                AS total_rows,
    round(count() / count(DISTINCT symbol), 0) AS avg_rows_per_symbol
FROM firstrate.stocks
```
