-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Reference Data Tables
CREATE TABLE IF NOT EXISTS companies (
    company_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    legal_name VARCHAR(255),
    country CHAR(2) NOT NULL,
    sector VARCHAR(100),
    industry VARCHAR(100),
    status VARCHAR(20) NOT NULL CHECK (status IN ('active', 'inactive')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS exchanges (
    exchange_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    mic_code CHAR(4) UNIQUE,
    acronym VARCHAR(20),
    country CHAR(2) NOT NULL,
    timezone VARCHAR(50) NOT NULL,
    currency CHAR(3) NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('active', 'inactive')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS instruments (
    instrument_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(company_id),
    exchange_id UUID NOT NULL REFERENCES exchanges(exchange_id),
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(255) NOT NULL,
    isin CHAR(12) UNIQUE,
    cusip CHAR(9),
    sedol VARCHAR(7),
    asset_class VARCHAR(20) NOT NULL CHECK (asset_class IN ('equity', 'etf', 'bond', 'option', 'future', 'other')),
    currency CHAR(3) NOT NULL,
    lot_size INTEGER,
    status VARCHAR(20) NOT NULL CHECK (status IN ('active', 'inactive', 'delisted')),
    delisted_at DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (exchange_id, symbol)
);

CREATE TABLE IF NOT EXISTS provider_instrument_mappings (
    mapping_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id UUID NOT NULL REFERENCES instruments(instrument_id),
    provider VARCHAR(50) NOT NULL,
    provider_symbol VARCHAR(50) NOT NULL,
    valid_from DATE,
    valid_to DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to >= valid_from),
    UNIQUE (provider, provider_symbol, valid_from)
);

-- Operational Metadata Tables
CREATE TABLE IF NOT EXISTS data_sources (
    data_source_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    provider_key VARCHAR(50) UNIQUE NOT NULL,
    provider_type VARCHAR(20) NOT NULL CHECK (provider_type IN ('market', 'fundamentals', 'news', 'filings')),
    base_url VARCHAR(500),
    auth_type VARCHAR(20),
    rate_limit INTEGER,
    status VARCHAR(20) NOT NULL CHECK (status IN ('active', 'inactive')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    dataset_key VARCHAR(50) UNIQUE NOT NULL,
    domain VARCHAR(20) NOT NULL CHECK (domain IN ('market', 'corporate', 'information')),
    description TEXT,
    schema_version INTEGER NOT NULL,
    storage_type VARCHAR(20) NOT NULL CHECK (storage_type IN ('parquet', 'postgresql')),
    status VARCHAR(20) NOT NULL CHECK (status IN ('active', 'inactive')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data_source_id UUID NOT NULL REFERENCES data_sources(data_source_id),
    dataset_id UUID NOT NULL REFERENCES datasets(dataset_id),
    job_type VARCHAR(20) NOT NULL CHECK (job_type IN ('backfill', 'incremental')),
    target_date DATE,
    status VARCHAR(20) NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'partial', 'failed')),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    records_received BIGINT NOT NULL DEFAULT 0,
    records_valid BIGINT NOT NULL DEFAULT 0,
    records_invalid BIGINT NOT NULL DEFAULT 0,
    records_duplicate BIGINT NOT NULL DEFAULT 0,
    records_written BIGINT NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS data_quality_results (
    quality_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES ingestion_jobs(job_id),
    dataset_id UUID NOT NULL REFERENCES datasets(dataset_id),
    records_received BIGINT NOT NULL DEFAULT 0,
    records_valid BIGINT NOT NULL DEFAULT 0,
    records_invalid BIGINT NOT NULL DEFAULT 0,
    records_duplicate BIGINT NOT NULL DEFAULT 0,
    quality_score DECIMAL(5,2),
    validation_summary JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rejected_records (
    rejection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES ingestion_jobs(job_id),
    dataset_id UUID NOT NULL REFERENCES datasets(dataset_id),
    record_data JSONB NOT NULL,
    rejection_reason VARCHAR(100) NOT NULL,
    rejection_details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
