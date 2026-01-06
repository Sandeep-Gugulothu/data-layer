# High-Level Design

**Product:** Financial Data Platform
**Owner:** Product and Engineering
**Last updated:** 5 January 2026

---

## 1. Purpose

Define the technical architecture for a financial data platform that ingests, preserves, normalizes, validates, stores, and serves market, corporate, and alternative data. The architecture is delivered incrementally across six phases, each adding a new data domain or capability while preserving the foundational patterns established in earlier phases.

This document establishes component boundaries, data models, storage strategy, API design, reliability guarantees, and the phasing that will guide implementation.

---

## 2. Scope and data volume estimates

Volume estimates drive every architectural decision. The platform is designed to handle the following at full maturity:

| Data domain | Approx. daily volume | Annual storage | Update pattern |
|---|---|---|---|
| Daily OHLCV (Phase 2) | 1 – 10 MB | < 1 GB | Daily batch |
| Intraday + trades (Phase 3) | 1 – 10 GB | 100 GB – 1 TB | Streaming / micro-batch |
| Fundamentals (Phase 4) | 10 – 50 MB | < 1 GB | Quarterly batch |
| News + filings (Phase 5) | 100 MB – 1 GB | 50 – 200 GB | Continuous |
| Extracted text + embeddings (Phase 6) | 1 – 10 GB | 100 GB – 1 TB | On ingestion |

Phase 1 and 2 operate at volumes where embedded DuckDB and file-based Parquet are appropriate. Phase 3 and beyond require partitioning, compaction, and potentially dedicated query infrastructure.

---

## 3. Overall architecture (final state)

![System Design Diagram](/docs/architecture/diagrams/Financial Data Platform Architecture.svg)

The final architecture is a hub of specialized pipelines sharing common infrastructure. Each pipeline follows the same pattern — ingest, preserve raw, validate, normalize, store canonical — but uses different storage formats and processing tools appropriate to its data shape.

```text
                          ┌─────────────────────────────┐
                          │   Scheduler / Orchestrator  │
                          │   (cron → Airflow in Phase5)│
                          └──────────────┬──────────────┘
                                         │
        ┌────────────────┬───────────────┼───────────────┬────────────────┐
        ▼                ▼               ▼               ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ OHLCV Worker │ │Intraday/Trade│ │ Fundamentals │ │ News Worker  │ │Filings Worker│
│   (Phase 2)  │ │   Worker     │ │   Worker     │ │  (Phase 5)   │ │  (Phase 5)   │
│              │ │  (Phase 3)   │ │  (Phase 4)   │ │              │ │              │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │                │                │
       └────────┬───────┴────────┬───────┴────────┬───────┴────────┬───────┘
                ▼                ▼                ▼                ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │                     Object Storage (S3 / R2 / MinIO)             │
       │                                                                  │
       │  raw/{provider}/{domain}/{date}/      ← immutable originals      │
       │  parquet/{domain}/{partition}/        ← normalized canonical     │
       │  documents/{domain}/{id}/             ← binary files (Phase 5+)  │
       │  extracted/{domain}/{id}/             ← parsed text (Phase 6)    │
       └──────────────────────────────────────────────────────────────────┘
                                          │
       ┌──────────────────────────────────┼──────────────────────────────┐
       ▼                                  ▼                              ▼
┌──────────────────┐            ┌──────────────────┐           ┌──────────────────┐
│   PostgreSQL     │            │    DuckDB        │           │  Search Index    │
│                  │            │   (embedded)     │           │ (Phase 6)        │
│ • Instruments    │            │                  │           │                  │
│ • Companies      │            │ Analytical SQL   │           │ Full-text +      │
│ • Exchanges      │            │ over Parquet     │           │ semantic search  │
│ • Jobs / Quality │            │                  │           │ over extracted   │
│ • Rejections     │            │                  │           │ text             │
│ • Vector store   │            │                  │           │                  │
│   (Phase 6)      │            │                  │           │                  │
└────────┬─────────┘            └────────┬─────────┘           └────────┬─────────┘
         │                               │                              │
         └───────────────┬───────────────┴──────────────────────────────┘
                         ▼
              ┌──────────────────────┐
              │   API Service        │
              │   (FastAPI)          │
              │                      │
              │  /v1/instruments     │
              │  /v1/ohlcv           │
              │  /v1/intraday        │
              │  /v1/fundamentals    │
              │  /v1/news            │
              │  /v1/filings         │
              │  /v1/search          │
              └──────────┬───────────┘
                         ▼
              Downstream consumers
         (App, notebooks, BI, AI/ML)
```

