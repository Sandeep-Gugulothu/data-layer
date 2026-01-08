-- Seed Data Sources
INSERT INTO data_sources (data_source_id, name, provider_key, provider_type, base_url, auth_type, rate_limit, status)
VALUES 
    ('d1000000-0000-0000-0000-000000000001', 'Yahoo Finance', 'yfinance', 'market', NULL, 'none', 60, 'active')
ON CONFLICT (provider_key) DO NOTHING;

-- Seed Datasets
INSERT INTO datasets (dataset_id, name, dataset_key, domain, description, schema_version, storage_type, status)
VALUES 
    ('d2000000-0000-0000-0000-000000000001', 'Daily OHLCV', 'ohlcv_daily', 'market', 'Daily Open High Low Close Volume data', 1, 'parquet', 'active')
ON CONFLICT (dataset_key) DO NOTHING;

-- Seed Exchanges
INSERT INTO exchanges (exchange_id, name, mic_code, acronym, country, timezone, currency, status)
VALUES 
    ('e1000000-0000-0000-0000-000000000001', 'National Stock Exchange of India', 'XNSE', 'NSE', 'IN', 'Asia/Kolkata', 'INR', 'active'),
    ('e1000000-0000-0000-0000-000000000002', 'NASDAQ', 'XNAS', 'NASDAQ', 'US', 'America/New_York', 'USD', 'active')
ON CONFLICT (mic_code) DO NOTHING;

-- Seed Companies
INSERT INTO companies (company_id, name, legal_name, country, sector, industry, status)
VALUES 
    ('c1000000-0000-0000-0000-000000000001', 'Apple Inc.', 'Apple Inc.', 'US', 'Technology', 'Consumer Electronics', 'active'),
    ('c1000000-0000-0000-0000-000000000002', 'Reliance Industries Limited', 'Reliance Industries Limited', 'IN', 'Energy', 'Oil & Gas', 'active')
ON CONFLICT DO NOTHING;

-- Seed Instruments
INSERT INTO instruments (instrument_id, company_id, exchange_id, symbol, name, asset_class, currency, status)
VALUES 
    ('a1000000-0000-0000-0000-000000000001', 'c1000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-000000000002', 'AAPL', 'Apple Inc.', 'equity', 'USD', 'active'),
    ('a1000000-0000-0000-0000-000000000002', 'c1000000-0000-0000-0000-000000000001', 'e1000000-0000-0000-0000-000000000001', 'RELIANCE.NS', 'Reliance Industries Limited', 'equity', 'INR', 'active')
ON CONFLICT (exchange_id, symbol) DO NOTHING;

-- Seed Provider Symbol Mappings
INSERT INTO provider_instrument_mappings (mapping_id, instrument_id, provider, provider_symbol, valid_from, valid_to)
VALUES 
    ('f1000000-0000-0000-0000-000000000001', 'a1000000-0000-0000-0000-000000000001', 'yfinance', 'AAPL', NULL, NULL),
    ('f1000000-0000-0000-0000-000000000002', 'a1000000-0000-0000-0000-000000000002', 'yfinance', 'RELIANCE.NS', NULL, NULL)
ON CONFLICT (provider, provider_symbol, valid_from) DO NOTHING;
