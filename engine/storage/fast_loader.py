"""
fast_loader.py — DuckDB parallel Parquet scan + in-process warm cache.

Replaces the per-call load_and_resample() with:
  1. DuckDB ":memory:" connection that scans Parquet files in parallel
     using predicate pushdown on the timestamp index. Target: <50ms for
     2-year 1h series (vs ~400ms for sequential pandas read_parquet loop).
  2. A bounded in-process warm cache (max 150MB) with 30-min TTL so
     repeated backtest requests on the same ticker hit RAM, not disk.

Falls back to parquet_store.load_and_resample() transparently on any error.
"""
import logging
import threading
import time

import duckdb
import pandas as pd

from engine.storage.parquet_store import DATA_DIR, load_and_resample

log = logging.getLogger("fast_loader")

_duck = duckdb.connect(":memory:")
_duck_lock = threading.Lock()

_WARM: dict[str, tuple[pd.DataFrame, float]] = {}
_WARM_LOCK = threading.Lock()
_WARM_TTL = 1800       # seconds (30 min)
_WARM_MAX_MB = 150     # total MB across all cached frames

_TF_RESAMPLE: dict[str, str | None] = {
    "1m":  None,
    "5m":  "5min",
    "15m": "15min",
    "30m": "30min",
    "1h":  "1h",
    "4h":  "4h",
    "1d":  "D",
    "1wk": "W",
    "1mo": "MS",
}

_OHLCV_AGG = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}


from engine.storage.parquet_store import _normalise_symbol as _normalise


def _parquet_glob(asset_class: str, symbol: str) -> str:
    return str(DATA_DIR / asset_class / _normalise(symbol) / "*.parquet")


def load_fast(
    asset_class: str,
    ticker: str,
    interval: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """
    Load OHLCV data via DuckDB parallel Parquet scan, resample to interval.
    Returns empty DataFrame (not an exception) when no data is found.
    """
    cache_key = f"{ticker}:{interval}:{start.date()}:{end.date()}"
    now = time.time()

    # 1. Warm cache hit
    with _WARM_LOCK:
        entry = _WARM.get(cache_key)
        if entry and now - entry[1] < _WARM_TTL:
            return entry[0].copy()

    # 2. DuckDB parallel scan
    glob = _parquet_glob(asset_class, ticker)
    try:
        sql = f"""
            SELECT index AS ts, Open, High, Low, Close, Volume
            FROM read_parquet('{glob}', hive_partitioning=false)
            WHERE index >= '{start}' AND index <= '{end}'
            ORDER BY index
        """
        with _duck_lock:
            df = _duck.execute(sql).df()

        if df.empty:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        df["ts"] = pd.to_datetime(df["ts"])
        df = df.set_index("ts")
        df.index.name = None

        rule = _TF_RESAMPLE.get(interval)
        if rule:
            df = df.resample(rule).agg(_OHLCV_AGG).dropna(how="all")

        # 3. Store in warm cache
        with _WARM_LOCK:
            _evict_if_needed()
            _WARM[cache_key] = (df.copy(), now)

        log.debug("load_fast ok ticker=%s interval=%s rows=%d", ticker, interval, len(df))
        return df

    except Exception as exc:
        log.warning("load_fast fallback for %s/%s: %s", ticker, interval, exc)
        return load_and_resample(asset_class, ticker, start, end, interval)


def _evict_if_needed() -> None:
    """Evict oldest cache entry if total memory exceeds _WARM_MAX_MB."""
    total_mb = sum(
        df.memory_usage(deep=True).sum() / 1_048_576
        for df, _ in _WARM.values()
    )
    while total_mb > _WARM_MAX_MB and _WARM:
        oldest_key = min(_WARM.items(), key=lambda x: x[1][1])[0]
        evicted_mb = _WARM[oldest_key][0].memory_usage(deep=True).sum() / 1_048_576
        del _WARM[oldest_key]
        total_mb -= evicted_mb


def warm_preload(asset_class: str, ticker: str, interval: str = "1h") -> None:
    """Preload last 3 years into warm cache (called at startup in a daemon thread)."""
    try:
        end = pd.Timestamp.now()
        start = end - pd.DateOffset(years=3)
        df = load_fast(asset_class, ticker, interval, start, end)
        if not df.empty:
            log.info("prewarm ok %s/%s rows=%d", ticker, interval, len(df))
    except Exception as exc:
        log.debug("prewarm skipped %s/%s: %s", ticker, interval, exc)


def cache_stats() -> dict:
    """Return current warm cache stats (used by /health endpoint)."""
    with _WARM_LOCK:
        total_mb = sum(
            df.memory_usage(deep=True).sum() / 1_048_576
            for df, _ in _WARM.values()
        )
        return {"entries": len(_WARM), "total_mb": round(total_mb, 1), "ttl_s": _WARM_TTL}
