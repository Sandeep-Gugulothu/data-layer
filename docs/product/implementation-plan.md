# Phase 1 Implementation Plan

**Product:** Financial Data Platform  
**Owner:** Product and Engineering  
**Last updated:** 6 January 2026  

---

## 1. Objective

Build the Phase 1 platform foundation and deliver one complete daily OHLCV data pipeline from an external provider to a queryable API. This phase establishes the architectural patterns, infrastructure, and operational procedures that all subsequent phases will extend.

**Success criteria:**

- A developer can run `docker compose up` and have a working platform.
- One provider's daily OHLCV data can be ingested end-to-end.
- Raw data is preserved, validated, normalized, and stored as Parquet.
- Historical data is queryable via a REST API.
- The pipeline is idempotent, retryable, and auditable.

---

## 2. Phase 1 outcome

The system shall deliver the following end-to-end flow:

```text
Scheduler / CLI trigger
  ↓
Fetch daily OHLCV data from provider
  ↓
Preserve the original provider response in raw storage
  ↓
Map provider symbols to internal instruments
  ↓
Validate records against business rules
  ↓
Normalize valid records to canonical schema
  ↓
Store valid data as partitioned Parquet files
  ↓
Record ingestion jobs and data-quality results
  ↓
Query historical data with embedded DuckDB
  ↓
Return results through FastAPI REST endpoints
```

---

## 3. Phase 1 scope

### 3.1 Included

| Component | Description |
|---|---|
| Infrastructure | Docker Compose with PostgreSQL, MinIO, Python worker, FastAPI |
| Reference data | Companies, exchanges, instruments, provider-symbol mappings |
| Ingestion pipeline | One provider adapter, daily OHLCV, raw preservation, validation, normalization |
| Storage | Raw payloads in MinIO, normalized Parquet in MinIO, metadata in PostgreSQL |
| Query engine | DuckDB embedded in FastAPI for analytical queries |
| API | REST endpoints for instruments and OHLCV history |
| Operations | CLI for triggering ingestion, job tracking, quality reporting |
| Testing | Unit, integration, and end-to-end tests |
| Documentation | README, architecture diagrams, runbooks |

### 3.2 Excluded

- Intraday or tick data (Phase 3)
- Fundamentals or corporate actions (Phase 4)
- News or filings (Phase 5)
- Search or AI features (Phase 6)
- Multiple providers (Phase 2+)
- Orchestration frameworks like Airflow (Phase 5+)
- Distributed infrastructure (Kafka, Kubernetes)
- Real-time caching (Redis)

---

## 4. Architecture and components

### 4.1 Component responsibilities

**Python Ingestion Worker**
- Calls the provider's REST API with authentication, pagination, rate limiting, and exponential-backoff retries.
- Writes the raw provider response to object storage before any parsing.
- Resolves provider symbols to internal instrument IDs.
- Validates records against business rules.
- Normalizes valid records to the canonical OHLCV schema.
- Writes normalized records to partitioned Parquet files.
- Records job metadata, quality metrics, and rejected records in PostgreSQL.

**PostgreSQL**
- Stores reference data: `companies`, `exchanges`, `instruments`, `provider_instrument_mappings`.
- Stores operational metadata: `data_sources`, `datasets`, `ingestion_jobs`, `data_quality_results`, `rejected_records`.
- Does **not** store market data (prices, volumes).

**MinIO (Local Object Storage)**
- Stores raw provider payloads under `raw/{provider}/ohlcv/{date}/`.
- Stores normalized Parquet files under `parquet/ohlcv/{exchange}/{year}/`.
- Provides an S3-compatible interface identical to production S3/R2.

**DuckDB (Embedded in FastAPI)**
- Reads Parquet files directly from object storage.
- Executes SQL queries for API responses.
- No separate DuckDB service; runs in-process within the API container.

**FastAPI**
- Serves versioned REST endpoints.
- Reads metadata from PostgreSQL.
- Queries Parquet data via embedded DuckDB.
- Authenticates requests when deployed outside the local environment.

### 4.2 Storage layout

**Raw data (immutable after write):**

```text
raw/
  {provider}/
    ohlcv/
      {date}/
        response.json
```

