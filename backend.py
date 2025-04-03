from fastapi import FastAPI, Query, HTTPException
import yfinance as yf
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from typing import Optional, List
from datetime import datetime, timedelta
import requests
import time
from functools import lru_cache

# Cache to store responses and avoid redundant API calls
@lru_cache(maxsize=1000)
def get_stock_data(ticker, period="1d", interval="1h"):
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period=period, interval=interval)
        return data
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None

# Fetch multiple tickers in a batch - more efficient than individual requests
def get_multiple_stocks(tickers, period="1d", interval="1h"):
    try:
        # Use yf.download instead of individual requests
        data = yf.download(" ".join(tickers), period=period, interval=interval, group_by='ticker')
        results = {}
        
        for ticker in tickers:
            if len(tickers) > 1:
                results[ticker] = data[ticker]
            else:
                results[ticker] = data
        
        return results
    except Exception as e:
        print(f"Error fetching multiple stocks: {e}")
        return None

# Initialize FastAPI app
app = FastAPI(title="Enhanced Financial Data API",
              description="Comprehensive API for stocks, forex, mutual funds, and index funds data")

# Enable CORS for frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to your frontend URL for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants for time periods
TIME_PERIODS = {
    "30d": 30,
    "90d": 90,
    "1y": 365,
    "all": None  # None will use max available data in yfinance
}

# Exchange suffix mapping
EXCHANGE_MAPPING = {
    "nse": ".NS",
    "bse": ".BO",
    "nasdaq": "",
    "nyse": ""
}

# Common indices mapping for easy reference
INDICES_MAPPING = {
    "nifty50": "^NSEI",
    "sensex": "^BSESN",
    "sp500": "^GSPC",
    "dow": "^DJI",
    "nasdaq": "^IXIC",
    "ftse": "^FTSE",
    "nikkei": "^N225"
}

# Forex pairs mapping
FOREX_MAPPING = {
    "usd_inr": "USD/INR=X",
    "eur_inr": "EUR/INR=X",
    "gbp_usd": "GBP/USD=X",
    "eur_usd": "EUR/USD=X",
    "jpy_usd": "JPY/USD=X"
}

# Helper function to calculate date range from period
def get_date_range(period):
    days = TIME_PERIODS.get(period, 90)
    end_date = datetime.now()
    start_date = None if days is None else end_date - timedelta(days=days)
    return start_date, end_date

# ✅ 1️⃣ Root Endpoint (Check if API is running)
@app.get("/")
def root():
    return {
        "message": "Welcome to the Enhanced Financial Data API!",
        "features": [
            "Stock Data (Indian & Global)",
            "Forex Trading Data",
            "Index Fund Data",
            "Mutual Fund Data"
        ]
    }

