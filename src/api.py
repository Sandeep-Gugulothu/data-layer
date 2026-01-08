import os
import psycopg2
from psycopg2.extras import RealDictCursor
import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from src.config import DATABASE_URL, LOCAL_STORAGE_PATH, logger
from src.storage import get_storage

app = FastAPI(title="Financial Data Platform API", version="1.0")

# Enable CORS for frontend connectivity
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# ── Front-End / Demo Serving API Endpoints ────────────────────────────────────

@app.get("/equity/quote")
def get_equity_quote(symbol: str = Query(...), exchange: str = Query("NSE")):
    import yfinance as yf
    
    yf_symbol = symbol
    if exchange == "NSE" and not symbol.endswith(".NS"):
        yf_symbol = f"{symbol}.NS"
    elif exchange == "BSE" and not symbol.endswith(".BO"):
        yf_symbol = f"{symbol}.BO"
        
    try:
        ticker = yf.Ticker(yf_symbol)
        info = ticker.info
        if not info or not info.get("regularMarketPrice"):
            raise HTTPException(status_code=404, detail=f"No quote data from yfinance for {yf_symbol}")
            
        return {
            "symbol": symbol,
            "name": info.get("longName", symbol),
            "price": info.get("regularMarketPrice", 0.0),
            "open": info.get("regularMarketOpen", 0.0),
            "high": info.get("regularMarketDayHigh", 0.0),
            "low": info.get("regularMarketDayLow", 0.0),
            "prev_close": info.get("regularMarketPreviousClose", 0.0),
            "change": info.get("regularMarketPrice", 0.0) - info.get("regularMarketPreviousClose", 0.0),
            "change_pct": ((info.get("regularMarketPrice", 0.0) - info.get("regularMarketPreviousClose", 0.0)) / info.get("regularMarketPreviousClose", 1.0)) * 100 if info.get("regularMarketPreviousClose") else 0.0,
            "volume": info.get("regularMarketVolume", 0),
            "market_cap": info.get("marketCap", 0),
            "exchange": exchange,
            "currency": info.get("currency", "INR")
        }
    except Exception as e:
        logger.error(f"Error fetching quote for {yf_symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/equity/profile")
def get_equity_profile(symbol: str = Query(...), exchange: str = Query("NSE")):
    import yfinance as yf
    
    yf_symbol = symbol
    if exchange == "NSE" and not symbol.endswith(".NS"):
        yf_symbol = f"{symbol}.NS"
    elif exchange == "BSE" and not symbol.endswith(".BO"):
        yf_symbol = f"{symbol}.BO"
        
    try:
        ticker = yf.Ticker(yf_symbol)
        info = ticker.info
        if not info:
            raise HTTPException(status_code=404, detail="Profile not found")
            
        return {
            "symbol": symbol,
            "exchange": exchange,
            "name": info.get("longName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "website": info.get("website"),
            "description": info.get("longBusinessSummary"),
            "currency": info.get("currency", "INR")
        }
    except Exception as e:
        logger.error(f"Error fetching profile for {yf_symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/equity/historical")
def get_equity_historical(
    symbol: str = Query(...),
    exchange: str = Query("NSE"),
    start_date: str = Query(None),
    end_date: str = Query(None),
    interval: str = Query("1d")
):
    import yfinance as yf
    
    yf_symbol = symbol
    if exchange == "NSE" and not symbol.endswith(".NS"):
        yf_symbol = f"{symbol}.NS"
    elif exchange == "BSE" and not symbol.endswith(".BO"):
        yf_symbol = f"{symbol}.BO"
        
    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(start=start_date, end=end_date, interval=interval)
        if df.empty:
            raise HTTPException(status_code=404, detail="No historical data found")
            
        df = df.reset_index()
        df = df.rename(columns={
            "Date": "date",
            "Datetime": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume"
        })
        
        # Convert date to string format
        df['date'] = df['date'].astype(str)
        
        records = df[['date', 'open', 'high', 'low', 'close', 'volume']].to_dict(orient="records")
        return records
    except Exception as e:
        logger.error(f"Error fetching historical data for {yf_symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/equity/news")
def get_equity_news(symbol: str = Query(...), exchange: str = Query("NSE")):
    import yfinance as yf
    
    yf_symbol = symbol
    if exchange == "NSE" and not symbol.endswith(".NS"):
        yf_symbol = f"{symbol}.NS"
    elif exchange == "BSE" and not symbol.endswith(".BO"):
        yf_symbol = f"{symbol}.BO"
        
    try:
        ticker = yf.Ticker(yf_symbol)
        news = ticker.news
        if not news:
            return []
            
        return [{
            "title": item.get("title"),
            "publisher": item.get("publisher"),
            "link": item.get("link"),
            "providerPublishTime": item.get("providerPublishTime"),
            "type": item.get("type")
        } for item in news]
    except Exception as e:
        logger.error(f"Error fetching news for {yf_symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tickers/search")
def search_tickers(q: str = Query(...)):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Scan instruments seeded in database matching query symbol or name
        query = """
            SELECT i.symbol, i.name, e.acronym as exchange
            FROM instruments i
            JOIN exchanges e ON i.exchange_id = e.exchange_id
            WHERE i.symbol ILIKE %s OR i.name ILIKE %s
            LIMIT 10
        """
        cursor.execute(query, (f"%{q}%", f"%{q}%"))
        res = cursor.fetchall()
        return res
    except Exception as e:
        logger.error(f"Error searching tickers: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

@app.get("/api/institutional/latest-bulk-deals")
def get_latest_bulk_deals():
    # Simple clean mock data feed to populate the frontend's transaction card
    return [
        {
            "trade_date": "2026-08-28",
            "symbol": "SBIN",
            "client_name": "RELIANCE MUTUAL FUND",
            "deal_type": "BUY",
            "quantity": 1250000,
            "price": 1045.20,
            "pct_equity": 0.13
        },
        {
            "trade_date": "2026-08-28",
            "symbol": "RELIANCE",
            "client_name": "HDFC MUTUAL FUND",
            "deal_type": "BUY",
            "quantity": 450000,
            "price": 2450.50,
            "pct_equity": 0.08
        }
    ]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
