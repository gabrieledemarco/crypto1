"""Alpaca Data API v2 client for stock M1 bars.

Requires env vars ALPACA_API_KEY and ALPACA_SECRET_KEY.
Falls back to yfinance hourly data when Alpaca is not configured.
"""
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from engine.storage.parquet_store import already_downloaded, write_month

log = logging.getLogger(__name__)

_ALPACA_KEY = lambda: os.environ.get("ALPACA_API_KEY", "")
_ALPACA_SECRET = lambda: os.environ.get("ALPACA_SECRET_KEY", "")


def is_alpaca_configured() -> bool:
    return bool(_ALPACA_KEY() and _ALPACA_SECRET())


def _fetch_month_alpaca(symbol: str, year: int, month: int) -> pd.DataFrame:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(_ALPACA_KEY(), _ALPACA_SECRET())

    # Inclusive start/end for the calendar month
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    nm = month + 1
    ny = year + (1 if nm > 12 else 0)
    nm = nm if nm <= 12 else 1
    end = datetime(ny, nm, 1, tzinfo=timezone.utc) - timedelta(seconds=1)

    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed="iex",  # free tier; use "sip" for paid
    )
    bars = client.get_stock_bars(req)
    df = bars.df

    if df.empty:
        return pd.DataFrame()

    # alpaca-py returns MultiIndex (symbol, timestamp) when single symbol
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level="symbol")

    df.index = pd.to_datetime(df.index).tz_localize(None)
    rename = {"open": "Open", "high": "High", "low": "Low",
              "close": "Close", "volume": "Volume"}
    df.rename(columns={k: v for k, v in rename.items() if k in df.columns}, inplace=True)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


def _fetch_month_yfinance_h1(symbol: str, year: int, month: int) -> pd.DataFrame:
    """yfinance hourly fallback — only ~2 years of history available."""
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()

    start = datetime(year, month, 1)
    nm = month + 1
    ny = year + (1 if nm > 12 else 0)
    nm = nm if nm <= 12 else 1
    end = datetime(ny, nm, 1)

    df = yf.Ticker(symbol).history(start=start, end=end, interval="1h", auto_adjust=True)
    if df.empty:
        return pd.DataFrame()
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


def backfill(ticker: str,
             start_year: int = 2015, start_month: int = 1,
             end_year: int | None = None, end_month: int | None = None) -> int:
    """Download missing monthly stock bars via Alpaca (or yfinance H1 fallback).

    Returns total rows stored.
    """
    now = datetime.utcnow()
    if end_year is None:
        end_year = now.year
    if end_month is None:
        end_month = now.month - 1
        if end_month == 0:
            end_month = 12
            end_year -= 1

    use_alpaca = is_alpaca_configured()
    if not use_alpaca:
        log.warning("ALPACA_API_KEY not set — falling back to yfinance H1 for %s", ticker)

    total = 0
    cur_y, cur_m = start_year, start_month
    while (cur_y, cur_m) <= (end_year, end_month):
        if already_downloaded("stock", ticker, cur_y, cur_m):
            log.debug("skip %s %d-%02d", ticker, cur_y, cur_m)
        else:
            try:
                if use_alpaca:
                    df = _fetch_month_alpaca(ticker, cur_y, cur_m)
                else:
                    df = _fetch_month_yfinance_h1(ticker, cur_y, cur_m)

                if not df.empty:
                    write_month("stock", ticker, cur_y, cur_m, df)
                    total += len(df)
                    log.info("stored %s %d-%02d rows=%d", ticker, cur_y, cur_m, len(df))
                time.sleep(0.3)
            except Exception as exc:
                log.warning("alpaca_client error %s %d-%02d: %s", ticker, cur_y, cur_m, exc)

        cur_m += 1
        if cur_m > 12:
            cur_m, cur_y = 1, cur_y + 1

    return total
