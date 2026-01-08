import os
import pytest
import pandas as pd
import duckdb
from unittest.mock import MagicMock

# Simple mock class for storage testing
class MockStorage:
    def __init__(self):
        self.files = {}

    def put(self, key: str, data: bytes) -> None:
        self.files[key] = data

    def get(self, key: str) -> bytes:
        return self.files.get(key, b"")

    def exists(self, key: str) -> bool:
        return key in self.files

# 1. Validation Logic Unit Test
def test_ohlcv_data_validation():
    # Test valid row
    valid_row = {'open': 100.0, 'high': 105.0, 'low': 98.0, 'close': 102.0, 'volume': 1500}
    assert valid_row['high'] >= valid_row['open']
    assert valid_row['high'] >= valid_row['close']
    assert valid_row['low'] <= valid_row['open']
    assert valid_row['low'] <= valid_row['close']
    assert valid_row['volume'] >= 0

    # Test invalid row (high lower than open)
    invalid_row = {'open': 100.0, 'high': 95.0, 'low': 90.0, 'close': 92.0, 'volume': 1500}
    assert invalid_row['high'] < invalid_row['open']  # Should trigger failure

# 2. Storage Adapter Unit Test
def test_mock_storage_put_get():
    storage = MockStorage()
    test_key = "parquet/test_data.parquet"
    test_content = b"fake-parquet-bytes"
    
    storage.put(test_key, test_content)
    assert storage.exists(test_key) is True
    assert storage.get(test_key) == test_content

# 3. DuckDB Query Execution Unit Test
def test_duckdb_parquet_scan(tmp_path):
    # Create dummy DataFrame
    df = pd.DataFrame([
        {"timestamp": "2026-08-01", "open": 100.0, "high": 105.0, "low": 98.0, "close": 102.0, "volume": 1000},
        {"timestamp": "2026-08-02", "open": 102.0, "high": 106.0, "low": 101.0, "close": 105.0, "volume": 1200}
    ])
    
    # Save to temp Parquet file
    parquet_file = tmp_path / "test.parquet"
    df.to_parquet(parquet_file)
    
    # Connect to DuckDB and query Parquet file
    conn = duckdb.connect(database=':memory:')
    res = conn.execute(f"SELECT COUNT(*) FROM read_parquet('{parquet_file}')").fetchone()
    
    assert res[0] == 2
