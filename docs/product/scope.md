# Platform Scope

**Parent document:** Product Brief  
**Owner:** Product and Engineering  
**Last updated:** 5 January 2026  

## Objective

Define the implementation boundaries and deliverables for the initial
Financial Data Platform.

The roadmap is designed to deliver one complete, testable data pipeline
early while leaving room for future market, corporate and alternative
data domains.

## Phase 1: Platform Foundation and First Data Slice

### Objective

Build the local platform foundation and demonstrate the complete lifecycle
of one daily OHLCV dataset.

### In scope

- Docker Compose development environment.
- PostgreSQL.
- MinIO for local object storage.
- Database migrations.
- Companies, exchanges and instruments.
- One approved market-data provider.
- Daily equity OHLCV ingestion.
- Raw provider-payload preservation.
- Instrument and provider-symbol mapping.
- OHLCV validation.
- Rejected-record storage.
- Idempotent ingestion.
- Ingestion-job tracking.
- Normalized Parquet output.
- DuckDB historical queries.
- Basic historical-price API.
- Basic structured logging.
- End-to-end tests.

### Out of scope

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
- Redis-based caching.
- Kafka, Spark and Kubernetes.

### Phase 1 output

A working system that can:

```text
Fetch daily OHLCV data
  ↓
Preserve the original provider payload
  ↓
Map provider symbols to internal instruments
  ↓
Validate and normalize records
  ↓
Store valid data as Parquet
  ↓
Record invalid data and job statistics
  ↓
Query historical data with DuckDB
  ↓
Return prices through FastAPI
```

## Phase 2: Expansion of Market Data

### Objective

Expand market-data coverage and improve update workflows.

### In scope

- Historical backfills.
- Incremental updates.
- Additional approved market-data providers.
- Intraday prices.
- Trade-level data.
- Improved data reconciliation.
- Parquet compaction.
- Data freshness monitoring.

### Out of scope

- Order-book data.
- Fundamentals.
- Corporate actions.
- News.
- Regulatory filings.
- Macro-economic data.
- AI features.
- Trading execution.
- Redis-based caching.
- Kafka, Spark and Kubernetes.

## Phase 3: Order-Book Data

### Objective

Support high-volume market-depth data.

### In scope

- Order-book snapshots.
- Order-book events or deltas.
- Sequence tracking.
- Latest order-book state.
- Historical order-book replay.
- High-volume partitioning.
- Retention and storage-cost controls.

### Out of scope

- Fundamentals.
- Corporate actions.
- News.
- Regulatory filings.
- Macro-economic data.
- AI features.
- Trading execution.
- Kafka, Spark and Kubernetes.

## Phase 4: Fundamental and Corporate Data

### Objective

Add structured company and financial-statement data.

### In scope

- Income statements.
- Balance sheets.
- Cash-flow statements.
- Financial ratios.
- Corporate actions.
- Restatements and historical versions.

### Out of scope

- News.
- Regulatory filings.
- Macro-economic data.
- AI features.
- Trading execution.
- Kafka, Spark and Kubernetes.

## Phase 5: News and Filings

### Objective

Add alternative and information data.

### In scope

- News metadata and content.
- News deduplication.
- Company and instrument mapping.
- Regulatory filing metadata.
- Filing-document storage.
- Extracted filing text.

### Out of scope

- Macro-economic data.
- AI features.
- Trading execution.
- Kafka, Spark and Kubernetes.

## Phase 6: AI-Ready Data Services

### Objective

Prepare platform data for advanced analytics and AI applications.

### In scope

- Document extraction.
- Structured document sections.
- Full-text search.
- Semantic search.
- Feature engineering.
- Embeddings.
- AI-facing data interfaces.

### Out of scope

- Trading execution.
- Kafka, Spark and Kubernetes.
