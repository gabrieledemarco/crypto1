"""
/runs/pipeline/vibe — Claude-powered strategy generation pipeline.

For each (ticker, timeframe), Claude generates an ORIGINAL custom strategy
(never a predefined archetype), backtests it, and saves ROBUST results to the Library.

Targets: Sharpe > 1.0, MaxDD < 8%.

POST /runs/pipeline/vibe
GET  /runs/pipeline/vibe/{job_id}/stream  — SSE (same event format as /runs/pipeline)
"""
import asyncio, concurrent.futures, json, os, re, uuid

import numpy as np, pandas as pd
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.db import get_conn
from api.utils import extract_config, extract_code

router = APIRouter()
_queues: dict[str, asyncio.Queue] = {}

_ROBUST_MIN_SHARPE = 1.5
_ROBUST_MAX_DD     = 8.0

_MIN_TRADES_ROBUST = {
    "1m": 50, "5m": 40, "15m": 30, "30m": 25,
    "1h": 20, "4h": 12, "1d":  8,
}

_TF_NORM    = {"1min":"1m","5min":"5m","15min":"15m","30min":"30m","1h":"1h","4h":"4h","1d":"1d"}
_YF_PERIOD  = {"1m":"7d","5m":"60d","15m":"60d","30m":"60d","1h":"730d","4h":"730d","1d":"max"}
_ACT_HOURS  = {"1m":[0,23],"5m":[0,23],"15m":[6,22],"30m":[6,22],"1h":[6,22],"4h":[0,22],"1d":[0,23]}
_ANN_FACTOR = {"1m":525600,"5m":105120,"15m":35040,"30m":17520,"1h":8760,"4h":2190,"1d":365}

# ── Vibe-specific system prompt ───────────────────────────────────────────────
_SYSTEM = """\
You are a professional quantitative trading engineer. Generate an ORIGINAL, custom trading strategy.

## Hard Performance Targets
- Sharpe ratio > 1.0 (primary)
- Max drawdown < 8% (hard constraint — must be achievable with the chosen risk_per_trade)
- Minimum 20 trades/year (statistical significance)

## Risk Sizing (mandatory)
- risk_per_trade 0.3-0.5% for volatile assets (ann_vol > 50%), 0.5-1.0% for moderate vol
- TP/SL ratio ≥ 2.0 (tp_mult ≥ 2 × sl_mult) to ensure positive expectancy
- sl_mult 1.5-2.0 for mean-reversion, 2.5-3.5 for trend-following

## Regime → Strategy Mapping
- Hurst > 0.55 (trending): momentum, breakout, trend continuation — trade WITH the trend
- Hurst < 0.45 (mean-reverting): Bollinger Band touches, RSI extremes, VWAP deviation — fade extremes
- Hurst ≈ 0.50 (random-walk): volatility breakout after squeeze expansion

## Forbidden Patterns (too generic, overfit)
- Simple RSI crossover alone (RSI > 50 / RSI < 50)
- Simple EMA crossover alone without filters
- Fixed percentage stops (always use ATR-based stops)

## Required Output Format

Step 1 — Rationale (2-4 sentences): regime fit, why DD < 8% is achievable, expected signal frequency.

Step 2 — JSON config in ```json block:
{
  "ticker": "BTC-USD",
  "timeframe": "1h",
  "sl_mult": 2.0,
  "tp_mult": 4.0,
  "active_hours": [6, 22],
  "risk_per_trade": 0.5,
  "direction": "ALL"
}

Step 3 — Python ```python block:
import pandas as pd
import numpy as np

def agent_fn(df: pd.DataFrame, ind=None) -> pd.DataFrame:
    df = df.copy()
    # ORIGINAL logic — must have at least 2 confirming conditions
    # Use .shift(1) on ALL conditions (no lookahead bias!)
    # ind() helper: ind("EMA",N), ind("BB",20,2.0) → (upper,mid,lower),
    #   ind("MACD",12,26,9) → (line,signal,hist), ind("STOCH",14) → (K,D,hist)
    df["signal"] = 0
    df["SL_dist"] = df["ATR14"] * 2.0
    df["TP_dist"] = df["ATR14"] * 4.0
    return df

df columns: Open,High,Low,Close,Volume,ATR14,RSI14,EMA50,EMA200,
  RollHigh6,RollLow6,garch_h,garch_regime(LOW/MED/HIGH),size_mult,ret,hour,dow
"""