# ✅ 2️⃣ Search Stocks by Name or Symbol
@app.get("/search/")
def search_instruments(
    query: str, 
    limit: Optional[int] = Query(10, description="Maximum number of results"),
    type: Optional[str] = Query(None, description="Filter by type: stock, forex, index, mutual_fund")
):
    try:
        # For production, better search API options:
        # 1. Alpha Vantage Symbol Search
        # 2. Yahoo Finance API through RapidAPI
        # 3. Custom database with pre-loaded symbols and names
        
        # Basic implementation using yfinance
        results = []
        
        # Add stock search
        if type is None or type == "stock":
            tickers = yf.Tickers(query)
            for ticker_name, ticker_obj in tickers.tickers.items():
                try:
                    info = ticker_obj.info
                    exchange = ""
                    if ".NS" in ticker_name:
                        exchange = "NSE"
                    elif ".BO" in ticker_name:
                        exchange = "BSE"
                    elif info.get('exchange') in ['NMS', 'NGS', 'NCM', 'NGM']:
                        exchange = "NASDAQ"
                    elif info.get('exchange') in ['NYQ', 'PSE', 'PCX', 'ASE', 'AMX']:
                        exchange = "NYSE"
                        
                    if info.get('quoteType') == 'EQUITY':
                        results.append({
                            "symbol": ticker_name,
                            "name": info.get('shortName', 'Unknown'),
                            "exchange": exchange,
                            "type": "stock"
                        })
                except:
                    continue
        
        # Add forex search
        if type is None or type == "forex":
            for key, symbol in FOREX_MAPPING.items():
                if query.lower() in key or query.lower() in symbol.lower():
                    results.append({
                        "symbol": symbol,
                        "name": symbol.replace("=X", ""),
                        "type": "forex"
                    })
        
        # Add index search
        if type is None or type == "index":
            for key, symbol in INDICES_MAPPING.items():
                if query.lower() in key or query.lower() in symbol.lower():
                    results.append({
                        "symbol": symbol,
                        "name": key.capitalize(),
                        "type": "index"
                    })
        
        return {"results": results[:limit]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ✅ 3️⃣ Get Stock Data (with exchange support)
@app.get("/stock/{symbol}")
def get_stock_data_endpoint(
    symbol: str,
    period: Optional[str] = Query("90d", description="Time period: 30d, 90d, 1y, all"),
    interval: Optional[str] = Query("1d", description="Data interval: 1d, 1wk, 1mo"),
    exchange: Optional[str] = Query(None, description="Exchange: nse, bse")
):
    try:
        # Add exchange suffix if specified
        if exchange and exchange.lower() in EXCHANGE_MAPPING:
            if not symbol.endswith(EXCHANGE_MAPPING[exchange.lower()]):
                symbol = symbol + EXCHANGE_MAPPING[exchange.lower()]
        
        # Use the cached function to get data
        start_date, end_date = get_date_range(period)
        
        # Try to get from cache first
        data = get_stock_data(symbol, period=period, interval=interval)
        if data is None:
            stock = yf.Ticker(symbol)
            data = stock.history(start=start_date, end=end_date, interval=interval)
        
        # Get stock info
        stock = yf.Ticker(symbol)
        info = stock.info
        name = info.get('shortName', 'Unknown')
        sector = info.get('sector', 'Unknown')
        market_cap = info.get('marketCap', 'Unknown')
        
        if data.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol}.")
        
        # Get current/live price
        live_price = info.get('currentPrice', info.get('regularMarketPrice', None))
        
        # Format response
        return {
            "symbol": symbol,
            "name": name,
            "sector": sector,
            "market_cap": market_cap,
            "live_price": live_price,
            "period": period,
            "interval": interval,
            "data": data.reset_index().to_dict(orient="records")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ✅ 4️⃣ Get Forex Data
@app.get("/forex/{pair}")
def get_forex_data(
    pair: str,
    period: Optional[str] = Query("90d", description="Time period: 30d, 90d, 1y, all"),
    interval: Optional[str] = Query("1d", description="Data interval: 1d, 1wk, 1mo")
):
    try:
        # Map common forex pair names
        symbol = FOREX_MAPPING.get(pair.lower(), pair)
        if not symbol.endswith('=X'):
            symbol = symbol + '=X'
            
        forex = yf.Ticker(symbol)
        
        # Get forex info
        info = forex.info
        name = info.get('shortName', symbol)
        
        # Get date range
        start_date, end_date = get_date_range(period)
        
        # Get historical data
        data = get_stock_data(symbol, period=period, interval=interval)
        if data is None:
            data = forex.history(start=start_date, end=end_date, interval=interval)
        
        if data.empty:
            raise HTTPException(status_code=404, detail=f"No data found for forex pair {pair}.")
        
        # Get current/live price
        live_rate = info.get('regularMarketPrice', None)
        
        # Format response
        return {
            "symbol": symbol,
            "name": name,
            "live_rate": live_rate,
            "period": period,
            "interval": interval,
            "data": data.reset_index().to_dict(orient="records")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ✅ 5️⃣ Get Index Data
@app.get("/index/{symbol}")
def get_index_data(
    symbol: str,
    period: Optional[str] = Query("90d", description="Time period: 30d, 90d, 1y, all"),
    interval: Optional[str] = Query("1d", description="Data interval: 1d, 1wk, 1mo")
):
    # Map from common names to actual symbols
    actual_symbol = INDICES_MAPPING.get(symbol.lower(), symbol)
    
    try:
        index = yf.Ticker(actual_symbol)
        
        # Get index info
        info = index.info
        name = info.get('shortName', actual_symbol)
        
        # Get date range
        start_date, end_date = get_date_range(period)
        
        # Get historical data
        data = get_stock_data(actual_symbol, period=period, interval=interval)
        if data is None:
            data = index.history(start=start_date, end=end_date, interval=interval)
        
        if data.empty:
            raise HTTPException(status_code=404, detail=f"No data found for index {symbol}.")
        
        # Get current/live value
        live_value = info.get('regularMarketPrice', None)
        
        # Format response
        return {
            "symbol": actual_symbol,
            "name": name,
            "live_value": live_value,
            "period": period,
            "interval": interval,
            "data": data.reset_index().to_dict(orient="records")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ✅ 6️⃣ Get Mutual Fund Data
@app.get("/mutual-fund/{symbol}")
def get_mutual_fund_data(
    symbol: str,
    period: Optional[str] = Query("90d", description="Time period: 30d, 90d, 1y, all"),
    interval: Optional[str] = Query("1d", description="Data interval: 1d, 1wk, 1mo")
):
    try:
        fund = yf.Ticker(symbol)
        
        # Get fund info
        info = fund.info
        name = info.get('shortName', 'Unknown')
        category = info.get('category', 'Unknown')
        
        # Get date range
        start_date, end_date = get_date_range(period)
        
        # Get historical data
        data = get_stock_data(symbol, period=period, interval=interval)
        if data is None:
            data = fund.history(start=start_date, end=end_date, interval=interval)
        
        if data.empty:
            raise HTTPException(status_code=404, detail=f"No data found for mutual fund {symbol}.")
        
        # Get current/live NAV
        live_nav = info.get('regularMarketPrice', None)
        
        # Format response
        return {
            "symbol": symbol,
            "name": name,
            "category": category,
            "live_nav": live_nav,
            "period": period,
            "interval": interval,
            "data": data.reset_index().to_dict(orient="records")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ✅ 7️⃣ Compare Multiple Instruments (Stocks, Indices, Forex, Mutual Funds)
@app.get("/compare/")
def compare_instruments(
    symbols: str = Query(..., description="Comma-separated list of symbols to compare"),
    period: Optional[str] = Query("90d", description="Time period: 30d, 90d, 1y, all"),
    interval: Optional[str] = Query("1d", description="Data interval: 1d, 1wk, 1mo")
):
    symbol_list = [s.strip() for s in symbols.split(',')]
    
    try:
        # Get date range
        start_date, end_date = get_date_range(period)
        
        # Use the optimized get_multiple_stocks function for batch fetching
        if len(symbol_list) > 1:
            result = get_multiple_stocks(symbol_list, period=period, interval=interval)
            
            if not result:
                # Fallback to yf.download
                data = yf.download(symbol_list, start=start_date, end=end_date, interval=interval)
                
                if data.empty:
                    raise HTTPException(status_code=404, detail="No data found for the specified symbols.")
                
                # Format the multi-level columns for easier consumption
                result = {}
                for field in ['Open', 'High', 'Low', 'Close', 'Volume']:
                    if field in data.columns.levels[0]:
                        field_data = data[field].reset_index()
                        result[field] = field_data.to_dict(orient="records")
                
                return {
                    "symbols": symbol_list,
                    "period": period,
                    "interval": interval,
                    "data": result
                }
            else:
                # Format the data from get_multiple_stocks
                formatted_result = {}
                for ticker, ticker_data in result.items():
                    formatted_result[ticker] = ticker_data.reset_index().to_dict(orient="records")
                
                return {
                    "symbols": symbol_list,
                    "period": period,
                    "interval": interval,
                    "data": formatted_result
                }
        else:
            # For single symbol, reuse get_stock_data
            data = get_stock_data(symbol_list[0], period=period, interval=interval)
            if data is None:
                data = yf.Ticker(symbol_list[0]).history(start=start_date, end=end_date, interval=interval)
            
            return {
                "symbol": symbol_list[0],
                "period": period,
                "interval": interval,
                "data": data.reset_index().to_dict(orient="records")
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ✅ 8️⃣ Get Popular Indian Mutual Funds by Category
@app.get("/mutual-funds/india/popular")
def get_popular_indian_mutual_funds(
    category: Optional[str] = Query(None, description="Fund category: equity, debt, hybrid, etc.")
):
    # This would ideally come from a database, but for demonstration:
    popular_funds = {
        "equity": [
            {"name": "HDFC Top 100 Fund", "symbol": "0P0000XVOI.BO"},
            {"name": "SBI Bluechip Fund", "symbol": "0P0000YCNI.BO"},
            {"name": "Axis Bluechip Fund", "symbol": "0P0000Z5X9.BO"},
            {"name": "Mirae Asset Large Cap Fund", "symbol": "0P0000YD2F.BO"}
        ],
        "debt": [
            {"name": "HDFC Corporate Bond Fund", "symbol": "0P0000YWLG.BO"},
            {"name": "SBI Corporate Bond Fund", "symbol": "0P0000ZM1O.BO"},
            {"name": "Kotak Corporate Bond Fund", "symbol": "0P0000Y5QE.BO"}
        ],
        "hybrid": [
            {"name": "ICICI Prudential Balanced Advantage Fund", "symbol": "0P0000XVE2.BO"},
            {"name": "HDFC Balanced Advantage Fund", "symbol": "0P0000XV7Y.BO"}
        ]
    }
    
    if category and category.lower() in popular_funds:
        return {"funds": popular_funds[category.lower()]}
    else:
        return {"funds": {cat: funds for cat, funds in popular_funds.items()}}

# Run FastAPI server
if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.environ.get("PORT", 10000))  # Use Render’s PORT or default 10000
    uvicorn.run(app, host="0.0.0.0", port=port)
