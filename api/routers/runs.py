"""
/runs router
============
POST /runs          → create run, kick async backtest task
GET  /runs          → list runs
GET  /runs/{id}     → run metadata + status
GET  /runs/{id}/equity  → equity series
GET  /runs/{id}/trades  → paginated trade log
GET  /runs/{id}/wfo     → WFO fold results
GET  /runs/{id}/sweep   → optimization grid
GET  /runs/{id}/mc      → Monte Carlo paths + percentiles
GET  /runs/{id}/stream  → SSE progress (EventSource)
POST /runs/preview      → lightweight preview backtest (~100ms)
"""
import asyncio
import json
import logging
import uuid
import sys
import os
from datetime import datetime
from typing import Optional

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.db import get_conn
from api.limiter import limiter
from api.models import RunCreate, RunParams
from engine.config import ANN_FACTORS as _ANN_FACTORS, BACKTEST_TIMEOUT as _BACKTEST_TIMEOUT, BOOTSTRAP_N_RESAMPLES as _N_RESAMPLES, SSE_STREAM_TIMEOUT as _SSE_TIMEOUT, StrategyVersion

router = APIRouter()
log = logging.getLogger("runs")


def _safe_float(val, ndigits: int = 3):
    """Convert val to float, round, return None on failure or non-finite."""
    try:
        f = float(val)
        if not (f == f) or f in (float("inf"), float("-inf")):  # NaN/inf guard
            return None
        return round(f, ndigits)
    except (TypeError, ValueError):
        return None


def _infer_ann_factor(equity_data: list) -> int:
    """Infer annualisation factor from equity point timestamps.

    Falls back to hourly (8760) if timestamps are absent or unreadable.
    """
    ts_list = [e.get("ts") for e in equity_data if e.get("ts")]
    if len(ts_list) < 2:
        return 365 * 24  # default: hourly
    try:
        from datetime import datetime
        t0 = datetime.fromisoformat(str(ts_list[0]).replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(str(ts_list[1]).replace("Z", "+00:00"))
        diff_secs = abs((t1 - t0).total_seconds())
        if diff_secs <= 0:
            return 365 * 24
        bars_per_year = int(365 * 24 * 3600 / diff_secs)
        # Snap to nearest known factor
        known = sorted(_ANN_FACTORS.values())
        return min(known, key=lambda x: abs(x - bars_per_year))
    except Exception:
        return 365 * 24  # hourly fallback


# In-memory SSE queues — fine for single-user
_sse_queues: dict[str, asyncio.Queue] = {}

# ── SSE stream ────────────────────────────────────────────────────────────────

@router.get("/{run_id}/stream")
async def stream_run(run_id: str):
    # Fast-path: if the backtest already finished before the SSE client connected,
    # synthesise the final event immediately rather than hanging on an empty queue.
    conn_check = get_conn()
    row = conn_check.execute("SELECT status FROM runs WHERE id=?", [run_id]).fetchone()
    if row and row[0] in ("done", "error"):
        existing_q = _sse_queues.get(run_id)
        if existing_q is None or existing_q.empty():
            phase = "done" if row[0] == "done" else "error"
            msg   = "complete" if phase == "done" else "backtest failed — check logs or backfill data first"
            pct   = 100 if phase == "done" else 0
            _sse_queues.pop(run_id, None)
            async def _instant():
                yield f"data: {json.dumps({'phase': phase, 'pct': pct, 'msg': msg})}\n\n"
            return StreamingResponse(_instant(), media_type="text/event-stream",
                                      headers={"Cache-Control": "no-cache",
                                               "X-Accel-Buffering": "no"})

    queue = _sse_queues.setdefault(run_id, asyncio.Queue())
    async def generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_SSE_TIMEOUT)
                except asyncio.TimeoutError:
                    # Client still connected but backtest never finished — terminate gracefully
                    yield f"data: {json.dumps({'phase': 'error', 'pct': 0, 'msg': 'stream timeout'})}\n\n"
                    break
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("phase") in ("done", "error"):
                    break
        finally:
            _sse_queues.pop(run_id, None)
    return StreamingResponse(generator(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache",
                                       "X-Accel-Buffering": "no"})

# ── List / get ────────────────────────────────────────────────────────────────