class VibePipelineRequest(BaseModel):
    tickers: list = ["BTC-USD", "ETH-USD", "SOL-USD", "EURUSD=X", "AAPL"]
    timeframes: list = ["1h", "4h", "1d"]
    max_attempts: int = 4
    stop_sharpe: float = 1.5
    max_dd: float = 8.0


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("")
async def start_vibe_pipeline(body: VibePipelineRequest):
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        return {"error": "ANTHROPIC_API_KEY not configured on this server"}
    job_id = uuid.uuid4().hex[:12]
    _queues[job_id] = asyncio.Queue()
    asyncio.create_task(_run(job_id, body, key))
    return {"job_id": job_id, "stream_url": f"/runs/pipeline/vibe/{job_id}/stream",
            "tickers": body.tickers, "timeframes": body.timeframes}


@router.get("/{job_id}/stream")
async def stream_vibe_pipeline(job_id: str):
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

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Coordinator ───────────────────────────────────────────────────────────────

async def _run(job_id: str, body: VibePipelineRequest, key: str):
    queue = _queues[job_id]

    async def _hb():
        while True:
            await asyncio.sleep(20)
            queue.put_nowait({"type": "ping"})

    hb = asyncio.create_task(_hb())
    try:
        with concurrent.futures.ThreadPoolExecutor() as pool:
            await asyncio.get_running_loop().run_in_executor(
                pool, _sync_worker, body, queue.put_nowait, key
            )
    except Exception as exc:
        queue.put_nowait({"type": "error", "msg": str(exc)})
    finally:
        hb.cancel()


# ── Sync worker ───────────────────────────────────────────────────────────────