Example: `raw/alpha_vantage/ohlcv/2025-01-02/response.json`

**Processed data (Parquet, partitioned):**

```text
parquet/
  ohlcv/
    {exchange}/
      {year}/
        part-000000.parquet
        part-000001.parquet
```

Example: `parquet/ohlcv/NSE/2025/part-000000.parquet`

**Rejected records (PostgreSQL table):**

Stored in the `rejected_records` table with:
- `job_id` — the ingestion job that produced the rejection.
- `record_data` — the original record as JSONB.
- `rejection_reason` — the validation rule code (e.g., `R8`, `R11`).
- `rejection_details` — human-readable explanation.
- `created_at` — when the rejection occurred.

---

## 5. Ingestion flow

### 5.1 Step-by-step flow

1. **Trigger:** A scheduler (cron) or manual CLI command initiates an ingestion run for a specific date and provider.
2. **Job creation:** The worker creates an `ingestion_jobs` record with status `pending`.
3. **Fetch:** The worker calls the provider's REST API, handling pagination and rate limits.
4. **Preserve raw:** The unmodified provider response is written to `raw/{provider}/ohlcv/{date}/response.json`. **No processing occurs before this write.**
5. **Parse:** The worker parses the JSON response into individual records.
6. **Resolve instruments:** For each record, the worker looks up the provider symbol in `provider_instrument_mappings` to find the internal `instrument_id`. Unresolved symbols are logged and recorded as rejected.
7. **Validate:** Each record is validated against the OHLCV validation rules (see §6). Invalid records are written to `rejected_records`.
8. **Normalize:** Valid records are transformed to the canonical OHLCV schema.
9. **Write Parquet:** Normalized records are written to `parquet/ohlcv/{exchange}/{year}/part-NNNNNN.parquet.tmp`, then atomically renamed to `part-NNNNNN.parquet`.
10. **Record quality:** The worker writes a `data_quality_results` record with counts and quality metrics.
11. **Finalize job:** The `ingestion_jobs` record is updated with status `succeeded`, `partial`, or `failed`, along with final counts and timestamps.

### 5.2 Idempotency

- Re-running an ingestion for the same `(provider, date)` overwrites the Parquet partition for that date.
- The `ingestion_jobs` table records every run, so historical job runs are auditable.
- No duplicate records are created within a single job (enforced by validation rule `R11`).

### 5.3 Error handling

**Retryable errors (exponential backoff, max 5 attempts):**
- Network timeouts.
- HTTP 429 (rate limit) responses.
- HTTP 5xx (server error) responses.
- Transient provider failures.

**Non-retryable errors (fail immediately):**
- HTTP 401/403 (authentication failure).
- HTTP 400 (bad request, invalid parameters).
- Schema parsing failures (provider changed API format).
- Database connection failures (after 3 attempts).

**Error recording:**
Every failed operation writes to the `ingestion_jobs` table:
- `job_id` — the job that failed.
- `error_message` — the error description.
- `status` — `failed` or `partial`.
- `completed_at` — when the failure occurred.

---

## 6. OHLCV validation rules

### 6.1 Hard rules (reject on failure)

| Rule ID | Rule | Description |
|---|---|---|
| `R1` | `instrument_id` exists | The instrument must exist in the `instruments` table. |
| `R2` | `timestamp` is valid | Must be a valid UTC timestamp. |
| `R3` | `timestamp` not in future | Must not be later than the ingestion time. |
| `R4` | `timeframe` supported | Must be `1d` in Phase 1. |
| `R5` | `currency` valid | Must be a valid ISO 4217 code. |
| `R6` | Prices non-null and positive | `open`, `high`, `low`, `close` must be non-null and > 0. |
| `R7` | `volume` non-negative | Must be >= 0. |
| `R8` | `high >= max(open, close)` | High must be the maximum. |
| `R9` | `low <= min(open, close)` | Low must be the minimum. |
| `R10` | `high >= low` | High must be >= low. |
| `R11` | No duplicate logical key | `(instrument_id, timestamp, timeframe)` must be unique within the job. |

### 6.2 Soft rules (flag but accept)

