"""engine/providers/ccxt_client.py — CCXT-based OHLCV fetcher for crypto assets."""
import pandas as pd


# Mapping from yfinance-style ticker to ccxt symbol
_TICKER_MAP = {
    "BTC-USD": "BTC/USDT",
    "ETH-USD": "ETH/USDT",
    "SOL-USD": "SOL/USDT",
    "BNB-USD": "BNB/USDT",
    "XRP-USD": "XRP/USDT",
    "ADA-USD": "ADA/USDT",
    "DOGE-USD": "DOGE/USDT",
}

# yfinance interval → ccxt timeframe
_INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d", "1wk": "1w", "1mo": "1M",
}

_PERIOD_TO_LIMIT = {
    "1d": 1440, "5d": 7200, "1mo": 2000, "3mo": 6000,
    "6mo": 6000, "1y": 8760, "2y": 17520, "5y": 43800, "max": 50000,
}


def is_crypto_ticker(ticker: str) -> bool:
    """Return True if ticker is a known crypto or follows CRYPTO-USD pattern."""
    if ticker in _TICKER_MAP:
        return True
    if ticker.endswith("-USD") and len(ticker) <= 12:
        base = ticker[:-4]
        return base.isalpha() and base.isupper() and len(base) <= 6
    return False


def fetch(ticker: str, period: str = "2y", interval: str = "1h",
          exchange_id: str = "binance") -> pd.DataFrame:
    """
    Fetch OHLCV bars for a crypto ticker via ccxt (Binance by default).
    Returns DataFrame with DatetimeIndex and columns: Open, High, Low, Close, Volume.
    Raises RuntimeError on failure.
    """
    try:
        import ccxt
    except ImportError:
        raise RuntimeError("ccxt not installed: pip install ccxt")

    symbol = _TICKER_MAP.get(ticker)
    if symbol is None:
        # Try to construct symbol from ticker like "XYZ-USD" → "XYZ/USDT"
        if ticker.endswith("-USD"):
            symbol = ticker[:-4] + "/USDT"
        else:
            raise RuntimeError(f"Cannot map ticker '{ticker}' to ccxt symbol")

    timeframe = _INTERVAL_MAP.get(interval, "1h")
    limit = _PERIOD_TO_LIMIT.get(period, 17520)

    exchange_class = getattr(ccxt, exchange_id, None)
    if exchange_class is None:
        raise RuntimeError(f"Unknown ccxt exchange: {exchange_id}")

    exchange = exchange_class({"enableRateLimit": True})

    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    except Exception as e:
        raise RuntimeError(f"ccxt fetch failed for {symbol} on {exchange_id}: {e}")

    if not ohlcv:
        raise RuntimeError(f"No data returned for {symbol}")

    df = pd.DataFrame(ohlcv, columns=["ts", "Open", "High", "Low", "Close", "Volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    df = df.set_index("ts")
    df.index.name = None
    return df.dropna()
