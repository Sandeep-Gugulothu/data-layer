# Phase 1 Checklist

## Scope and decisions

- [x] Phase 1 scope is approved.
- [x] Initial provider is selected.
- [x] Provider usage and storage rights are confirmed.
- [x] Initial exchange coverage is defined.
- [x] Initial instrument universe is defined.
- [x] Historical date range is defined.
- [x] Timezone and currency policies are defined.
- [x] Adjusted and unadjusted price policy is defined.

## Project foundation

- [x] Git repository is created.
- [x] Project structure is created.
- [x] Python environment is configured.
- [x] Dependency management is configured.
- [x] Environment-variable configuration is implemented.
- [x] `.env.example` is created.
- [x] Docker Compose configuration is created.
- [x] README contains local setup instructions.

## Local infrastructure

- [x] PostgreSQL container starts successfully.
- [x] MinIO container starts successfully.
- [ ] FastAPI service starts successfully.
- [ ] Worker service starts successfully.
- [x] PostgreSQL health check passes.
- [x] MinIO health check passes.
- [x] Database migrations run successfully.
- [x] MinIO bucket structure is created.

## Reference data

- [x] Companies table is created.
- [x] Exchanges table is created.
- [x] Instruments table is created.
- [x] Provider-symbol mappings are created.
- [x] Initial reference data can be seeded.
- [x] Provider symbols resolve to internal instrument IDs.
- [ ] Unresolved symbols are recorded clearly.

## Ingestion

- [x] Provider adapter is implemented.
- [x] Provider authentication works.
- [x] Provider requests work for the selected dataset.
- [ ] Rate limiting is implemented.
- [ ] Retry handling is implemented.
- [x] Backfill command is implemented.
- [ ] Incremental update behavior is defined or implemented.
- [x] Ingestion jobs are created before fetching data.
- [x] Job status is updated throughout the ingestion process.

## Raw data

- [x] Original provider responses are stored before processing.
- [ ] Raw objects include provider and job metadata.
- [ ] Raw objects are immutable after creation.
- [x] Raw data can be retrieved from MinIO.
- [ ] Raw data can be used to rebuild processed data.

## Validation and normalization

- [x] Required fields are checked.
- [x] Instrument existence is checked.
- [ ] Timestamp validity is checked.
- [ ] Future timestamps are rejected.
- [ ] Supported timeframe is checked.
- [ ] Currency is checked.
- [x] Prices are non-null and positive.
- [x] `high >= open` is checked.
- [x] `high >= close` is checked.
- [x] `low <= open` is checked.
- [x] `low <= close` is checked.
- [x] `high >= low` is checked.
- [x] Volume is non-negative.
- [ ] Duplicate logical keys are detected.
- [x] Valid records are normalized to the canonical OHLCV schema.
- [x] Invalid records are stored with rejection reasons.
- [ ] Soft validation warnings are recorded.

## Processed storage

- [x] Valid records are written as Parquet.
- [x] Parquet files use the agreed partitioning strategy.
- [ ] Temporary files are not exposed as completed data.
- [x] Parquet files can be read after ingestion.
- [ ] Schema metadata is recorded.
- [ ] Reprocessing from raw data produces valid Parquet output.

## Job and quality tracking

- [ ] Job status supports `pending`.
- [ ] Job status supports `running`.
- [ ] Job status supports `succeeded`.
- [ ] Job status supports `partial`.
- [ ] Job status supports `failed`.
- [ ] Records received are recorded.
- [ ] Records accepted are recorded.
- [ ] Records rejected are recorded.
- [ ] Duplicate records are recorded.
- [ ] Records written are recorded.
- [ ] Error details are recorded.
- [ ] Data-quality results are stored.

## Query and API

- [x] DuckDB reads the processed Parquet data.
- [x] Historical OHLCV query works for one instrument.
- [x] Historical OHLCV query supports a date range.
- [x] API endpoint for historical OHLCV is implemented.
- [x] Instruments endpoint is implemented.
- [ ] Ingestion-jobs endpoint is implemented.
- [x] Health endpoint is implemented.
- [ ] Invalid instrument requests return a clear error.
- [ ] Invalid date ranges return a clear error.
- [x] Empty results are handled correctly.
- [ ] API response matches the documented contract.
- [x] OpenAPI documentation is available.

## Testing

- [ ] Provider adapter unit tests pass.
- [ ] Instrument-resolution tests pass.
- [ ] Validation tests pass.
- [ ] Duplicate-detection tests pass.
- [ ] Raw-storage integration tests pass.
- [ ] PostgreSQL integration tests pass.
- [ ] Parquet-writing tests pass.
- [ ] DuckDB query tests pass.
- [ ] API tests pass.
- [ ] Retry tests pass.
- [ ] Rejection-handling tests pass.
- [ ] Idempotency tests pass.
- [ ] End-to-end pipeline test passes.

## Documentation and operations

- [ ] README explains local setup.
- [ ] README explains how to seed reference data.
- [ ] README explains how to run ingestion.
- [ ] README explains how to query the API.
- [ ] Runbook explains how to check job status.
- [ ] Runbook explains how to investigate rejected records.
- [ ] Runbook explains how to rebuild processed data from raw data.
- [ ] Architecture diagram is updated.
- [ ] Known limitations are documented.
- [ ] All configuration variables are documented.

## Phase 1 completion

Phase 1 is complete only when:

- [ ] The platform starts locally.
- [ ] Real provider data can be ingested.
- [ ] Raw data is preserved.
- [ ] Valid data is stored as Parquet.
- [ ] Invalid data is traceable.
- [ ] Job and quality information is recorded.
- [ ] Historical data is queryable through the API.
- [ ] Re-running ingestion is safe.
- [ ] The end-to-end test passes.
- [ ] Documentation is sufficient for another developer to run the system.
