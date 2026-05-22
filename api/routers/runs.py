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
import uuid
import sys
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.db import get_conn
from api.models import RunCreate, RunParams

router = APIRouter()

# In-memory SSE queues — fine for single-user
_sse_queues: dict[str, asyncio.Queue] = {}

# ── SSE stream ────────────────────────────────────────────────────────────────

@router.get("/{run_id}/stream")
async def stream_run(run_id: str):
    queue = _sse_queues.setdefault(run_id, asyncio.Queue())
    async def generator():
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("phase") == "done" or event.get("phase") == "error":
                break
    return StreamingResponse(generator(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache",
                                       "X-Accel-Buffering": "no"})

# ── List / get ────────────────────────────────────────────────────────────────

@router.get("")
def list_runs(strategy_id: Optional[str] = Query(None)):
    conn = get_conn()
    where = "WHERE r.strategy_id = ?" if strategy_id else ""
    args  = [strategy_id] if strategy_id else []
    rows = conn.execute(f"""
        SELECT r.id, r.name, r.ticker, r.timeframe, r.status, r.params, r.created_at,
               r.strategy_id, rr.metrics, rr.equity
        FROM runs r
        LEFT JOIN run_results rr ON r.id = rr.run_id
        {where}
        ORDER BY r.created_at DESC
    """, args).fetchall()
    result = []
    for r in rows:
        run_id, name, ticker, timeframe, status, params_str, created_at, strat_id, metrics_str, equity_str = r
        params = json.loads(params_str) if params_str else {}
        best_m: dict = {}
        if metrics_str:
            all_m = json.loads(metrics_str)
            best_key = "V_Agent" if "V_Agent" in all_m else "V4 +GARCH+Costi"
            if best_key not in all_m and all_m:
                best_key = next(iter(all_m))
            best_m = all_m.get(best_key, {})
        start_date = end_date = None
        if equity_str:
            eq = json.loads(equity_str)
            if eq:
                start_date = str(eq[0].get("ts", ""))[:10] or None
                end_date   = str(eq[-1].get("ts", ""))[:10] or None
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
            "sharpe": round(float(best_m["sharpe_ratio"]), 3) if "sharpe_ratio" in best_m else None,
            "cagr": round(float(best_m["cagr_pct"]), 2) if "cagr_pct" in best_m else None,
            "max_dd": round(float(best_m["max_drawdown_pct"]), 2) if "max_drawdown_pct" in best_m else None,
            "pf": round(float(best_m["profit_factor"]), 2) if "profit_factor" in best_m and best_m["profit_factor"] != float("inf") else None,
            "n_trades": int(best_m.get("n_trades", 0)) if best_m else None,
            "win_rate": round(float(best_m["win_rate_pct"]), 1) if "win_rate_pct" in best_m else None,
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
        placeholders = ",".join(["?" for _ in ids])
        conn.execute(f"DELETE FROM run_results WHERE run_id IN ({placeholders})", ids)
        conn.execute(f"DELETE FROM runs WHERE id IN ({placeholders})", ids)
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
    metrics = json.loads(result_row[0]) if result_row and result_row[0] else None
    return {
        "id": row[0], "name": row[1], "ticker": row[2], "status": row[3],
        "params": json.loads(row[4]) if row[4] else {},
        "created_at": str(row[5]),
        "metrics": metrics,
    }

@router.get("/{run_id}/equity")
def get_equity(run_id: str):
    conn = get_conn()
    row = conn.execute("SELECT equity FROM run_results WHERE run_id=?", [run_id]).fetchone()
    if not row or not row[0]:
        raise HTTPException(404, "Equity not ready")
    return json.loads(row[0])

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
    trades = json.loads(row[0])
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
    return json.loads(row[0])

@router.get("/{run_id}/sweep")
def get_sweep(run_id: str):
    conn = get_conn()
    row = conn.execute("SELECT sweep FROM run_results WHERE run_id=?", [run_id]).fetchone()
    if not row or not row[0]:
        return []
    return json.loads(row[0])

@router.get("/{run_id}/mc")
def get_mc(run_id: str):
    conn = get_conn()
    row = conn.execute("SELECT mc FROM run_results WHERE run_id=?", [run_id]).fetchone()
    if not row or not row[0]:
        return {}
    return json.loads(row[0])

# ── Create + async backtest ───────────────────────────────────────────────────

@router.post("")
async def create_run(body: RunCreate):
    run_id = str(uuid.uuid4())[:8]
    name   = body.name or f"run-{run_id}"
    params = body.params.model_dump()

    conn = get_conn()
    conn.execute(
        "INSERT INTO runs (id, name, ticker, timeframe, params, status, strategy_id) VALUES (?,?,?,?,?,?,?)",
        [run_id, name, params["ticker"], params["timeframe"], json.dumps(params), "pending", body.strategy_id]
    )

    asyncio.create_task(_run_backtest(run_id, params))
    return {"id": run_id, "name": name, "status": "pending"}


