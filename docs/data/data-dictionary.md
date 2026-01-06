# Data Dictionary

**Product:** Financial Data Platform  
**Owner:** Product and Engineering  
**Last updated:** 6 January 2026  

---

## Overview

This document defines the canonical PostgreSQL schema for the Financial Data Platform. It covers reference data, operational metadata, data quality tracking, and all domain-specific datasets across the platform's six delivery phases.

**Design principles:**

1. **Single source of truth** — each entity has one canonical representation.
2. **Auditability** — all records track creation, updates, and source provenance.
3. **Idempotency** — schema supports safe retries and reruns without duplicates.
4. **Queryability** — indexes and partitioning optimized for common access patterns.
5. **Extensibility** — JSONB columns used where schema evolution is expected.

---

## Schema conventions

### Identifiers

All primary keys use `UUID` type, generated via `gen_random_uuid()`. UUIDs provide:

- Global uniqueness across distributed systems.
- No information leakage (unlike sequential IDs).
- Safe merging of data from multiple sources.

Foreign keys reference the primary key of the related table.

### Timestamps

All timestamps use `TIMESTAMP WITH TIME ZONE` and are normalized to UTC.

- `created_at` — set once on insert, never updated.
- `updated_at` — updated on every modification via trigger.
- Domain-specific timestamps (e.g., `published_at`, `filed_at`) retain the original event time.

### Currencies

All currency fields use `CHAR(3)` with ISO 4217 codes (e.g., `USD`, `EUR`, `JPY`).

### Status values

Status fields use `VARCHAR` with a controlled vocabulary enforced via `CHECK` constraints. Permitted values are documented per table.

### Null values

Missing data is stored as `NULL`. Placeholder strings (`N/A`, `unknown`, `-`) are prohibited.

### JSONB usage

JSONB columns are used for:

- Provider-specific symbol mappings (flexible schema evolution).
- Validation summaries (variable structure per validation rule).
- Filing metadata (varies by filing type and provider).
- Corporate action details (varies by action type).

JSONB columns are indexed via GIN when frequently queried.

### Soft deletes

Records are not physically deleted. A `status` field indicates logical deletion (`inactive`, `delisted`). Hard deletes are prohibited except for temporary staging tables.

### Audit columns

Every table includes:

- `created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()`
- `updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()`

An `updated_at` trigger automatically updates the timestamp on row modification.

---

## Reference data tables

### companies

Represents legal entities that issue securities.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `company_id` | UUID | NO | Primary key |
| `name` | VARCHAR(255) | NO | Common display name |
| `legal_name` | VARCHAR(255) | YES | Registered legal name |
| `country` | CHAR(2) | NO | ISO 3166-1 alpha-2 country code |
| `sector` | VARCHAR(100) | YES | GICS sector |
| `industry` | VARCHAR(100) | YES | GICS industry |
| `status` | VARCHAR(20) | NO | `active`, `inactive` |
| `created_at` | TIMESTAMPTZ | NO | Record creation time |
| `updated_at` | TIMESTAMPTZ | NO | Last modification time |

**Constraints:**

- `CHECK (status IN ('active', 'inactive'))`
- `CHECK (country ~ '^[A-Z]{2}$')`

**Indexes:**

- `idx_companies_name` on `name`
- `idx_companies_country` on `country`
- `idx_companies_status` on `status`

---

### exchanges

Represents trading venues.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `exchange_id` | UUID | NO | Primary key |
| `name` | VARCHAR(255) | NO | Exchange display name |
| `mic_code` | CHAR(4) | YES | ISO 10383 Market Identifier Code |
| `acronym` | VARCHAR(20) | YES | Common abbreviation (e.g., `NYSE`) |
| `country` | CHAR(2) | NO | ISO 3166-1 alpha-2 country code |
| `timezone` | VARCHAR(50) | NO | IANA timezone (e.g., `America/New_York`) |
| `currency` | CHAR(3) | NO | Default trading currency (ISO 4217) |
| `status` | VARCHAR(20) | NO | `active`, `inactive` |
| `created_at` | TIMESTAMPTZ | NO | Record creation time |
| `updated_at` | TIMESTAMPTZ | NO | Last modification time |

**Constraints:**

