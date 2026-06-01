"""Tests for engine/storage/parquet_store.py"""
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def _patch_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("M1_DATA_DIR", str(tmp_path))
    import engine.storage.parquet_store as ps
    monkeypatch.setattr(ps, "DATA_DIR", tmp_path)
    return tmp_path


def _make_m1(n: int = 60) -> pd.DataFrame:
    idx = pd.date_range("2023-01-01", periods=n, freq="1min")
    return pd.DataFrame(
        {"Open": 1.0, "High": 1.01, "Low": 0.99, "Close": 1.0, "Volume": 100.0},
        index=idx,
    )


def test_parquet_path_normalisation():
    from engine.storage.parquet_store import parquet_path
    p1 = parquet_path("crypto", "BTC-USD", 2023, 1)
    p2 = parquet_path("crypto", "btc-usd", 2023, 1)
    assert p1.name == p2.name == "2023_01.parquet"
    assert p1.parent.name == "BTCUSD"


def test_write_and_read_month():
    from engine.storage.parquet_store import write_month, load_range

    df = _make_m1(60)
    write_month("crypto", "BTC-USD", 2023, 1, df)

    result = load_range(
        "crypto", "BTC-USD",
        pd.Timestamp("2023-01-01"),
        pd.Timestamp("2023-01-31"),
    )
    assert not result.empty
    assert list(result.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_already_downloaded_false_when_missing():
    from engine.storage.parquet_store import already_downloaded
    assert not already_downloaded("crypto", "BTC-USD", 2099, 1)


def test_already_downloaded_true_after_write():
    from engine.storage.parquet_store import write_month, already_downloaded
    write_month("crypto", "BTC-USD", 2023, 3, _make_m1(30))
    assert already_downloaded("crypto", "BTC-USD", 2023, 3)


def test_list_available_empty():
    from engine.storage.parquet_store import list_available
    assert list_available("crypto", "UNKNOWN") == []


def test_list_available_returns_sorted_months():
    from engine.storage.parquet_store import write_month, list_available
    write_month("crypto", "ETH-USD", 2023, 2, _make_m1(10))
    write_month("crypto", "ETH-USD", 2023, 1, _make_m1(10))
    available = list_available("crypto", "ETH-USD")
    assert available == [(2023, 1), (2023, 2)]


def test_load_range_spans_multiple_months():
    from engine.storage.parquet_store import write_month, load_range

    for month in [1, 2, 3]:
        idx = pd.date_range(f"2023-{month:02d}-01", periods=30, freq="1min")
        df = pd.DataFrame(
            {"Open": float(month), "High": float(month), "Low": float(month),
             "Close": float(month), "Volume": 10.0},
            index=idx,
        )
        write_month("crypto", "SOL-USD", 2023, month, df)

    result = load_range(
        "crypto", "SOL-USD",
        pd.Timestamp("2023-01-01"),
        pd.Timestamp("2023-03-31"),
    )
    assert len(result) == 90


def test_load_and_resample_to_1h():
    from engine.storage.parquet_store import write_month, load_and_resample

    # 120 M1 bars = 2 hours of data
    idx = pd.date_range("2023-06-01 00:00", periods=120, freq="1min")
    df = pd.DataFrame(
        {"Open": 1.0, "High": 1.05, "Low": 0.95, "Close": 1.0, "Volume": 1.0},
        index=idx,
    )
    write_month("crypto", "BTC-USD", 2023, 6, df)

    result = load_and_resample(
        "crypto", "BTC-USD",
        pd.Timestamp("2023-06-01"),
        pd.Timestamp("2023-06-30"),
        interval="1h",
    )
    assert not result.empty
    assert len(result) == 2
    assert result["High"].max() == pytest.approx(1.05)


def test_load_range_no_data_returns_empty():
    from engine.storage.parquet_store import load_range
    result = load_range(
        "stock", "AAPL",
        pd.Timestamp("2023-01-01"),
        pd.Timestamp("2023-01-31"),
    )
    assert result.empty