def _sync_worker(body: VibePipelineRequest, push, key: str):
    from api.routers.brain import get_brain_context

    tickers = body.tickers
    tfs = [_TF_NORM.get(t.strip(), t.strip()) for t in body.timeframes]

    push({"type": "start", "tickers": tickers, "timeframes": tfs,
          "max_attempts": body.max_attempts, "max_dd": body.max_dd, "mode": "vibe"})

    summary, global_iter = [], 0

    for t_idx, ticker in enumerate(tickers):
        push({"type": "ticker_start", "ticker": ticker, "idx": t_idx + 1, "total": len(tickers)})

        tf_data = {}
        for tf in tfs:
            period = _YF_PERIOD.get(tf, "max")
            push({"type": "downloading", "ticker": ticker, "tf": tf, "period": period})
            try:
                df = _fetch(ticker, tf, period)
                if df is None or df.empty:
                    raise ValueError("empty response")
                _store(ticker, tf, df)
                tf_data[tf] = df
                push({"type": "download_done", "ticker": ticker, "tf": tf,
                      "bars": len(df), "period": period,
                      "start": str(df.index[0].date()), "end": str(df.index[-1].date())})
            except Exception as exc:
                push({"type": "download_error", "ticker": ticker, "tf": tf, "msg": str(exc)})

        if not tf_data:
            push({"type": "ticker_done", "ticker": ticker, "verdict": "no_data"})
            summary.append({"ticker": ticker, "verdict": "no_data"})
            continue

        best_sharpe, best_sid, best_tf_val = float("-inf"), None, None
        found_robust = False

        for tf in tfs:
            if found_robust:
                break
            df = tf_data.get(tf)
            if df is None or df.empty:
                continue

            stats = _asset_stats(df, ticker, tf)
            brain_ctx = ""
            try:
                brain_ctx = get_brain_context(
                    f"trading strategy {ticker} {tf} {stats['regime']} drawdown risk management",
                    asset=ticker) or ""
            except Exception:
                pass

            prev_feedback = ""
            for attempt in range(1, body.max_attempts + 1):
                global_iter += 1
                push({"type": "iter_start", "ticker": ticker, "iter": global_iter,
                      "tf": tf, "arch": f"vibe_a{attempt:02d}"})

                try:
                    config, code = _call_claude(ticker, tf, stats, brain_ctx, attempt, prev_feedback, key)
                except Exception as exc:
                    push({"type": "iter_error", "ticker": ticker, "iter": global_iter, "msg": str(exc)})
                    break

                try:
                    sid, sharpe, dd, n_tr, wr, mc, drift, verdict = _run_attempt(
                        ticker, tf, df, config, code, attempt)
                except Exception as exc:
                    push({"type": "iter_error", "ticker": ticker, "iter": global_iter, "msg": str(exc)})
                    prev_feedback = f"Code execution failed: {exc}. Write simpler, safer code."
                    continue

                push({"type": "iter_done", "ticker": ticker, "iter": global_iter,
                      "tf": tf, "arch": f"vibe_a{attempt:02d}", "sid": sid,
                      "sharpe": round(sharpe, 3), "dd": round(dd, 2),
                      "n_trades": n_tr, "win_rate": round(wr, 1), "verdict": verdict,
                      "mc_p_profit": mc.get("p_profit"), "mc_p_ruin": mc.get("p_ruin"),
                      "drift": round(drift, 6)})

                if sharpe > best_sharpe:
                    best_sharpe, best_sid, best_tf_val = sharpe, sid, tf

                if verdict == "ROBUST":
                    _promote(sid, "live")
                    push({"type": "ticker_done", "ticker": ticker, "verdict": "ROBUST",
                          "sid": sid, "tf": tf, "sharpe": round(sharpe, 3), "dd": round(dd, 2)})
                    summary.append({"ticker": ticker, "verdict": "ROBUST", "sid": sid,
                                    "tf": tf, "sharpe": round(sharpe, 3), "dd": round(dd, 2)})
                    found_robust = True
                    if sharpe >= body.stop_sharpe:
                        break
                    break
                else:
                    prev_feedback = _build_feedback(attempt, sharpe, dd, n_tr, wr, verdict)

        if not found_robust:
            if best_sid:
                _promote(best_sid, "marginal")
            push({"type": "ticker_done", "ticker": ticker, "verdict": "none",
                  "sid": best_sid, "tf": best_tf_val,
                  "sharpe": round(best_sharpe, 3) if best_sid else None})
            summary.append({"ticker": ticker, "verdict": "none", "sid": best_sid,
                            "tf": best_tf_val,
                            "sharpe": round(best_sharpe, 3) if best_sid else None})

    push({"type": "complete", "total_tickers": len(tickers),
          "robust_found": sum(1 for s in summary if s["verdict"] == "ROBUST"),
          "summary": summary})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _asset_stats(df: pd.DataFrame, ticker: str, tf: str) -> dict:
    rets = np.diff(np.log(df["Close"].values))
    rets = rets[np.isfinite(rets)]
    ann = _ANN_FACTOR.get(tf, 8760)
    vol = float(np.std(rets) * np.sqrt(ann) * 100)
    ret = float(np.mean(rets) * ann * 100)
    hurst = 0.5
    try:
        lp = np.log(df["Close"].values)
        lp = lp[np.isfinite(lp)]
        n = len(lp)
        if n >= 50:
            rs_v, lag_v = [], []
            for lag in [max(2, n // k) for k in [8, 4, 2]]:
                s = lp[:lag]
                d = np.cumsum(s - s.mean())
                r, sd = d.max() - d.min(), s.std()
                if sd > 0:
                    rs_v.append(np.log(r / sd)); lag_v.append(np.log(lag))
            if len(rs_v) >= 2:
                hurst = float(max(0.1, min(0.9, np.polyfit(lag_v, rs_v, 1)[0])))
    except Exception:
        pass
    regime = "trending" if hurst > 0.55 else ("mean-reverting" if hurst < 0.45 else "random-walk")
    return {"ticker": ticker, "timeframe": tf, "bars": len(df),
            "ann_vol_pct": round(vol, 1), "ann_ret_pct": round(ret, 1),
            "sharpe_bh": round(ret / vol, 2) if vol > 0 else 0,
            "hurst": round(hurst, 3), "regime": regime,
            "period": f"{df.index[0].date()} → {df.index[-1].date()}"}


def _call_claude(ticker, tf, stats, brain_ctx, attempt, prev_feedback, key):
    import anthropic
    client = anthropic.Anthropic(api_key=key, timeout=120.0)
    system = (brain_ctx + "\n\n" + _SYSTEM) if brain_ctx else _SYSTEM
    lines = [
        f"Asset: {ticker}  Timeframe: {tf}  Bars: {stats['bars']:,}  Period: {stats['period']}",
        f"Ann.vol: {stats['ann_vol_pct']}%  Ann.ret: {stats['ann_ret_pct']}%  "
        f"Sharpe(B&H): {stats['sharpe_bh']}",
        f"Hurst: {stats['hurst']} ({stats['regime']})",
        f"",
        f"Attempt #{attempt} — Generate original strategy targeting Sharpe>1.0, MaxDD<8%.",
    ]
    if prev_feedback:
        lines += ["", "FEEDBACK FROM PREVIOUS ATTEMPT (design something different):", prev_feedback]
    resp = client.messages.create(
        model="claude-opus-4-7", max_tokens=3000,
        system=system, messages=[{"role": "user", "content": "\n".join(lines)}]
    )
    text = resp.content[0].text
    config = extract_config(text)
    code = extract_code(text)
    if not config:
        config = {"ticker": ticker, "timeframe": tf, "sl_mult": 2.0, "tp_mult": 4.0,
                  "active_hours": _ACT_HOURS.get(tf, [6, 22]),
                  "risk_per_trade": 0.5, "direction": "ALL"}
    config.setdefault("active_hours", _ACT_HOURS.get(tf, [6, 22]))
    return config, code


def _build_feedback(attempt, sharpe, dd, n_trades, wr, verdict) -> str:
    msg = f"Attempt {attempt}: Sharpe={sharpe:.3f}, DD={dd:.1f}%, Trades={n_trades}, WR={wr:.1f}%."
    if sharpe < 0:
        msg += " Strategy lost money overall. Try a completely different signal logic."
    elif abs(dd) > _ROBUST_MAX_DD:
        msg += (f" DD too high ({abs(dd):.1f}% > {_ROBUST_MAX_DD}%). "
                "Reduce risk_per_trade or use tighter stops (smaller sl_mult).")
    elif n_trades < 10:
        msg += " Too few trades — signal is too rare. Relax entry conditions."
    elif sharpe < _ROBUST_MIN_SHARPE:
        msg += (f" Sharpe={sharpe:.3f} too low. Add stronger entry filters "
                "or improve TP/SL ratio (tp_mult should be at least 2×sl_mult).")
    return msg


def _run_attempt(ticker, tf, df, config, code, attempt):
    from engine.strategy_core import compute_indicators_v2
    from engine.backtest import run_versions, INITIAL_CAPITAL
    from engine.montecarlo import run_bootstrap

    df_ind = compute_indicators_v2(df, fit_garch=True)
    risk = float(config.get("risk_per_trade", 0.5))
    if risk > 0.1:
        risk /= 100.0
    cfg = {
        "sl_mult": float(config.get("sl_mult", 2.0)),
        "tp_mult": float(config.get("tp_mult", 4.0)),
        "active_hours": list(config.get("active_hours", [6, 22])),
        "commission_pips": 1.0, "slippage_pips": 0.5,
        "leverage": 1.0, "risk_per_trade": risk,
        "direction": config.get("direction", "ALL"),
        "max_positions": 1, "cooldown_bars": 0,
    }
    if code:
        try:
            ns: dict = {}
            exec(compile(code, "<vibe_agent_fn>", "exec"), ns)
            if "agent_fn" in ns:
                cfg["agent_fn"] = ns["agent_fn"]
        except Exception:
            pass

    versions = run_versions(df_ind, cfg, direction=cfg["direction"])
    best_key = next((k for k in ["V_Agent", "V4 +GARCH+Costi", "V2 +Costi", "V1 Base"]
                     if k in versions and "metrics" in versions[k]), "")
    if not best_key and versions:
        best_key = next(iter(versions))

    m = versions.get(best_key, {}).get("metrics", {})
    sharpe  = float(m.get("sharpe_ratio", m.get("sharpe", 0)) or 0)
    dd      = float(m.get("max_drawdown_pct", m.get("max_dd", 0)) or 0)
    n_tr    = int(m.get("n_trades", 0) or 0)
    wr      = float(m.get("win_rate_pct", 0) or 0)

    trades_df = (versions.get(best_key, {}).get("result") or {}).get("trades")
    drift = 0.0
    if trades_df is not None and not trades_df.empty:
        try: drift = float(trades_df["pnl"].mean())
        except: pass

    mc_result: dict = {}
    if trades_df is not None and not trades_df.empty and len(trades_df) >= 5:
        try:
            pnl = trades_df["pnl"].values.astype(float)
            ann = _ANN_FACTOR.get(tf, 8760)
            days = float(max((df.index[-1] - df.index[0]).days, 1))
            bs = run_bootstrap(pnl, n_sims=500, initial_capital=INITIAL_CAPITAL,
                               days_in_period=days, ann_factor=ann)
            mc_result = {
                "p_profit": round(float((bs["final_capital"] > INITIAL_CAPITAL).mean()), 4),
                "p_ruin":   round(float((bs["final_capital"] < INITIAL_CAPITAL * 0.5).mean()), 4),
            }
        except Exception:
            pass

    # ── OOS validation: last 20% of bars as unseen hold-out ─────────────────
    oos_sharpe: float | None = None
    n_oos = len(df_ind) // 5
    if n_oos >= 80 and best_key:
        try:
            df_oos  = df_ind.iloc[-n_oos:]
            oos_cfg = {k: v for k, v in cfg.items() if k != "agent_fn"}
            if "agent_fn" in cfg:
                oos_cfg["agent_fn"] = cfg["agent_fn"]
            v_oos   = run_versions(df_oos, oos_cfg, direction=oos_cfg.get("direction", "ALL"))
            m_oos   = v_oos.get(best_key, {}).get("metrics", {})
            oos_sharpe = float(m_oos.get("sharpe_ratio", m_oos.get("sharpe", -999)) or -999)
        except Exception:
            pass

    min_tr    = _MIN_TRADES_ROBUST.get(tf, 20)
    dd_ok     = abs(dd) <= _ROBUST_MAX_DD
    drift_ok  = drift > 0
    trades_ok = n_tr >= min_tr
    oos_ok    = (oos_sharpe is None) or (oos_sharpe > 0)
    mc_ok     = (mc_result.get("p_profit", 0) >= 0.55
                 and mc_result.get("p_ruin", 1) < 0.01
                 and drift_ok)
    verdict  = ("ROBUST" if sharpe >= _ROBUST_MIN_SHARPE and dd_ok and mc_ok
                             and trades_ok and oos_ok
                else "marginal" if sharpe >= 0 else "failed")

    conn = get_conn()
    sid = uuid.uuid4().hex[:8]
    cfg_save = {k: v for k, v in config.items()}
    cfg_save["best_version"] = best_key
    cfg_save["perf"] = {
        "sharpe": round(sharpe, 3), "dd": round(dd, 2),
        "n_trades": n_tr, "win_rate": round(wr, 1), "drift": round(drift, 6),
    }
    if oos_sharpe is not None:
        cfg_save["perf"]["oos_sharpe"] = round(oos_sharpe, 3)
    if mc_result:
        cfg_save["perf"]["mc_p_profit"] = mc_result.get("p_profit")
        cfg_save["perf"]["mc_p_ruin"]   = mc_result.get("p_ruin")
    name = f"vibe_{ticker.replace('-','_')}_{tf}_a{attempt:02d}"
    conn.execute(
        "INSERT INTO strategies (id,name,strategy_type,config,code,status) VALUES (?,?,?,?,?,?)",
        [sid, name, "vibe", json.dumps(cfg_save), code, "research"]
    )
    return sid, sharpe, dd, n_tr, wr, mc_result, drift, verdict



def _fetch(ticker, tf, period):
    from engine.providers.ccxt_client import is_crypto_ticker, fetch as ccxt_fetch
    from engine.providers.yfinance_client import fetch as yf_fetch
    if is_crypto_ticker(ticker):
        try: return ccxt_fetch(ticker, period=period, interval=tf)
        except: pass
    return yf_fetch(ticker, period=period, interval=tf)


def _store(ticker, tf, df):
    from engine.storage.bulk_writer import bulk_store
    bulk_store(get_conn(), ticker, f"yfinance:{tf}", df)


def _promote(sid: str, status: str):
    try:
        get_conn().execute("UPDATE strategies SET starred=TRUE, status=? WHERE id=?", [status, sid])
    except Exception:
        pass
