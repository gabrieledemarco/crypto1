"""
/runs/optimize — server-side multi-timeframe optimization loop.

POST /runs/optimize
    body: {ticker, timeframes, max_iter, max_dd, stop_sharpe, period}
    returns: {job_id, stream_url}

GET  /runs/optimize/{job_id}/stream
    SSE: start | downloading | download_done | iter_start | iter_done |
         iter_error | complete | error

Usage (curl):
    JOB=$(curl -s -X POST https://<api-host>/runs/optimize \
        -H 'Content-Type: application/json' \
        -d '{"ticker":"BTC-USD","timeframes":"15m,1h,4h","max_iter":10}' \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
    curl -N https://<api-host>/runs/optimize/$JOB/stream
"""
import asyncio
import concurrent.futures
import json
import os
import sys
import uuid
from typing import Optional

import pandas as pd
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts")
sys.path.insert(0, _SCRIPTS)

from api.db import get_conn
from engine.strategy_core import compute_indicators_v2
from engine.backtest import run_versions, run_wfo

router = APIRouter()
_queues: dict[str, asyncio.Queue] = {}

# ── Timeframe constants ────────────────────────────────────────────────────────
_TF_NORM = {  # user aliases → yfinance interval string
    "1min": "1m", "5min": "5m", "15min": "15m", "30min": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d",
}
_YF_PERIOD = {  # max lookback yfinance allows per interval
    "1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d",
    "1h": "730d", "4h": "730d", "1d": "max",
}
_ACTIVE_HOURS = {  # [start_h, end_h] filter
    "1m": [0, 23], "5m": [0, 23], "15m": [6, 22],
    "30m": [6, 22], "1h": [6, 22], "4h": [0, 22], "1d": [0, 23],
}


# ── Request model ──────────────────────────────────────────────────────────────

class OptimizeRequest(BaseModel):
    ticker: str = "BTC-USD"
    timeframes: str = "15m,1h,4h"   # comma-separated; aliases like '15min' ok
    max_iter: int = 10
    max_dd: float = 20.0            # stop if |drawdown| <= this %
    stop_sharpe: float = 1.5
    period: Optional[str] = None    # override auto period (e.g. "30d")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("")
async def start_optimize(body: OptimizeRequest):
    job_id = uuid.uuid4().hex[:12]
    _queues[job_id] = asyncio.Queue()
    asyncio.create_task(_run_optimize(job_id, body))
    return {
        "job_id": job_id,
        "stream_url": f"/runs/optimize/{job_id}/stream",
    }


@router.get("/{job_id}/stream")
async def stream_optimize(job_id: str):
    queue = _queues.setdefault(job_id, asyncio.Queue())

    async def gen():
        try:
            while True:
                evt = await queue.get()
                yield f"data: {json.dumps(evt)}\n\n"
                if evt.get("type") in ("complete", "error"):
                    break
        finally:
            _queues.pop(job_id, None)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Async coordinator ──────────────────────────────────────────────────────────

async def _run_optimize(job_id: str, body: OptimizeRequest):
    queue = _queues[job_id]

    def push(evt: dict):
        queue.put_nowait(evt)

    loop = asyncio.get_running_loop()
    try:
        with concurrent.futures.ThreadPoolExecutor() as pool:
            await loop.run_in_executor(pool, _sync_optimize, body, push)
    except Exception as exc:
        push({"type": "error", "msg": str(exc)})


# ── Sync worker (runs in thread pool) ─────────────────────────────────────────

