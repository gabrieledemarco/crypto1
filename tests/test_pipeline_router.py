"""
Tests for api/routers/pipeline.py — no external network required.
"""
import json
import sys
import os
import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api.routers.pipeline import (
    PipelineRequest,
    _resample,
    _TF_NORM,
    _YF_PERIOD,
    _ANN_FACTORS,
    _ACTIVE_HOURS,
)


# ── PipelineRequest validation ─────────────────────────────────────────────────

def test_pipeline_request_defaults():
    req = PipelineRequest()
    assert req.tickers == ["BTC-USD", "ETH-USD", "SOL-USD"]
    assert req.timeframes == ["1h", "4h", "1d"]
    assert req.max_iter == 30
    assert req.stop_sharpe == 1.5
    assert req.max_dd == 20.0
    assert req.period is None


def test_pipeline_request_custom():
    req = PipelineRequest(
        tickers=["BTC-USD"],
        timeframes=["1h"],
        max_iter=5,
        stop_sharpe=2.0,
        max_dd=15.0,
        period="30d",
    )
    assert req.tickers == ["BTC-USD"]
    assert req.max_iter == 5
    assert req.period == "30d"


# ── Timeframe normalisation ────────────────────────────────────────────────────

def test_tf_norm_covers_common_aliases():
    assert _TF_NORM["1min"] == "1m"
    assert _TF_NORM["1h"] == "1h"
    assert _TF_NORM["4h"] == "4h"
    assert _TF_NORM["1d"] == "1d"


def test_yf_period_all_tfs_covered():
    for tf in ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]:
        assert tf in _YF_PERIOD, f"{tf} missing from _YF_PERIOD"


def test_ann_factors_ordering():
    # Higher frequency → higher annualisation factor
    assert _ANN_FACTORS["1m"] > _ANN_FACTORS["5m"] > _ANN_FACTORS["1h"] > _ANN_FACTORS["1d"]


def test_active_hours_all_tfs_covered():
    for tf in ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]:
        assert tf in _ACTIVE_HOURS
        lo, hi = _ACTIVE_HOURS[tf]
        assert 0 <= lo <= hi <= 23


# ── _resample helper ───────────────────────────────────────────────────────────

def _make_ohlcv(n=200, freq="1h"):
    idx = pd.date_range("2024-01-01", periods=n, freq=freq)
    rng = np.random.default_rng(42)
    close = 30000 + np.cumsum(rng.normal(0, 100, n))
    df = pd.DataFrame({
        "Open":   close * 0.999,
        "High":   close * 1.002,
        "Low":    close * 0.997,
        "Close":  close,
        "Volume": rng.integers(100, 1000, n).astype(float),
    }, index=idx)
    return df


def test_resample_1h_to_4h():
    df_1h = _make_ohlcv(200, "1h")
    df_4h = _resample(df_1h, "4h")
    assert not df_4h.empty
    assert len(df_4h) <= len(df_1h) // 4 + 1
    assert list(df_4h.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_resample_1h_to_1d():
    df_1h = _make_ohlcv(240, "1h")
    df_1d = _resample(df_1h, "1d")
    assert not df_1d.empty
    assert len(df_1d) <= 11  # 240h / 24 = 10 days


def test_resample_unknown_tf_returns_original():
    df = _make_ohlcv(50, "1h")
    result = _resample(df, "3h")  # not in freq_map
    assert len(result) == len(df)


def test_resample_high_is_max():
    df_1h = _make_ohlcv(48, "1h")
    df_1d = _resample(df_1h, "1d")
    # Each daily High must be ≥ every hourly High in that day
    for day, group in df_1h.groupby(df_1h.index.date):
        ts = pd.Timestamp(day)
        if ts in df_1d.index:
            assert df_1d.loc[ts, "High"] >= group["High"].max() - 1e-9


def test_resample_low_is_min():
    df_1h = _make_ohlcv(48, "1h")
    df_1d = _resample(df_1h, "1d")
    for day, group in df_1h.groupby(df_1h.index.date):
        ts = pd.Timestamp(day)
        if ts in df_1d.index:
            assert df_1d.loc[ts, "Low"] <= group["Low"].min() + 1e-9


def test_resample_volume_is_sum():
    df_1h = _make_ohlcv(48, "1h")
    df_1d = _resample(df_1h, "1d")
    total_h = df_1h["Volume"].sum()
    total_d = df_1d["Volume"].sum()
    assert abs(total_h - total_d) < 1e-6


# ── SSE endpoint plumbing (async) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_pipeline_returns_job_id(monkeypatch):
    """POST /runs/pipeline should return a job_id without actually running."""
    import asyncio
    from api.routers.pipeline import start_pipeline

    # Prevent the background task from actually executing
    monkeypatch.setattr(asyncio, "create_task", lambda coro: coro.close() or None)

    req = PipelineRequest(tickers=["BTC-USD"], timeframes=["1h"], max_iter=1)
    result = await start_pipeline(req)

    assert "job_id" in result
    assert len(result["job_id"]) == 12
    assert result["stream_url"] == f"/runs/pipeline/{result['job_id']}/stream"
    assert result["tickers"] == ["BTC-USD"]


@pytest.mark.asyncio
async def test_stream_pipeline_terminates_on_complete():
    """SSE generator must stop after receiving a 'complete' event."""
    import asyncio
    from api.routers.pipeline import _queues, stream_pipeline

    job_id = "testjob00001"
    import asyncio
    q = asyncio.Queue()
    _queues[job_id] = q

    events = [
        {"type": "start"},
        {"type": "iter_done", "iter": 1},
        {"type": "complete", "total_tickers": 1, "robust_found": 0, "summary": []},
    ]
    for e in events:
        q.put_nowait(e)

    response = await stream_pipeline(job_id)
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    assert len(chunks) == 3
    assert '"type": "complete"' in chunks[-1]
    assert job_id not in _queues  # cleaned up


@pytest.mark.asyncio
async def test_stream_pipeline_terminates_on_error():
    """SSE generator must stop after receiving an 'error' event."""
    import asyncio
    from api.routers.pipeline import _queues, stream_pipeline

    job_id = "testjob00002"
    q = asyncio.Queue()
    _queues[job_id] = q
    q.put_nowait({"type": "error", "msg": "something blew up"})

    response = await stream_pipeline(job_id)
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    assert len(chunks) == 1
    assert "error" in chunks[0]
    assert job_id not in _queues
