"""
Integration test: POST /runs → poll until done → verify metrics.

Uses a temp-file DuckDB and synthetic bar data so no network calls are needed.
A temp file (rather than :memory:) is required because FastAPI runs sync
endpoints in a thread pool — each worker thread would otherwise get its own
empty in-memory database.
"""
import datetime
import json
import sys
import os
import tempfile
import time

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def _seed_bars(conn, ticker: str = "BTC-USD", tf: str = "1h", n: int = 500) -> None:
    """Insert synthetic OHLCV bars into the assets table.

    Source format must match the 'source LIKE %:<interval>' pattern in _load_or_fetch.
    """
    rng = np.random.default_rng(0)
    closes = 30_000.0 + np.cumsum(rng.normal(0, 50, n))
    opens = closes + rng.normal(0, 10, n)
    highs = np.maximum(opens, closes) + rng.uniform(0, 20, n)
    lows = np.minimum(opens, closes) - rng.uniform(0, 20, n)
    volumes = rng.uniform(100, 1_000, n)
    idx = pd.date_range(start=datetime.datetime(2023, 1, 1), periods=n, freq="1h")
    source = f"yfinance:{tf}"

    conn.executemany(
        "INSERT OR IGNORE INTO assets (ticker, source, ts, open, high, low, close, volume) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [
            (ticker, source, ts.to_pydatetime(), float(o), float(h), float(l), float(c), float(v))
            for ts, o, h, l, c, v in zip(idx, opens, highs, lows, closes, volumes)
        ],
    )


@pytest.fixture()
def client():
    """Start the FastAPI app against a temp-file DuckDB so all threads share data."""
    import api.db as _db
    from api.main import app
    from fastapi.testclient import TestClient

    with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as f:
        db_path = f.name  # file is deleted on close — DuckDB will create it fresh

    # Point the module at the temp file before any connection is made
    original_path = _db.DB_PATH
    _db.DB_PATH = db_path
    _db._schema_done = False
    if hasattr(_db._local, "conn") and _db._local.conn is not None:
        try:
            _db._local.conn.close()
        except Exception:
            pass
        _db._local.conn = None

    conn = _db.get_conn()
    _seed_bars(conn)
    conn.commit()

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    # Cleanup
    _db.DB_PATH = original_path
    _db._schema_done = False
    if hasattr(_db._local, "conn") and _db._local.conn is not None:
        try:
            _db._local.conn.close()
        except Exception:
            pass
        _db._local.conn = None
    try:
        os.unlink(db_path)
    except OSError:
        pass


def test_run_lifecycle(client):
    """POST /runs → poll GET /runs/{id} until done → assert metrics present."""
    payload = {
        "ticker": "BTC-USD",
        "timeframe": "1h",
        "commission": 0.0004,
        "slippage": 0.0001,
        "sl_mult": 1.5,
        "tp_mult": 2.5,
        "risk_per_trade": 0.01,
        "direction": "ALL",
    }
    resp = client.post("/runs", json=payload)
    assert resp.status_code == 200, f"POST /runs failed: {resp.text}"
    run_id = resp.json().get("id") or resp.json().get("run_id")
    assert run_id, f"No run_id in response: {resp.json()}"

    # Poll until done or error (max 90 s)
    deadline = time.time() + 90
    status = None
    while time.time() < deadline:
        r = client.get(f"/runs/{run_id}")
        assert r.status_code == 200
        data = r.json()
        status = data.get("status")
        if status in ("done", "error"):
            break
        time.sleep(0.5)

    assert status == "done", f"Run ended with status={status!r}"

    # Verify metrics dict is present (even a zero-trade run returns a metrics dict)
    data = client.get(f"/runs/{run_id}").json()
    metrics = data.get("metrics")
    assert metrics, "No metrics returned for completed run"

    # Find a metrics version with actual trade data (skip error-only entries)
    m = None
    for v in metrics.values():
        if "sharpe_ratio" in v and "n_trades" in v:
            m = v
            break

    if m is not None and m.get("n_trades", 0) > 0:
        # When trades are present: verify caps hold
        pf = m.get("profit_factor")
        assert pf is not None, "profit_factor missing"
        assert pf <= 999.9, f"profit_factor not capped: {pf}"
        assert m["sharpe_ratio"] != float("inf"), "sharpe should not be inf"
        assert m["sharpe_ratio"] != float("-inf"), "sharpe should not be -inf"

    # Equity endpoint must return a list (may be empty for zero-trade run)
    eq_resp = client.get(f"/runs/{run_id}/equity")
    assert eq_resp.status_code == 200
    eq = eq_resp.json()
    assert isinstance(eq, list), "Equity response should be a list"

    # Trades endpoint must return the correct shape
    tr_resp = client.get(f"/runs/{run_id}/trades")
    assert tr_resp.status_code == 200
    tr = tr_resp.json()
    assert "total" in tr and "trades" in tr, "Trades response malformed"
