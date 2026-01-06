# OHLCV Schema

**Product:** Financial Data Platform  
**Owner:** Product and Engineering  
**Last updated:** 6 January 2026  

---

## 1. Purpose

Define the canonical structure for normalized OHLCV (Open, High, Low, Close, Volume) records across all timeframes — daily, intraday, and any future granularity.

This schema is **provider-agnostic**. Every provider's response is transformed into this canonical form before storage. The schema is independent of provider-specific response formats, field names, or conventions.

This document governs:

- The logical structure of OHLCV records.
- The physical Parquet layout in object storage.
- Validation rules applied during ingestion.
- Policies for timestamps, prices, volume, and corporate actions.
- Schema evolution and backward compatibility.

---

## 2. Record structure

### 2.1 Logical fields

| Field | Type | Nullable | Description |
|---|---|---|---|
| `instrument_id` | UUID | NO | Internal instrument identifier (FK to `instruments`) |
| `timestamp` | TIMESTAMP WITH TIME ZONE | NO | Start time of the candle, normalized to UTC |
| `timeframe` | VARCHAR(10) | NO | Candle interval: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w`, `1M` |
| `open` | DECIMAL(18,6) | NO | Opening price of the interval |
| `high` | DECIMAL(18,6) | NO | Highest price during the interval |
| `low` | DECIMAL(18,6) | NO | Lowest price during the interval |
| `close` | DECIMAL(18,6) | NO | Closing price of the interval |
| `adjusted_close` | DECIMAL(18,6) | YES | Corporate-action-adjusted closing price |
| `volume` | BIGINT | NO | Traded quantity during the interval (shares, contracts, or units) |
| `currency` | CHAR(3) | NO | ISO 4217 currency code for prices |
| `source` | VARCHAR(50) | NO | Provider identifier (FK to `data_sources.provider_key`) |
| `ingested_at` | TIMESTAMP WITH TIME ZONE | NO | Time the platform ingested the record |

### 2.2 Metadata fields (Parquet footer / sidecar)

These fields are not stored in every row but are tracked per file or partition:

| Field | Type | Description |
|---|---|---|
| `ingestion_job_id` | UUID | FK to `ingestion_jobs.job_id` |
| `schema_version` | INTEGER | Version of this canonical schema |
| `processing_version` | INTEGER | Version of the normalization logic |
| `provider_timestamp` | TIMESTAMP WITH TIME ZONE | Original timestamp as reported by provider |

---

## 3. Example record

```json
{
  "instrument_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "timestamp": "2025-01-02T00:00:00Z",
  "timeframe": "1d",
  "open": 245.100000,
  "high": 248.500000,
  "low": 243.800000,
  "close": 247.900000,
  "adjusted_close": 247.900000,
  "volume": 1250000,
  "currency": "INR",
  "source": "alpha_vantage",
  "ingested_at": "2026-08-29T10:30:00Z"
}
```

---

## 4. Logical identity

Each OHLCV record is uniquely identified by the composite key:

```text
(instrument_id, timestamp, timeframe)
```

The `source` field identifies the origin of the record but does **not** form part of the logical identity. If two providers supply the same `(instrument_id, timestamp, timeframe)` tuple, they are treated as **two distinct records** from different sources — both are preserved.

Within a single ingestion job, the logical key must be unique. Duplicate keys within a job are rejected and recorded in `rejected_records`.

---

## 5. Timeframe policy

### 5.1 Supported timeframes

| Code | Meaning | Typical use |
|---|---|---|
| `1m` | 1-minute bar | Intraday (Phase 3) |
| `5m` | 5-minute bar | Intraday (Phase 3) |
| `15m` | 15-minute bar | Intraday (Phase 3) |
| `30m` | 30-minute bar | Intraday (Phase 3) |
| `1h` | 1-hour bar | Intraday (Phase 3) |
| `4h` | 4-hour bar | Intraday (Phase 3) |
| `1d` | Daily bar | Phase 2 and beyond |
| `1w` | Weekly bar | Derived or provider-supplied |
| `1M` | Monthly bar | Derived or provider-supplied |

### 5.2 Timestamp semantics

- The `timestamp` field represents the **start** of the candle interval.
- A daily bar for `2025-01-02` has `timestamp = 2025-01-02T00:00:00Z`.
- A 5-minute bar starting at 09:30 has `timestamp = ...T09:30:00Z` and covers `[09:30, 09:35)`.
- All timestamps are normalized to UTC. The exchange's local session boundaries are documented per exchange in the `exchanges` table.

### 5.3 Exchange session boundaries

Each exchange has a defined trading session. Daily bars are aligned to the exchange's session close, not to midnight UTC. The mapping is:

```text
exchange.timezone       → determines local session hours
exchange.currency       → determines price currency
exchange.mic_code       → identifies the exchange
```

For example, NSE (India) closes at 15:30 IST. A daily bar for NSE on `2025-01-02` covers the session from 09:15 to 15:30 IST, and its `timestamp` is `2025-01-02T00:00:00Z` (midnight UTC of that trading date).

---

## 6. Price policy

### 6.1 Precision

All price fields use `DECIMAL(18,6)`:

- 18 total digits of precision.
- 6 digits after the decimal point.
- Supports prices from `0.000001` to `999999999999.999999`.
- Sufficient for all global equity, ETF, and derivative markets.

### 6.2 Close vs. adjusted close

The platform maintains a strict separation:

| Field | Meaning |
|---|---|
| `close` | Provider-reported closing price. **Never modified** by the platform. |
| `adjusted_close` | Closing price adjusted for corporate actions (splits, dividends, rights issues). Supplied by the provider when available; otherwise `NULL`. |

**Rules:**

1. `close` is always the raw provider value. It is immutable after ingestion.
2. `adjusted_close` is optional. If the provider does not supply it, the field is `NULL`.
3. The platform **does not** compute `adjusted_close` itself in Phase 2. Computation from corporate actions data is deferred to Phase 4.
4. The platform **never** silently replaces `close` with `adjusted_close`.

### 6.3 Price sanity checks

During validation, the following invariants must hold:

```text
high >= max(open, close)
low  <= min(open, close)
high >= low
open > 0
close > 0
high > 0
low > 0
```

Records violating these invariants are rejected.

### 6.4 Price outlier detection

Beyond hard invariants, the platform applies soft outlier detection:

- Price change vs. previous close exceeds ±50% (configurable per instrument).
- Price is zero or negative after corporate-action adjustment.
- Price is outside the exchange's defined price band (if available).

Outliers are flagged but not automatically rejected. Flagged records are written to canonical storage with a quality flag in the associated `quality_results` entry.

---

## 7. Volume policy

### 7.1 Type and range

- Volume is stored as `BIGINT` (64-bit signed integer).
- Volume must be `>= 0`.
- Zero volume is valid (e.g., no trades during the interval).

### 7.2 Volume semantics per provider

The meaning of `volume` varies by provider and asset class. This must be documented per provider in the `data_sources` table:

| Provider | Asset class | Volume meaning |
|---|---|---|
| Provider A | Equity | Number of shares traded |
| Provider B | Equity | Number of shares traded |
| Provider C | Futures | Number of contracts traded |
| Provider D | Crypto | Base asset quantity |

The platform does **not** normalize volume across providers. Consumers must interpret volume in the context of the source provider and asset class.

### 7.3 Volume sanity checks

- `volume >= 0` (hard rule).
- `volume > 0` when `close != open` or `high != low` (soft rule — a bar with price movement should have volume).

---

## 8. Validation rules

### 8.1 Hard rules (reject on failure)

A record is rejected if any of the following fail:

| Rule | Description |
|---|---|
| `R1` | `instrument_id` exists in `instruments` table |
| `R2` | `timestamp` is a valid UTC timestamp |
| `R3` | `timestamp` is not in the future (relative to ingestion time) |
| `R4` | `timeframe` is in the supported set |
| `R5` | `currency` is a valid ISO 4217 code |
| `R6` | `open`, `high`, `low`, `close` are non-null and non-negative |
| `R7` | `volume` is non-null and non-negative |
| `R8` | `high >= max(open, close)` |
| `R9` | `low <= min(open, close)` |
| `R10` | `high >= low` |
| `R11` | No duplicate `(instrument_id, timestamp, timeframe)` within the same job |

### 8.2 Soft rules (flag on failure)

A record is accepted but flagged if:

| Rule | Description |
|---|---|
| `S1` | Price change vs. previous close exceeds ±50% |
| `S2` | Volume is zero but price moved |
| `S3` | `adjusted_close` differs from `close` by more than 20% (possible stale adjustment) |
| `S4` | `timestamp` falls on a non-trading day for the exchange |

### 8.3 Rejection handling

Rejected records are written to `rejected_records` with:

- The original payload (as JSONB).
- The rejection reason code (e.g., `R8`, `R11`).
- A human-readable explanation.
- The associated `job_id`.

Rejected records are **never** silently discarded.

---

## 9. Corporate actions and adjusted prices

### 9.1 Phase 2 behavior

In Phase 2, `adjusted_close` is passed through from the provider as-is. The platform does not compute adjustments.

### 9.2 Phase 4+ behavior

Once corporate actions data is available (Phase 4), the platform will:

1. Store the provider-supplied `adjusted_close` unchanged.
2. Compute a platform-derived `adjusted_close` using the corporate actions table.
3. Expose both via the API so consumers can choose.

The platform-derived adjustment will use:

- Split ratios from `corporate_actions` where `action_type = 'split'`.
- Dividend amounts from `corporate_actions` where `action_type = 'dividend'`.
- The standard adjustment formula: `adjusted_close = close * cumulative_adjustment_factor`.

---

## 10. Missing data handling

### 10.1 Market holidays and suspensions

On days when an exchange is closed (market holiday) or an instrument is suspended:

- The provider may return no record for that `(instrument_id, timestamp)`.
- The platform does **not** insert a placeholder record.
- Consumers must treat missing records as "no data for this date," not "zero activity."

### 10.2 Partial bars

For intraday data, a bar may be incomplete if the ingestion runs before the interval closes:

- The platform ingests whatever the provider supplies.
- The `ingested_at` timestamp records when the data was captured.
- A subsequent ingestion may overwrite the bar with a complete version (idempotent partition-level writes).

### 10.3 Late corrections

Providers sometimes correct data after the fact:

- The raw provider payload is always preserved in `raw/` storage.
- A re-ingestion job overwrites the Parquet partition for the affected date.
- The new job is recorded in `ingestion_jobs` with a reference to the corrected data.

---

## 11. Source tracking

Every record carries source information to support auditability and reproducibility:

| Field | Where stored | Purpose |
|---|---|---|
| `source` | Row column | Identifies the provider |
| `ingested_at` | Row column | Identifies when the platform processed the record |
| `ingestion_job_id` | Parquet file metadata | Links to the specific ingestion run |
| `schema_version` | Parquet file metadata | Identifies the canonical schema version |
| `processing_version` | Parquet file metadata | Identifies the normalization logic version |

The `ingestion_job_id` is also written to the `ingestion_jobs` table, creating a bidirectional link between the Parquet file and the job record.

---

## 12. Storage format

### 12.1 File format

OHLCV records are stored as **Apache Parquet** files in object storage.

**Parquet configuration:**

| Setting | Value | Rationale |
|---|---|---|
| Compression | `ZSTD` (level 3) | Best balance of compression ratio and speed for financial data |
| Row group size | 100,000 rows | Optimizes DuckDB scan performance |
| Page size | 1 MB | Default; no tuning needed at Phase 2 volumes |
| Dictionary encoding | Enabled for `timeframe`, `source`, `currency` | Low-cardinality string columns |

### 12.2 Partitioning layout

```text
parquet/ohlcv/
  {exchange}/
    {year}/
      data.parquet