@router.get("")
def list_runs(
    strategy_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    conn = get_conn()
    # Exclude equity blob from list query — it can be MBs per row
    base_select = (
        "SELECT r.id, r.name, r.ticker, r.timeframe, r.status, r.params, r.created_at,"
        " r.strategy_id, rr.metrics"
        " FROM runs r LEFT JOIN run_results rr ON r.id = rr.run_id"
    )
    if strategy_id:
        rows = conn.execute(
            f"{base_select} WHERE r.strategy_id = ? ORDER BY r.created_at DESC LIMIT ? OFFSET ?",
            [strategy_id, limit, offset]
        ).fetchall()
    else:
        rows = conn.execute(
            f"{base_select} ORDER BY r.created_at DESC LIMIT ? OFFSET ?",
            [limit, offset]
        ).fetchall()
    result = []
    for r in rows:
        run_id, name, ticker, timeframe, status, params_str, created_at, strat_id, metrics_str = r
        try:
            params = json.loads(params_str) if params_str else {}
        except (json.JSONDecodeError, TypeError):
            log.warning("Failed to parse JSON field: %r", params_str)
            params = {}
        best_m: dict = {}
        if metrics_str:
            try:
                all_m = json.loads(metrics_str)
            except (json.JSONDecodeError, TypeError):
                log.warning("Failed to parse JSON field: %r", metrics_str)
                all_m = {}
            if isinstance(all_m, dict):
                best_key = next(
                    (v.value for v in StrategyVersion.preference_order() if v.value in all_m),
                    None
                )
                if best_key is None and all_m:
                    best_key = next(iter(all_m))
                candidate = all_m.get(best_key) if best_key else None
                best_m = candidate if isinstance(candidate, dict) else {}
        # Derive date range from stored params or metrics rather than loading equity blob
        start_date = params.get("_start_date")
        end_date = params.get("_end_date")
        result.append({
            "id": run_id,
            "name": name,
            "ticker": ticker or params.get("ticker", ""),
            "timeframe": timeframe or params.get("timeframe", ""),
            "status": status,
            "strategy_id": strat_id,
            "params": params,
            "created_at": str(created_at),
            "start_date": start_date,
            "end_date": end_date,
            "sharpe": _safe_float(best_m.get("sharpe_ratio"), 3),
            "cagr": _safe_float(best_m.get("cagr_pct"), 2),
            "max_dd": _safe_float(best_m.get("max_drawdown_pct"), 2),
            "pf": _safe_float(best_m.get("profit_factor"), 2) if best_m.get("profit_factor") != float("inf") else None,
            "n_trades": int(best_m.get("n_trades", 0)) if best_m else None,
            "win_rate": _safe_float(best_m.get("win_rate_pct"), 1),
        })
    return result


@router.delete("")
def delete_unlinked_runs():
    """Delete all runs that have no strategy_id (cleanup)."""
    conn = get_conn()
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM runs WHERE strategy_id IS NULL OR strategy_id = ''"
    ).fetchall()]
    if ids:
        for run_id_del in ids:
            conn.execute("DELETE FROM run_results WHERE run_id = ?", [run_id_del])
            conn.execute("DELETE FROM runs WHERE id = ?", [run_id_del])
    return {"deleted": len(ids), "ids": ids}


@router.delete("/{run_id}")
def delete_run(run_id: str):
    conn = get_conn()
    existing = conn.execute("SELECT id FROM runs WHERE id=?", [run_id]).fetchone()
    if not existing:
        raise HTTPException(404, "Run not found")
    conn.execute("DELETE FROM run_results WHERE run_id=?", [run_id])
    conn.execute("DELETE FROM runs WHERE id=?", [run_id])
    return {"deleted": run_id}

@router.get("/{run_id}")
def get_run(run_id: str):
    conn = get_conn()
    row = conn.execute("SELECT id, name, ticker, status, params, created_at FROM runs WHERE id=?", [run_id]).fetchone()
    if not row:
        raise HTTPException(404, "Run not found")
    result_row = conn.execute("SELECT metrics FROM run_results WHERE run_id=?", [run_id]).fetchone()
    metrics = None
    if result_row and result_row[0]:
        try:
            metrics = json.loads(result_row[0])
        except (json.JSONDecodeError, TypeError):
            log.warning("Failed to parse JSON field: %r", result_row[0])
    try:
        params = json.loads(row[4]) if row[4] else {}
    except (json.JSONDecodeError, TypeError):
        log.warning("Failed to parse JSON field: %r", row[4])
        params = {}
    return {
        "id": row[0], "name": row[1], "ticker": row[2], "status": row[3],
        "params": params,
        "created_at": str(row[5]),
        "metrics": metrics,
    }

@router.get("/{run_id}/equity")
def get_equity(run_id: str):
    conn = get_conn()
    row = conn.execute("SELECT equity FROM run_results WHERE run_id=?", [run_id]).fetchone()
    if not row or not row[0]:
        raise HTTPException(404, "Equity not ready")
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        log.warning("Failed to parse JSON field: %r", row[0])
        return []

