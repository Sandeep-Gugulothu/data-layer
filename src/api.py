import os
import psycopg2
from psycopg2.extras import RealDictCursor
import duckdb
from fastapi import FastAPI, HTTPException, Query
from src.config import DATABASE_URL, LOCAL_STORAGE_PATH, logger
from src.storage import get_storage

app = FastAPI(title="Financial Data Platform API", version="1.0")
storage = get_storage()

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

@app.get("/v1/health")
def health():
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "healthy", "database": "connected", "storage": type(storage).__name__}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unhealthy: {e}")

@app.get("/v1/instruments")
def list_instruments(
    exchange: str = Query(None, description="Filter by exchange acronym (e.g., NASDAQ, NSE)"),
    status: str = Query("active", description="Filter by instrument status")
):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        query = """
            SELECT i.instrument_id, i.symbol, i.name, i.asset_class, i.currency, e.acronym as exchange, i.status
            FROM instruments i
            JOIN exchanges e ON i.exchange_id = e.exchange_id
            WHERE i.status = %s
        """
        params = [status]
        if exchange:
            query += " AND e.acronym = %s"
            params.append(exchange)
            
        cursor.execute(query, params)
        res = cursor.fetchall()
        return res
    finally:
        cursor.close()
        conn.close()

@app.get("/v1/ohlcv")
def get_ohlcv(
    instrument_id: str,
    start_date: str,
    end_date: str
):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Check if instrument exists and get exchange acronym
        cursor.execute("""
            SELECT i.symbol, e.acronym as exchange_name 
            FROM instruments i
            JOIN exchanges e ON i.exchange_id = e.exchange_id
            WHERE i.instrument_id = %s
        """, (instrument_id,))
        inst = cursor.fetchone()
        if not inst:
            raise HTTPException(status_code=404, detail="Instrument not found")
        
        exchange_name = inst['exchange_name']
    finally:
        cursor.close()
        conn.close()

    # Query Parquet via DuckDB
    # If storage is MinioStorage, we copy the file locally for DuckDB to query,
    # or if LocalStorage, it's already local under LOCAL_STORAGE_PATH.
    year = start_date[:4]
    parquet_key = f"parquet/ohlcv/{exchange_name}/{year}/data.parquet"
    local_parquet_path = os.path.join(LOCAL_STORAGE_PATH, parquet_key)

    if not storage.exists(parquet_key):
        return {"instrument_id": instrument_id, "start_date": start_date, "end_date": end_date, "records": [], "count": 0}

    # Fetch from MinIO to local cache if using MinioStorage
    if not isinstance(storage, type(LOCAL_STORAGE_PATH)):
        os.makedirs(os.path.dirname(local_parquet_path), exist_ok=True)
        file_bytes = storage.get(parquet_key)
        with open(local_parquet_path, "wb") as f:
            f.write(file_bytes)

    try:
        # Query DuckDB
        duck_conn = duckdb.connect(database=':memory:')
        query = f"""
            SELECT timestamp, timeframe, open, high, low, close, adjusted_close, volume, currency, source
            FROM read_parquet('{local_parquet_path}')
            WHERE instrument_id = '{instrument_id}'
              AND timestamp >= '{start_date}'
              AND timestamp <= '{end_date}'
            ORDER BY timestamp ASC
        """
        df = duck_conn.execute(query).df()
        # Convert timestamp to ISO format strings
        df['timestamp'] = df['timestamp'].astype(str)
        records = df.to_dict(orient="records")
        return {
            "instrument_id": instrument_id,
            "start_date": start_date,
            "end_date": end_date,
            "records": records,
            "count": len(records)
        }
    except Exception as e:
        logger.error(f"DuckDB query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
