# Financial Data Platform (Phase 1)

A clean, modular data engineering platform for ingesting, validating, storing, and serving financial market data. 

---

## 1. Project Architecture

The pipeline implements the following layout:
```text
yfinance API
  ↓
Ingestion Worker (python)
  ↓
Raw Payload Preservation (MinIO JSON)
  ↓
Validation & Normalization (pandas)
  ↓
Canonical Partitioned Storage (MinIO Parquet)
  ↓
Serving layer (FastAPI + Embedded DuckDB)
```

---

## 2. Local Setup

### Prerequisites
* Docker & Docker Compose
* Python 3.10+

### Step 1: Start Local Infrastructure
Run the following command to boot up PostgreSQL (for metadata/audit logs) and MinIO (object storage):
```bash
docker compose up -d
```

### Step 2: Configure Environment
Copy `.env.example` to create your local `.env`:
```bash
cp .env.example .env
```

### Step 3: Install Python Dependencies
Install the required packages:
```bash
pip install -r requirements.txt
```

---

## 3. Database Initialization & Seeding

Run the database schema setup and seed reference data (exchanges, instruments, and mappings) by executing the scripts against the PostgreSQL container:

```bash
# Apply schemas
docker compose exec -T postgres psql -U postgres -d fdp_metadata -f /db/migrations/schema.sql

# Seed initial instrument and mapping data
docker compose exec -T postgres psql -U postgres -d fdp_metadata -f /db/migrations/seed.sql
```

*(Note: If executing locally outside Docker, run the SQL files against your database client).*

---

## 4. Run Ingestion Pipeline (Worker CLI)

Run the worker script to fetch historical daily price records, run quality checks, and merge them into the Parquet partition:

```bash
python -m src.worker AAPL 2026-08-01 2026-08-28
python -m src.worker RELIANCE.NS 2026-08-01 2026-08-28
```

This will:
1. Save the raw provider responses in MinIO under `raw/yfinance/ohlcv/{end_date}/`.
2. Validate incoming records against rules `R1` to `R11`.
3. Route rejected rows to the `rejected_records` database log.
4. Merge valid rows into the target partition: `parquet/ohlcv/{exchange}/{year}/data.parquet`.

---

## 5. Start API Server

Launch the FastAPI serving layer:
```bash
python -m src.api
```

The API will be available at `http://localhost:8000`. You can visit the Interactive Swagger docs at `http://localhost:8000/docs`.

### API Endpoints
* **Health Check**: `GET /v1/health`
* **List Instruments**: `GET /v1/instruments`
* **Historical Prices (DuckDB scan over Parquet)**: 
  ```http
  GET /v1/prices/{instrument_id}/history?start_date=2026-08-01&end_date=2026-08-28
  ```