| Rule ID | Rule | Description |
|---|---|---|
| `S1` | `Price change <= ±50%` | Price change vs. previous close should not exceed ±50%. |
| `S2` | Volume > 0 if price moved | If `close != open` or `high != low`, volume should be > 0. |

Soft-rule violations are recorded in `data_quality_results.validation_summary` but do not cause rejection.

---

## 7. API design

### 7.1 Endpoints

| Endpoint | Method | Description | Parameters |
|---|---|---|---|
| `/v1/health` | GET | Service health and latest job freshness | — |
| `/v1/instruments` | GET | List instruments | `exchange`, `asset_class`, `status` (optional filters) |
| `/v1/instruments/{id}` | GET | Single instrument detail | — |
| `/v1/ohlcv` | GET | Query OHLCV history | `instrument_id`, `start_date`, `end_date` (required) |
| `/v1/jobs` | GET | List ingestion jobs | `provider`, `status`, `limit` (optional) |
| `/v1/jobs/{id}` | GET | Job detail with quality summary | — |

### 7.2 Query flow

```text
Client
  ↓
FastAPI (HTTP request)
  ↓
Price service (Python)
  ↓
DuckDB (embedded, SQL query)
  ↓
Parquet files (object storage)
  ↓
JSON response
```

### 7.3 Example request

```http
GET /v1/ohlcv?instrument_id=a1b2c3d4-e5f6-7890-abcd-ef1234567890&start_date=2025-01-01&end_date=2025-01-31
```

**Response:**

```json
{
  "instrument_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "start_date": "2025-01-01",
  "end_date": "2025-01-31",
  "records": [
    {
      "timestamp": "2025-01-02T00:00:00Z",
      "timeframe": "1d",
      "open": 245.10,
      "high": 248.50,
      "low": 243.80,
      "close": 247.90,
      "volume": 1250000,
      "currency": "INR",
      "source": "alpha_vantage"
    }
  ],
  "count": 1
}
```

---

## 8. Implementation Milestones

The implementation is divided into 5 milestones, each delivering a working increment.

### Milestone 1: Infrastructure and foundation

**Deliverables:**
- Repository structure with clear separation (workers, API, shared libraries, infrastructure).
- Docker Compose with PostgreSQL, MinIO, Python worker, FastAPI.
- PostgreSQL schema migrations for all Phase 1 tables.
- MinIO bucket structure and object-storage abstraction layer.
- Python environment with dependency management (Poetry or pip).
- Logging foundation using `structlog` with JSON output and `job_id` correlation.
- Configuration management via environment variables.

**Acceptance criteria:**
- `docker compose up` starts all services.
- Migrations run cleanly against a fresh database.
- Object-storage abstraction passes integration tests against MinIO.
- A sample Python script can write a test file to MinIO and read it back.

---

### Milestone 2: Reference data and instrument master

**Deliverables:**
- Seed script to populate initial `companies`, `exchanges`, and `instruments` from a CSV or JSON file.
- CLI command to load provider-symbol mappings.
- API endpoints for listing and retrieving instruments.
- Unit tests for instrument resolution logic.

**Acceptance criteria:**
- A developer can run a seed script and populate the database with sample instruments.
- The `/v1/instruments` endpoint returns the seeded data.
- Provider-symbol mapping resolution works correctly in unit tests.

---

### Milestone 3: Ingestion pipeline

**Deliverables:**
- Provider adapter for one approved provider (e.g., Alpha Vantage, Polygon, or a free provider).
- Raw-data preservation: write provider response to MinIO before parsing.
- Instrument resolution: map provider symbols to internal IDs.
- Validation logic implementing all hard and soft rules.
- Rejection handling: write invalid records to `rejected_records`.
- Normalization: transform valid records to canonical OHLCV schema.
- Parquet writing: write normalized records to partitioned Parquet files with atomic writes.
- Job tracking: create and update `ingestion_jobs` records.
- Quality recording: write `data_quality_results` with counts and metrics.
- CLI command to trigger an ingestion run for a specific date.
- Unit and integration tests for each component.

