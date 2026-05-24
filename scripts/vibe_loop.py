#!/usr/bin/env python3
"""
scripts/vibe_loop.py
====================
Multi-timeframe iterative strategy optimization loop.
Cycles 12 archetypes × 9 SL/TP combos across 1h / 4h / 1d bars,
targeting Sharpe ≥ 1.5 with drawdown ≤ --max-dd %.

Sub-hourly timeframes (1min / 5min / 15min) require tick-level data
that is not in the local archive — they are skipped with a warning.

Usage:
    cd /home/user/crypto1
    python scripts/vibe_loop.py \\
        [--ticker BTC-USD] \\
        [--timeframes 1h,4h,1d] \\
        [--max-iter 100] \\
        [--max-dd 20] \\
        [--stop-sharpe 1.5]

Environment:
    ANTHROPIC_API_KEY  — optional; omit to use the archetype library.
    DUCKDB_PATH        — defaults to /tmp/pareto.db (set by api/db.py).
"""
import argparse
import json
import math
import os
import sys
import uuid
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)
sys.path.insert(0, _SCRIPTS)

from api.db import get_conn
from engine.strategy_core import compute_indicators_v2
from engine.backtest import run_versions, run_wfo
from strategies import get_archetype

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── Timeframe metadata ─────────────────────────────────────────────────────────
_SUB_HOURLY    = {"1min", "5min"}           # truly unsupported (need real tick data)
_RESAMPLE_FREQ = {"4h": "4h", "4H": "4h", "1d": "D", "d": "D"}
_ANN_FACTORS   = {"15min": 35040, "1h": 8760, "4h": 2190, "1d": 365}

# ── Archive CSV map ────────────────────────────────────────────────────────────
_CSV_DIR = os.path.join(_ROOT, "archive", "btc_analysis", "output")
_TICKER_CSV = {"BTC-USD": "btc_hourly.csv", "ETH-USD": "eth_hourly.csv", "SOL-USD": "sol_hourly.csv"}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Data — load 1h, resample to higher timeframes
# ─────────────────────────────────────────────────────────────────────────────

def _seed_csv(ticker: str) -> None:
    fname = _TICKER_CSV.get(ticker)
    if not fname or not os.path.exists(os.path.join(_CSV_DIR, fname)):
        return
    print(f"  Seeding DuckDB from {fname}...")
    df = pd.read_csv(os.path.join(_CSV_DIR, fname), parse_dates=["Date"])
    df = df.rename(columns={"Date": "ts", "Open": "open", "High": "high",
                             "Low": "low", "Close": "close", "Volume": "volume"})
    df["ticker"] = ticker
    df["source"] = "csv_archive"
    conn = get_conn()
    n = 0
    for row in df.itertuples(index=False):
        try:
            conn.execute(
                "INSERT OR IGNORE INTO assets (ticker,source,ts,open,high,low,close,volume) "
                "VALUES (?,?,?,?,?,?,?,?)",
                [row.ticker, row.source, row.ts,
                 row.open, row.high, row.low, row.close, row.volume],
            )
            n += 1
        except Exception:
            pass
    print(f"  Inserted {n} rows")


def load_bars(ticker: str, native_tf: str = "1h") -> pd.DataFrame:
    """
    Load the native-resolution bars for ticker from DuckDB.
    Falls back to seeding from the hourly CSV archive when the table is empty.
    """
    conn = get_conn()

    def _q():
        return conn.execute(
            "SELECT ts,open,high,low,close,volume FROM assets WHERE ticker=? ORDER BY ts",
            [ticker],
        ).fetchall()

    rows = _q()
    if not rows:
        _seed_csv(ticker)
        rows = _q()
    if not rows:
        raise RuntimeError(f"No OHLCV for '{ticker}'. Place CSV in {_CSV_DIR}.")

    df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    print(f"  {native_tf} : {len(df):,} bars ({df.index[0].date()} → {df.index[-1].date()})")
    return df


def resample(df_1h: pd.DataFrame, tf: str) -> pd.DataFrame:
    freq = _RESAMPLE_FREQ.get(tf)
    if not freq:
        return df_1h
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    out = df_1h.resample(freq).agg(agg).dropna()
    print(f"  {tf} : {len(out):,} bars")
    return out