**Core architectural invariants (apply to every phase):**

1. Raw provider data is always written to object storage before any parsing.
2. Canonical data is always derived from raw data and can be rebuilt from it.
3. PostgreSQL holds metadata and identities, never market or document data.
4. Parquet is the canonical analytical format for time-series and tabular data.
5. Every ingestion run produces a job record with status, counts, and quality metrics.
6. All writes to a given partition are idempotent — reruns overwrite, never duplicate.

---

## 4. Cross-cutting concerns

These concerns apply to every phase and are established in Phase 1.

### 4.1 Reliability

| Guarantee | Mechanism |
|---|---|
| Raw data is never lost | Raw payload is written to object storage before parsing begins |
| Safe retries | Jobs are idempotent; rerunning a date overwrites the target partition |
| No duplicate records | Partition-level atomic writes (write to temp key, then move) |
| Failed data is tracked | Rejected records stored in PostgreSQL with reason codes |
| Job status is auditable | Every run creates a job record with status, timing, counts |
| Data is rebuildable | Any Parquet partition can be regenerated from preserved raw data |

### 4.2 Security

- Provider credentials loaded from environment variables or a secrets manager.
- Credentials never committed to source control (`.env` gitignored).
- Object storage buckets private by default; no public read access.
- API endpoints require authentication (API key or bearer token) outside the local environment.
- PostgreSQL access restricted to the ingestion worker and API service.
- PII and sensitive metadata handled according to data-classification policy.

### 4.3 Observability

| Concern | Approach |
|---|---|
| Logging | Structured JSON logs via `structlog`; every log line includes `job_id` and `domain` |
| Metrics | Job-level metrics (duration, record count, rejection count) stored in PostgreSQL; exported to Prometheus in Phase 3+ |
| Alerting | Phase 1–2: manual review of job status. Phase 3+: alerts on job failure, rejection rate threshold, or freshness SLA breach |
| Tracing | Added in Phase 3 via OpenTelemetry |

### 4.4 Local deployment

Docker Compose provides the local development environment. Services grow per phase:

| Service | Phase 1 | Phase 2 | Phase 3 | Phase 5 | Phase 6 |
|---|---|---|---|---|---|
| PostgreSQL | ✓ | ✓ | ✓ | ✓ | ✓ |
| MinIO | ✓ | ✓ | ✓ | ✓ | ✓ |
| Ingestion Worker(s) | scaffold | OHLCV | +intraday | +news, filings | +extraction |
| API Service (FastAPI) | — | ✓ | ✓ | ✓ | ✓ |
| Search Index | — | — | — | — | ✓ |
| Vector DB / pgvector | — | — | — | — | ✓ |

---

## 5. Phase 1 — Platform foundation

### 5.1 Scope

Deliver the development and storage environment that every subsequent phase builds on. No market data flows through the system yet.

### 5.2 Components

- **Repository structure** with clear separation between workers, API, shared libraries, and infrastructure.
- **Docker Compose** defining PostgreSQL and MinIO services.
- **PostgreSQL** with schema-migration framework (e.g., Alembic) and initial tables: `providers`, `exchanges`, `companies`, `instruments`, `ingestion_jobs`, `job_steps`, `rejected_records`, `quality_results`.
- **MinIO** configured as a local S3-compatible object store with bucket lifecycle rules.
- **Object-storage abstraction** providing a uniform interface over MinIO (local) and S3/R2 (production).
- **Python environment** with shared libraries for logging, configuration, and provider-client base classes.
- **Logging foundation** using `structlog` with JSON output and `job_id` correlation.

### 5.3 Deliverables

- A developer can run `docker compose up` and have PostgreSQL + MinIO available.
- Migrations run cleanly against a fresh database.
- Object-storage abstraction passes integration tests against MinIO.
- A sample ingestion job skeleton writes a job record to PostgreSQL and a test file to MinIO.

### 5.4 Phase 1 boundary

**Included:** infrastructure, migrations, abstractions, logging, sample job skeleton.
**Excluded:** any real provider integration, market data, API.

---

## 6. Phase 2 — Core market and master data

### 6.1 Scope

Deliver the first complete vertical slice: instrument master data plus daily OHLCV from one provider, end-to-end from ingestion to API.