def _sync_optimize(body: OptimizeRequest, push):
    from strategies import get_archetype
    from api.routers.learning import save_run_lesson

    # Normalize TF names
    tfs = [_TF_NORM.get(t.strip(), t.strip()) for t in body.timeframes.split(",")]

    push({"type": "start", "ticker": body.ticker, "timeframes": tfs,
          "max_iter": body.max_iter, "stop_sharpe": body.stop_sharpe,
          "max_dd": body.max_dd})

    # ── 1. Download data ───────────────────────────────────────────────────────
    tf_data: dict[str, pd.DataFrame] = {}
    for tf in tfs:
        period = body.period or _YF_PERIOD.get(tf, "max")
        push({"type": "downloading", "tf": tf, "period": period})
        try:
            from engine.providers.ccxt_client import is_crypto_ticker, fetch as ccxt_fetch
            from engine.providers.yfinance_client import fetch as yf_fetch

            if is_crypto_ticker(body.ticker):
                try:
                    df = ccxt_fetch(body.ticker, period=period, interval=tf)
                except Exception:
                    df = yf_fetch(body.ticker, period=period, interval=tf)
            else:
                df = yf_fetch(body.ticker, period=period, interval=tf)

            if df is None or df.empty:
                raise ValueError("empty response")

            # Store downloaded bars in DuckDB
            conn  = get_conn()
            src   = f"yfinance:{tf}"
            count = 0
            for ts, row in df.iterrows():
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO assets "
                        "(ticker,source,ts,open,high,low,close,volume) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        [body.ticker, src, ts, float(row["Open"]),
                         float(row["High"]), float(row["Low"]),
                         float(row["Close"]), float(row["Volume"])],
                    )
                    count += 1
                except Exception:
                    pass

            push({"type": "download_done", "tf": tf, "bars": len(df),
                  "stored": count, "period": period,
                  "start": str(df.index[0].date()),
                  "end":   str(df.index[-1].date())})
            tf_data[tf] = df

        except Exception as exc:
            push({"type": "download_error", "tf": tf, "msg": str(exc)})

    if not tf_data:
        push({"type": "error", "msg": "No data available for any timeframe."})
        return

    avail = list(tf_data.keys())

    # ── 2. Optimization loop ───────────────────────────────────────────────────
    best_sharpe, best_sid, best_tf = float("-inf"), None, None
    log: list[dict] = []

    for iteration in range(1, body.max_iter + 1):
        tf = avail[(iteration - 1) % len(avail)]
        df = tf_data[tf]
        arch_name, code, sl, tp = get_archetype(iteration)

        push({"type": "iter_start", "iter": iteration, "total": body.max_iter,
              "tf": tf, "arch": arch_name, "sl": sl, "tp": tp})

        config = {
            "ticker": body.ticker, "timeframe": tf,
            "sl_mult": sl, "tp_mult": tp,
            "active_hours": _ACTIVE_HOURS.get(tf, [6, 22]),
            "risk_per_trade": 1.0, "direction": "ALL",
            "commission": 0.0004, "slippage": 0.0001,
        }

        # Persist strategy
        conn = get_conn()
        sid  = uuid.uuid4().hex[:8]
        conn.execute(
            "INSERT INTO strategies (id,name,strategy_type,config,code,status) "
            "VALUES (?,?,?,?,?,?)",
            [sid, f"opt_{iteration:03d}_{tf}", "optimize",
             json.dumps(config), code, "research"],
        )

        try:
            df_ind = compute_indicators_v2(df, fit_garch=True)

            risk = float(config["risk_per_trade"])
            if risk > 0.1:
                risk /= 100.0
            cfg = {
                "sl_mult":        float(config["sl_mult"]),
                "tp_mult":        float(config["tp_mult"]),
                "active_hours":   config["active_hours"],
                "commission":     float(config["commission"]),
                "slippage":       float(config["slippage"]),
                "risk_per_trade": risk,
            }
            if code and code.strip():
                ns: dict = {}
                exec(compile(code, "<agent_fn>", "exec"), ns)
                if "agent_fn" in ns:
                    cfg["agent_fn"] = ns["agent_fn"]

            versions = run_versions(df_ind, cfg, direction="ALL")
            try:
                wfo_df   = run_wfo(df_ind, cfg, direction="ALL")
                wfo_rows = wfo_df.to_dict("records") if not wfo_df.empty else []
            except Exception:
                wfo_rows = []

            bk = ("V_Agent"
                  if "V_Agent" in versions and "metrics" in versions.get("V_Agent", {})
                  else next((k for k in versions if "metrics" in versions[k]), ""))
            bm = versions.get(bk, {}).get("metrics", {})

            sharpe   = float(bm.get("sharpe_ratio",    0) or 0)
            dd       = float(bm.get("max_drawdown_pct", -999) or -999)
            cagr     = float(bm.get("cagr_pct",        0) or 0)
            n_trades = int(bm.get("n_trades",          0) or 0)
            win_rate = float(bm.get("win_rate_pct",    0) or 0)

            dd_ok   = abs(dd) <= body.max_dd
            verdict = ("ROBUST"   if sharpe >= body.stop_sharpe and dd_ok else
                       "marginal" if sharpe >= 0.5                        else
                       "failed")

            # Persist run + results
            run_id = uuid.uuid4().hex[:12]
            conn.execute(
                "INSERT INTO runs (id,name,ticker,timeframe,params,status,strategy_id) "
                "VALUES (?,?,?,?,?,?,?)",
                [run_id, f"opt_{run_id}", body.ticker, tf,
                 json.dumps({**config, "_strategy_id": sid}), "done", sid],
            )
            conn.execute(
                "INSERT INTO run_results (run_id,metrics,equity,trades,wfo,sweep,mc) "
                "VALUES (?,?,?,?,?,?,?)",
                [run_id,
                 json.dumps({k: v["metrics"] for k, v in versions.items() if "metrics" in v}),
                 "[]", "[]", json.dumps(wfo_rows), "[]", "{}"],
            )

            # Save learning lesson
            try:
                save_run_lesson(
                    run_id=run_id, asset=body.ticker, timeframe=tf,
                    strategy_code=code, params=config,
                    all_metrics={k: v["metrics"] for k, v in versions.items() if "metrics" in v},
                    wfo_folds=wfo_rows, df_ind=df_ind,
                )
            except Exception:
                pass

        except Exception as exc:
            push({"type": "iter_error", "iter": iteration, "msg": str(exc)})
            continue

        entry = {
            "type": "iter_done", "iter": iteration, "total": body.max_iter,
            "tf": tf, "arch": arch_name, "sid": sid, "run_id": run_id,
            "sharpe": round(sharpe, 3), "cagr": round(cagr, 1),
            "dd": round(dd, 1), "n_trades": n_trades,
            "win_rate": round(win_rate, 1), "verdict": verdict,
        }
        push(entry)
        log.append(entry)

        if sharpe > best_sharpe:
            best_sharpe, best_sid, best_tf = sharpe, sid, tf

        if verdict == "ROBUST":
            push({"type": "complete", "status": "ROBUST", "iters": iteration,
                  "best_sharpe": round(sharpe, 3), "best_dd": round(dd, 1),
                  "best_sid": sid, "best_tf": tf, "log": log})
            return

    push({"type": "complete", "status": "exhausted",
          "iters": body.max_iter,
          "best_sharpe": round(best_sharpe, 3),
          "best_sid": best_sid, "best_tf": best_tf, "log": log})