async def _run_backtest(run_id: str, params: dict):
    """Async backtest pipeline with SSE progress events."""
    import numpy as np
    queue = _sse_queues.setdefault(run_id, asyncio.Queue())

    def push(phase: str, pct: int, msg: str = ""):
        queue.put_nowait({"phase": phase, "pct": pct, "msg": msg})

    conn = get_conn()

    try:
        conn.execute("UPDATE runs SET status='running' WHERE id=?", [run_id])
        push("start", 0, "loading data")

        # Load bars from DuckDB — strip any accidental double suffix e.g. "BNB-USD-USD"
        ticker = params["ticker"]
        while ticker.endswith("-USD-USD") or ticker.endswith("-USDT-USDT"):
            ticker = ticker[:-4]
        await asyncio.sleep(0)  # yield to event loop
        rows = conn.execute(
            "SELECT ts, open, high, low, close, volume FROM assets WHERE ticker=? ORDER BY ts",
            [ticker]
        ).fetchall()

        if not rows:
            raise ValueError(f"No data for {ticker}. Fetch asset first.")

        import pandas as pd
        df = pd.DataFrame(rows, columns=["Date","Open","High","Low","Close","Volume"])
        df = df.set_index("Date")

        push("indicators", 10, "computing indicators")
        await asyncio.sleep(0)

        # Run in thread pool to avoid blocking event loop
        import concurrent.futures
        loop = asyncio.get_event_loop()

        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(
                pool,
                _sync_backtest_pipeline,
                df, params, push
            )

        # Persist results
        push("saving", 95, "saving results")
        metrics_json = json.dumps(result["metrics"])
        equity_json  = json.dumps(result["equity"])
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

    except Exception as exc:
        conn.execute("UPDATE runs SET status='error' WHERE id=?", [run_id])
        push("error", 0, str(exc))


def _sync_backtest_pipeline(df, params: dict, push) -> dict:
    """CPU-bound portion — runs in thread pool."""
    import numpy as np
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from engine.strategy_core import compute_indicators_v2, compute_metrics
    from engine.backtest import run_versions, run_wfo, run_optimization, INITIAL_CAPITAL
    from engine.montecarlo import run_bootstrap, run_stress

    push("indicators", 15, "computing GARCH indicators")
    df_ind = compute_indicators_v2(df, fit_garch=True)

    push("versions", 25, "running strategy versions")
    cfg = {
        "sl_mult":       params.get("sl_mult", 2.0),
        "tp_mult":       params.get("tp_mult", 5.0),
        "active_hours":  params.get("active_hours", [6, 22]),
        "commission":    params.get("commission", 0.0004),
        "slippage":      params.get("slippage", 0.0001),
        "risk_per_trade": params.get("risk_per_trade", 0.01),
    }
    direction = params.get("direction", "ALL")

    versions = run_versions(df_ind, cfg, direction=direction, progress_cb=push)

    # Pick best version for equity/trades export
    best_key = "V4 +GARCH+Costi"
    if "V_Agent" in versions and "result" in versions.get("V_Agent", {}):
        best_key = "V_Agent"
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

    # All version metrics
    metrics_out = {}
    for v_name, v_data in versions.items():
        if "metrics" in v_data:
            metrics_out[v_name] = v_data["metrics"]

    result = {
        "metrics": metrics_out,
        "equity": equity_list,
        "trades": trades_list,
    }

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

        bs     = run_bootstrap(pnl_arr, n_sims=n_sims, n_bars=n_bars, initial_capital=INITIAL_CAPITAL)
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
        }

    return result


# ── Preview endpoint ──────────────────────────────────────────────────────────

@router.post("/preview")
async def preview_run(body: RunParams):
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
        loop = asyncio.get_event_loop()
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
    comm = params.get("commission", 0.0004)
    slip = params.get("slippage", 0.0001)
    risk = params.get("risk_per_trade", 0.01)

    df_s = generate_signals_v2(df_ind, atr_mult_sl=sl, atr_mult_tp=tp,
                                active_hours=hrs, use_garch_filter=False)
    df_s = _apply_direction_filter(df_s, params.get("direction", "ALL"))
    res  = backtest_v2(df_s, INITIAL_CAPITAL, risk, commission=comm, slippage=slip)
    m    = compute_metrics(res, INITIAL_CAPITAL)
    # Sample equity curve (max 120 points) for preview chart
    eq_series = res.get("equity")
    equity_sample: list = []
    if eq_series is not None and len(eq_series) > 0:
        eq_vals = (eq_series / INITIAL_CAPITAL).tolist()
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