@router.get("/{run_id}/trades")
def get_trades(run_id: str,
               side: Optional[str] = None,
               pnl: Optional[str] = None,
               offset: int = Query(0, ge=0),
               limit: int = Query(100, le=1000)):
    conn = get_conn()
    row = conn.execute("SELECT trades FROM run_results WHERE run_id=?", [run_id]).fetchone()
    if not row or not row[0]:
        raise HTTPException(404, "Trades not ready")
    try:
        trades = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        log.warning("Failed to parse JSON field: %r", row[0])
        trades = []
    if side and side.upper() in ("LONG", "SHORT"):
        trades = [t for t in trades if t.get("direction") == side.upper()]
    if pnl == "win":
        trades = [t for t in trades if t.get("pnl", 0) > 0]
    elif pnl == "loss":
        trades = [t for t in trades if t.get("pnl", 0) <= 0]
    total = len(trades)
    return {"total": total, "trades": trades[offset: offset + limit]}

@router.get("/{run_id}/wfo")
def get_wfo(run_id: str):
    conn = get_conn()
    row = conn.execute("SELECT wfo FROM run_results WHERE run_id=?", [run_id]).fetchone()
    if not row or not row[0]:
        return []
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        log.warning("Failed to parse JSON field: %r", row[0])
        return []

@router.get("/{run_id}/sweep")
def get_sweep(run_id: str):
    conn = get_conn()
    row = conn.execute("SELECT sweep FROM run_results WHERE run_id=?", [run_id]).fetchone()
    if not row or not row[0]:
        return []
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        log.warning("Failed to parse JSON field: %r", row[0])
        return []

@router.get("/{run_id}/mc")
def get_mc(run_id: str):
    conn = get_conn()
    row = conn.execute("SELECT mc FROM run_results WHERE run_id=?", [run_id]).fetchone()
    if not row or not row[0]:
        return {}
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        log.warning("Failed to parse JSON field: %r", row[0])
        return {}

@router.get("/{run_id}/bootstrap-ci")
def get_bootstrap_ci(run_id: str):
    """Bootstrap 95% confidence intervals for Sharpe ratio and CAGR."""
    import warnings
    from scipy.stats import bootstrap as sp_bootstrap

    conn = get_conn()
    # Return cached result if already computed
    cached_row = conn.execute(
        "SELECT mc FROM run_results WHERE run_id=?", [run_id]
    ).fetchone()
    if cached_row and cached_row[0]:
        mc_data = json.loads(cached_row[0]) if isinstance(cached_row[0], str) else cached_row[0]
        if mc_data and "bootstrap_ci" in mc_data:
            return mc_data["bootstrap_ci"]

    row = conn.execute("SELECT equity FROM run_results WHERE run_id=?", [run_id]).fetchone()
    if not row or not row[0]:
        raise HTTPException(404, "No results for this run")

    equity_data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    # equity_data is list of {i, v, dd, ts?}
    vals = [float(e["v"]) for e in equity_data if "v" in e]
    if len(vals) < 30:
        raise HTTPException(400, "Not enough equity data for bootstrap (need ≥30 points)")

    rets = np.array([(vals[i] - vals[i-1]) / vals[i-1] for i in range(1, len(vals))])
    rets = rets[np.isfinite(rets)]
    n = len(rets)
    if n < 20:
        raise HTTPException(400, "Not enough returns for bootstrap")

    # Infer bar interval from equity timestamps to get correct annualisation
    ann_factor = _infer_ann_factor(equity_data)

    def sharpe_fn(x):
        m, s = float(np.mean(x)), float(np.std(x))
        return (m / s * np.sqrt(ann_factor)) if s > 0 else 0.0

    def cagr_fn(x):
        total = float(np.prod(1.0 + x)) - 1.0
        return float((1.0 + total) ** (ann_factor / len(x)) - 1.0) * 100

    sharpe_point = sharpe_fn(rets)
    cagr_point   = cagr_fn(rets)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            bs_sharpe = sp_bootstrap(
                (rets,), sharpe_fn, n_resamples=_N_RESAMPLES, confidence_level=0.95,
                method="percentile", random_state=42
            )
            bs_cagr = sp_bootstrap(
                (rets,), cagr_fn, n_resamples=_N_RESAMPLES, confidence_level=0.95,
                method="percentile", random_state=42
            )
        sharpe_ci = (float(bs_sharpe.confidence_interval.low), float(bs_sharpe.confidence_interval.high))
        cagr_ci   = (float(bs_cagr.confidence_interval.low),   float(bs_cagr.confidence_interval.high))
    except Exception as e:
        import logging
        log.warning(f"Bootstrap CI failed: {e}")
        sharpe_ci = (None, None)
        cagr_ci = (None, None)
        ci_method = "unavailable"

    result = {
        "run_id":    run_id,
        "n_returns": n,
        "sharpe": {
            "point":   round(sharpe_point, 3),
            "ci_low":  round(sharpe_ci[0], 3) if sharpe_ci[0] is not None else None,
            "ci_high": round(sharpe_ci[1], 3) if sharpe_ci[1] is not None else None,
        },
        "cagr_pct": {
            "point":   round(cagr_point, 2),
            "ci_low":  round(cagr_ci[0], 2) if cagr_ci[0] is not None else None,
            "ci_high": round(cagr_ci[1], 2) if cagr_ci[1] is not None else None,
        },
    }
    # Persist CI result into mc JSON so subsequent calls are instant
    try:
        mc_row = conn.execute(
            "SELECT mc FROM run_results WHERE run_id=?", [run_id]
        ).fetchone()
        if mc_row:
            mc_data = (json.loads(mc_row[0]) if isinstance(mc_row[0], str) else mc_row[0]) or {}
            mc_data["bootstrap_ci"] = result
            conn.execute(
                "UPDATE run_results SET mc=? WHERE run_id=?",
                [json.dumps(mc_data), run_id]
            )
    except Exception as _cache_exc:
        log.debug("Failed to cache bootstrap CI: %s", _cache_exc)
    return result

