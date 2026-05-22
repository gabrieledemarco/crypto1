"""Alpaca OHLCV client — stub for future implementation."""
import pandas as pd


def fetch(ticker: str, period: str = "2y", interval: str = "1h") -> pd.DataFrame:
    """
    Fetch OHLCV bars from Alpaca Markets API.
    Not yet implemented — will be added in a future milestone.
    """
    raise NotImplementedError(
        "Alpaca client is not yet implemented. "
        "Use engine.providers.yfinance_client.fetch() instead, "
        "or set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables "
        "once this provider is implemented."
    )
