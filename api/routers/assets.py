"""
/assets router
==============
POST /assets/fetch               → fetch ticker via yfinance, store in DuckDB
POST /assets/backfill            → start deep M1 backfill (SSE progress)
GET  /assets/backfill/{job}/stream → SSE stream for backfill progress
GET  /assets/{ticker}/bars       → OHLCV array
GET  /assets/{ticker}/stats      → quant stats
GET  /assets                     → list available tickers
"""
import asyncio
import atexit
import json
import sys, os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
import pandas as pd
import numpy as np
from api.db import get_conn
from api.limiter import limiter
from api.models import AssetFetch, BackfillRequest
from engine.config import ANN_FACTORS as _BARS_PER_YEAR

# ── Backfill job state ─────────────────────────────────────────────────────────
_backfill_queues: dict[str, asyncio.Queue] = {}
_bf_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="backfill")
atexit.register(_bf_executor.shutdown, wait=False)

# Simple TTL cache for quant stats (expensive: Hurst, ADF, GARCH)
_QUANT_CACHE: dict[tuple, tuple] = {}  # key → (result, computed_at)
_QUANT_CACHE_LOCK = threading.Lock()
_QUANT_TTL = 300  # seconds

router = APIRouter()


@router.post("/repair")
def repair_assets(conn=None):
    """
    Remove all 'parquet:*' rows from the assets table.

    These rows were written by old versions of _load_or_fetch which incorrectly
    cached Parquet data into DuckDB. Interrupting that write left the table with
    partial/corrupted rows. After this repair, historical data is served directly
    from the Parquet files (the authoritative store).

    Safe to call multiple times — idempotent.
    """
    if conn is None:
        conn = get_conn()
    try:
        before = conn.execute(
            "SELECT COUNT(*) FROM assets WHERE source LIKE 'parquet:%'"
        ).fetchone()[0]
        conn.execute("DELETE FROM assets WHERE source LIKE 'parquet:%'")
        conn.commit()
        return {
            "ok": True,
            "deleted": before,
            "message": (
                f"Removed {before} cached rows (parquet:* source). "
                "Historical data is now served directly from Parquet files."
            ),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Repair failed: {exc}")


@router.delete("/history")
def delete_history(ticker: str | None = None):
    """
    Delete Parquet history files to free Railway disk space.
    Runs and strategies in DuckDB are NOT affected.

    - DELETE /assets/history          → deletes ALL symbols
    - DELETE /assets/history?ticker=BTC-USD → deletes one symbol only

    Returns a summary of what was removed.
    """
    import shutil
    from engine.storage.parquet_store import DATA_DIR

    removed_files = 0
    removed_bytes = 0

    if ticker:
        from engine.storage.parquet_store import _normalise_symbol
        symbol_dir = DATA_DIR / "crypto" / _normalise_symbol(ticker)
        if symbol_dir.exists():
            for f in symbol_dir.glob("*.parquet"):
                removed_bytes += f.stat().st_size
                removed_files += 1
            shutil.rmtree(symbol_dir)
        target = str(symbol_dir)
    else:
        if DATA_DIR.exists():
            for f in DATA_DIR.rglob("*.parquet"):
                removed_bytes += f.stat().st_size
                removed_files += 1
            shutil.rmtree(DATA_DIR)
        target = str(DATA_DIR)

    return {
        "ok": True,
        "target": target,
        "removed_files": removed_files,
        "freed_mb": round(removed_bytes / 1_048_576, 1),
        "message": f"Deleted {removed_files} Parquet file(s), freed {round(removed_bytes/1_048_576,1)} MB. DuckDB runs/strategies intact.",
    }


@router.get("")
def list_assets():
    """List all available tickers with their source, interval, date range and bar count."""
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
@limiter.limit("10/minute")
def fetch_asset(request: Request, body: AssetFetch):
    VALID_INTERVALS = {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"}
    if body.interval not in VALID_INTERVALS:
        raise HTTPException(400, f"Invalid interval '{body.interval}'. Must be one of: {sorted(VALID_INTERVALS)}")

    try:
        from engine.providers.ccxt_client import is_crypto_ticker, fetch as ccxt_fetch
        from engine.providers.yfinance_client import fetch as yf_fetch
        if is_crypto_ticker(body.ticker):
            try:
                df = ccxt_fetch(body.ticker, period=body.period, interval=body.interval)
            except Exception as ccxt_exc:
                # fallback to yfinance if ccxt fails
                try:
                    df = yf_fetch(body.ticker, period=body.period, interval=body.interval)
                except Exception as yf_exc:
                    raise HTTPException(400, f"Fetch failed (ccxt: {ccxt_exc}; yfinance: {yf_exc})")
        else:
            df = yf_fetch(body.ticker, period=body.period, interval=body.interval)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Fetch failed: {exc}")

    conn = get_conn()
    source_key = f"{body.source}:{body.interval}"
    from engine.storage.bulk_writer import bulk_store
    inserted = bulk_store(conn, body.ticker, source_key, df)
    return {"ticker": body.ticker, "bars": inserted, "source": source_key}


@router.post("/backfill")
async def start_backfill(body: BackfillRequest):
    """Start a deep M1 backfill for a ticker. Returns a job_id to stream progress."""
    from datetime import datetime
    try:
        start = datetime.strptime(body.start_date, "%Y-%m-%d")
        end   = datetime.strptime(body.end_date,   "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(400, f"Invalid date format: {exc}")
    if start > end:
        raise HTTPException(400, "start_date must be ≤ end_date")

    job_id = str(uuid.uuid4())[:8]
    queue: asyncio.Queue = asyncio.Queue()
    _backfill_queues[job_id] = queue
    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        _bf_executor,
        _run_backfill_thread,
        job_id, body.ticker,
        start.year, start.month, end.year, end.month,
        body.interval, loop,
    )
    return {"job_id": job_id}


def _run_backfill_thread(job_id: str, ticker: str,
                          start_year: int, start_month: int,
                          end_year: int, end_month: int,
                          interval: str, loop: asyncio.AbstractEventLoop) -> None:
    queue = _backfill_queues.get(job_id)

    def push(msg: str, phase: str = "running", pct: int = 0, rows_total: int = 0) -> None:
        if queue:
            asyncio.run_coroutine_threadsafe(
                queue.put({"phase": phase, "pct": pct, "msg": msg, "rows_total": rows_total}),
                loop,
            )

    try:
        total_months = (end_year - start_year) * 12 + (end_month - start_month + 1)
        push(
            f"Avvio backfill {ticker} · {start_year}-{start_month:02d} → {end_year}-{end_month:02d} ({total_months} mesi)",
            pct=0,
        )

        from engine.backfill import backfill_ticker, classify_ticker

        def on_progress(year, month, month_idx, total_mo, month_rows, rows_total):
            pct = int(month_idx / total_mo * 90)  # reserve last 10% for resample
            cached = month_rows == 0
            label = "cached" if cached else f"+{month_rows:,} righe"
            push(
                f"{year}-{month:02d}  [{month_idx}/{total_mo}]  {label}  · totale {rows_total:,}",
                pct=pct,
                rows_total=rows_total,
            )

        result = backfill_ticker(
            ticker, start_year, start_month, end_year, end_month,
            on_progress=on_progress,
        )

        if not result.get("ok"):
            push(result.get("error", "Backfill fallito"), "error", pct=0)
            return

        m1_rows = result.get("rows", 0)
        push(f"Download completato · {m1_rows:,} righe M1 · verifica file Parquet…", pct=92, rows_total=m1_rows)

        # Count available months in Parquet store for final summary
        try:
            from engine.backfill import classify_ticker as _cls
            from engine.storage.parquet_store import list_available
            asset_class = _cls(ticker)
            available = list_available(asset_class, ticker)
            n_months = len(available)
        except Exception:
            n_months = total_months

        push(
            f"✓ {m1_rows:,} righe M1 · {n_months} mesi Parquet · pronto per backtest",
            "done",
            pct=100,
            rows_total=m1_rows,
        )

    except Exception as exc:
        push(f"Backfill fallito: {exc}", "error", pct=0)


@router.get("/backfill/{job_id}/stream")
async def stream_backfill(job_id: str):
    """SSE stream for a running backfill job."""
    queue = _backfill_queues.get(job_id)
    if queue is None:
        raise HTTPException(404, "Backfill job not found")

    async def generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=3600)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'phase': 'error', 'msg': 'timeout'})}\n\n"
                    break
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("phase") in ("done", "error"):
                    break
        finally:
            _backfill_queues.pop(job_id, None)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{ticker}/bars")