# ── Create + async backtest ───────────────────────────────────────────────────

@router.post("")
@limiter.limit("20/minute")
async def create_run(request: Request, body: RunCreate):
    run_id = str(uuid.uuid4()).replace('-', '')[:12]
    name   = body.name or f"run-{run_id}"
    params = body.params.model_dump()

    conn = get_conn()
    conn.execute(
        "INSERT INTO runs (id, name, ticker, timeframe, params, status, strategy_id) VALUES (?,?,?,?,?,?,?)",
        [run_id, name, params["ticker"], params["timeframe"], json.dumps(params), "pending", body.strategy_id]
    )
    conn.commit()  # Flush INSERT before fire-and-forget task reads the row

    params["_strategy_id"] = body.strategy_id
    asyncio.create_task(_run_backtest(run_id, params))
    return {"id": run_id, "name": name, "status": "pending"}


def _load_or_fetch(conn, ticker: str, interval: str, push=None) -> list:
    """
    Return OHLCV rows for ticker+interval from the Parquet store.

    Downloads are only possible via backfill (Assets → BACKFILL).
    If no Parquet data exists for this ticker/interval, raises ValueError
    with a message that tells the user to backfill first.
    """
    import pandas as pd
    from engine.backfill import classify_ticker
    from engine.storage.parquet_store import list_available
    from engine.storage.fast_loader import load_fast

    try:
        asset_class = classify_ticker(ticker)
        available = list_available(asset_class, ticker)
        if available:
            if push:
                push("start", 2, f"loading {ticker} from Parquet store…")
            start_y, start_mo = available[0]
            end_y, end_mo = available[-1]
            nm = end_mo + 1
            ny = end_y + (1 if nm > 12 else 0)
            nm = nm if nm <= 12 else 1
            end_ts = pd.Timestamp(ny, nm, 1) - pd.Timedelta(days=1)
            df = load_fast(
                asset_class, ticker,
                interval,
                pd.Timestamp(start_y, start_mo, 1),
                end_ts,
            )
            if not df.empty:
                rows = list(zip(
                    df.index,
                    df["Open"], df["High"], df["Low"], df["Close"], df["Volume"],
                ))
                log.info("Parquet load ok ticker=%s interval=%s rows=%d", ticker, interval, len(rows))
                return rows
    except Exception as exc:
        log.warning("Parquet store lookup failed for %s/%s: %s", ticker, interval, exc)

    raise ValueError(
        f"Nessun dato disponibile per {ticker} ({interval}). "
        f"Vai su Assets → BACKFILL per scaricare la serie storica prima di eseguire un backtest."
    )


