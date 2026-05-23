"""
engine/indicators.py
====================
Lazy indicator dispatcher for agent_fn use.
make_ind(df) → ind(name, *params) callable.
"""
import numpy as np
import pandas as pd


def make_ind(df: pd.DataFrame):
    """Return a cached indicator function bound to df."""
    cache: dict = {}

    def _col(name_lower: str, name_upper: str):
        if name_upper in df.columns:
            return df[name_upper]
        if name_lower in df.columns:
            return df[name_lower]
        raise KeyError(f"Column {name_upper!r} not found in DataFrame")

    def ind(name: str, *params):
        key = (name.upper(), params)
        if key in cache:
            return cache[key]

        n = name.upper()
        close = _col("close", "Close")
        high  = _col("high",  "High")  if ("High"  in df.columns or "high"  in df.columns) else close
        low   = _col("low",   "Low")   if ("Low"   in df.columns or "low"   in df.columns) else close
        vol   = _col("volume","Volume") if ("Volume" in df.columns or "volume" in df.columns) else pd.Series(1.0, index=df.index)

        result = None

        if n == "EMA":
            span = int(params[0]) if params else 20
            result = close.ewm(span=span, adjust=False).mean()

        elif n == "SMA":
            window = int(params[0]) if params else 20
            result = close.rolling(window).mean()

        elif n == "RSI":
            span = int(params[0]) if params else 14
            delta = close.diff()
            gain = delta.clip(lower=0).ewm(span=span, adjust=False).mean()
            loss = (-delta.clip(upper=0)).ewm(span=span, adjust=False).mean()
            result = 100 - 100 / (1 + gain / loss.replace(0, np.nan))

        elif n in ("BBANDS", "BB", "BOLLINGER"):
            window = int(params[0]) if params else 20
            k      = float(params[1]) if len(params) > 1 else 2.0
            mid    = close.rolling(window).mean()
            std    = close.rolling(window).std()
            # Returns (upper, mid, lower) tuple — caller indexes as needed
            result = (mid + k * std, mid, mid - k * std)

        elif n == "VWAP":
            typical = (high + low + close) / 3
            cumvol  = vol.cumsum()
            result  = (typical * vol).cumsum() / cumvol.replace(0, np.nan)

        elif n == "ATR":
            span = int(params[0]) if params else 14
            hl   = high - low
            hc   = (high - close.shift(1)).abs()
            lc   = (low  - close.shift(1)).abs()
            tr   = pd.concat([hl, hc, lc], axis=1).max(axis=1)
            result = tr.ewm(span=span, adjust=False).mean()

        elif n == "MACD":
            fast     = int(params[0]) if params else 12
            slow_p   = int(params[1]) if len(params) > 1 else 26
            signal_p = int(params[2]) if len(params) > 2 else 9
            macd_line   = close.ewm(span=fast).mean() - close.ewm(span=slow_p).mean()
            signal_line = macd_line.ewm(span=signal_p).mean()
            result = (macd_line, signal_line, macd_line - signal_line)

        elif n in ("STOCH", "STOCHASTIC"):
            k_period = int(params[0]) if params else 14
            d_period = int(params[1]) if len(params) > 1 else 3
            low_n  = low.rolling(k_period).min()
            high_n = high.rolling(k_period).max()
            k = 100 * (close - low_n) / (high_n - low_n).replace(0, np.nan)
            result = (k, k.rolling(d_period).mean())

        elif n in ("ROLLHIGH", "ROLLING_HIGH"):
            window = int(params[0]) if params else 6
            result = high.rolling(window).max().shift(1)

        elif n in ("ROLLLOW", "ROLLING_LOW"):
            window = int(params[0]) if params else 6
            result = low.rolling(window).min().shift(1)

        elif n == "DONCHIAN":
            window = int(params[0]) if params else 20
            result = (high.rolling(window).max(), low.rolling(window).min())

        else:
            # Unknown — return zeros (won't crash, agent should log a warning)
            result = pd.Series(0.0, index=df.index)

        cache[key] = result
        return result

    return ind
