"""Fetch OHLCV bars from yfinance. Fallback provider for non-crypto assets; crypto assets are handled by ccxt_client."""
import pandas as pd


def fetch(ticker: str, period: str = "2y", interval: str = "1h") -> pd.DataFrame:
    """
    Returns DataFrame with DatetimeIndex and columns: Open, High, Low, Close, Volume.
    Raises RuntimeError on failure.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError("yfinance not installed")
    t = yf.Ticker(ticker)
    df = t.history(period=period, interval=interval, auto_adjust=True)
    if df.empty:
        raise RuntimeError(f"No data returned for {ticker}")
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df