### 6.2 Components

**Instrument master loader**
- Ingests companies, exchanges, and instruments from the provider.
- Writes canonical records to PostgreSQL.
- Maintains a `provider_symbols` JSONB mapping on each instrument for symbol resolution during OHLCV ingestion.

**OHLCV ingestion worker**
- Calls the provider's REST API with pagination, rate limiting, and exponential-backoff retries.
- Writes the raw response to `raw/{provider}/ohlcv/{date}/` before any parsing.
- Resolves each record's provider symbol to an internal `instrument_id` via the instrument master.
- Validates records (non-null OHLCV, positive volume, price within plausible range, no future dates, no duplicate dates per instrument).
- Normalizes to the canonical OHLCV schema.
- Writes normalized records to `parquet/ohlcv/{exchange}/{year}/` with atomic partition replacement.
- Writes job metadata, quality metrics, and rejected records to PostgreSQL.

**DuckDB (embedded in API service)**
- Reads Parquet files directly from object storage.
- Executes SQL queries for API responses.

**FastAPI service**
- Serves versioned REST endpoints.
- Reads metadata from PostgreSQL, market data via embedded DuckDB.

### 6.3 Canonical data models

**OHLCV (Parquet)**

| Column | Type | Description |
|---|---|---|
| `instrument_id` | UUID | Internal instrument identifier |
| `date` | DATE | Trading date |
| `open` | DECIMAL(18,6) | Opening price |
| `high` | DECIMAL(18,6) | Highest price |
| `low` | DECIMAL(18,6) | Lowest price |
| `close` | DECIMAL(18,6) | Closing price |
| `volume` | BIGINT | Trading volume |
| `provider` | VARCHAR | Source provider identifier |
| `ingested_at` | TIMESTAMP | When the record was ingested |

Partitioning: `parquet/ohlcv/{exchange}/{year}/`

**Instrument (PostgreSQL)**

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `symbol` | VARCHAR | Internal canonical symbol |
| `name` | VARCHAR | Instrument name |
| `exchange_id` | UUID | FK to `exchanges` |
| `company_id` | UUID | FK to `companies` (nullable) |
| `asset_class` | VARCHAR | `equity`, `etf`, `bond`, etc. |
| `currency` | VARCHAR | ISO 4217 currency code |
| `provider_symbols` | JSONB | `{provider_id: provider_symbol}` |
| `status` | VARCHAR | `active`, `delisted`, `unknown` |
| `created_at`, `updated_at` | TIMESTAMP | Audit timestamps |

**Ingestion job (PostgreSQL)**

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `provider_id` | UUID | FK to `providers` |
| `domain` | VARCHAR | `ohlcv`, `intraday`, `fundamentals`, etc. |
| `target_date` | DATE | Date or period the job covers |
| `status` | VARCHAR | `pending`, `running`, `succeeded`, `failed` |
| `started_at`, `finished_at` | TIMESTAMP | Timing |
| `records_fetched` | INTEGER | Records received from provider |
| `records_accepted` | INTEGER | Records written to canonical storage |
| `records_rejected` | INTEGER | Records that failed validation |
| `error_message` | TEXT | Failure reason (nullable) |

### 6.4 API design

| Endpoint | Method | Description |
|---|---|---|
| `/v1/instruments` | GET | List instruments (filters: `exchange`, `asset_class`, `status`) |
| `/v1/instruments/{id}` | GET | Single instrument detail |
| `/v1/ohlcv` | GET | Query OHLCV (params: `instrument_id`, `start_date`, `end_date`) |
| `/v1/ohlcv/batch` | POST | Query OHLCV for multiple instruments |
| `/v1/jobs` | GET | List ingestion jobs (filters: `provider`, `domain`, `status`) |
| `/v1/jobs/{id}` | GET | Job detail with quality summary |
| `/v1/health` | GET | Service health and latest job freshness |

All responses use JSON. List endpoints use cursor-based pagination. OHLCV responses return arrays of records.

### 6.5 Validation rules (Phase 2)

- OHLCV fields non-null.
- `high >= low`, `high >= open`, `high >= close`, `low <= open`, `low <= close`.
- `volume >= 0`.
- Prices within ±50% of previous close (configurable per instrument).
- No future dates.
- No duplicate `(instrument_id, date)` within a single job.

### 6.6 Phase 2 boundary

