import os
import glob
import duckdb
import json
import uuid
import datetime
import pandas as pd
import yfinance as yf
import psycopg2
from psycopg2.extras import RealDictCursor
from src.config import DATABASE_URL, logger
from src.storage import get_storage

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

class IngestionWorker:
    def __init__(self):
        self.storage = get_storage()

    def resolve_instrument(self, cursor, provider_symbol: str):
        query = """
            SELECT instrument_id FROM provider_instrument_mappings
            WHERE provider = 'yfinance' AND provider_symbol = %s
            LIMIT 1;
        """
        cursor.execute(query, (provider_symbol,))
        res = cursor.fetchone()
        return res['instrument_id'] if res else None

    def run(self, provider_symbol: str, start_date: str = None, end_date: str = None):
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # 1. Resolve Instrument
        instrument_id = self.resolve_instrument(cursor, provider_symbol)
        if not instrument_id:
            logger.error(f"Failed to resolve symbol {provider_symbol} to an internal instrument.")
            return

        # Get EXCHANGE and CURRENCY details
        cursor.execute("""
            SELECT e.acronym as exchange_name, i.currency
            FROM instruments i
            JOIN exchanges e ON i.exchange_id = e.exchange_id
            WHERE i.instrument_id = %s
        """, (instrument_id,))
        inst_info = cursor.fetchone()

        exchange_name = inst_info['exchange_name'] if inst_info else 'UNKNOWN'
        currency = inst_info['currency'] if inst_info else 'USD'

        # Determine start and end dates incrementally if not provided
        if not end_date:
            end_date = datetime.date.today().isoformat()
            
        if not start_date:
            max_date = None
            parquet_pattern = os.path.join("./data_storage", f"parquet/ohlcv/{exchange_name}/**/*.parquet")
            parquet_files = glob.glob(parquet_pattern, recursive=True)
            if parquet_files:
                duck_conn = duckdb.connect(database=':memory:')
                try:
                    files_str = ", ".join([f"'{f}'" for f in parquet_files])
                    res = duck_conn.execute(f"SELECT MAX(timestamp) FROM read_parquet([{files_str}]) WHERE instrument_id = '{instrument_id}'").fetchone()
                    if res and res[0]:
                        max_date = pd.to_datetime(res[0]).date()
                except Exception as ex:
                    logger.warning(f"Failed to query max date from Parquet: {ex}")
                    
            if max_date:
                start_date = (max_date + datetime.timedelta(days=1)).isoformat()
                logger.info(f"Incremental Ingestion: found previous max date {max_date}. Setting start_date to {start_date}")
            else:
                start_date = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
                logger.info(f"Incremental Ingestion: no previous data found. Defaulting start_date to 30 days ago: {start_date}")

        # Get Source and Dataset IDs
        cursor.execute("SELECT data_source_id FROM data_sources WHERE provider_key = 'yfinance' LIMIT 1")
        data_source_id = cursor.fetchone()['data_source_id']
        
        cursor.execute("SELECT dataset_id FROM datasets WHERE dataset_key = 'ohlcv_daily' LIMIT 1")
        dataset_id = cursor.fetchone()['dataset_id']

        # 2. Register Ingestion Job
        job_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO ingestion_jobs (job_id, data_source_id, dataset_id, job_type, target_date, status, started_at)
            VALUES (%s, %s, %s, 'backfill', %s, 'running', now())
        """, (job_id, data_source_id, dataset_id, end_date))
        conn.commit()

        logger.info(f"Started ingestion job {job_id} for symbol {provider_symbol} ({start_date} to {end_date})")

        try:
            # 3. Fetch from yfinance
            ticker = yf.Ticker(provider_symbol)
            df = ticker.history(start=start_date, end=end_date, interval="1d")
            
            # 4. Save Raw Payload
            raw_payload = df.reset_index().to_json(date_format='iso')
            raw_key = f"raw/yfinance/ohlcv/{end_date}/{provider_symbol}.json"
            self.storage.put(raw_key, raw_payload.encode('utf-8'))
            logger.info(f"Saved raw payload to object store: {raw_key}")

            records_received = len(df)
            records_valid = 0
            records_invalid = 0
            records_duplicate = 0

            valid_rows = []

            for idx, row in df.iterrows():
                # Extract columns
                timestamp_str = idx.isoformat()
                open_val = float(row['Open'])
                high_val = float(row['High'])
                low_val = float(row['Low'])
                close_val = float(row['Close'])
                adj_close = float(row.get('Adj Close', close_val))
                volume = int(row['Volume'])

                # Rules validation
                reasons = []
                if pd.isna(open_val) or pd.isna(high_val) or pd.isna(low_val) or pd.isna(close_val):
                    reasons.append("missing_field")
                else:
                    if open_val <= 0 or high_val <= 0 or low_val <= 0 or close_val <= 0:
                        reasons.append("invalid_price")
                    if high_val < open_val or high_val < close_val or low_val > open_val or low_val > close_val or high_val < low_val:
                        reasons.append("invalid_price")
                if volume < 0:
                    reasons.append("out_of_range")

                if reasons:
                    records_invalid += 1
                    # Write to DLQ (rejected_records)
                    cursor.execute("""
                        INSERT INTO rejected_records (job_id, dataset_id, record_data, rejection_reason, rejection_details)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (job_id, dataset_id, json.dumps({'timestamp': timestamp_str, 'open': open_val, 'high': high_val, 'low': low_val, 'close': close_val, 'volume': volume}), reasons[0], f"Failed validations: {', '.join(reasons)}"))
                else:
                    records_valid += 1
                    valid_rows.append({
                        'instrument_id': instrument_id,
                        'timestamp': timestamp_str,
                        'timeframe': '1d',
                        'open': open_val,
                        'high': high_val,
                        'low': low_val,
                        'close': close_val,
                        'adjusted_close': adj_close,
                        'volume': volume,
                        'currency': currency,
                        'source': 'yfinance',
                        'ingested_at': datetime.datetime.utcnow().isoformat() + "Z"
                    })

            # 5. Write to Parquet (idempotent merge)
            if valid_rows:
                new_df = pd.DataFrame(valid_rows)
                new_df['instrument_id'] = new_df['instrument_id'].astype(str)
                
                # Fetch existing partition from storage if exists
                year = start_date[:4]
                parquet_key = f"parquet/ohlcv/{exchange_name}/{year}/data.parquet"
                
                if self.storage.exists(parquet_key):
                    logger.info(f"Partition exists. Merging with existing data for {exchange_name}/{year}")
                    existing_bytes = self.storage.get(parquet_key)
                    # Write to temp file to read via pandas
                    temp_in = f"temp_in_{job_id}.parquet"
                    with open(temp_in, "wb") as f:
                        f.write(existing_bytes)
                    
                    old_df = pd.read_parquet(temp_in)
                    os.remove(temp_in)
                    
                    # Combine and drop duplicates (uniqueness: instrument_id + timestamp + timeframe)
                    combined_df = pd.concat([old_df, new_df]).drop_duplicates(
                        subset=['instrument_id', 'timestamp', 'timeframe'], keep='last'
                    )
                    records_written = len(combined_df)
                else:
                    combined_df = new_df
                    records_written = len(new_df)

                # Write out consolidated Parquet
                temp_out = f"temp_out_{job_id}.parquet"
                combined_df.to_parquet(temp_out, index=False, compression="ZSTD")
                
                with open(temp_out, "rb") as f:
                    self.storage.put(parquet_key, f.read())
                
                os.remove(temp_out)
                logger.info(f"Wrote {records_written} total records to {parquet_key}")
            else:
                records_written = 0

            # 6. Record Job Quality Metric & Finalize Ingestion Job
            quality_score = (records_valid / records_received * 100) if records_received > 0 else 100.0
            
            cursor.execute("""
                INSERT INTO data_quality_results (job_id, dataset_id, records_received, records_valid, records_invalid, records_duplicate, quality_score, validation_summary)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (job_id, dataset_id, records_received, records_valid, records_invalid, records_duplicate, quality_score, json.dumps({"status": "completed"})))

            cursor.execute("""
                UPDATE ingestion_jobs 
                SET status = 'succeeded', completed_at = now(), records_received = %s, records_valid = %s, records_invalid = %s, records_written = %s
                WHERE job_id = %s
            """, (records_received, records_valid, records_invalid, records_written, job_id))
            
            conn.commit()
            logger.info(f"Successfully finalized job {job_id}")

        except Exception as e:
            conn.rollback()
            logger.error(f"Job {job_id} failed: {e}")
            cursor.execute("""
                UPDATE ingestion_jobs 
                SET status = 'failed', completed_at = now(), error_message = %s
                WHERE job_id = %s
            """, (str(e), job_id))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    start = sys.argv[2] if len(sys.argv) > 2 else None
    end = sys.argv[3] if len(sys.argv) > 3 else None
    
    worker = IngestionWorker()
    worker.run(symbol, start, end)
