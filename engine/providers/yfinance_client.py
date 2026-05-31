"""Fetch OHLCV bars from yfinance. Fallback provider for non-crypto assets; crypto assets are handled by ccxt_client."""
import time
import pandas as pd

_MAX_ATTEMPTS = 3


def fetch(ticker: str, period: str = "2y", interval: str = "1h") -> pd.DataFrame:
    """
    Returns DataFrame with DatetimeIndex and columns: Open, High, Low, Close, Volume.
    Retries up to 3 times with exponential backoff (2 / 4 / 8 s) before raising.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError("yfinance not installed")

    last_exc: Exception = RuntimeError("unknown")
    for attempt in range(_MAX_ATTEMPTS):
        try:
            df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
            if not df.empty:
                df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
                df.index = pd.to_datetime(df.index).tz_localize(None)
                return df
            last_exc = RuntimeError(f"No data returned for {ticker}")
        except Exception as exc:
            last_exc = exc
        if attempt < _MAX_ATTEMPTS - 1:
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"yfinance fetch failed for {ticker} after {_MAX_ATTEMPTS} attempts: {last_exc}")
