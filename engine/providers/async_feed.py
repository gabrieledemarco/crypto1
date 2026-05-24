"""engine/providers/async_feed.py — Async paginated OHLCV fetcher using ccxt.async_support.

Features:
- Paginated cursor loop (Binance hard limit = 1,000 bars/call)
- asyncio.Semaphore to cap concurrent exchange connections
- Exponential backoff on RateLimitExceeded
- Fan-out parallel fetch across tickers × timeframes
"""
import asyncio
import datetime
from typing import Optional

import pandas as pd

from engine.providers.ccxt_client import _TICKER_MAP, _INTERVAL_MAP, is_crypto_ticker

_SEMAPHORE: Optional[asyncio.Semaphore] = None

# Binance hard limit per request
_BATCH_LIMIT = 1000

_TF_TO_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800, "12h": 43200,
    "1d": 86400, "3d": 259200, "1w": 604800,
}


def _get_semaphore(max_connections: int = 5) -> asyncio.Semaphore:
    global _SEMAPHORE
    if _SEMAPHORE is None:
        _SEMAPHORE = asyncio.Semaphore(max_connections)
    return _SEMAPHORE


async def fetch_ohlcv_full(
    ticker: str,
    timeframe: str = "1h",
    days_back: int = 730,
    exchange_id: str = "binance",
    max_retries: int = 4,
) -> pd.DataFrame:
    """
    Fetch full OHLCV history with pagination, rate-limit retry, and semaphore.

    Args:
        ticker: Asset ticker e.g. "BTC-USD"
        timeframe: ccxt timeframe e.g. "1h", "4h", "1d"
        days_back: How many calendar days of history to fetch
        exchange_id: ccxt exchange ID (default: "binance")
        max_retries: Max retries on RateLimitExceeded

    Returns:
        DataFrame with DatetimeIndex and columns Open/High/Low/Close/Volume.

    Raises:
        RuntimeError on unrecoverable fetch failure.
    """
    try:
        import ccxt.async_support as ccxt_async
    except ImportError:
        raise RuntimeError("ccxt not installed: pip install ccxt")

    symbol = _TICKER_MAP.get(ticker)
    if symbol is None:
        if ticker.endswith("-USD"):
            symbol = ticker[:-4] + "/USDT"
        else:
            raise RuntimeError(f"Cannot map ticker '{ticker}' to ccxt symbol")

    tf = _INTERVAL_MAP.get(timeframe, timeframe)
    tf_secs = _TF_TO_SECONDS.get(tf, 3600)

    now_ms = int(datetime.datetime.utcnow().timestamp() * 1000)
    since_ms = now_ms - int(days_back * 86400 * 1000)

    exchange_class = getattr(ccxt_async, exchange_id, None)
    if exchange_class is None:
        raise RuntimeError(f"Unknown ccxt exchange: {exchange_id}")

    exchange = exchange_class({"enableRateLimit": True})
    sem = _get_semaphore()
    all_bars: list = []

    try:
        async with sem:
            cursor = since_ms
            while cursor < now_ms:
                retries = 0
                batch = None
                while retries <= max_retries:
                    try:
                        batch = await exchange.fetch_ohlcv(
                            symbol, tf, since=cursor, limit=_BATCH_LIMIT
                        )
                        break
                    except Exception as e:
                        err_str = str(e).lower()
                        if "ratelimit" in err_str or "429" in err_str or "too many" in err_str:
                            if retries >= max_retries:
                                raise RuntimeError(f"Rate limit exceeded after {max_retries} retries: {e}")
                            await asyncio.sleep(2 ** retries)
                            retries += 1
                        else:
                            raise RuntimeError(f"ccxt async fetch failed: {e}")

                if not batch:
                    break

                all_bars.extend(batch)
                last_ts = batch[-1][0]
                # Advance cursor by one bar width to avoid re-fetching last bar
                cursor = last_ts + tf_secs * 1000

                # If we got fewer bars than the limit, we've reached the end
                if len(batch) < _BATCH_LIMIT:
                    break
    finally:
        await exchange.close()

    if not all_bars:
        raise RuntimeError(f"No data returned for {symbol}/{tf}")

    df = pd.DataFrame(all_bars, columns=["ts", "Open", "High", "Low", "Close", "Volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_localize(None)
    df = df.set_index("ts")
    df.index.name = None
    # De-duplicate timestamps (rare but possible at pagination boundary)
    df = df[~df.index.duplicated(keep="last")]
    return df.dropna()


async def fetch_all(
    tickers: list,
    timeframes: list,
    days_back: int = 730,
    exchange_id: str = "binance",
    max_connections: int = 5,
) -> dict:
    """
    Fan-out parallel fetch for multiple tickers × timeframes.

    Returns:
        Dict mapping (ticker, timeframe) → DataFrame or Exception.
    """
    global _SEMAPHORE
    _SEMAPHORE = asyncio.Semaphore(max_connections)

    async def _one(ticker, tf):
        try:
            df = await fetch_ohlcv_full(ticker, tf, days_back=days_back, exchange_id=exchange_id)
            return (ticker, tf), df
        except Exception as e:
            return (ticker, tf), e

    tasks = [_one(t, tf) for t in tickers for tf in timeframes]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return dict(results)


def fetch_all_sync(
    tickers: list,
    timeframes: list,
    days_back: int = 730,
    exchange_id: str = "binance",
    max_connections: int = 5,
) -> dict:
    """Sync wrapper around fetch_all for use in synchronous contexts."""
    return asyncio.run(
        fetch_all(tickers, timeframes, days_back=days_back,
                  exchange_id=exchange_id, max_connections=max_connections)
    )
