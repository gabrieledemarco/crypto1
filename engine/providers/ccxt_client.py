"""engine/providers/ccxt_client.py — CCXT-based OHLCV fetcher for crypto assets."""
import datetime
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

# Timeframe → milliseconds per bar (for cursor advancement)
_TF_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
    "1w": 604_800_000, "1M": 2_592_000_000,
}

# Period string → days of history to fetch
_PERIOD_TO_DAYS = {
    "1d": 1, "5d": 5, "1mo": 30, "3mo": 90,
    "6mo": 180, "1y": 365, "2y": 730, "5y": 1825, "max": 1825,
}

# Binance hard limit per request
_BATCH_LIMIT = 1000


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
    Fetch OHLCV bars for a crypto ticker via ccxt with cursor-based pagination.

    Binance hard limit is 1,000 bars/request; the old limit=50000 silently
    truncated at 1,000. This version loops until all history is retrieved.

    Returns DataFrame with DatetimeIndex and columns: Open, High, Low, Close, Volume.
    Raises RuntimeError on failure.
    """
    try:
        import ccxt
    except ImportError:
        raise RuntimeError("ccxt not installed: pip install ccxt")

    symbol = _TICKER_MAP.get(ticker)
    if symbol is None:
        if ticker.endswith("-USD"):
            symbol = ticker[:-4] + "/USDT"
        else:
            raise RuntimeError(f"Cannot map ticker '{ticker}' to ccxt symbol")

    timeframe = _INTERVAL_MAP.get(interval, "1h")
    tf_ms = _TF_MS.get(timeframe, 3_600_000)

    days = _PERIOD_TO_DAYS.get(period, 730)
    now_ms = int(datetime.datetime.utcnow().timestamp() * 1000)
    since_ms = now_ms - int(days * 86_400_000)

    exchange_class = getattr(ccxt, exchange_id, None)
    if exchange_class is None:
        raise RuntimeError(f"Unknown ccxt exchange: {exchange_id}")

    exchange = exchange_class({"enableRateLimit": True})

    all_bars: list = []
    cursor = since_ms

    try:
        while cursor < now_ms:
            try:
                batch = exchange.fetch_ohlcv(
                    symbol, timeframe=timeframe, since=cursor, limit=_BATCH_LIMIT
                )
            except Exception as e:
                raise RuntimeError(f"ccxt fetch failed for {symbol} on {exchange_id}: {e}")

            if not batch:
                break

            all_bars.extend(batch)
            last_ts = batch[-1][0]
            cursor = last_ts + tf_ms

            # Fewer bars than limit means we've reached the end
            if len(batch) < _BATCH_LIMIT:
                break
    finally:
        try:
            exchange.close()
        except Exception:
            pass

    if not all_bars:
        raise RuntimeError(f"No data returned for {symbol}")

    df = pd.DataFrame(all_bars, columns=["ts", "Open", "High", "Low", "Close", "Volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    df = df.set_index("ts")
    df.index.name = None
    df = df[~df.index.duplicated(keep="last")]
    return df.dropna()