- `CHECK (status IN ('active', 'inactive'))`
- `CHECK (country ~ '^[A-Z]{2}$')`
- `CHECK (currency ~ '^[A-Z]{3}$')`
- `UNIQUE (mic_code)` where `mic_code IS NOT NULL`

**Indexes:**

- `idx_exchanges_name` on `name`
- `idx_exchanges_country` on `country`

---

### instruments

Represents tradeable securities (stocks, ETFs, bonds, etc.).

| Column | Type | Nullable | Description |
|---|---|---|---|
| `instrument_id` | UUID | NO | Primary key |
| `company_id` | UUID | YES | FK to `companies` (nullable for ETFs, indices) |
| `exchange_id` | UUID | NO | FK to `exchanges` |
| `symbol` | VARCHAR(20) | NO | Canonical display symbol |
| `name` | VARCHAR(255) | NO | Instrument name |
| `isin` | CHAR(12) | YES | ISO 6166 International Securities ID |
| `cusip` | CHAR(9) | YES | CUSIP identifier (North America) |
| `sedol` | VARCHAR(7) | YES | SEDOL identifier (UK) |
| `asset_class` | VARCHAR(20) | NO | `equity`, `etf`, `bond`, `option`, `future`, `other` |
| `currency` | CHAR(3) | NO | Trading currency (ISO 4217) |
| `lot_size` | INTEGER | YES | Minimum trading lot size |
| `status` | VARCHAR(20) | NO | `active`, `inactive`, `delisted` |
| `delisted_at` | DATE | YES | Delisting date (if applicable) |
| `created_at` | TIMESTAMPTZ | NO | Record creation time |
| `updated_at` | TIMESTAMPTZ | NO | Last modification time |

**Constraints:**

- `CHECK (status IN ('active', 'inactive', 'delisted'))`
- `CHECK (asset_class IN ('equity', 'etf', 'bond', 'option', 'future', 'other'))`
- `CHECK (currency ~ '^[A-Z]{3}$')`
- `UNIQUE (exchange_id, symbol)` — symbol unique per exchange
- `UNIQUE (isin)` where `isin IS NOT NULL`

**Indexes:**

- `idx_instruments_company` on `company_id`
- `idx_instruments_exchange` on `exchange_id`
- `idx_instruments_symbol` on `symbol`
- `idx_instruments_asset_class` on `asset_class`
- `idx_instruments_status` on `status`

---

### provider_instrument_mappings

Maps internal instrument IDs to provider-specific symbols. Supports historical mappings (e.g., ticker changes).

| Column | Type | Nullable | Description |
|---|---|---|---|
| `mapping_id` | UUID | NO | Primary key |
| `instrument_id` | UUID | NO | FK to `instruments` |
| `provider` | VARCHAR(50) | NO | Provider identifier (e.g., `alpha_vantage`, `polygon`) |
| `provider_symbol` | VARCHAR(50) | NO | Provider-specific symbol |
| `valid_from` | DATE | YES | Mapping validity start (nullable = since inception) |
| `valid_to` | DATE | YES | Mapping validity end (nullable = still valid) |
| `created_at` | TIMESTAMPTZ | NO | Record creation time |

**Constraints:**

- `CHECK (valid_to IS NULL OR valid_to >= valid_from)`
- `UNIQUE (provider, provider_symbol, valid_from)` — prevent overlapping validity periods

**Indexes:**

- `idx_provider_mappings_instrument` on `instrument_id`
- `idx_provider_mappings_provider_symbol` on `provider, provider_symbol`
- `idx_provider_mappings_validity` on `provider, provider_symbol, valid_from, valid_to`

**Usage:** During ingestion, resolve provider symbol to internal `instrument_id` by querying:

```sql
SELECT instrument_id
FROM provider_instrument_mappings
WHERE provider = $1
  AND provider_symbol = $2
  AND (valid_from IS NULL OR valid_from <= $3)
  AND (valid_to IS NULL OR valid_to >= $3)
LIMIT 1;
```

---

## Operational metadata tables

### data_sources

