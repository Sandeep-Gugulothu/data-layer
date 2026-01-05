## Description
Please include a summary of the changes and the related issue/milestone.

## Phase 1 Checklist Progress
Verify which items from the Phase 1 Checklist are completed in this PR:

### Project Foundation
- [ ] Project structure is created.
- [ ] Python environment is configured.
- [ ] Dependency management is configured.
- [ ] Environment-variable configuration is implemented.
- [ ] `.env.example` is created.
- [ ] Docker Compose configuration is created.
- [ ] README contains local setup instructions.

### Local Infrastructure
- [ ] PostgreSQL container starts successfully.
- [ ] MinIO container starts successfully.
- [ ] FastAPI service starts successfully.
- [ ] Worker service starts successfully.
- [ ] PostgreSQL health check passes.
- [ ] MinIO health check passes.
- [ ] Database migrations run successfully.
- [ ] MinIO bucket structure is created.

### Reference Data & Ingestion
- [ ] Reference data tables are created & seeded.
- [ ] Symbol resolution mapping is working.
- [ ] Raw responses are preserved.
- [ ] validation rules `R1` - `R11` and `S1`, `S2` are enforced.
- [ ] Partitioned Parquet outputting is functional.
- [ ] Ingestion jobs and quality metrics are logged.

### Serving & API
- [ ] API endpoints `/v1/health` and `/v1/instruments` are active.
- [ ] Historical price endpoint `GET /v1/prices/{instrument_id}/history` via DuckDB is active.

## Testing & Verification
- [ ] Unit tests pass (`pytest tests/`)
- [ ] Manual verification steps completed

## Screenshots / CLI Logs
Attach logs or screenshots showing successful execution if applicable.
