# Phase 1 Product Requirements

**Product:** Financial Data Platform  

## 1. Overview

Phase 1 will establish the foundation for the Financial Data Platform
and deliver the first complete data pipeline.

The system will collect daily OHLCV data from one approved provider,
preserve the original response, validate and normalize the data, store
the processed data in Parquet and make it queryable through an API.

## 2. Phase 1 objective

The objective is to prove that the platform can reliably move data
through the complete lifecycle:

```text
External provider
  ↓
Ingestion
  ↓
Raw storage
  ↓
Validation
  ↓
Normalization
  ↓
Processed Parquet
  ↓
DuckDB query
  ↓
API response
```

## 3. Users and consumers

Phase 1 will support:

- Financial Data Platform application services.
- Internal developers.
- Data and quantitative research workflows.
- Future analytics and AI systems.

The initial release is an internal platform capability. It is not a
public financial-data product.

## 4. Phase 1 boundaries

### Included

- One approved market-data provider (Yahoo Finance).
- Equity instruments.
- Daily OHLCV data.
- Instrument, company and exchange reference data.
- Historical backfill.
- Basic incremental update support.
- Raw provider-response preservation.
- Canonical data normalization.
- Data validation.
- Ingestion-job tracking.
- Parquet-based historical storage.
- DuckDB analytical queries.
- Basic historical-price API.
- Idempotent ingestion.
- Basic automated tests and logging.

### Excluded

- Intraday data.
- Tick and trade-level data.
- Order-book data.
- Fundamentals.
- Corporate actions.
- News.
- Regulatory filings.
- Macro-economic data.
- AI features.
- Trading execution.
- Distributed streaming.
- Kafka, Spark and Kubernetes.

## 5. Initial data boundary

```text
Provider: Yahoo Finance
Asset class: Equities
Frequency: Daily
Instrument universe: Apple (AAPL), Reliance Industries (RELIANCE.NS)
Historical range: User-defined start/end date range
Exchange coverage: NASDAQ (US), NSE (India)
Currency: USD, INR
```

## 6. User stories

### US-001: Ingest market data

As a platform operator, I want to run an ingestion job for a selected
instrument universe so that daily OHLCV data is collected from the
approved provider.

### US-002: Preserve source data

As a data engineer, I want the original provider response preserved so
that the data can be audited and processed again later.

### US-003: Query historical prices

As an internal application or analyst, I want to request historical
prices for an instrument and date range so that I can perform analysis.

### US-004: Track ingestion status

As a platform operator, I want to see whether an ingestion job succeeded,
failed or partially completed so that data problems are visible.

### US-005: Rerun jobs safely

As a platform operator, I want to rerun an ingestion job without creating
duplicates so that temporary failures can be recovered safely.

## 7. Functional requirements

### FR-001: Provider ingestion

The system shall retrieve daily OHLCV data from the selected provider.

### FR-002: Instrument mapping

The system shall map provider symbols to internal instruments.

All normalized market records shall reference an internal
`instrument_id`.

### FR-003: Job creation

The system shall create an ingestion-job record before starting a data
collection operation.

### FR-004: Raw preservation

The system shall store the original provider response without modifying
it.

Each raw object shall contain enough metadata to identify:

```text
provider
dataset
retrieval time
job ID
request or response reference
```

### FR-005: Normalization

The system shall convert provider-specific fields into the canonical
OHLCV structure:

```text
instrument_id
timestamp
timeframe
open
high
low
close
adjusted_close
volume
currency
source
ingested_at
```

### FR-006: Validation

The system shall validate each OHLCV record before publishing it.

At minimum:

```text
high >= open
high >= close
low <= open
low <= close
high >= low
volume >= 0
timestamp is valid
instrument exists
```

### FR-007: Rejected records

The system shall preserve invalid records with their validation failure
and shall not silently discard them.

### FR-008: Historical storage

The system shall write valid normalized records to Parquet in object
storage.

### FR-009: Analytical querying

The system shall allow historical OHLCV data to be queried using DuckDB.