Represents external data providers.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `data_source_id` | UUID | NO | Primary key |
| `name` | VARCHAR(100) | NO | Provider display name |
| `provider_key` | VARCHAR(50) | NO | Unique provider identifier (e.g., `alpha_vantage`) |
| `provider_type` | VARCHAR(20) | NO | `market`, `fundamentals`, `news`, `filings` |
| `base_url` | VARCHAR(500) | YES | API base URL |
| `auth_type` | VARCHAR(20) | YES | `api_key`, `oauth2`, `none` |
| `rate_limit` | INTEGER | YES | Requests per minute |
| `status` | VARCHAR(20) | NO | `active`, `inactive` |
| `created_at` | TIMESTAMPTZ | NO | Record creation time |
| `updated_at` | TIMESTAMPTZ | NO | Last modification time |

**Constraints:**

- `CHECK (provider_type IN ('market', 'fundamentals', 'news', 'filings'))`
- `CHECK (status IN ('active', 'inactive'))`
- `UNIQUE (provider_key)`

**Indexes:**

- `idx_data_sources_provider_type` on `provider_type`

---

### datasets

Represents logical data collections (e.g., `daily_ohlcv`, `income_statement`).

| Column | Type | Nullable | Description |
|---|---|---|---|
| `dataset_id` | UUID | NO | Primary key |
| `name` | VARCHAR(100) | NO | Dataset name |
| `dataset_key` | VARCHAR(50) | NO | Unique dataset identifier (e.g., `ohlcv_daily`) |
| `domain` | VARCHAR(20) | NO | `market`, `corporate`, `information` |
| `description` | TEXT | YES | Dataset purpose and contents |
| `schema_version` | INTEGER | NO | Canonical schema version |
| `storage_type` | VARCHAR(20) | NO | `parquet`, `postgresql` |
| `status` | VARCHAR(20) | NO | `active`, `inactive` |
| `created_at` | TIMESTAMPTZ | NO | Record creation time |
| `updated_at` | TIMESTAMPTZ | NO | Last modification time |

**Constraints:**

- `CHECK (domain IN ('market', 'corporate', 'information'))`
- `CHECK (storage_type IN ('parquet', 'postgresql'))`
- `CHECK (status IN ('active', 'inactive'))`
- `UNIQUE (dataset_key)`

**Indexes:**

- `idx_datasets_domain` on `domain`

---

### ingestion_jobs

Tracks every ingestion run.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `job_id` | UUID | NO | Primary key |
| `data_source_id` | UUID | NO | FK to `data_sources` |
| `dataset_id` | UUID | NO | FK to `datasets` |
| `job_type` | VARCHAR(20) | NO | `backfill`, `incremental` |
| `target_date` | DATE | YES | Date or period end date (nullable for streaming) |
| `status` | VARCHAR(20) | NO | `pending`, `running`, `succeeded`, `partial`, `failed` |
| `started_at` | TIMESTAMPTZ | YES | Job start time |
| `completed_at` | TIMESTAMPTZ | YES | Job completion time |
| `records_received` | BIGINT | NO | Records returned by provider |
| `records_valid` | BIGINT | NO | Records passing validation |
| `records_invalid` | BIGINT | NO | Records failing validation |
| `records_duplicate` | BIGINT | NO | Duplicate records detected |
| `records_written` | BIGINT | NO | Records written to storage |
| `error_message` | TEXT | YES | Failure reason |
| `created_at` | TIMESTAMPTZ | NO | Job creation time |

**Constraints:**

- `CHECK (job_type IN ('backfill', 'incremental'))`
- `CHECK (status IN ('pending', 'running', 'succeeded', 'partial', 'failed'))`
- `CHECK (records_received >= 0)`
- `CHECK (records_valid >= 0)`
- `CHECK (records_invalid >= 0)`
- `CHECK (records_duplicate >= 0)`
- `CHECK (records_written >= 0)`

**Indexes:**

- `idx_jobs_data_source` on `data_source_id`
- `idx_jobs_dataset` on `dataset_id`
- `idx_jobs_status` on `status`
- `idx_jobs_target_date` on `target_date`
- `idx_jobs_created` on `created_at DESC`

**Partitioning:** Partition by `created_at` (monthly) for jobs older than 1 year.

---

### rejected_records