async def _run_backtest(run_id: str, params: dict):
    """Async backtest pipeline with SSE progress events."""
    import numpy as np
    queue = _sse_queues.setdefault(run_id, asyncio.Queue())
    loop = asyncio.get_running_loop()

    def push(phase: str, pct: int, msg: str = ""):
        loop.call_soon_threadsafe(queue.put_nowait, {"phase": phase, "pct": pct, "msg": msg})

    conn = get_conn()

    try:
        conn.execute("UPDATE runs SET status='running' WHERE id=?", [run_id])
        push("start", 0, "loading data")

        ticker_raw = params.get("ticker", "?")
        tf = params.get("timeframe", "?")
        log.info("backtest start run_id=%s ticker=%s tf=%s", run_id, ticker_raw, tf)

        # Load bars from DuckDB — strip any accidental double suffix e.g. "BNB-USD-USD"
        ticker = params["ticker"]
        while ticker.endswith("-USD-USD") or ticker.endswith("-USDT-USDT"):
            ticker = ticker[:-4]
        interval = params.get("timeframe", "1d")
        await asyncio.sleep(0)  # yield to event loop
        rows = _load_or_fetch(conn, ticker, interval, push)

        import pandas as pd
        df = pd.DataFrame(rows, columns=["Date","Open","High","Low","Close","Volume"])
        df = df.set_index("Date")

        push("indicators", 10, "computing indicators")
        await asyncio.sleep(0)

        # Run in thread pool to avoid blocking event loop
        import concurrent.futures
        loop = asyncio.get_running_loop()

        with concurrent.futures.ThreadPoolExecutor() as pool:
            fut = loop.run_in_executor(pool, _sync_backtest_pipeline, df, params, push)
            try:
                result = await asyncio.wait_for(fut, timeout=_BACKTEST_TIMEOUT)
            except asyncio.TimeoutError:
                push("error", 0, "Backtest timed out after 300s")
                raise HTTPException(status_code=504, detail="Backtest timed out")

        # Persist results
        push("saving", 95, "saving results")
        # Store date range in params so list_runs never needs the equity blob
        equity_raw = result["equity"]
        if equity_raw:
            params["_start_date"] = str(equity_raw[0].get("ts", ""))[:10] or None
            params["_end_date"]   = str(equity_raw[-1].get("ts", ""))[:10] or None
            conn.execute(
                "UPDATE runs SET params=? WHERE id=?",
                [json.dumps(params), run_id]
            )
        metrics_json = json.dumps(result["metrics"])
        equity_json  = json.dumps(equity_raw)
        trades_json  = json.dumps(result["trades"])
        wfo_json     = json.dumps(result.get("wfo", []))
        sweep_json   = json.dumps(result.get("sweep", []))
        mc_json      = json.dumps(result.get("mc", {}))

        existing = conn.execute("SELECT run_id FROM run_results WHERE run_id=?", [run_id]).fetchone()
        if existing:
            conn.execute(
                "UPDATE run_results SET metrics=?, equity=?, trades=?, wfo=?, sweep=?, mc=? WHERE run_id=?",
                [metrics_json, equity_json, trades_json, wfo_json, sweep_json, mc_json, run_id]
            )
        else:
            conn.execute(
                "INSERT INTO run_results (run_id,metrics,equity,trades,wfo,sweep,mc) VALUES (?,?,?,?,?,?,?)",
                [run_id, metrics_json, equity_json, trades_json, wfo_json, sweep_json, mc_json]
            )
        conn.execute("UPDATE runs SET status='done' WHERE id=?", [run_id])
        push("done", 100, "complete")
        log.info(
            "backtest done run_id=%s ticker=%s tf=%s n_trades=%s sharpe=%s",
            run_id, ticker_raw, tf,
            result.get("metrics", {}).get("n_trades"),
            result.get("metrics", {}).get("sharpe_ratio"),
        )

        # Post-run learning: extract lesson and store in brain_chunks
        try:
            from api.routers.learning import save_run_lesson
            _strategy_code = None
            _strategy_id = params.get("_strategy_id")
            if _strategy_id:
                _srow = conn.execute(
                    "SELECT code FROM strategies WHERE id=?", [_strategy_id]
                ).fetchone()
                _strategy_code = _srow[0] if _srow else None
            save_run_lesson(
                run_id=run_id,
                asset=params.get("ticker", ""),
                timeframe=params.get("timeframe", "1h"),
                strategy_code=_strategy_code,
                params=params,
                all_metrics=result.get("metrics", {}),
                wfo_folds=result.get("wfo", []),
                df_ind=result.get("_df_ind"),
            )
        except Exception as _learn_exc:
            log.warning("Learning update failed (non-blocking): %s", _learn_exc)

    except Exception as exc:
        conn.execute("UPDATE runs SET status='error' WHERE id=?", [run_id])
        log.exception("Backtest pipeline error for run_id=%s", run_id)
        err_msg = str(exc).strip()[:200] if str(exc).strip() else "An internal error occurred. Please try again."
        push("error", 0, err_msg)
    finally:
        # Ensure queue is removed even when no SSE client ever connected
        _sse_queues.pop(run_id, None)


def _validate_bars(df) -> None:
    """Raise ValueError if the OHLCV DataFrame has data quality issues."""
    if df is None or (hasattr(df, "empty") and df.empty):
        raise ValueError("No price data available")
    if df["Close"].isna().any():
        raise ValueError(f"NaN values in Close ({int(df['Close'].isna().sum())} rows)")
    if (df["Close"] <= 0).any():
        raise ValueError("Non-positive Close prices detected")
    if (df["High"] < df["Low"]).any():
        raise ValueError("Price reversal: High < Low in one or more rows")
    dups = int(df.index.duplicated().sum())
    if dups > 0:
        raise ValueError(f"Duplicate timestamps: {dups} rows")