### FR-010: API serving

The system shall expose an endpoint for retrieving historical OHLCV
data.

The initial endpoint shall support:

```text
instrument_id
start date
end date
timeframe
```

### FR-011: Idempotency

The system shall prevent duplicate logical OHLCV records.

The logical uniqueness key shall be:

```text
instrument_id + timestamp + timeframe
```

### FR-012: Backfill

The system shall support historical ingestion for a specified date range.

### FR-013: Incremental update

The system shall support fetching data after the last successful
ingestion point.

### FR-014: Job statistics

The system shall record:

```text
records received
records valid
records invalid
records duplicated
records written
job status
start time
completion time
error details
```

### FR-015: Error handling

The system shall retry temporary provider or network failures and shall
record permanent failures for later investigation.

## 8. Data and storage requirements

Phase 1 shall use the following storage responsibilities:

```text
PostgreSQL:
  instruments, companies, exchanges, data sources, ingestion jobs
  and quality metadata

MinIO:
  local raw and processed object storage

Parquet:
  normalized historical OHLCV data

DuckDB:
  analytical queries over Parquet

Redis:
  Not required for the first working pipeline
```

Raw data shall be immutable.

Processed data shall be reproducible from raw data.

## 9. API requirement

The initial API shall expose a historical-price operation equivalent to:

```text
GET /v1/prices/{instrument_id}/history
```

Required query parameters:

```text
start
end
timeframe
```

The response shall include:

```text
instrument_id
timeframe
data points
timestamp
open
high
low
close
adjusted_close
volume
currency
```

The API shall return clear errors for:

```text
unknown instrument
invalid date range
unsupported timeframe
missing data
internal processing failure
```

## 10. Non-functional requirements

### Reliability

The ingestion process shall be safely restartable and rerunnable.

### Reproducibility

Processed data shall be rebuildable from the preserved raw response.

### Observability

Every ingestion job shall produce structured logs containing the job
ID, provider, dataset, status and record counts.

### Security

Provider credentials shall be loaded through environment configuration
or a secrets-management system. Credentials shall not be committed to
the repository.

### Local development

The Phase 1 platform shall run locally through Docker Compose.

### Maintainability

Provider-specific logic shall remain inside a provider adapter and shall
not leak into downstream storage or API logic.

### Performance

The initial system only needs to support the agreed Phase 1 instrument
universe and daily data volume. Distributed processing is not required.

## 11. Acceptance criteria

Phase 1 is accepted when all of the following are true:

- The platform starts locally with Docker Compose.
- PostgreSQL and MinIO are available.
- The selected provider can be contacted successfully.
- A provider symbol can be mapped to an internal instrument.
- A backfill can be run for the selected date range.
- The original provider response is preserved.
- Valid OHLCV records are normalized.
- Invalid records are stored with rejection reasons.
- Processed records are written as Parquet.
- Historical data can be queried using DuckDB.
- The historical-price API returns the expected records.
- Ingestion-job status and record counts are stored.
- Temporary provider failures are retried.
- Repeating the same job does not create duplicates.
- Automated tests pass for the primary data flow.

## 12. Success measurement

Phase 1 success will be measured by:

```text
Data can be collected end to end.
Raw data can be audited.
Processed data can be regenerated.
Historical data can be queried.
API results are traceable to source data.
Repeated ingestion is safe.
Failures are visible.
```

## 13. Decided Policies

```text
1. Initial data provider: Yahoo Finance (yfinance wrapper)
2. Initial exchange: NASDAQ (US) & NSE (India)
3. Initial instrument universe: AAPL, RELIANCE.NS
4. Historical backfill range: Dynamically defined by user start/end parameters
5. Timezone policy: Naive local/UTC timestamps
6. Currency policy: Native instrument currencies (USD, INR)
7. Price adjustment: Adjusted close is normalized alongside raw close
```

## 14. Definition of done

The Phase 1 product is complete when the acceptance criteria have passed
and the complete pipeline can be demonstrated using real provider data.
