"""
/assets router
==============
POST /assets/fetch           → fetch ticker via yfinance, store in DuckDB
GET  /assets/{ticker}/bars   → OHLCV array
GET  /assets/{ticker}/stats  → quant stats
GET  /assets                 → list available tickers
"""
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import APIRouter, HTTPException
import pandas as pd
import numpy as np
from api.db import get_conn
from api.models import AssetFetch

router = APIRouter()


@router.get("")
def list_assets():
    conn = get_conn()
    rows = conn.execute(
        "SELECT ticker, source, MIN(ts) as start, MAX(ts) as end, COUNT(*) as bars "
        "FROM assets GROUP BY ticker, source ORDER BY ticker"
    ).fetchall()
    return [{"ticker": r[0], "source": r[1], "start": str(r[2]), "end": str(r[3]), "bars": r[4]}
            for r in rows]


@router.post("/fetch")
def fetch_asset(body: AssetFetch):
    from engine.providers.yfinance_client import fetch as yf_fetch

    try:
        df = yf_fetch(body.ticker, period=body.period)
    except Exception as exc:
        raise HTTPException(400, f"Fetch failed: {exc}")

    conn = get_conn()
    # Upsert bars
    inserted = 0
    for ts, row in df.iterrows():
        try:
            conn.execute(
                "INSERT OR IGNORE INTO assets (ticker, source, ts, open, high, low, close, volume) "
                "VALUES (?,?,?,?,?,?,?,?)",
                [body.ticker, body.source, ts,
                 float(row["Open"]), float(row["High"]), float(row["Low"]),
                 float(row["Close"]), float(row["Volume"])]
            )
            inserted += 1
        except Exception:
            pass
    return {"ticker": body.ticker, "bars": inserted, "source": body.source}


@router.get("/{ticker}/bars")
def get_bars(ticker: str, limit: int = 1000):
    conn = get_conn()
    rows = conn.execute(
        "SELECT ts, open, high, low, close, volume FROM assets WHERE ticker=? ORDER BY ts DESC LIMIT ?",
        [ticker, limit]
    ).fetchall()
    if not rows:
        raise HTTPException(404, f"No bars for {ticker}")
    result = list(reversed([
        {"ts": str(r[0]), "o": r[1], "h": r[2], "l": r[3], "c": r[4], "v": r[5]}
        for r in rows
    ]))
    return result


@router.get("/{ticker}/stats")
def get_stats(ticker: str):
    conn = get_conn()
    rows = conn.execute(
        "SELECT ts, close FROM assets WHERE ticker=? ORDER BY ts",
        [ticker]
    ).fetchall()
    if not rows:
        raise HTTPException(404, f"No data for {ticker}")

    closes = np.array([r[1] for r in rows])
    rets   = np.diff(np.log(closes))
    if len(rets) < 2:
        raise HTTPException(400, "Not enough data")

    mean = float(rets.mean())
    std  = float(rets.std())
    sharpe = (mean / std * np.sqrt(24 * 365)) if std > 0 else 0
    # CAGR
    total_ret = closes[-1] / closes[0]
    n_hours   = len(closes)
    cagr      = (total_ret ** (24 * 365 / n_hours) - 1) * 100
    # MaxDD
    peak_arr = np.maximum.accumulate(closes)
    dd_arr   = (closes - peak_arr) / peak_arr * 100
    max_dd   = float(dd_arr.min())
    # Skew/Kurt
    m3 = float(((rets - mean)**3).mean())
    m4 = float(((rets - mean)**4).mean())
    skew = m3 / (std**3) if std > 0 else 0
    kurt = m4 / (std**4) - 3 if std > 0 else 0

    return {
        "ticker": ticker,
        "bars": len(rows),
        "cagr": round(float(cagr), 2),
        "ann_vol": round(float(std * np.sqrt(24 * 365) * 100), 2),
        "sharpe": round(float(sharpe), 3),
        "max_dd": round(float(max_dd), 2),
        "skew": round(float(skew), 3),
        "kurt": round(float(kurt), 3),
    }