def _active_hours(tf: str) -> list[int]:
    """Bars are 1 per day at midnight for 1d; open all hours."""
    if tf == "1d":
        return [0, 23]   # daily bars land at midnight, must open all
    return [6, 22]        # 1h, 4h, 15min all have intraday hour resolution


# ─────────────────────────────────────────────────────────────────────────────
# 2. Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _hurst(prices: np.ndarray) -> float:
    p = prices[np.isfinite(prices) & (prices > 0)]
    if len(p) < 50:
        return 0.5
    try:
        lp = np.log(p)
        n  = len(lp)
        rs_v, lag_v = [], []
        for lag in [max(2, n // k) for k in [8, 4, 2]]:
            s = lp[:lag]
            d = np.cumsum(s - s.mean())
            r, sd = d.max() - d.min(), s.std()
            if sd > 0:
                rs_v.append(math.log(r / sd))
                lag_v.append(math.log(lag))
        if len(rs_v) >= 2:
            return float(max(0.1, min(0.9, np.polyfit(lag_v, rs_v, 1)[0])))
    except Exception:
        pass
    return 0.5


def _asset_stats(df: pd.DataFrame, ticker: str, tf: str) -> str:
    ann = _ANN_FACTORS.get(tf, 8760)
    rets = np.diff(np.log(df["Close"].values))
    rets = rets[np.isfinite(rets)]
    vol  = float(np.std(rets) * np.sqrt(ann) * 100)
    h    = _hurst(df["Close"].values)
    reg  = "trending" if h > 0.55 else ("mean-reverting" if h < 0.45 else "random-walk")
    return (
        f"Asset:{ticker}  TF:{tf}  Bars:{len(df):,}\n"
        f"Ann.vol:{vol:.1f}%  Hurst:{h:.3f}({reg})\n"
        f"Period:{df.index[0].date()}→{df.index[-1].date()}"
    )


def _brain_history(ticker: str) -> str:
    try:
        rows = get_conn().execute(
            "SELECT content, verdict FROM brain_chunks WHERE source='empirical' AND asset=? "
            "ORDER BY synced_at DESC LIMIT 6",
            [ticker],
        ).fetchall()
        if not rows:
            return ""
        ico = {"promising": "+", "failed": "-", "marginal": "~"}
        lines = ["<history>"] + [
            f"[{ico.get(v,'?')}] {c[:280].strip()}" for c, v in rows
        ] + ["</history>"]
        return "\n".join(lines)
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# 3. Strategy generation
# ─────────────────────────────────────────────────────────────────────────────

_SYS = """\
You are a quant strategy assistant. Generate a robust, low-drawdown strategy.

Step 1 — 2-4 sentence rationale (regime fit, why low drawdown).
Step 2 — ```json config: {"ticker","timeframe","sl_mult","tp_mult",
  "active_hours","risk_per_trade","direction"}
Step 3 — ```python agent_fn(df, ind=None):
  Columns: Open,High,Low,Close,Volume,ATR14,RSI14,EMA50,EMA200,
  RollHigh6,RollLow6,garch_h,garch_regime,size_mult,ret,hour,dow.
  ind helper: ind("EMA",20), ind("RSI",14), ind("BB",20,2.0), etc.
  Must set df["signal"] (1/-1/0), df["SL_dist"], df["TP_dist"].
  NEVER use garch_regime as a per-bar entry gate (lookahead risk).
  Minimise drawdown: prefer mean-reversion on sideways, trend-follow on trends.
"""


def generate_strategy(
    ticker: str, tf: str, df: pd.DataFrame, iteration: int, history: str
) -> tuple[str, dict, str]:
    if not ANTHROPIC_KEY:
        name, code, sl, tp = get_archetype(iteration)
        config = {
            "ticker": ticker, "timeframe": tf,
            "sl_mult": sl, "tp_mult": tp,
            "active_hours": _active_hours(tf),
            "risk_per_trade": 1.0, "direction": "ALL",
        }
        return f"[{name}] SL={sl}x TP={tp}x", config, code

    import anthropic
    import re

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY, timeout=90.0)

    brain = ""
    try:
        from api.routers.brain import get_brain_context
        brain = get_brain_context(f"trading strategy {ticker} {tf}", asset=ticker) or ""
    except Exception:
        pass

    user = (
        f"Iteration {iteration}\n\nAsset stats:\n{_asset_stats(df, ticker, tf)}\n\n"
        + (f"Prior lessons:\n{history}\n\n" if history else "")
        + "Generate a creative strategy. Vary signal logic, regime filter, direction. "
          "PRIMARY goal: minimise max drawdown while keeping Sharpe ≥ 1.5."
    )

    resp = client.messages.create(
        model="claude-opus-4-7", max_tokens=2000,
        system=(brain + "\n\n" if brain else "") + _SYS,
        messages=[{"role": "user", "content": user}],
    )
    text = resp.content[0].text

    config: dict = {}
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            config = json.loads(m.group(1))
        except Exception:
            pass
    if not config:
        config = {"ticker": ticker, "timeframe": tf, "sl_mult": 2.0, "tp_mult": 4.0,
                  "active_hours": _active_hours(tf), "risk_per_trade": 1.0, "direction": "ALL"}

    code = ""
    m2 = re.search(r"```python\s*(.*?)\s*```", text, re.DOTALL)
    if m2:
        code = m2.group(1).strip()

    config.setdefault("active_hours", _active_hours(tf))
    return text[:400].strip(), config, code


# ─────────────────────────────────────────────────────────────────────────────
# 4. Backtest / persist / evaluate
# ─────────────────────────────────────────────────────────────────────────────

def save_strategy(name: str, config: dict, code: str) -> str:
    sid = str(uuid.uuid4())[:8]
    get_conn().execute(
        "INSERT INTO strategies (id,name,strategy_type,config,code,status) VALUES (?,?,?,?,?,?)",
        [sid, name, "vibe_loop", json.dumps(config), code, "research"],
    )
    return sid


def run_backtest(df: pd.DataFrame, config: dict, code: str) -> dict:
    df_ind = compute_indicators_v2(df, fit_garch=True)

    sl   = float(config.get("sl_mult", 2.0))
    tp   = float(config.get("tp_mult", 5.0))
    risk = float(config.get("risk_per_trade", 1.0))
    if risk > 0.1:
        risk /= 100.0
    cfg = {
        "sl_mult":        sl,
        "tp_mult":        tp,
        "active_hours":   list(config.get("active_hours", [6, 22])),
        "commission":     float(config.get("commission", 0.0004)),
        "slippage":       float(config.get("slippage", 0.0001)),
        "risk_per_trade": risk,
    }

    if code and code.strip():
        try:
            ns: dict = {}
            exec(compile(code, "<agent_fn>", "exec"), ns)
            if "agent_fn" in ns:
                cfg["agent_fn"] = ns["agent_fn"]
        except Exception as e:
            print(f"  agent_fn compile error: {e}")

    dirn     = config.get("direction", "ALL")
    versions = run_versions(df_ind, cfg, direction=dirn)

    wfo_rows: list = []
    try:
        wfo_df   = run_wfo(df_ind, cfg, direction=dirn)
        wfo_rows = wfo_df.to_dict("records") if not wfo_df.empty else []
    except Exception as e:
        print(f"  WFO skipped: {e}")

    best_key = "V_Agent" if ("V_Agent" in versions and "metrics" in versions.get("V_Agent", {})) \
               else next((k for k in versions if "metrics" in versions[k]), "")

    return {
        "metrics":      {k: v["metrics"] for k, v in versions.items() if "metrics" in v},
        "best_key":     best_key,
        "best_metrics": versions.get(best_key, {}).get("metrics", {}),
        "wfo":          wfo_rows,
        "_df_ind":      df_ind,
    }


def save_run(run_id: str, sid: str, ticker: str, tf: str, config: dict, result: dict) -> None:
    conn   = get_conn()
    params = {**config, "_strategy_id": sid}
    conn.execute(
        "INSERT INTO runs (id,name,ticker,timeframe,params,status,strategy_id) VALUES (?,?,?,?,?,?,?)",
        [run_id, f"vibe_{run_id}", ticker, tf, json.dumps(params), "done", sid],
    )
    mj = json.dumps(result.get("metrics", {}))
    wj = json.dumps(result.get("wfo", []))
    if conn.execute("SELECT 1 FROM run_results WHERE run_id=?", [run_id]).fetchone():
        conn.execute(
            "UPDATE run_results SET metrics=?,equity=?,trades=?,wfo=?,sweep=?,mc=? WHERE run_id=?",
            [mj, "[]", "[]", wj, "[]", "{}", run_id],
        )
    else:
        conn.execute(
            "INSERT INTO run_results (run_id,metrics,equity,trades,wfo,sweep,mc) VALUES (?,?,?,?,?,?,?)",
            [run_id, mj, "[]", "[]", wj, "[]", "{}"],
        )


def evaluate(result: dict, stop_sharpe: float, max_dd: float) -> tuple[float, float, str]:
    """Return (sharpe, max_drawdown_pct, verdict)."""
    m      = result.get("best_metrics", {})
    sharpe = float(m.get("sharpe_ratio", 0) or 0)
    dd     = float(m.get("max_drawdown_pct", -999) or -999)  # stored negative
    dd_ok  = abs(dd) <= max_dd
    verdict = (
        "ROBUST"   if sharpe >= stop_sharpe and dd_ok else
        "marginal" if sharpe >= 0.5                   else
        "failed"
    )
    return sharpe, dd, verdict


# ─────────────────────────────────────────────────────────────────────────────
# 5. Main
# ─────────────────────────────────────────────────────────────────────────────

def _promote_strategy(sid: str, status: str) -> None:
    """Mark strategy as starred and update its status in the library."""
    try:
        get_conn().execute(
            "UPDATE strategies SET starred=TRUE, status=? WHERE id=?",
            [status, sid],
        )
        print(f"  [library] strategy {sid} → starred, status={status}")
    except Exception as e:
        print(f"  [library] promote failed: {e}")


def _print_table(log: list[dict]) -> None:
    if not log:
        return
    hdr = f"  {'I':>3} {'TF':>3} {'Archetype':<22} {'Sharpe':>7} {'CAGR%':>6} {'DD%':>7} {'N':>5} {'WR%':>5}  Verdict"
    print("\n" + hdr)
    print("  " + "─" * (len(hdr) - 2))
    for r in log:
        flag = " ★" if r["verdict"] == "ROBUST" else (" ·" if r["verdict"] == "marginal" else "")
        print(
            f"  {r['iter']:>3} {r['tf']:>3} {r['arch']:<22} "
            f"{r['sharpe']:>+7.3f} {r['cagr']:>6.1f} {r['dd']:>7.1f} "
            f"{r['n_trades']:>5} {r['win']:>5.1f}  {r['verdict']}{flag}"
        )


def main() -> dict:
    p = argparse.ArgumentParser(description="Multi-TF strategy optimization loop")
    p.add_argument("--ticker",      default="BTC-USD")
    p.add_argument("--timeframes",  default="1h,4h,1d",
                   help="Comma-separated. Sub-hourly (1min/5min/15min) need tick data → skipped.")
    p.add_argument("--max-iter",    type=int,   default=100)
    p.add_argument("--stop-sharpe", type=float, default=1.5)
    p.add_argument("--max-dd",      type=float, default=20.0,
                   help="Max acceptable drawdown %% (abs). Default 20.")
    args = p.parse_args()

    ticker      = args.ticker
    stop_sharpe = args.stop_sharpe
    max_dd      = args.max_dd
    max_iter    = args.max_iter

    requested = [t.strip() for t in args.timeframes.split(",")]
    skipped   = [t for t in requested if t in _SUB_HOURLY]
    avail     = [t for t in requested if t not in _SUB_HOURLY]

    if not avail:
        print("ERROR: no supported timeframes. Sub-hourly needs tick data (1min/5min/15min).")
        sys.exit(1)

    print(f"\n{'='*70}")
    print(f"  Multi-TF Vibe Loop  |  {ticker}")
    print(f"  Timeframes : {avail}" +
          (f"   (skipped sub-hourly={skipped}: need tick data)" if skipped else ""))
    print(f"  Stop       : Sharpe ≥ {stop_sharpe}  AND  MaxDD ≤ {max_dd}%")
    print(f"  Max iters  : {max_iter}   Archetypes: 12 × 9 SL/TP = 108 baseline combos")
    print(f"  API key    : {'✓ set (Claude will generate)' if ANTHROPIC_KEY else '✗ not set (archetype library)'}")
    print(f"{'='*70}\n")

    print("[*] Loading data...")
    # native_tf = the smallest requested tf (bars already in DuckDB)
    native_tf = avail[0]
    df_native = load_bars(ticker, native_tf)
    tf_data: dict[str, pd.DataFrame] = {native_tf: df_native}
    for tf in avail:
        if tf != native_tf:
            tf_data[tf] = resample(df_native, tf)

    best_sharpe = float("-inf")
    best_sid    = None
    best_tf_    = None
    log: list[dict] = []

    for iteration in range(1, max_iter + 1):
        tf   = avail[(iteration - 1) % len(avail)]
        df   = tf_data[tf]
        name, _, sl_used, tp_used = get_archetype(iteration)

        print(f"\n{'─'*70}")
        print(f"  [{iteration:>3}/{max_iter}]  {tf}  |  arch={name}  SL={sl_used}x TP={tp_used}x")
        print(f"{'─'*70}")

        history = _brain_history(ticker)
        if history:
            print(f"  [brain] {len(history)} chars")

        try:
            expl, config, code = generate_strategy(ticker, tf, df, iteration, history)
        except Exception as e:
            print(f"  gen failed: {e}")
            continue
        print(f"  {expl[:110]}")
        config["active_hours"] = _active_hours(tf)  # enforce correct hours per tf

        sid = save_strategy(f"vibe_{iteration:03d}_{tf}_{ticker.replace('-','_')}", config, code)
        print(f"  sid={sid}")

        try:
            result = run_backtest(df, config, code)
        except Exception as e:
            import traceback
            print(f"  backtest failed: {e}")
            traceback.print_exc()
            continue

        run_id = uuid.uuid4().hex[:12]
        try:
            save_run(run_id, sid, ticker, tf, config, result)
        except Exception as e:
            print(f"  run save failed: {e}")

        try:
            from api.routers.learning import save_run_lesson
            save_run_lesson(
                run_id=run_id, asset=ticker, timeframe=tf,
                strategy_code=code, params=dict(config),
                all_metrics=result.get("metrics", {}),
                wfo_folds=result.get("wfo", []),
                df_ind=result.get("_df_ind"),
            )
        except Exception:
            pass

        sharpe, dd, verdict = evaluate(result, stop_sharpe, max_dd)
        m     = result.get("best_metrics", {})
        cagr  = float(m.get("cagr_pct", 0))
        n_tr  = int(m.get("n_trades", 0))
        win   = float(m.get("win_rate_pct", 0))

        log.append({"iter": iteration, "tf": tf, "arch": name, "sid": sid,
                    "sharpe": round(sharpe, 3), "cagr": round(cagr, 1),
                    "dd": round(dd, 1), "n_trades": n_tr,
                    "win": round(win, 1), "verdict": verdict})

        print(
            f"  Sharpe={sharpe:+.3f}  CAGR={cagr:.1f}%  DD={dd:.1f}%  "
            f"N={n_tr}  WR={win:.1f}%  [{verdict}]"
        )

        if sharpe > best_sharpe:
            best_sharpe, best_sid, best_tf_ = sharpe, sid, tf

        if verdict == "ROBUST":
            _promote_strategy(sid, "live")
            print(f"\n{'='*70}")
            print(f"  ★  ROBUST STRATEGY FOUND  ★")
            print(f"  Iteration {iteration}  |  {tf}  |  strategy={sid}")
            print(f"  Sharpe={sharpe:.3f}  MaxDD={dd:.1f}%")
            print(f"{'='*70}")
            _print_table(log)
            return {"verdict": "ROBUST", "sid": sid, "tf": tf,
                    "sharpe": sharpe, "dd": dd, "log": log}

    if best_sid:
        _promote_strategy(best_sid, "marginal")
    print(f"\n{'='*70}")
    print(f"  Loop complete — {max_iter} iterations, no ROBUST strategy found.")
    print(f"  Best Sharpe: {best_sharpe:.3f}  strategy={best_sid}  tf={best_tf_}")
    print(f"{'='*70}")
    _print_table(log)
    return {"verdict": "none", "sid": best_sid, "tf": best_tf_,
            "sharpe": best_sharpe, "dd": None, "log": log}


if __name__ == "__main__":
    main()