Stores individual records that failed validation.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `rejection_id` | UUID | NO | Primary key |
| `job_id` | UUID | NO | FK to `ingestion_jobs` |
| `dataset_id` | UUID | NO | FK to `datasets` |
| `record_data` | JSONB | NO | Original record payload |
| `rejection_reason` | VARCHAR(100) | NO | Reason code (e.g., `invalid_price`, `missing_field`) |
| `rejection_details` | TEXT | YES | Human-readable explanation |
| `created_at` | TIMESTAMPTZ | NO | Rejection time |

**Constraints:**

- `CHECK (rejection_reason IN ('invalid_price', 'missing_field', 'duplicate', 'out_of_range', 'schema_mismatch', 'other'))`

**Indexes:**

- `idx_rejections_job` on `job_id`
- `idx_rejections_reason` on `rejection_reason`
- `idx_rejections_created` on `created_at DESC`

**Partitioning:** Partition by `created_at` (monthly). Retain for 90 days, then archive or delete.

---

## Domain-specific tables (Phase 4+)

### fundamentals_income_statement

Canonical income statement data. One row per company per reporting period.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `statement_id` | UUID | NO | Primary key |
| `company_id` | UUID | NO | FK to `companies` |
| `period_type` | VARCHAR(20) | NO | `annual`, `quarterly`, `ttm` |
| `period_end_date` | DATE | NO | Period end date |
| `filed_at` | TIMESTAMPTZ | NO | Filing timestamp |
| `restated_at` | TIMESTAMPTZ | YES | Restatement timestamp (if applicable) |
| `version` | INTEGER | NO | Statement version (1 = initial, 2+ = restated) |
| `accounting_standard` | VARCHAR(10) | NO | `gaap`, `ifrs` |
| `currency` | CHAR(3) | NO | Reporting currency |
| `revenue` | DECIMAL(20,4) | YES | Total revenue |
| `cost_of_revenue` | DECIMAL(20,4) | YES | Cost of goods sold |
| `gross_profit` | DECIMAL(20,4) | YES | Gross profit |
| `operating_expenses` | DECIMAL(20,4) | YES | Total operating expenses |
| `operating_income` | DECIMAL(20,4) | YES | Operating income |
| `net_income` | DECIMAL(20,4) | YES | Net income |
| `eps_basic` | DECIMAL(10,4) | YES | Basic earnings per share |
| `eps_diluted` | DECIMAL(10,4) | YES | Diluted earnings per share |
| `provider` | VARCHAR(50) | NO | Data source provider |
| `created_at` | TIMESTAMPTZ | NO | Record creation time |
| `updated_at` | TIMESTAMPTZ | NO | Last modification time |

**Constraints:**

- `CHECK (period_type IN ('annual', 'quarterly', 'ttm'))`
- `CHECK (accounting_standard IN ('gaap', 'ifrs'))`
- `CHECK (currency ~ '^[A-Z]{3}$')`
- `CHECK (version >= 1)`
- `UNIQUE (company_id, period_type, period_end_date, version)`

**Indexes:**

- `idx_income_company_period` on `company_id, period_type, period_end_date DESC`
- `idx_income_filed` on `filed_at DESC`

---

### corporate_actions

Tracks corporate events affecting instruments.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `action_id` | UUID | NO | Primary key |
| `instrument_id` | UUID | NO | FK to `instruments` |
| `action_type` | VARCHAR(30) | NO | `dividend`, `split`, `merger`, `rights_issue`, `other` |
| `announcement_date` | DATE | YES | Announcement date |
| `ex_date` | DATE | YES | Ex-dividend/ex-event date |
| `record_date` | DATE | YES | Record date |
| `pay_date` | DATE | YES | Payment/execution date |
| `details` | JSONB | YES | Action-specific details (e.g., dividend amount, split ratio) |
| `provider` | VARCHAR(50) | NO | Data source provider |
| `created_at` | TIMESTAMPTZ | NO | Record creation time |
| `updated_at` | TIMESTAMPTZ | NO | Last modification time |

**Constraints:**

- `CHECK (action_type IN ('dividend', 'split', 'merger', 'rights_issue', 'other'))`

**Indexes:**

- `idx_actions_instrument` on `instrument_id`
- `idx_actions_type` on `action_type`
- `idx_actions_ex_date` on `ex_date`

---

### news (Phase 5)