```

**Example:**

```text
parquet/ohlcv/
  NSE/
    2025/
      part-000000.parquet
      part-000001.parquet
  NYSE/
    2025/
      part-000000.parquet
```

**Rationale:**

- Partitioning by `exchange` isolates queries to a single exchange.
- Partitioning by `year` keeps file counts manageable and aligns with annual backfill patterns.
- Monthly partitioning is added in Phase 3 for intraday data (see §13).

### 12.3 File naming

Files within a partition are named `part-NNNNNN.parquet` where `NNNNNN` is a zero-padded sequence number. This ensures deterministic ordering and makes it easy to detect missing files.

### 12.4 Atomic writes

To prevent partial writes from being visible to readers:

1. The ingestion worker writes to a temporary file: `part-NNNNNN.parquet.tmp`.
2. After the write completes and the file is validated, it is renamed to `part-NNNNNN.parquet`.
3. Object storage rename is atomic (S3 `CopyObject` + `DeleteObject`, or MinIO native rename).

---

## 13. Phase 3 extension — intraday partitioning

In Phase 3, intraday data (1m, 5m, 15m, 30m, 1h, 4h) uses a finer partitioning scheme due to higher volume:

```text
parquet/intraday/
  {exchange}/
    {year}/
      {month}/
        {day}/
          {timeframe}/
            data.parquet
