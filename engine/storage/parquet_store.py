"""Parquet-based deep historical M1 store.

Layout: $M1_DATA_DIR/{asset_class}/{symbol}/{year}_{month:02d}.parquet

M1 is the atomic unit; higher timeframes are derived on demand via resample.
Skip-if-exists check is O(1) (Path.exists + size guard).
"""
import gc
import os
from pathlib import Path

import pandas as pd

DATA_DIR = Path(os.environ.get("M1_DATA_DIR", "/data/m1_history"))

_OHLCV_AGG = {
    "Open": "first",
    "High": "max",
    "Low": "min",
    "Close": "last",
    "Volume": "sum",
}

# yfinance-style interval → pandas resample rule
_TF_RESAMPLE: dict[str, str | None] = {
    "1m":  None,     # native M1, no resample
    "5m":  "5min",
    "15m": "15min",
    "30m": "30min",
    "1h":  "1h",
    "4h":  "4h",
    "1d":  "D",
    "1wk": "W",
    "1mo": "MS",     # Month Start anchor
}


def _normalise_symbol(symbol: str) -> str:
    return symbol.upper().replace("/", "").replace("-", "").replace("=", "")


def parquet_path(asset_class: str, symbol: str, year: int, month: int) -> Path:
    return DATA_DIR / asset_class / _normalise_symbol(symbol) / f"{year}_{month:02d}.parquet"


def already_downloaded(asset_class: str, symbol: str, year: int, month: int) -> bool:
    p = parquet_path(asset_class, symbol, year, month)
    return p.exists() and p.stat().st_size >= 512


def write_month(asset_class: str, symbol: str, year: int, month: int,
                df: pd.DataFrame) -> None:
    """Persist a monthly M1 DataFrame (snappy Parquet)."""
    p = parquet_path(asset_class, symbol, year, month)
    p.parent.mkdir(parents=True, exist_ok=True)
    out = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    out.index = pd.to_datetime(out.index)
    out.sort_index(inplace=True)
    out.to_parquet(p, compression="snappy", engine="pyarrow")


def load_range(asset_class: str, symbol: str,
               start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Load M1 data from Parquet files that overlap [start, end]."""
    parts: list[pd.DataFrame] = []
    cur = pd.Timestamp(start.year, start.month, 1)
    while cur <= end:
        p = parquet_path(asset_class, symbol, cur.year, cur.month)
        if p.exists() and p.stat().st_size >= 512:
            chunk = pd.read_parquet(p, engine="pyarrow")
            parts.append(chunk)
            del chunk

        # Advance to next month
        nm = cur.month + 1
        ny = cur.year + (1 if nm > 12 else 0)
        nm = nm if nm <= 12 else 1
        cur = pd.Timestamp(ny, nm, 1)

    if not parts:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    df = pd.concat(parts)
    del parts
    gc.collect()

    df.index = pd.to_datetime(df.index)
    df.sort_index(inplace=True)
    df = df[~df.index.duplicated(keep="last")]
    return df[(df.index >= start) & (df.index <= end)]


def load_and_resample(asset_class: str, symbol: str,
                      start: pd.Timestamp, end: pd.Timestamp,
                      interval: str = "1h") -> pd.DataFrame:
    """Load M1 data and resample to the requested interval."""
    df = load_range(asset_class, symbol, start, end)
    if df.empty:
        return df

    rule = _TF_RESAMPLE.get(interval)
    if rule is None:
        return df  # native M1

    resampled = df.resample(rule).agg(_OHLCV_AGG).dropna(how="all")
    return resampled


def list_available(asset_class: str, symbol: str) -> list[tuple[int, int]]:
    """Return sorted list of (year, month) tuples with downloaded data."""
    base = DATA_DIR / asset_class / _normalise_symbol(symbol)
    if not base.exists():
        return []
    result: list[tuple[int, int]] = []
    for p in sorted(base.glob("*.parquet")):
        try:
            year_s, month_s = p.stem.split("_")
            result.append((int(year_s), int(month_s)))
        except ValueError:
            pass
    return result
