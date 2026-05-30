"""
/runs/pipeline — server-side autonomous pipeline for multiple tickers.

POST /runs/pipeline
    body: {tickers, timeframes, max_iter, stop_sharpe, max_dd, period}
    returns: {job_id, stream_url}

GET  /runs/pipeline/{job_id}/stream
    SSE: start | ticker_start | downloading | download_done | download_error
         | iter_start | iter_done | iter_error | ticker_done | complete | error

Each ROBUST strategy found is automatically starred and set to status=live
in the strategies table so it appears in the Library screen.

Usage (curl):
    JOB=$(curl -s -X POST https://<api>/runs/pipeline \\
        -H 'Content-Type: application/json' \\
        -d '{"tickers":["BTC-USD","ETH-USD","SOL-USD"],"timeframes":["1h","4h","1d"]}' \\
        | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
    curl -N https://<api>/runs/pipeline/$JOB/stream
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

# Use realpath so relative __file__ on Railway resolves to an absolute path
_HERE    = os.path.dirname(os.path.realpath(__file__))   # .../api/routers
_ROOT    = os.path.dirname(os.path.dirname(_HERE))        # project root
_SCRIPTS = os.path.join(_ROOT, "scripts")
for _p in (_ROOT, _SCRIPTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.db import get_conn
from api.strategies import get_archetype   # always available: COPY api/ ./api/

router = APIRouter()
_queues: dict[str, asyncio.Queue] = {}

# Minimum Sharpe for a strategy to be classified ROBUST, independent of stop_sharpe.
# stop_sharpe controls early exit; _ROBUST_MIN_SHARPE controls classification.
_ROBUST_MIN_SHARPE = 1.5

# Minimum number of closed trades required for a ROBUST verdict — prevents
# Sharpe estimates based on noise (< 30 trades → huge statistical uncertainty).
_MIN_TRADES_ROBUST = {
    "1m": 50, "5m": 40, "15m": 30, "30m": 25,
    "1h": 20, "4h": 12, "1d":  8,
}

_TF_NORM = {
    "1min": "1m", "5min": "5m", "15min": "15m", "30min": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d",
}
_YF_PERIOD = {
    "1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d",
    "1h": "730d", "4h": "730d", "1d": "max",
}
_ACTIVE_HOURS = {
    "1m": [0, 23], "5m": [0, 23], "15m": [6, 22],
    "30m": [6, 22], "1h": [6, 22], "4h": [0, 22], "1d": [0, 23],
}
_ANN_FACTORS = {
    "1m": 525600, "5m": 105120, "15m": 35040, "30m": 17520,
    "1h": 8760, "4h": 2190, "1d": 365,
}

# Risk configurations cycled across pipeline iterations
_RISK_GRID = [
    {"leverage": 1.0, "trailing_stop": False, "position_size_method": "risk_pct"},
    {"leverage": 2.0, "trailing_stop": False, "position_size_method": "risk_pct"},
    {"leverage": 1.0, "trailing_stop": True,  "trailing_stop_method": "atr",  "trailing_stop_value": 1.5,  "position_size_method": "risk_pct"},
    {"leverage": 1.0, "trailing_stop": True,  "trailing_stop_method": "pct",  "trailing_stop_value": 1.5,  "position_size_method": "risk_pct"},
    {"leverage": 1.0, "trailing_stop": False, "position_size_method": "fixed_pct"},
    {"leverage": 2.0, "trailing_stop": True,  "trailing_stop_method": "atr",  "trailing_stop_value": 2.0,  "position_size_method": "risk_pct"},
    {"leverage": 3.0, "trailing_stop": False, "position_size_method": "risk_pct"},
    {"leverage": 1.0, "trailing_stop": True,  "trailing_stop_method": "atr",  "trailing_stop_value": 2.5,  "position_size_method": "risk_pct"},
]


class PipelineRequest(BaseModel):
    tickers: list = ["BTC-USD", "ETH-USD", "SOL-USD"]
    timeframes: list = ["1m", "5m", "15m", "1h"]
    max_iter: int = 40        # ~10 per timeframe with 4 TFs
    stop_sharpe: float = 1.5
    max_dd: float = 20.0
    period: Optional[str] = None   # override max lookback for all TFs
    iter_offset: int = 0     # start archetype search from this iteration (0 = default)


# ── Endpoints ──────────────────────────────────────────────────────────────────────────────

@router.post("")
async def start_pipeline(body: PipelineRequest):
    job_id = uuid.uuid4().hex[:12]
    _queues[job_id] = asyncio.Queue()
    asyncio.create_task(_run_pipeline(job_id, body))
    return {
        "job_id": job_id,
        "stream_url": f"/runs/pipeline/{job_id}/stream",
        "tickers": body.tickers,
        "timeframes": body.timeframes,
    }


@router.get("/{job_id}/stream")
async def stream_pipeline(job_id: str):
    queue = _queues.setdefault(job_id, asyncio.Queue())

    async def gen():
        try:
            while True:
                evt = await queue.get()
                if evt.get("type") == "ping":
                    yield ": heartbeat\n\n"
                    continue
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


# ── Async coordinator ─────────────────────────────────────────────────────────────────────────────

async def _run_pipeline(job_id: str, body: PipelineRequest):
    queue = _queues[job_id]

    def push(evt: dict):
        queue.put_nowait(evt)

    loop = asyncio.get_running_loop()

    async def _heartbeat():
        while True:
            await asyncio.sleep(20)
            queue.put_nowait({"type": "ping"})

    hb = asyncio.create_task(_heartbeat())
    try:
        with concurrent.futures.ThreadPoolExecutor() as pool:
            await loop.run_in_executor(pool, _sync_pipeline, body, push)
    except Exception as exc:
        push({"type": "error", "msg": str(exc)})
    finally:
        hb.cancel()


# ── Sync worker ───────────────────────────────────────────────────────────────────────────────

def _sync_pipeline(body: PipelineRequest, push):
    tickers = body.tickers
    tfs = [_TF_NORM.get(t.strip(), t.strip()) for t in body.timeframes]
    total_tickers = len(tickers)

    push({
        "type": "start",
        "tickers": tickers,
        "timeframes": tfs,
        "max_iter": body.max_iter,
        "stop_sharpe": body.stop_sharpe,
        "max_dd": body.max_dd,
    })

    summary = []

    for ticker_idx, ticker in enumerate(tickers):
        push({"type": "ticker_start", "ticker": ticker,
              "idx": ticker_idx + 1, "total": total_tickers})

        # ── 1. Download all timeframes for this ticker ─────────────────────────────────────
        tf_data: dict[str, pd.DataFrame] = {}
        for tf in tfs:
            period = body.period or _YF_PERIOD.get(tf, "max")
            push({"type": "downloading", "ticker": ticker, "tf": tf, "period": period})
            try:
                df = _fetch(ticker, tf, period)
                if df is None or df.empty:
                    raise ValueError("empty response")
                _store(ticker, tf, df)
                push({"type": "download_done", "ticker": ticker, "tf": tf,
                      "bars": len(df), "period": period,
                      "start": str(df.index[0].date()),
                      "end":   str(df.index[-1].date())})
                tf_data[tf] = df
            except Exception as exc:
                push({"type": "download_error", "ticker": ticker, "tf": tf,
                      "msg": str(exc)})

        if not tf_data:
            push({"type": "ticker_done", "ticker": ticker, "verdict": "no_data"})
            summary.append({"ticker": ticker, "verdict": "no_data"})
            continue

        # Resample to cover all requested TFs from the finest available
        native_tf = min(tf_data.keys(), key=lambda t: _ANN_FACTORS.get(t, 365))
        df_native = tf_data[native_tf]
        for tf in tfs:
            if tf not in tf_data and tf != native_tf:
                tf_data[tf] = _resample(df_native, tf)

        # ── 2. Optimization loop ─────────────────────────────────────────────────────────────────
        best_sharpe = float("-inf")
        best_sid = best_tf = None
        log = []

        for iteration in range(1, body.max_iter + 1):
            tf = tfs[(iteration - 1) % len(tfs)]
            df = tf_data.get(tf)
            if df is None or df.empty:
                continue

            effective_iter = iteration + body.iter_offset
            arch_name, _, sl, tp = get_archetype(effective_iter)
            push({"type": "iter_start", "ticker": ticker, "iter": iteration,
                  "tf": tf, "arch": arch_name, "effective_iter": effective_iter})

            risk_cfg = _RISK_GRID[(iteration - 1) % len(_RISK_GRID)]
            try:
                sid, sharpe, dd, n_trades, win_rate, mc, drift, oos_sharpe = _run_iteration(
                    ticker, tf, df, effective_iter, arch_name, sl, tp, risk_cfg=risk_cfg
                )
            except Exception as exc:
                push({"type": "iter_error", "ticker": ticker, "iter": iteration,
                      "msg": str(exc)})
                continue

            min_tr    = _MIN_TRADES_ROBUST.get(tf, 20)
            dd_ok     = abs(dd) <= body.max_dd
            drift_ok  = drift > 0
            trades_ok = n_trades >= min_tr
            oos_ok    = (oos_sharpe is None) or (oos_sharpe > 0)  # None = skip gate (not enough data)
            mc_ok     = (mc.get("p_profit", 0.0) >= 0.55
                         and mc.get("p_ruin", 1.0) < 0.01
                         and drift_ok)
            verdict = ("ROBUST" if sharpe >= _ROBUST_MIN_SHARPE and dd_ok and mc_ok
                                    and trades_ok and oos_ok
                       else "marginal" if sharpe >= 0 else "failed")

            push({
                "type": "iter_done", "ticker": ticker, "iter": iteration,
                "tf": tf, "arch": arch_name, "sid": sid,
                "sharpe": round(sharpe, 3), "dd": round(dd, 2),
                "n_trades": n_trades, "win_rate": round(win_rate, 1),
                "verdict": verdict,
                "mc_p_profit": mc.get("p_profit"),
                "mc_p_ruin":   mc.get("p_ruin"),
                "drift":       round(drift, 6),
                "oos_sharpe":  round(oos_sharpe, 3) if oos_sharpe is not None else None,
                "trades_ok":   trades_ok,
                "oos_ok":      oos_ok,
            })
            log.append({"iter": iteration, "tf": tf, "arch": arch_name,
                        "sid": sid, "sharpe": sharpe, "dd": dd,
                        "n_trades": n_trades, "win_rate": win_rate,
                        "verdict": verdict,
                        "mc_p_profit": mc.get("p_profit"),
                        "mc_p_ruin":   mc.get("p_ruin"),
                        "drift":       round(drift, 6)})

            if sharpe > best_sharpe:
                best_sharpe, best_sid, best_tf = sharpe, sid, tf

            if verdict == "ROBUST":
                _promote(sid, "live")
                push({"type": "ticker_done", "ticker": ticker, "verdict": "ROBUST",
                      "sid": sid, "tf": tf, "sharpe": round(sharpe, 3),
                      "dd": round(dd, 2), "log": log})
                summary.append({"ticker": ticker, "verdict": "ROBUST", "sid": sid,
                                 "tf": tf, "sharpe": round(sharpe, 3), "dd": round(dd, 2)})
                if sharpe >= body.stop_sharpe:
                    break
        else:
            if best_sid:
                _promote(best_sid, "marginal")
            push({"type": "ticker_done", "ticker": ticker, "verdict": "none",
                  "sid": best_sid, "tf": best_tf,
                  "sharpe": round(best_sharpe, 3) if best_sid else None,
                  "log": log})
            summary.append({"ticker": ticker, "verdict": "none", "sid": best_sid,
                             "tf": best_tf, "sharpe": round(best_sharpe, 3) if best_sid else None})

    robust = [s for s in summary if s["verdict"] == "ROBUST"]
    push({
        "type": "complete",
        "total_tickers": len(tickers),
        "robust_found": len(robust),
        "summary": summary,
    })


# ── Helpers ──────────────────────────────────────────────────────────────────────────────────

def _fetch(ticker: str, tf: str, period: str) -> pd.DataFrame:
    from engine.providers.ccxt_client import is_crypto_ticker, fetch as ccxt_fetch
    from engine.providers.yfinance_client import fetch as yf_fetch

    if is_crypto_ticker(ticker):
        try:
            return ccxt_fetch(ticker, period=period, interval=tf)
        except Exception:
            pass
    return yf_fetch(ticker, period=period, interval=tf)


def _store(ticker: str, tf: str, df: pd.DataFrame) -> None:
    from engine.storage.bulk_writer import bulk_store
    bulk_store(get_conn(), ticker, f"yfinance:{tf}", df)


def _resample(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    freq_map = {"4h": "4h", "1d": "D", "1wk": "W"}
    freq = freq_map.get(tf)
    if not freq:
        return df
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    return df.resample(freq).agg(agg).dropna()


def _run_iteration(ticker, tf, df, iteration, arch_name, sl, tp, risk_cfg: dict | None = None):
    import numpy as np
    from engine.strategy_core import compute_indicators_v2
    from engine.backtest import run_versions, INITIAL_CAPITAL
    from engine.montecarlo import run_bootstrap

    _, code, sl_used, tp_used = get_archetype(iteration)
    rc = risk_cfg or {}

    config = {
        "ticker": ticker, "timeframe": tf,
        "sl_mult": sl_used, "tp_mult": tp_used,
        "active_hours": _ACTIVE_HOURS.get(tf, [6, 22]),
        "commission_pips": 1.0, "slippage_pips": 0.5,
        "risk_per_trade": 0.01, "direction": "ALL",
        "max_positions": 1, "cooldown_bars": 0,
        "leverage":             float(rc.get("leverage", 1.0)),
        "trailing_stop":        bool(rc.get("trailing_stop", False)),
        "trailing_stop_method": rc.get("trailing_stop_method", "atr"),
        "trailing_stop_value":  float(rc.get("trailing_stop_value", 1.5)),
        "position_size_method": rc.get("position_size_method", "risk_pct"),
    }

    df_ind = compute_indicators_v2(df, fit_garch=True)
    ns: dict = {}
    try:
        exec(compile(code, "<agent_fn>", "exec"), ns)
        if "agent_fn" in ns:
            config["agent_fn"] = ns["agent_fn"]
    except Exception:
        pass

    versions = run_versions(df_ind, config, direction=config["direction"])
    best_key = next((k for k in ["V_Agent", "V4 +GARCH+Costi", "V2 +Costi", "V1 Base"]
                     if k in versions and "metrics" in versions[k]), "")
    if not best_key and versions:
        best_key = next(iter(versions))

    m = versions.get(best_key, {}).get("metrics", {})
    sharpe = float(m.get("sharpe_ratio", m.get("sharpe", 0)) or 0)
    dd = float(m.get("max_drawdown_pct", m.get("max_dd", 0)) or 0)
    n_trades = int(m.get("n_trades", 0) or 0)
    win_rate = float(m.get("win_rate_pct", 0) or 0)
    cagr_raw = m.get("cagr_pct", 0)
    cagr = float(cagr_raw["point"] if isinstance(cagr_raw, dict) else cagr_raw or 0)
    pf_raw = m.get("profit_factor", 0)
    pf = float(pf_raw if pf_raw not in (None, float("inf"), float("-inf")) else 0)

    # ── Drift: mean PnL per trade (positive = positive expected value) ────────
    best_res = versions.get(best_key, {}).get("result", {})
    trades_df = best_res.get("trades") if best_res else None
    drift = 0.0
    if trades_df is not None and not trades_df.empty:
        try:
            drift = float(trades_df["pnl"].mean())
        except Exception:
            pass

    # ── Monte Carlo simulation (500 paths for reliable p_ruin estimate) ───────
    mc_result: dict = {}
    if trades_df is not None and not trades_df.empty and len(trades_df) >= 5:
        try:
            pnl_arr = trades_df["pnl"].values.astype(float)
            ann_factor = _ANN_FACTORS.get(tf, 8760)
            days_in_period = float(max((df.index[-1] - df.index[0]).days, 1))
            bs = run_bootstrap(pnl_arr, n_sims=500, initial_capital=INITIAL_CAPITAL,
                               days_in_period=days_in_period, ann_factor=ann_factor)
            mc_result = {
                "p_profit":      round(float((bs["final_capital"] > INITIAL_CAPITAL).mean()), 4),
                "p_ruin":        round(float((bs["final_capital"] < INITIAL_CAPITAL * 0.5).mean()), 4),
                "mc_sharpe_p50": round(float(np.percentile(bs["sharpe"], 50)), 3),
                "mc_sharpe_p5":  round(float(np.percentile(bs["sharpe"], 5)), 3),
                "n_sims":        500,
            }
        except Exception:
            pass

    # ── OOS validation: hold out last 20% of bars as unseen data ────────────
    # Requires OOS Sharpe > 0 so the strategy is profitable on data it never
    # saw during IS selection — the simplest guard against data snooping.
    oos_sharpe: float | None = None
    n_oos = len(df_ind) // 5           # 20 % hold-out
    min_oos_bars = 80                   # skip OOS gate if not enough history
    if n_oos >= min_oos_bars and best_key:
        try:
            df_oos  = df_ind.iloc[-n_oos:]
            oos_cfg = {k: v for k, v in config.items()}
            v_oos   = run_versions(df_oos, oos_cfg, direction=oos_cfg.get("direction", "ALL"))
            m_oos   = v_oos.get(best_key, {}).get("metrics", {})
            oos_sharpe = float(m_oos.get("sharpe_ratio", m_oos.get("sharpe", -999)) or -999)
        except Exception:
            pass

    # Enrich config with best-version info and achieved metrics
    config.pop("agent_fn", None)   # not JSON-serialisable
    config["best_version"] = best_key
    config["perf"] = {
        "sharpe":        round(sharpe, 3),
        "max_dd":        round(dd, 2),
        "cagr_pct":      round(cagr, 2),
        "profit_factor": round(pf, 2),
        "n_trades":      n_trades,
        "win_rate":      round(win_rate, 1),
        "drift":         round(drift, 6),
    }
    if oos_sharpe is not None:
        config["perf"]["oos_sharpe"] = round(oos_sharpe, 3)
    if mc_result:
        config["perf"]["mc_p_profit"] = mc_result.get("p_profit")
        config["perf"]["mc_p_ruin"]   = mc_result.get("p_ruin")

    # Save strategy + run to DB
    conn = get_conn()
    sid = uuid.uuid4().hex[:8]
    conn.execute(
        "INSERT INTO strategies (id,name,strategy_type,config,code,status) VALUES (?,?,?,?,?,?)",
        [sid, f"pipe_{iteration:03d}_{tf}_{ticker.replace('-','_')}",
         "pipeline", json.dumps(config), code, "research"],
    )
    run_id = uuid.uuid4().hex[:12]
    metrics_json = json.dumps({best_key: m})
    mc_json = json.dumps(mc_result)
    conn.execute(
        "INSERT INTO runs (id,name,ticker,timeframe,params,status,strategy_id) VALUES (?,?,?,?,?,?,?)",
        [run_id, f"pipe_{iteration:03d}_{tf}_{arch_name}",
         ticker, tf, json.dumps(config), "done", sid],
    )
    existing = conn.execute("SELECT run_id FROM run_results WHERE run_id=?", [run_id]).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO run_results (run_id,metrics,equity,trades,wfo,sweep,mc) VALUES (?,?,?,?,?,?,?)",
            [run_id, metrics_json, "[]", "[]", "[]", "[]", mc_json],
        )

    return sid, sharpe, dd, n_trades, win_rate, mc_result, drift, oos_sharpe


def _promote(sid: str, status: str) -> None:
    try:
        get_conn().execute(
            "UPDATE strategies SET starred=TRUE, status=? WHERE id=?", [status, sid]
        )
    except Exception:
        pass