def get_bars(ticker: str, limit: int = 1000, interval: str = "1d"):
    VALID_INTERVALS = {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"}
    if interval not in VALID_INTERVALS:
        raise HTTPException(400, f"Invalid interval '{interval}'")
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
    VALID_INTERVALS = {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"}
    if interval not in VALID_INTERVALS:
        raise HTTPException(400, f"Invalid interval '{interval}'")
    ann_factor = _BARS_PER_YEAR.get(interval, 365)
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
    n_hours   = max(len(closes), 1)
    raw_cagr  = (total_ret ** (ann_factor / n_hours) - 1) * 100
    cagr      = max(min(raw_cagr, 999.0), -99.9)
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
    _VALID_INTERVALS = set(_BARS_PER_YEAR.keys())
    if interval not in _VALID_INTERVALS:
        raise HTTPException(status_code=422, detail=f"Invalid interval '{interval}'. Valid: {sorted(_VALID_INTERVALS)}")

    cache_key = (ticker, interval)
    now = time.monotonic()
    with _QUANT_CACHE_LOCK:
        cached = _QUANT_CACHE.get(cache_key)
    if cached and now - cached[1] < _QUANT_TTL:
        return cached[0]

    from engine.quant_stats import compute_hurst, test_stationarity, compute_var_cvar, rolling_metrics
    conn = get_conn()
    try:
        source_key = f"yfinance:{interval}"
        rows = conn.execute(
            "SELECT close FROM assets WHERE ticker = ? AND source = ? ORDER BY ts ASC",
            [ticker, source_key]
        ).fetchall()
    except Exception:
        rows = []
    if not rows or len(rows) < 50:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}/{interval} (need ≥50 bars)")
    prices = np.array([r[0] for r in rows], dtype=float)
    rets = np.diff(np.log(prices[prices > 0]))
    result = {
        "ticker": ticker,
        "interval": interval,
        "n_bars": len(prices),
        "hurst": compute_hurst(prices),
        "stationarity": test_stationarity(prices),
        "var_cvar": compute_var_cvar(rets),
        "rolling": rolling_metrics(prices),
    }
    with _QUANT_CACHE_LOCK:
        _QUANT_CACHE[cache_key] = (result, now)
    return result


@router.get("/{ticker}/garch-forecast")
def get_garch_forecast(ticker: str, interval: str = Query("1h")):
    """GARCH(1,1) model fit + volatility forecast for 1/5/22 bars ahead."""
    import warnings
    from arch import arch_model
    from statsmodels.stats.diagnostic import acorr_ljungbox

    ann_factor = _BARS_PER_YEAR.get(interval, 365)
    source_key = f"yfinance:{interval}"
    conn = get_conn()
    # Query all stored sources for this ticker/interval so ccxt-fetched data is also found
    rows = conn.execute(
        "SELECT close FROM assets WHERE ticker=? AND source LIKE ? ORDER BY ts",
        [ticker, f"%:{interval}"]
    ).fetchall()
    if interval == "1d" and not rows:
        rows = conn.execute(
            "SELECT close FROM assets WHERE ticker=? AND source IN (?, ?) ORDER BY ts",
            [ticker, source_key, "yfinance"]
        ).fetchall()
    if not rows or len(rows) < 100:
        raise HTTPException(404, f"Not enough data for {ticker}/{interval} (need ≥100 bars)")

    prices = np.array([r[0] for r in rows], dtype=float)
    prices = prices[np.isfinite(prices) & (prices > 0)]
    if len(prices) < 100:
        raise HTTPException(404, f"Insufficient valid prices for {ticker}/{interval}")

    rets_pct = np.diff(np.log(prices)) * 100  # percentage log-returns
    # Remove zero-return runs that can cause GARCH degeneracy (e.g. forex weekends)
    rets_pct = rets_pct[np.isfinite(rets_pct)]

    garch_error: str | None = None
    omega = alpha = beta = persistence = 0.0
    half_life = None
    current_vol = vol_1d = vol_5d = vol_22d = 0.0

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = arch_model(rets_pct, p=1, q=1, vol="Garch", dist="normal", rescale=True)
            res = model.fit(disp="off", options={"maxiter": 500})

        params = res.params
        omega = float(params.get("omega", 0))
        alpha = float(params.get("alpha[1]", 0))
        beta  = float(params.get("beta[1]", 0))
        persistence = alpha + beta
        half_life = float(np.log(0.5) / np.log(persistence)) if 0 < persistence < 1 else None

        try:
            fc = res.forecast(horizon=22, reindex=False)
            var_fc = fc.variance.values[-1]
            vol_1d  = float(np.sqrt(max(var_fc[0], 0)))
            vol_5d  = float(np.sqrt(max(var_fc[4], 0)))
            vol_22d = float(np.sqrt(max(var_fc[21], 0)))
        except Exception:
            pass

        current_vol = float(np.sqrt(max(res.conditional_volatility.iloc[-1] ** 2, 0)))

    except Exception as e:
        garch_error = str(e)

    # Ljung-Box on returns and squared returns (lag=10)
    try:
        lb_ret = acorr_ljungbox(rets_pct, lags=[10], return_df=True)
        lb_sq  = acorr_ljungbox(rets_pct**2, lags=[10], return_df=True)
        lb_ret_stat = float(lb_ret["lb_stat"].iloc[0])
        lb_ret_pval = float(lb_ret["lb_pvalue"].iloc[0])
        lb_sq_stat  = float(lb_sq["lb_stat"].iloc[0])
        lb_sq_pval  = float(lb_sq["lb_pvalue"].iloc[0])
    except Exception:
        lb_ret_stat = lb_ret_pval = lb_sq_stat = lb_sq_pval = 0.0

    return {
        "ticker":   ticker,
        "interval": interval,
        "n_bars":   len(prices),
        "garch_error": garch_error,
        "params": {
            "omega":          round(omega, 8),
            "alpha":          round(alpha, 4),
            "beta":           round(beta, 4),
            "persistence":    round(persistence, 4),
            "half_life_bars": round(half_life, 1) if half_life else None,
        },
        "current_vol_pct": round(current_vol, 4),
        "forecast_vol_pct": {
            "h1":  round(vol_1d, 4),
            "h5":  round(vol_5d, 4),
            "h22": round(vol_22d, 4),
        },
        "ann_vol_pct": round(current_vol * float(np.sqrt(ann_factor)), 2),
        "ljung_box": {
            "returns":     {"stat": round(lb_ret_stat, 2), "pvalue": round(lb_ret_pval, 4), "significant": lb_ret_pval < 0.05},
            "sq_returns":  {"stat": round(lb_sq_stat, 2),  "pvalue": round(lb_sq_pval, 4),  "significant": lb_sq_pval < 0.05},
        },
    }