**Included:** one provider, daily OHLCV, instrument master, raw preservation, validation, normalization, Parquet storage, DuckDB queries, FastAPI.
**Excluded:** intraday, order book, fundamentals, corporate actions, news, filings, search, AI features.

---

## 7. Phase 3 — High-volume market data

### 7.1 Scope

Extend the market-data pipeline to intraday prices, trades, and order-book data. This phase introduces high-volume storage patterns and is gated on measured volume and latency requirements from Phase 2.

### 7.2 Key design decisions

- **Partitioning changes:** intraday data partitions by `{exchange}/{year}/{month}/{day}`; order-book data partitions by `{exchange}/{symbol}/{date}`.
- **Compaction:** small Parquet files produced during the day are compacted into larger files overnight to keep query performance stable.
- **Latest-state cache:** Redis is introduced to serve the latest order-book snapshot and last-trade price, avoiding Parquet scans for hot queries.
- **Historical replay:** a dedicated replay worker can reconstruct any historical intraday window from Parquet for backtesting.
- **Observability upgrade:** OpenTelemetry tracing added; Prometheus metrics exported.

### 7.3 New canonical models

**Intraday bar (Parquet)**

| Column | Type |
|---|---|
| `instrument_id` | UUID |
| `timestamp` | TIMESTAMP |
| `interval` | VARCHAR (`1m`, `5m`, `1h`) |
| `open`, `high`, `low`, `close` | DECIMAL(18,6) |
| `volume` | BIGINT |
| `provider` | VARCHAR |
| `ingested_at` | TIMESTAMP |

**Trade (Parquet)**

| Column | Type |
|---|---|
| `instrument_id` | UUID |
| `timestamp` | TIMESTAMP |
| `price` | DECIMAL(18,6) |
| `volume` | BIGINT |
| `side` | VARCHAR (`buy`, `sell`, `unknown`) |
| `trade_id` | VARCHAR |
| `provider` | VARCHAR |
| `ingested_at` | TIMESTAMP |

**Order-book snapshot (Parquet)**

| Column | Type |
|---|---|
| `instrument_id` | UUID |
| `timestamp` | TIMESTAMP |
| `bids` | ARRAY(STRUCT(price DECIMAL, volume BIGINT)) |
| `asks` | ARRAY(STRUCT(price DECIMAL, volume BIGINT)) |
| `sequence` | BIGINT |
| `provider` | VARCHAR |
| `ingested_at` | TIMESTAMP |

### 7.4 New API endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/v1/intraday` | GET | Intraday bars (params: `instrument_id`, `interval`, `start`, `end`) |
| `/v1/trades` | GET | Trade history |
| `/v1/orderbook/snapshot` | GET | Latest or historical snapshot |
| `/v1/orderbook/latest` | GET | Latest snapshot (served from Redis) |

### 7.5 Phase 3 boundary

**Included:** intraday, trades, order-book snapshots, compaction, Redis cache, replay, OpenTelemetry.
**Excluded:** order-book event stream (L3), fundamentals, corporate actions, news, filings.
**Gate:** phase begins only after Phase 2 volume, latency, and retention requirements are measured.

---

## 8. Phase 4 — Fundamental and corporate data

### 8.1 Scope

Add financial statements and corporate actions. This data is low-volume but high-complexity due to restatements, multiple accounting standards, and hierarchical schemas.

### 8.2 Key design decisions

- **Storage choice:** fundamentals are stored in PostgreSQL (not Parquet) because they are frequently joined with instrument metadata and require transactional updates when restatements arrive.
- **Versioning:** every restatement creates a new version of the statement; queries default to the latest version but can request any historical version.
- **Accounting standards:** statements are tagged with `accounting_standard` (`gaap`, `ifrs`) and normalized into a canonical chart of accounts where possible.

### 8.3 Canonical models

**Income statement, balance sheet, cash flow (PostgreSQL)**

Each statement type has its own table with a canonical set of line items as columns, plus:

| Column | Type |
|---|---|
| `id` | UUID |
| `company_id` | UUID |
| `period_type` | VARCHAR (`annual`, `quarterly`, `ttm`) |
| `period_end_date` | DATE |
| `filed_at` | TIMESTAMP |
| `restated_at` | TIMESTAMP (nullable) |
| `version` | INTEGER |
| `accounting_standard` | VARCHAR |
| `currency` | VARCHAR |
| `provider` | VARCHAR |
| `line items...` | DECIMAL(20,4) |

**Corporate action (PostgreSQL)**