**Acceptance criteria:**
- A developer can run the CLI command and ingest one day of OHLCV data.
- The raw provider response is preserved in MinIO.
- Valid records are written to Parquet.
- Invalid records are recorded in `rejected_records` with reason codes.
- The `ingestion_jobs` table shows the job status and counts.
- Re-running the same date overwrites the Parquet partition (idempotent).
- All unit and integration tests pass.

---

### Milestone 4: Query engine and API

**Deliverables:**
- DuckDB integration in FastAPI: read Parquet files from MinIO.
- SQL query builder for OHLCV history queries.
- FastAPI endpoints: `/v1/ohlcv`, `/v1/instruments`, `/v1/jobs`, `/v1/health`.
- Error handling and validation in API layer.
- API documentation (OpenAPI/Swagger).
- Integration tests for API endpoints.

**Acceptance criteria:**
- A client can query OHLCV history via the API and receive correct results.
- The API returns 404 for non-existent instruments.
- The API returns 400 for invalid date ranges.
- The `/v1/health` endpoint reports service status and latest job freshness.
- All integration tests pass.

---

### Milestone 5: Testing, documentation, and polish

**Deliverables:**
- End-to-end test: ingest data, query via API, verify results.
- Idempotency test: run ingestion twice, verify no duplicates.
- Retry test: simulate provider failure, verify retry logic.
- README with setup instructions, architecture overview, and usage examples.
- Runbook for common operations (trigger ingestion, check job status, investigate rejections).
- Architecture diagrams (Mermaid or similar).
- Code review and refactoring.
- Performance testing: measure ingestion throughput and query latency.

**Acceptance criteria:**
- All end-to-end, idempotency, and retry tests pass.
- README is clear and a new developer can set up the platform in less than 30 minutes.
- Runbook covers common operational tasks.
- Ingestion throughput is >= 10,000 records/second.
- API query latency is less than 500ms for a 1-year date range.

---

## 9. Operational procedures

### 9.1 Starting the platform

```bash
# Start all services
docker compose up -d

# Run database migrations
docker compose exec worker alembic upgrade head

# Seed reference data
docker compose exec worker python -m scripts.seed_instruments

# Check service health
curl http://localhost:8000/v1/health
```

### 9.2 Triggering ingestion

```bash
# Ingest data for a specific date
docker compose exec worker python -m scripts.ingest --provider alpha_vantage --date 2025-01-02

# Ingest data for a date range (backfill)
docker compose exec worker python -m scripts.ingest --provider alpha_vantage --start 2025-01-01 --end 2025-01-31
```

### 9.3 Checking job status

```bash
# List recent jobs
curl http://localhost:8000/v1/jobs?limit=10

# Get job detail
curl http://localhost:8000/v1/jobs/{job_id}
```

### 9.4 Investigating rejections

```bash
# Query rejected records via psql
docker compose exec postgres psql -U postgres -d aerovest -c "
  SELECT job_id, rejection_reason, COUNT(*)
  FROM rejected_records
  WHERE created_at > NOW() - INTERVAL '1 day'
  GROUP BY job_id, rejection_reason
  ORDER BY COUNT(*) DESC;
"
```

### 9.5 Rebuilding data from raw

If Parquet files are corrupted or lost:

```bash
# Re-ingest from raw data
docker compose exec worker python -m scripts.rebuild --provider alpha_vantage --date 2025-01-02
```

This reads the raw payload from MinIO and re-runs the validation and normalization steps.

---

## 10. Testing strategy

### 10.1 Test levels

| Level | Scope | Tools | Coverage target |
|---|---|---|---|
| Unit | Individual functions and classes | pytest | 80% |
| Integration | Component interactions (DB, MinIO) | pytest + testcontainers | 70% |
| End-to-end | Full pipeline from provider to API | pytest + httpx | 1 critical path |

### 10.2 Critical test scenarios

**End-to-end pipeline test:**
1. Mock provider returns sample OHLCV data.
2. Trigger ingestion via CLI.
3. Verify raw payload is in MinIO.
4. Verify Parquet files are created.
5. Verify `ingestion_jobs` record shows `succeeded`.
6. Query via API and verify correct data is returned.

**Idempotency test:**
1. Ingest data for a date.
2. Ingest the same date again.
3. Verify no duplicate records in Parquet.
4. Verify two `ingestion_jobs` records exist.

