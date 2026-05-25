"""Benchmark and unit tests for engine/storage/bulk_writer.py

Run with:
    python3 tests/test_bulk_writer.py
"""
import sys
import os
import time
import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def _make_df(n_bars: int = 20_401) -> pd.DataFrame:
    """Generate a synthetic OHLCV DataFrame with n_bars rows for benchmarking."""
    rng = np.random.default_rng(42)
    base = 30_000.0
    closes = base + np.cumsum(rng.normal(0, 50, n_bars))
    opens = closes + rng.normal(0, 10, n_bars)
    highs = np.maximum(opens, closes) + rng.uniform(0, 20, n_bars)
    lows = np.minimum(opens, closes) - rng.uniform(0, 20, n_bars)
    volumes = rng.uniform(100, 1000, n_bars)

    idx = pd.date_range(
        start=datetime.datetime(2022, 1, 1),
        periods=n_bars,
        freq="1h",
    )
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
        index=idx,
    )


def _make_db():
    import duckdb
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE assets (
            ticker  VARCHAR NOT NULL,
            source  VARCHAR NOT NULL,
            ts      TIMESTAMP NOT NULL,
            open    DOUBLE,
            high    DOUBLE,
            low     DOUBLE,
            close   DOUBLE,
            volume  DOUBLE,
            PRIMARY KEY (ticker, source, ts)
        )
    """)
    return conn


def bench_row_by_row(conn, df: pd.DataFrame, ticker: str = "BTC-USD", source: str = "bench:row") -> tuple:
    start = time.perf_counter()
    count = 0
    for ts, row in df.iterrows():
        try:
            conn.execute(
                "INSERT OR IGNORE INTO assets (ticker, source, ts, open, high, low, close, volume) "
                "VALUES (?,?,?,?,?,?,?,?)",
                [ticker, source, ts,
                 float(row["Open"]), float(row["High"]), float(row["Low"]),
                 float(row["Close"]), float(row["Volume"])]
            )
            count += 1
        except Exception:
            pass
    elapsed = time.perf_counter() - start
    return count, elapsed


def bench_bulk_arrow(conn, df: pd.DataFrame, ticker: str = "BTC-USD", source: str = "bench:arrow") -> tuple:
    from engine.storage.bulk_writer import bulk_store
    start = time.perf_counter()
    count = bulk_store(conn, ticker, source, df)
    elapsed = time.perf_counter() - start
    return count, elapsed


def test_bulk_writer_correctness():
    """Verify bulk_store inserts the correct number of rows and deduplicates."""
    from engine.storage.bulk_writer import bulk_store

    df = _make_df(100)
    conn = _make_db()

    n = bulk_store(conn, "BTC-USD", "test:1h", df)
    assert n == 100, f"Expected 100 rows, got {n}"

    # Re-insert same data — should insert 0 (all duplicates)
    n2 = bulk_store(conn, "BTC-USD", "test:1h", df)
    total = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    assert total == 100, f"Expected 100 rows in DB after dedup, got {total}"
    assert n2 == 0, f"Expected 0 new rows on re-insert, got {n2}"
    print(f"  correctness: OK — inserted {n}, re-insert={n2} (dedup), DB total={total}")


def test_benchmark(n_bars: int = 20_401):
    """Benchmark row-by-row vs PyArrow bulk insert."""
    print(f"\nBenchmark: {n_bars:,} rows")
    df = _make_df(n_bars)

    # Row-by-row
    conn_rr = _make_db()
    rr_count, rr_elapsed = bench_row_by_row(conn_rr, df)
    rr_rate = rr_count / rr_elapsed if rr_elapsed > 0 else 0

    # Bulk PyArrow
    conn_ar = _make_db()
    ar_count, ar_elapsed = bench_bulk_arrow(conn_ar, df)
    ar_rate = ar_count / ar_elapsed if ar_elapsed > 0 else 0

    speedup = rr_elapsed / ar_elapsed if ar_elapsed > 0 else float("inf")

    print(f"  Row-by-row : {rr_count:,} rows in {rr_elapsed:.3f}s  ({rr_rate:,.0f} rows/s)")
    print(f"  PyArrow    : {ar_count:,} rows in {ar_elapsed:.4f}s  ({ar_rate:,.0f} rows/s)")
    print(f"  Speedup    : {speedup:.1f}×")

    assert rr_count == ar_count, f"Row count mismatch: {rr_count} vs {ar_count}"
    # Speed comparison is environment-dependent; we only assert correctness here


def test_pagination_logic():
    """Verify ccxt_client pagination constants are set correctly."""
    from engine.providers.ccxt_client import _BATCH_LIMIT, _PERIOD_TO_DAYS, _TF_MS

    assert _BATCH_LIMIT == 1000, "Binance limit should be 1000"
    assert _PERIOD_TO_DAYS["2y"] == 730
    assert _PERIOD_TO_DAYS["max"] == 1825
    assert _TF_MS["1h"] == 3_600_000
    assert _TF_MS["4h"] == 14_400_000
    assert _TF_MS["1d"] == 86_400_000
    print("  pagination constants: OK")


def test_async_feed_importable():
    """Verify async_feed module imports cleanly."""
    from engine.providers import async_feed  # noqa: F401
    assert hasattr(async_feed, "fetch_ohlcv_full")
    assert hasattr(async_feed, "fetch_all")
    assert hasattr(async_feed, "fetch_all_sync")
    print("  async_feed module: OK")


if __name__ == "__main__":
    print("=" * 60)
    print("engine/storage/bulk_writer — test suite")
    print("=" * 60)

    print("\n[1] Correctness test")
    test_bulk_writer_correctness()

    print("\n[2] Benchmark")
    speedup = test_benchmark()

    print("\n[3] Pagination constants")
    test_pagination_logic()

    print("\n[4] async_feed importable")
    test_async_feed_importable()

    print(f"\n{'=' * 60}")
    print(f"All tests passed. PyArrow bulk insert is {speedup:.1f}× faster.")
    print("=" * 60)