def _load_strategy_agent_fn(strategy_id: str, push) -> object | None:
    """Load and sandboxed-exec strategy code; return agent_fn or None."""
    try:
        from api.db import get_conn as _get_conn
        from engine.safe_exec import safe_exec_strategy, CodeSecurityError
        _row = _get_conn().execute(
            "SELECT code FROM strategies WHERE id=?", [strategy_id]
        ).fetchone()
        if _row and _row[0] and _row[0].strip():
            ns = safe_exec_strategy(_row[0], strategy_id=str(strategy_id))
            return ns.get("agent_fn")
    except Exception as _exc:
        push("versions", 25, f"Strategy code load failed: {type(_exc).__name__}: {_exc}")
    return None


def _sync_backtest_pipeline(df, params: dict, push) -> dict:
    """CPU-bound portion — runs in thread pool."""
    import numpy as np
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from engine.strategy_core import compute_indicators_v2, compute_metrics
    from engine.backtest import run_versions, run_wfo, run_optimization, INITIAL_CAPITAL
    from engine.montecarlo import run_bootstrap, run_stress

    # Validate data quality before any computation
    _validate_bars(df)

    push("indicators", 15, "computing GARCH indicators")
    df_ind = compute_indicators_v2(df, fit_garch=True)
    garch_status = df_ind.attrs.get("garch_status", "unknown")
    if garch_status != "ok":
        push("indicators", 16, f"GARCH fallback: {garch_status}")

    push("versions", 25, "running strategy versions")
    cfg = {
        "sl_mult":              params.get("sl_mult", 2.0),
        "tp_mult":              params.get("tp_mult", 5.0),
        "active_hours":         params.get("active_hours", [6, 22]),
        "commission":           params.get("commission", 0.0004),
        "slippage":             params.get("slippage", 0.0001),
        "risk_per_trade":       params.get("risk_per_trade", 0.01),
        "max_positions":        int(params.get("max_positions", 1)),
        "cooldown_bars":        int(params.get("cooldown_bars", 0)),
        "initial_capital":      float(params.get("initial_capital", 10_000)),
        "leverage":             float(params.get("leverage", 1.0)),
        "trailing_stop":        bool(params.get("trailing_stop", False)),
        "trailing_stop_method": params.get("trailing_stop_method", "atr"),
        "trailing_stop_value":  float(params.get("trailing_stop_value", 1.5)),
        "position_size_method": params.get("position_size_method", "risk_pct"),
    }
    strategy_id = params.get("_strategy_id")
    if strategy_id:
        agent_fn = _load_strategy_agent_fn(strategy_id, push)
        if agent_fn:
            cfg["agent_fn"] = agent_fn
    direction = params.get("direction", "ALL")

    versions = run_versions(df_ind, cfg, direction=direction, progress_cb=push)

    # ── NautilusTrader engine (optional, gated by USE_NAUTILUS_ENGINE=1) ──────
    # Completely isolated: any failure here must never affect the main pipeline.
    try:
        import os as _os
        if _os.getenv("USE_NAUTILUS_ENGINE", "").lower() in ("1", "true", "yes"):
            from engine.nautilus_engine import is_enabled as _nt_enabled, run_nautilus_backtest
            if _nt_enabled():
                push("versions", 68, "running NautilusTrader engine")
                _nt_cfg = {
                    **cfg,
                    "ticker":    params.get("ticker", "BTC-USD"),
                    "timeframe": params.get("timeframe", "1h"),
                    "use_garch_filter": True,
                }
                _nt_result  = run_nautilus_backtest(df_ind, _nt_cfg)
                _nt_metrics = compute_metrics(_nt_result, float(cfg.get("initial_capital", 10_000)))
                versions["V_Nautilus"] = {"result": _nt_result, "metrics": _nt_metrics}
                log.info("NautilusTrader engine ok — sharpe=%.3f n_trades=%s",
                         _nt_metrics.get("sharpe_ratio", 0), _nt_metrics.get("n_trades", 0))
    except BaseException as _nt_exc:
        log.warning("NautilusTrader engine skipped: %s", _nt_exc)

    # Pick best version for equity/trades export
    _nautilus_ok = (
        "V_Nautilus" in versions
        and "result" in versions.get("V_Nautilus", {})
    )
    if _nautilus_ok:
        best_key = "V_Nautilus"
    else:
        best_key = next(
            (v.value for v in StrategyVersion.preference_order()
             if v.value in versions and "result" in versions.get(v.value, {})),
            None
        )
    if best_key is None:
        best_key = next(iter(versions))
    best = versions.get(best_key, list(versions.values())[0])
    best_result = best.get("result", {})
    best_metrics = best.get("metrics", {})

    # Equity series → list of {i, v, dd}
    equity_s = best_result.get("equity")
    equity_list = []
    if equity_s is not None and len(equity_s) > 0:
        peak = equity_s.iloc[0]
        for i, (ts, v) in enumerate(equity_s.items()):
            peak = max(peak, v)
            dd = (v - peak) / peak if peak > 0 else 0
            equity_list.append({"i": i, "ts": str(ts), "v": round(float(v), 4),
                                  "dd": round(float(dd), 4)})

    # Trades → list of dicts (JSON-serializable)
    trades_df = best_result.get("trades")
    trades_list = []
    if trades_df is not None and not trades_df.empty:
        trades_list = trades_df.assign(
            entry_time=trades_df["entry_time"].astype(str),
            exit_time=trades_df["exit_time"].astype(str),
        ).to_dict("records")

    # All version metrics (includes V_Nautilus when present)
    metrics_out = {}
    for v_name, v_data in versions.items():
        if "metrics" in v_data:
            metrics_out[v_name] = v_data["metrics"]

    result = {
        "metrics": metrics_out,
        "equity": equity_list,
        "trades": trades_list,
    }
    result["_df_ind"] = df_ind   # passed to learning hook (not serialized)

    # WFO
    if params.get("run_wfo", True):
        push("wfo", 70, "walk-forward optimization")
        wfo_df = run_wfo(df_ind, cfg, direction=direction, progress_cb=push)
        result["wfo"] = wfo_df.to_dict("records") if not wfo_df.empty else []

    # Sweep
    if params.get("run_sweep", True):
        push("sweep", 80, "parameter sweep")
        sweep_df = run_optimization(df_ind, cfg, progress_cb=push)
        result["sweep"] = sweep_df.to_dict("records") if not sweep_df.empty else []

    # MC
    if params.get("run_mc", True) and trades_list:
        push("mc", 90, "monte carlo")
        pnl_arr = np.array([t.get("pnl", 0) for t in trades_list])
        dir_arr = np.array([
            1 if str(t.get("direction", "")).upper() == "LONG" else -1
            for t in trades_list
        ])
        n_sims  = max(100, int(params.get("mc_sims", 1000)))
        mc_bars_raw = params.get("mc_bars")
        n_bars  = int(mc_bars_raw) if (mc_bars_raw and int(mc_bars_raw) > 0) else None

        # Compute actual backtest duration in days for CAGR annualization
        mc_days = 365.0
        if equity_s is not None and len(equity_s) >= 2:
            try:
                mc_days = max((equity_s.index[-1] - equity_s.index[0]).days, 1)
            except Exception as _ts_exc:
                log.debug("Could not compute backtest date range: %s", _ts_exc)
                mc_days = 365.0
        bs     = run_bootstrap(pnl_arr, n_sims=n_sims, n_bars=n_bars, initial_capital=INITIAL_CAPITAL, days_in_period=mc_days)
        stress = run_stress(pnl_arr, initial_capital=INITIAL_CAPITAL)

        # Trade stats from original trades
        n_long  = int((dir_arr == 1).sum())
        n_short = int((dir_arr == -1).sum())
        n_total = len(pnl_arr)
        win_rate_base  = round(float((pnl_arr > 0).mean() * 100), 1) if n_total > 0 else 0.0
        win_rate_long  = round(float((pnl_arr[dir_arr == 1] > 0).mean() * 100), 1) if n_long > 0 else 0.0
        win_rate_short = round(float((pnl_arr[dir_arr == -1] > 0).mean() * 100), 1) if n_short > 0 else 0.0

        wr_arr = bs["win_rates"]

        # Percentiles per timestep
        eq_mat = bs["equity_matrix"]
        steps = eq_mat.shape[1]
        percentiles = {
            "p5":  [round(float(np.percentile(eq_mat[:, t], 5)), 4) for t in range(steps)],
            "p25": [round(float(np.percentile(eq_mat[:, t], 25)), 4) for t in range(steps)],
            "p50": [round(float(np.percentile(eq_mat[:, t], 50)), 4) for t in range(steps)],
            "p75": [round(float(np.percentile(eq_mat[:, t], 75)), 4) for t in range(steps)],
            "p95": [round(float(np.percentile(eq_mat[:, t], 95)), 4) for t in range(steps)],
        }
        result["mc"] = {
            "percentiles": percentiles,
            "finals":    [round(float(x), 4) for x in bs["final_capital"].tolist()[:200]],
            "dd_finals": [round(float(x), 4) for x in bs["max_dd_pct"].tolist()[:200]],
            "stress":    stress,
            "p_profit":  round(float((bs["final_capital"] > INITIAL_CAPITAL).mean()), 4),
            "p_ruin":    round(float((bs["final_capital"] < INITIAL_CAPITAL * 0.5).mean()), 4),
            # Trade metrics
            "n_trades":       n_total,
            "n_long":         n_long,
            "n_short":        n_short,
            "win_rate_base":  win_rate_base,
            "win_rate_long":  win_rate_long,
            "win_rate_short": win_rate_short,
            "win_rate_p5":    round(float(np.percentile(wr_arr, 5)), 1),
            "win_rate_p50":   round(float(np.percentile(wr_arr, 50)), 1),
            "win_rate_p95":   round(float(np.percentile(wr_arr, 95)), 1),
            "n_sims":         n_sims,
            "path_len":       n_bars or n_total,
            "p_daily_dd_1":  round(float(bs["p_daily_dd_1"]), 2),
            "p_daily_dd_5":  round(float(bs["p_daily_dd_5"]), 2),
            "p_daily_dd_10": round(float(bs["p_daily_dd_10"]), 2),
        }

    return result