```

**Example:**

```text
parquet/intraday/
  NSE/
    2025/
      01/
        02/
          5m/
            part-000000.parquet
```

The record structure is identical to §2.1; only the partitioning changes.

---

## 14. Query patterns

The schema is optimized for the following query patterns:

| Pattern | Example | Partition pruning |
|---|---|---|
| Single instrument, date range | `WHERE instrument_id = ? AND timestamp BETWEEN ? AND ?` | Prunes to relevant year partitions |
| Multiple instruments, single date | `WHERE instrument_id IN (...) AND timestamp = ?` | Prunes to single year partition |
| Full exchange scan | `WHERE exchange = 'NSE'` | Prunes to exchange partition |
| Latest close for instrument | `WHERE instrument_id = ? ORDER BY timestamp DESC LIMIT 1` | Scans most recent partition first |

DuckDB's partition-aware reader automatically skips irrelevant files, making these queries efficient even as the dataset grows.

---

## 15. Schema evolution

### 15.1 Backward compatibility

Changes to this schema **must** be backward-compatible:

- **Adding fields:** Allowed. New fields must be nullable or have a default value.
- **Removing fields:** Prohibited. Deprecated fields are marked as such but retained.
- **Changing field types:** Prohibited. If a type change is needed, a new field is added.
- **Changing field semantics:** Prohibited. If the meaning of a field changes, a new field is added.

### 15.2 Versioning

The `schema_version` field in Parquet metadata tracks the schema version:

- `schema_version = 1` — initial schema (Phase 2).
- `schema_version = 2` — first backward-compatible addition.
- And so on.

Consumers can check `schema_version` to determine which fields are available.

### 15.3 Potential future fields

The following fields are under consideration for future schema versions:

| Field | Type | Rationale |
|---|---|---|
| `open_interest` | BIGINT | Derivatives markets |
| `vwap` | DECIMAL(18,6) | Volume-weighted average price |
| `trade_count` | BIGINT | Number of trades in the interval |
| `provider_timestamp` | TIMESTAMP WITH TIME ZONE | Original provider timestamp (currently in metadata) |
| `corporate_action_flag` | BOOLEAN | Indicates the close was affected by a corporate action |
| `quality_flag` | VARCHAR | Soft-rule violations (e.g., `outlier`, `zero_volume`) |

Adding these fields will not change the meaning of existing fields.

---

## 16. Relationship to other schemas

| Schema | Relationship |
|---|---|
| `instruments` (PostgreSQL) | `instrument_id` is a FK. The instrument must exist before OHLCV records are ingested. |
| `exchanges` (PostgreSQL) | Determines session boundaries, timezone, and currency. |
| `data_sources` (PostgreSQL) | `source` is a FK to `provider_key`. |
| `ingestion_jobs` (PostgreSQL) | `ingestion_job_id` links the Parquet file to the job that produced it. |
| `corporate_actions` (PostgreSQL, Phase 4) | Used to compute platform-derived `adjusted_close`. |
| `rejected_records` (PostgreSQL) | Stores records that fail validation. |

---

## 17. Summary of invariants

1. Every OHLCV record is uniquely identified by `(instrument_id, timestamp, timeframe)`.
2. `close` is the raw provider value; `adjusted_close` is optional and provider-supplied.
3. All timestamps are UTC.
4. All prices are `DECIMAL(18,6)`; volume is `BIGINT`.
5. Hard validation rules reject invalid records; soft rules flag anomalies.
6. Rejected records are preserved with reason codes.
7. Raw provider data is preserved in `raw/` storage before any processing.
8. Parquet files are written atomically and partitioned by `{exchange}/{year}`.
9. Schema changes are backward-compatible and versioned.
10. Source tracking enables full auditability and reproducibility.