| Column | Type |
|---|---|
| `id` | UUID |
| `instrument_id` | UUID |
| `action_type` | VARCHAR (`dividend`, `split`, `merger`, `rights_issue`) |
| `ex_date`, `record_date`, `pay_date` | DATE |
| `announcement_date` | DATE |
| `details` | JSONB |
| `provider` | VARCHAR |

### 8.4 New API endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/v1/fundamentals/income-statement` | GET | Income statement (params: `company_id`, `period_type`) |
| `/v1/fundamentals/balance-sheet` | GET | Balance sheet |
| `/v1/fundamentals/cash-flow` | GET | Cash flow statement |
| `/v1/fundamentals/ratios` | GET | Derived financial ratios |
| `/v1/corporate-actions` | GET | Corporate actions for an instrument |

### 8.5 Phase 4 boundary

**Included:** three financial statements, ratios, corporate actions, restatement versioning.
**Excluded:** news, filings, search, AI features.

---

## 9. Phase 5 — Alternative and information data

### 9.1 Scope

Add news and regulatory filings. This phase introduces unstructured data, document storage, and the first steps toward text processing.

### 9.2 Key design decisions

- **Documents stored as binaries** in object storage under `documents/{domain}/{id}/`; metadata in PostgreSQL.
- **News deduplication** via headline + source + time-window hashing; duplicates are linked rather than stored twice.
- **Company/instrument mapping** uses a lightweight keyword matcher in Phase 5; semantic matching deferred to Phase 6.
- **Filing metadata** captured (type, date, company, URL); raw document preserved; text extraction deferred to Phase 6.

### 9.3 Canonical models

**News (PostgreSQL + object storage)**

| Column | Type |
|---|---|
| `id` | UUID |
| `headline` | VARCHAR |
| `body` | TEXT |
| `source` | VARCHAR |
| `published_at` | TIMESTAMP |
| `dedupe_hash` | VARCHAR |
| `related_instruments` | UUID[] |
| `related_companies` | UUID[] |
| `raw_url` | VARCHAR |
| `provider` | VARCHAR |

**Filing (PostgreSQL + object storage)**

| Column | Type |
|---|---|
| `id` | UUID |
| `company_id` | UUID |
| `filing_type` | VARCHAR (`10-K`, `10-Q`, `8-K`, etc.) |
| `filed_at` | TIMESTAMP |
| `period_end_date` | DATE |
| `document_url` | VARCHAR |
| `document_storage_key` | VARCHAR |
| `metadata` | JSONB |
| `provider` | VARCHAR |

### 9.4 New API endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/v1/news` | GET | News list (params: `query`, `instrument_id`, `company_id`, `start`, `end`) |
| `/v1/news/{id}` | GET | Single news article |
| `/v1/filings` | GET | Filing list (params: `company_id`, `filing_type`, `start`, `end`) |
| `/v1/filings/{id}` | GET | Filing metadata |
| `/v1/filings/{id}/document` | GET | Download raw document |

### 9.5 Phase 5 boundary

**Included:** news ingestion, deduplication, instrument mapping, filing metadata, document storage.
**Excluded:** text extraction, full-text search, semantic search, embeddings, AI-facing interfaces.

---

## 10. Phase 6 — AI-ready data services

### 10.1 Scope

Make the platform's data directly consumable by AI and analytics systems. This phase adds text extraction, search, embeddings, and feature engineering.

### 10.2 Key design decisions

- **Document text extraction** via PDF/HTML parsers; extracted text stored in object storage under `extracted/{domain}/{id}/`.
- **Full-text search** via PostgreSQL FTS for Phase 6 GA; Elasticsearch considered if query volume or relevance requirements exceed PostgreSQL FTS capabilities.
- **Semantic search** via embeddings stored in `pgvector` (PostgreSQL extension); embeddings generated by a configurable model so the model can be swapped without re-architecting.
- **Feature engineering** exposed as materialized views and pre-computed Parquet datasets for ML consumption.
- **AI-facing interfaces** expose clean, versioned, traceable datasets; AI components never scrape external providers directly.

### 10.3 New components

- **Extraction worker:** parses documents, writes extracted text to object storage, indexes into search.
- **Embedding worker:** generates embeddings for news headlines, filing sections, and other text; stores in `pgvector`.
- **Feature store:** materialized views and Parquet datasets of engineered features (rolling averages, ratios, sentiment scores).