# ── Preview endpoint ──────────────────────────────────────────────────────────

@router.post("/preview")
@limiter.limit("30/minute")
async def preview_run(request: Request, body: RunParams):
    """Lightweight preview: last 500 bars, V4 only, no WFO/MC."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    import numpy as np
    import pandas as pd
    from engine.strategy_core import compute_indicators_v2, generate_signals_v2, backtest_v2, compute_metrics
    from engine.backtest import _apply_direction_filter

    conn = get_conn()
    rows = conn.execute(
        "SELECT ts, open, high, low, close, volume FROM assets WHERE ticker=? ORDER BY ts DESC LIMIT 500",
        [body.ticker]
    ).fetchall()
    if not rows:
        raise HTTPException(404, f"No data for {body.ticker}")

    df = pd.DataFrame(reversed(rows), columns=["Date","Open","High","Low","Close","Volume"])
    df = df.set_index("Date")

    try:
        import concurrent.futures
        loop = asyncio.get_running_loop()
        params = body.model_dump()
        result = await loop.run_in_executor(None, _sync_preview, df, params)
        return result
    except Exception as exc:
        raise HTTPException(500, str(exc))


def _sync_preview(df, params: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from engine.strategy_core import compute_indicators_v2, generate_signals_v2, backtest_v2, compute_metrics
    from engine.backtest import _apply_direction_filter, INITIAL_CAPITAL

    df_ind = compute_indicators_v2(df, fit_garch=False)
    sl  = params.get("sl_mult", 2.0)
    tp  = params.get("tp_mult", 5.0)
    hrs = tuple(params.get("active_hours", [6, 22]))
    comm     = params.get("commission", 0.0004)
    slip     = params.get("slippage", 0.0001)
    risk     = params.get("risk_per_trade", 0.01)
    max_pos  = int(params.get("max_positions", 1))
    cooldown = int(params.get("cooldown_bars", 0))
    cap      = float(params.get("initial_capital", INITIAL_CAPITAL))
    lvg      = float(params.get("leverage", 1.0))
    ts_on    = bool(params.get("trailing_stop", False))
    ts_meth  = params.get("trailing_stop_method", "atr")
    ts_val   = float(params.get("trailing_stop_value", 1.5))
    ps_meth  = params.get("position_size_method", "risk_pct")

    df_s = generate_signals_v2(df_ind, atr_mult_sl=sl, atr_mult_tp=tp,
                                active_hours=hrs, use_garch_filter=False)
    df_s = _apply_direction_filter(df_s, params.get("direction", "ALL"))
    res  = backtest_v2(df_s, cap, risk, commission_pips=comm, slippage_pips=slip,
                       max_positions=max_pos, cooldown_bars=cooldown, leverage=lvg,
                       trailing_stop=ts_on, trailing_stop_method=ts_meth,
                       trailing_stop_value=ts_val, position_size_method=ps_meth)
    m    = compute_metrics(res, cap)
    # Sample equity curve (max 120 points) for preview chart
    eq_series = res.get("equity")
    equity_sample: list = []
    if eq_series is not None and len(eq_series) > 0:
        eq_vals = (eq_series / cap).tolist()
        step = max(1, len(eq_vals) // 120)
        equity_sample = [round(float(v), 4) for v in eq_vals[::step][:120]]
    return {
        "sharpe":   round(m.get("sharpe_ratio", 0), 3),
        "cagr":     round(m.get("cagr_pct", 0), 1),
        "max_dd":   round(m.get("max_drawdown_pct", 0), 1),
        "trades":   m.get("n_trades", 0),
        "win_rate": round(m.get("win_rate_pct", 0), 1),
        "exposure": 0,
        "equity":   equity_sample,
    }