**Retry test:**
1. Mock provider returns HTTP 500 on first attempt, HTTP 200 on second.
2. Verify ingestion succeeds after retry.
3. Verify `ingestion_jobs` shows `succeeded`.

**Validation test:**
1. Inject invalid records (e.g., `high < low`).
2. Verify records are rejected.
3. Verify `rejected_records` contains the invalid records with correct reason codes.

**Rejection handling test:**
1. Inject records with unresolvable provider symbols.
2. Verify records are rejected with reason `R1`.
3. Verify valid records are still processed.

---

## 11. Performance targets

| Metric | Target | Measurement |
|---|---|---|
| Ingestion throughput | >= 10,000 records/second | Records processed per second during ingestion |
| API query latency (1-year range) | less than 500ms | Time from request to response |
| API query latency (10-year range) | less than 2 seconds | Time from request to response |
| Parquet write latency (1-day partition) | less than 5 seconds | Time to write and finalize a partition |
| Raw preservation latency | less than 1 second | Time to write raw payload to MinIO |

---

## 12. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Provider API changes without notice | Medium | High | Raw preservation allows reprocessing; adapter is isolated and easy to update. |
| Provider rate limits are stricter than documented | High | Medium | Implement conservative rate limiting with exponential backoff; log rate-limit responses. |
| Data volume is larger than expected | Low | Medium | Phase 1 volume is small (less than 1 GB/year); partitioning strategy can be adjusted in Phase 3. |
| DuckDB query performance degrades | Low | Medium | Monitor query latency; if > 2s, consider materializing results or moving DuckDB to a dedicated worker. |
| Instrument resolution fails for many symbols | Medium | High | Log unresolved symbols; provide a CLI tool to manually map symbols; improve mapping logic in Phase 2. |
| Developer unfamiliar with Parquet or DuckDB | Medium | Medium | Allocate 1 day for learning; use existing libraries (pyarrow, duckdb); consult documentation. |

---

## 13. Definition of done

Phase 1 is complete when **all** of the following are true:

- [ ] The platform starts locally with `docker compose up`.
- [ ] PostgreSQL and MinIO are available and healthy.
- [ ] One provider adapter works and can ingest daily OHLCV data.
- [ ] Instruments can be seeded and mapped to provider symbols.
- [ ] Raw provider responses are preserved in MinIO before any processing.
- [ ] Valid records are normalized and written to partitioned Parquet files.
- [ ] Invalid records are recorded in `rejected_records` with reason codes.
- [ ] Ingestion jobs and quality results are tracked in PostgreSQL.
- [ ] Historical data can be queried through the REST API.
- [ ] Temporary failures (network, rate limits) are retried with exponential backoff.
- [ ] Repeated ingestion of the same date does not create duplicate records.
- [ ] All automated tests pass (unit, integration, end-to-end).
- [ ] The complete pipeline can be demonstrated using real provider data.
- [ ] README and runbook are complete and accurate.
- [ ] Performance targets are met.

---

## 14. Dependencies and prerequisites

| Dependency | Status | Notes |
|---|---|---|
| Approved provider account | Required | Sign up for a free or paid account with one provider (e.g., Alpha Vantage, Polygon). |
| Provider API documentation | Required | Ensure API docs are available and up-to-date. |
| Development environment | Required | Docker, Docker Compose, Python 3.10+, PostgreSQL client. |
| Git repository | Required | Create a new repository or use an existing one. |
| CI/CD pipeline | Optional | Can be added later; not required for Phase 1. |

---

## 15. Post-Phase 1 next steps

After Phase 1 is complete, the following work is planned:

**Phase 2 (next):**
- Add a second provider.
- Implement incremental updates (only fetch new data, not full backfills).
- Add more exchanges and instruments.
- Improve instrument resolution (fuzzy matching, alias support).

**Phase 3 (future):**
- Add intraday data (1m, 5m, 1h bars).
- Introduce Redis for caching latest prices.
- Add OpenTelemetry tracing.

**Phase 4+ (long-term):**
- Add fundamentals, corporate actions, news, filings, and AI features as defined in the HLD.