### 10.4 New API endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/v1/search` | GET | Full-text + semantic search across news and filings |
| `/v1/filings/{id}/text` | GET | Extracted text of a filing |
| `/v1/filings/{id}/sections` | GET | Structured sections of a filing |
| `/v1/features/{name}` | GET | Pre-computed feature dataset |
| `/v1/embeddings` | POST | Generate embeddings for arbitrary text (internal use) |

### 10.5 Phase 6 boundary

**Included:** text extraction, full-text search, semantic search, embeddings, feature store, AI-facing interfaces.
**Excluded:** proprietary LLM training, trading execution, real-time streaming infrastructure.

---

## 11. Storage strategy (final state)

| Storage | Content | Phase introduced |
|---|---|---|
| PostgreSQL | Instruments, companies, exchanges, fundamentals, corporate actions, news metadata, filing metadata, jobs, quality, rejections, embeddings (pgvector) | 1 |
| Object Storage — `raw/` | Immutable provider payloads | 1 |
| Object Storage — `parquet/` | Normalized OHLCV, intraday, trades, order-book, features | 2 |
| Object Storage — `documents/` | Binary filings, news attachments | 5 |
| Object Storage — `extracted/` | Parsed text from documents | 6 |
| DuckDB (embedded) | Analytical queries over Parquet | 2 |
| Redis | Latest order-book snapshot, last-trade price, hot API responses | 3 |
| pgvector (PostgreSQL) | Embeddings for semantic search | 6 |

---

## 12. Known trade-offs and risks

| Trade-off | Rationale | Risk / Mitigation |
|---|---|---|
| DuckDB embedded in FastAPI | Simple deployment; no separate service. | Query load shares resources with HTTP. Mitigation: move DuckDB to a dedicated worker if latency SLAs are breached. |
| Fundamentals in PostgreSQL, not Parquet | Frequent joins with metadata; transactional updates for restatements. | Analytical queries over large fundamentals history may be slower than Parquet. Mitigation: materialize analytical views periodically. |
| No orchestration framework in Phase 1–2 | Cron is sufficient for one provider and one data type. | Multi-pipeline coordination in Phase 5+ becomes painful. Mitigation: introduce Airflow/Prefect at Phase 5. |
| JSONB for provider symbol mapping | Flexible for Phase 2. | Query performance degrades at scale. Mitigation: normalize into a join table in Phase 3. |
| PostgreSQL FTS before Elasticsearch | Avoids extra infrastructure in Phase 6. | Relevance and scale limits. Mitigation: migrate to Elasticsearch if needed; schema is compatible. |
| Single ingestion worker per domain in Phase 2–3 | Simple; no concurrency issues. | Throughput ceiling. Mitigation: partition workers by exchange or symbol range in Phase 3+. |
| Parquet append/overwrite model | Simple and correct for batch data. | Concurrent writes require care. Mitigation: atomic partition-level writes; no concurrent writers to the same partition. |

**Top risks:**

1. **Provider schema instability** — providers change APIs without notice. Mitigation: provider adapters are isolated; raw preservation allows reprocessing after schema changes.
2. **Data volume surprises in Phase 3** — intraday and order-book data can be 100x larger than estimated. Mitigation: Phase 3 is gated on measured Phase 2 volumes.
3. **Document parsing quality in Phase 6** — PDFs vary widely in structure. Mitigation: extraction quality is measured; fallback to manual review for low-confidence parses.

---

## 13. Definition of product success

The platform is successful when:

- A new provider can be added through an adapter without changing core code.
- Raw data is preserved and auditable for every ingested record.
- Canonical data can be regenerated from raw data at any time.
- Backfills and incremental updates are supported for every domain.
- Repeated jobs never create duplicate records.
- Data-quality failures are visible and actionable.
- Applications can query all domains through stable, versioned APIs.
- Future analytics and AI systems can consume the platform without directly depending on external providers.

---

## 14. Non-goals

The platform will not build:

- Trading execution or high-frequency trading infrastructure.
- Investment advice or automated financial decisions.
- A proprietary large language model.
- A complete data warehouse replacing analytical databases.
- Kafka or distributed streaming infrastructure (unless Phase 3 measurements require it).
- Spark processing (unless Phase 3 measurements require it).
- Kubernetes deployment (unless operational scale requires it).
- Full sentiment-analysis systems (embeddings and search only).

These may be considered later if product requirements and measured workloads justify them.