News articles and press releases.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `news_id` | UUID | NO | Primary key |
| `headline` | VARCHAR(500) | NO | Article headline |
| `body` | TEXT | YES | Full article text |
| `source` | VARCHAR(100) | NO | News source (e.g., `Reuters`, `Bloomberg`) |
| `published_at` | TIMESTAMPTZ | NO | Publication timestamp |
| `dedupe_hash` | VARCHAR(64) | NO | SHA-256 hash for deduplication |
| `related_instruments` | UUID[] | YES | Array of related instrument IDs |
| `related_companies` | UUID[] | YES | Array of related company IDs |
| `raw_url` | VARCHAR(1000) | YES | Original article URL |
| `language` | CHAR(2) | YES | ISO 639-1 language code |
| `provider` | VARCHAR(50) | NO | Data source provider |
| `created_at` | TIMESTAMPTZ | NO | Record creation time |

**Constraints:**

- `UNIQUE (dedupe_hash)` — prevents duplicate articles

**Indexes:**

- `idx_news_published` on `published_at DESC`
- `idx_news_source` on `source`
- `idx_news_dedupe` on `dedupe_hash`
- `idx_news_instruments` using GIN on `related_instruments`
- `idx_news_companies` using GIN on `related_companies`
- Full-text search index on `headline` and `body`

---

### filings (Phase 5)

Regulatory filings (10-K, 10-Q, 8-K, etc.).

| Column | Type | Nullable | Description |
|---|---|---|---|
| `filing_id` | UUID | NO | Primary key |
| `company_id` | UUID | NO | FK to `companies` |
| `filing_type` | VARCHAR(20) | NO | `10-K`, `10-Q`, `8-K`, `DEF 14A`, `other` |
| `filed_at` | TIMESTAMPTZ | NO | Filing timestamp |
| `period_end_date` | DATE | YES | Period end date (for periodic filings) |
| `document_url` | VARCHAR(1000) | YES | Original document URL |
| `document_storage_key` | VARCHAR(500) | NO | Object storage key for raw document |
| `extracted_text_key` | VARCHAR(500) | YES | Object storage key for extracted text (Phase 6) |
| `metadata` | JSONB | YES | Filing-specific metadata |
| `provider` | VARCHAR(50) | NO | Data source provider |
| `created_at` | TIMESTAMPTZ | NO | Record creation time |
| `updated_at` | TIMESTAMPTZ | NO | Last modification time |

**Constraints:**

- `CHECK (filing_type IN ('10-K', '10-Q', '8-K', 'DEF 14A', '6-K', '20-F', 'other'))`

**Indexes:**

- `idx_filings_company` on `company_id`
- `idx_filings_type` on `filing_type`
- `idx_filings_filed` on `filed_at DESC`
- `idx_filings_period` on `period_end_date DESC`

---

## Parquet schemas (object storage)

These are not PostgreSQL tables but define the structure of Parquet files stored in object storage.

### OHLCV (Phase 2)

**Location:** `parquet/ohlcv/{exchange}/{year}/data.parquet`

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

**Partitioning:** `{exchange}/{year}`

---

### Intraday bars (Phase 3)

**Location:** `parquet/intraday/{exchange}/{year}/{month}/{day}/data.parquet`

| Column | Type | Description |
|---|---|---|
| `instrument_id` | UUID | Internal instrument identifier |
| `timestamp` | TIMESTAMP | Bar start time (UTC) |
| `interval` | VARCHAR | `1m`, `5m`, `15m`, `1h` |
| `open` | DECIMAL(18,6) | Opening price |
| `high` | DECIMAL(18,6) | Highest price |
| `low` | DECIMAL(18,6) | Lowest price |
| `close` | DECIMAL(18,6) | Closing price |
| `volume` | BIGINT | Trading volume |
| `provider` | VARCHAR | Source provider identifier |
| `ingested_at` | TIMESTAMP | When the record was ingested |

**Partitioning:** `{exchange}/{year}/{month}/{day}`

---

### Trades (Phase 3)

**Location:** `parquet/trades/{exchange}/{year}/{month}/{day}/data.parquet`

