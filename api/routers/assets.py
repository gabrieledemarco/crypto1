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

from fastapi import APIRouter, HTTPException, Query
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
    result = []
    for r in rows:
        source = r[1]
        interval = source.split(":")[-1] if ":" in source else "1d"
        result.append({
            "ticker": r[0], "source": r[1], "interval": interval,
            "start": str(r[2]), "end": str(r[3]), "bars": r[4]
        })
    return result


@router.get("/{ticker}/series")
def list_ticker_series(ticker: str):
    """All stored series (interval + date range) for a single ticker."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT source, MIN(ts) as start, MAX(ts) as end, COUNT(*) as bars "
        "FROM assets WHERE ticker=? GROUP BY source ORDER BY source",
        [ticker]
    ).fetchall()
    result = []
    for r in rows:
        source = r[0]
        interval = source.split(":")[-1] if ":" in source else "1d"
        result.append({
            "ticker": ticker, "source": source, "interval": interval,
            "start": str(r[1]), "end": str(r[2]), "bars": r[3]
        })
    return result


@router.post("/fetch")
def fetch_asset(body: AssetFetch):
    from engine.providers.yfinance_client import fetch as yf_fetch

    try:
        df = yf_fetch(body.ticker, period=body.period, interval=body.interval)
    except Exception as exc:
        raise HTTPException(400, f"Fetch failed: {exc}")

    conn = get_conn()
    source_key = f"{body.source}:{body.interval}"
    # Upsert bars
    inserted = 0
    for ts, row in df.iterrows():
        try:
            conn.execute(
                "INSERT OR IGNORE INTO assets (ticker, source, ts, open, high, low, close, volume) "
                "VALUES (?,?,?,?,?,?,?,?)",
                [body.ticker, source_key, ts,
                 float(row["Open"]), float(row["High"]), float(row["Low"]),
                 float(row["Close"]), float(row["Volume"])]
            )
            inserted += 1
        except Exception:
            pass
    return {"ticker": body.ticker, "bars": inserted, "source": source_key}


@router.get("/{ticker}/bars")
def get_bars(ticker: str, limit: int = 1000, interval: str = "1d"):
    source_key = f"yfinance:{interval}"
    conn = get_conn()
    # backward compat: 1d also matches legacy source="yfinance"
    if interval == "1d":
        rows = conn.execute(
            "SELECT ts, open, high, low, close, volume FROM assets "
            "WHERE ticker=? AND (source=? OR source=?) ORDER BY ts DESC LIMIT ?",
            [ticker, source_key, "yfinance", limit]
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT ts, open, high, low, close, volume FROM assets "
            "WHERE ticker=? AND source=? ORDER BY ts DESC LIMIT ?",
            [ticker, source_key, limit]
        ).fetchall()
    if not rows:
        raise HTTPException(404, f"No bars for {ticker} @ {interval}")
    result = list(reversed([
        {"ts": str(r[0]), "o": r[1], "h": r[2], "l": r[3], "c": r[4], "v": r[5]}
        for r in rows
    ]))
    return result


@router.get("/{ticker}/stats")
def get_stats(ticker: str, interval: str = "1d"):
    BARS_PER_YEAR = {
        "1m": 60*24*365, "5m": 12*24*365, "15m": 4*24*365,
        "30m": 2*24*365, "1h": 24*365, "4h": 6*365,
        "1d": 365, "1wk": 52, "1mo": 12,
    }
    ann_factor = BARS_PER_YEAR.get(interval, 365)
    source_key = f"yfinance:{interval}"
    conn = get_conn()
    # backward compat: 1d also matches legacy source="yfinance"
    if interval == "1d":
        rows = conn.execute(
            "SELECT ts, close FROM assets WHERE ticker=? AND (source=? OR source=?) ORDER BY ts",
            [ticker, source_key, "yfinance"]
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT ts, close FROM assets WHERE ticker=? AND source=? ORDER BY ts",
            [ticker, source_key]
        ).fetchall()
    if not rows:
        raise HTTPException(404, f"No data for {ticker}")

    closes = np.array([r[1] for r in rows])
    rets   = np.diff(np.log(closes))
    if len(rets) < 2:
        raise HTTPException(400, "Not enough data")

    mean = float(rets.mean())
    std  = float(rets.std())
    sharpe = (mean / std * np.sqrt(ann_factor)) if std > 0 else 0
    # CAGR
    total_ret = closes[-1] / closes[0]
    n_hours   = len(closes)
    cagr      = (total_ret ** (ann_factor / n_hours) - 1) * 100
    # MaxDD
    peak_arr = np.maximum.accumulate(closes)
    dd_arr   = (closes - peak_arr) / peak_arr * 100
    max_dd   = float(dd_arr.min())
    # Skew/Kurt
    m3 = float(((rets - mean)**3).mean())
    m4 = float(((rets - mean)**4).mean())
    skew = m3 / (std**3) if std > 0 else 0
    kurt = m4 / (std**4) - 3 if std > 0 else 0

    # Daily aggregation for sortino, var95, cvar95, best_day, worst_day
    day_closes: dict = {}
    for ts, c in rows:
        day = str(ts)[:10]
        day_closes[day] = float(c)
    daily_vals = np.array([v for _, v in sorted(day_closes.items())])
    daily_rets = np.diff(np.log(daily_vals)) if len(daily_vals) > 1 else np.array([])

    if len(daily_rets) > 1:
        neg_rets = daily_rets[daily_rets < 0]
        down_std = float(neg_rets.std()) if len(neg_rets) > 1 else 0
        daily_mean = float(daily_rets.mean())
        sortino   = float(daily_mean * 252 / (down_std * np.sqrt(252))) if down_std > 0 else 0
        var95     = float(np.percentile(daily_rets, 5))
        mask      = daily_rets <= np.percentile(daily_rets, 5)
        cvar95    = float(daily_rets[mask].mean()) if mask.any() else var95
        best_day  = float(daily_rets.max())
        worst_day = float(daily_rets.min())
    else:
        sortino = var95 = cvar95 = best_day = worst_day = 0.0

    return {
        "ticker": ticker,
        "bars": len(rows),
        "cagr": round(float(cagr), 2),
        "ann_vol": round(float(std * np.sqrt(ann_factor) * 100), 2),
        "sharpe": round(float(sharpe), 3),
        "max_dd": round(float(max_dd), 2),
        "skew": round(float(skew), 3),
        "kurt": round(float(kurt), 3),
        "sortino":   round(sortino, 3),
        "var95":     round(var95, 4),
        "cvar95":    round(cvar95, 4),
        "best_day":  round(best_day, 4),
        "worst_day": round(worst_day, 4),
    }


@router.get("/{ticker}/quant")
def get_quant_stats(ticker: str, interval: str = Query("1h")):
    """Return Hurst, stationarity, VaR/CVaR for a stored asset series."""
    from engine.quant_stats import compute_hurst, test_stationarity, compute_var_cvar, rolling_metrics
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT close FROM assets WHERE ticker = ? AND interval = ? ORDER BY ts ASC",
            [ticker.replace("-USD", ""), interval]
        ).fetchall()
    except Exception:
        rows = []
    if not rows or len(rows) < 50:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}/{interval} (need ≥50 bars)")
    prices = np.array([r[0] for r in rows], dtype=float)
    rets = np.diff(np.log(prices[prices > 0]))
    return {
        "ticker": ticker,
        "interval": interval,
        "n_bars": len(prices),
        "hurst": compute_hurst(prices),
        "stationarity": test_stationarity(prices),
        "var_cvar": compute_var_cvar(rets),
        "rolling": rolling_metrics(prices),
    }