| Column | Type | Description |
|---|---|---|
| `instrument_id` | UUID | Internal instrument identifier |
| `timestamp` | TIMESTAMP | Trade time (UTC) |
| `price` | DECIMAL(18,6) | Trade price |
| `volume` | BIGINT | Trade volume |
| `side` | VARCHAR | `buy`, `sell`, `unknown` |
| `trade_id` | VARCHAR | Provider trade identifier |
| `provider` | VARCHAR | Source provider identifier |
| `ingested_at` | TIMESTAMP | When the record was ingested |

**Partitioning:** `{exchange}/{year}/{month}/{day}`

---

### Order-book snapshots (Phase 3)

**Location:** `parquet/orderbook/{exchange}/{symbol}/{date}/data.parquet`

| Column | Type | Description |
|---|---|---|
| `instrument_id` | UUID | Internal instrument identifier |
| `timestamp` | TIMESTAMP | Snapshot time (UTC) |
| `bids` | `ARRAY<STRUCT<price DECIMAL(18,6), volume BIGINT>>` | Bid levels |
| `asks` | `ARRAY<STRUCT<price DECIMAL(18,6), volume BIGINT>>` | Ask levels |
| `sequence` | BIGINT | Provider sequence number |
| `provider` | VARCHAR | Source provider identifier |
| `ingested_at` | TIMESTAMP | When the record was ingested |

**Partitioning:** `{exchange}/{symbol}/{date}`

---

## Relationships diagram

```text
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│  companies   │────────<│ instruments  │────────<│  exchanges   │
└──────────────┘         └──────┬───────┘         └──────────────┘
                                │
                                │
                                ▼
                    ┌───────────────────────┐
                    │ provider_instrument_  │
                    │      mappings         │
                    └───────────────────────┘
                                │
                                │ (used during ingestion)
                                ▼
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│ data_sources │────────<│ingestion_jobs│────────<│  datasets    │
└──────────────┘         └──────┬───────┘         └──────────────┘
                                │
                                │
                                ▼
                    ┌───────────────────────┐
                    │  rejected_records     │
                    └───────────────────────┘


Domain-specific relationships:

instruments ──────< fundamentals_income_statement
instruments ──────< fundamentals_balance_sheet
instruments ──────< fundamentals_cash_flow
instruments ──────< corporate_actions
companies ────────< filings
instruments ─────< news (via related_instruments array)
companies ───────< news (via related_companies array)
```

---

## Indexes summary

**High-cardinality columns (use B-tree):**

- All primary keys (UUID)
- Foreign keys
- Timestamps used in range queries (`published_at`, `filed_at`, `created_at`)
- Status fields with few distinct values

**Low-cardinality columns (use B-tree or skip if rarely queried):**

- `status`, `asset_class`, `action_type`, `filing_type`

**Array columns (use GIN):**

- `related_instruments`, `related_companies` in `news`

**JSONB columns (use GIN if queried):**

- `metadata` in `filings`
- `details` in `corporate_actions`
- `validation_summary` in `data_quality_results`

**Full-text search:**

- `headline` and `body` in `news` (Phase 6)
- Extracted text in `filings` (Phase 6)

---

## Migration strategy

1. **Phase 1:** Create all reference tables (`companies`, `exchanges`, `instruments`, `provider_instrument_mappings`, `data_sources`, `datasets`) and operational tables (`ingestion_jobs`, `rejected_records`, `data_quality_results`).

2. **Phase 2:** No new PostgreSQL tables. OHLCV data stored in Parquet.

3. **Phase 3:** No new PostgreSQL tables. Intraday, trades, and order-book data stored in Parquet.

4. **Phase 4:** Add `fundamentals_income_statement`, `fundamentals_balance_sheet`, `fundamentals_cash_flow`, and `corporate_actions`.

5. **Phase 5:** Add `news` and `filings`.

6. **Phase 6:** Add `pgvector` extension and embedding tables (if separate from `news`/`filings`).

---

## Data retention

| Table | Retention | Notes |
|---|---|---|
| Reference data (`companies`, `exchanges`, `instruments`) | Indefinite | Soft-delete only |
| Operational data (`ingestion_jobs`) | 2 years | Partition by `created_at`, archive older partitions |
| `rejected_records` | 90 days | Partition by `created_at`, delete older partitions |
| Parquet files | Indefinite | Immutable; can be regenerated from raw data |
| Raw object storage | Indefinite | Immutable; source of truth |
| `news`, `filings` | Indefinite | Soft-delete only |
