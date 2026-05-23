#!/usr/bin/env python3
"""
scripts/vibe_loop.py
====================
Iterative strategy generation + backtest loop.
Generates strategies via Claude (or a hard-coded baseline when no API key is
set), backtests them in-process, saves lessons to brain_chunks, and iterates
until finding a robust strategy (Sharpe > 1.5, WFO eff > 0.6) or exhausting
MAX_ITER attempts.

Usage:
    cd /home/user/crypto1
    python scripts/vibe_loop.py [--ticker BTC-USD] [--timeframe 1h] [--max-iter 8]

Environment:
    ANTHROPIC_API_KEY  — optional; omit to use the hard-coded baseline strategy.
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

# ── Path setup — allow running from any cwd ────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from api.db import get_conn
from engine.strategy_core import compute_indicators_v2, compute_metrics
from engine.backtest import run_versions, run_wfo, INITIAL_CAPITAL

# ── Stop criteria & global limits ─────────────────────────────────────────────
STOP_SHARPE  = 1.5
STOP_WFO_EFF = 0.6
MAX_ITER     = 8

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ─────────────────────────────────────────────────────────────────────────────
# 1. Data loading — DuckDB then CSV fallback
# ─────────────────────────────────────────────────────────────────────────────

_TICKER_CSV_MAP = {
    "BTC-USD": "btc_hourly.csv",
    "ETH-USD": "eth_hourly.csv",
    "SOL-USD": "sol_hourly.csv",
}

_CSV_DIR = os.path.join(_ROOT, "archive", "btc_analysis", "output")


def _seed_from_csv(ticker: str) -> pd.DataFrame | None:
    """Load a cached CSV from archive and insert rows into DuckDB assets table."""
    fname = _TICKER_CSV_MAP.get(ticker)
    if not fname:
        return None
    fpath = os.path.join(_CSV_DIR, fname)
    if not os.path.exists(fpath):
        return None
    print(f"  Seeding DuckDB from {fname}...")
    df = pd.read_csv(fpath, parse_dates=["Date"])
    df = df.rename(columns={"Date": "ts", "Open": "open", "High": "high",
                             "Low": "low", "Close": "close", "Volume": "volume"})
    df["ticker"] = ticker
    df["source"] = "csv_archive"
    conn = get_conn()
    inserted = 0
    for row in df.itertuples(index=False):
        try:
            conn.execute(
                "INSERT OR IGNORE INTO assets (ticker, source, ts, open, high, low, close, volume) "
                "VALUES (?,?,?,?,?,?,?,?)",
                [row.ticker, row.source, row.ts,
                 row.open, row.high, row.low, row.close, row.volume],
            )
            inserted += 1
        except Exception:
            pass
    print(f"  Inserted {inserted} rows for {ticker}")
    return None  # caller will re-query


def load_ohlcv(ticker: str, timeframe: str) -> pd.DataFrame:
    """
    Load bars from DuckDB.  If the table is empty for this ticker, attempt to
    seed it from the local CSV archive before raising.
    """
    conn = get_conn()

    def _query() -> list:
        return conn.execute(
            "SELECT ts, open, high, low, close, volume FROM assets "
            "WHERE ticker=? ORDER BY ts",
            [ticker],
        ).fetchall()

    rows = _query()
    if not rows:
        _seed_from_csv(ticker)
        rows = _query()

    if not rows:
        raise RuntimeError(
            f"No OHLCV data for '{ticker}' in DuckDB and no local CSV fallback found.\n"
            f"Fetch data first via the Assets screen or /assets endpoint, "
            f"or place a CSV in {_CSV_DIR}."
        )

    df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    print(
        f"  Loaded {len(df):,} bars for {ticker} "
        f"({df.index[0].date()} -> {df.index[-1].date()})"
    )
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 2. Utility helpers
# ─────────────────────────────────────────────────────────────────────────────

def _compute_hurst(prices: np.ndarray) -> float:
    """R/S Hurst exponent — no external dependency."""
    prices = prices[np.isfinite(prices) & (prices > 0)]
    if len(prices) < 50:
        return 0.5
    try:
        log_p = np.log(prices)
        n     = len(log_p)
        lags  = [max(2, n // k) for k in [8, 4, 2]]
        rs_vals, lag_vals = [], []
        for lag in lags:
            series = log_p[:lag]
            dev = np.cumsum(series - series.mean())
            r   = dev.max() - dev.min()
            s   = series.std()
            if s > 0:
                rs_vals.append(math.log(r / s))
                lag_vals.append(math.log(lag))
        if len(rs_vals) >= 2:
            h = float(np.polyfit(lag_vals, rs_vals, 1)[0])
            return max(0.1, min(0.9, h))
    except Exception:
        pass
    return 0.5


def _build_asset_stats(df: pd.DataFrame, ticker: str, timeframe: str) -> str:
    """Compact asset statistics string for the Claude prompt."""
    rets    = np.diff(np.log(df["Close"].values))
    rets    = rets[np.isfinite(rets)]
    ann_f   = 24 * 365  # hourly annualisation factor
    ann_vol = float(np.std(rets) * np.sqrt(ann_f) * 100)
    mean_r  = float(np.mean(rets) * ann_f * 100)
    sharpe  = mean_r / ann_vol if ann_vol > 0 else 0.0
    hurst   = _compute_hurst(df["Close"].values)
    regime  = (
        "trending"       if hurst > 0.55 else
        "mean-reverting" if hurst < 0.45 else
        "random-walk"
    )
    return (
        f"Asset: {ticker}  Timeframe: {timeframe}  Bars: {len(df):,}\n"
        f"Ann.vol: {ann_vol:.1f}%  Est.CAGR: {mean_r:.1f}%  Est.Sharpe: {sharpe:.2f}\n"
        f"Hurst: {hurst:.3f} ({regime})\n"
        f"Period: {df.index[0].date()} -> {df.index[-1].date()}"
    )


def _get_history_summary(ticker: str, timeframe: str) -> str:
    """Fetch the most recent empirical lessons from brain_chunks."""
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT content, verdict FROM brain_chunks "
            "WHERE source='empirical' AND asset=? "
            "ORDER BY synced_at DESC LIMIT 5",
            [ticker],
        ).fetchall()
        if not rows:
            return ""
        lines = ["<strategy_history>"]
        for content, verdict in rows:
            icon = "+" if verdict == "promising" else ("-" if verdict == "failed" else "~")
            lines.append(f"[{icon}] {content[:350].strip()}")
        lines.append("</strategy_history>")
        return "\n".join(lines)
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# 3. Strategy generation via Claude (with hard-coded baseline fallback)
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a quantitative trading strategy assistant for the Pareto Terminal.
Analyse the asset statistics and generate a robust, profitable trading strategy.

Step 1 — Brief explanation (2-4 sentences) of why this strategy fits the asset regime.

Step 2 — JSON config in a ```json block:
{
  "ticker": "BTC-USD",
  "timeframe": "1h",
  "sl_mult": 2.0,
  "tp_mult": 4.0,
  "active_hours": [6, 22],
  "risk_per_trade": 1.0,
  "direction": "ALL"
}

Step 3 — Python agent_fn in a ```python block.
The function receives:
  df (DataFrame) with columns: Open, High, Low, Close, Volume, ATR14, RSI14,
  EMA50, EMA200, RollHigh6, RollLow6, garch_h, garch_regime, size_mult, ret, hour, dow.
  ind helper: ind("EMA", 20), ind("BB", 20, 2.0), ind("ATR", 14), ind("VWAP"), etc.
Must return df with columns: signal (1/-1/0), SL_dist, TP_dist (absolute price distances).
Rules:
- Use only pandas / numpy (no external libraries).
- Keep the function self-contained.
- DO NOT use garch_regime as a bar-by-bar entry signal (lookahead risk).
- SL_dist and TP_dist must be absolute price distances, e.g. df["ATR14"] * 2.0.
"""


def _baseline_strategy(ticker: str, timeframe: str, iteration: int) -> tuple[str, dict, str]:
    """Deterministic fallback used when ANTHROPIC_API_KEY is absent."""
    sl = round(1.5 + iteration * 0.3, 2)
    tp = round(3.0 + iteration * 0.5, 2)
    config = {
        "ticker": ticker, "timeframe": timeframe,
        "sl_mult": sl, "tp_mult": tp,
        "active_hours": [6, 22],
        "risk_per_trade": 1.0,
        "direction": "ALL",
    }
    code = f"""import pandas as pd
import numpy as np

def agent_fn(df: pd.DataFrame, ind=None) -> pd.DataFrame:
    df = df.copy()
    ema_fast  = df["EMA50"]
    ema_slow  = df["EMA200"]
    rsi       = df["RSI14"]
    trend_up  = ema_fast > ema_slow
    trend_dn  = ema_fast < ema_slow
    bo_long   = df["Close"] > df["RollHigh6"]
    bo_short  = df["Close"] < df["RollLow6"]
    df["signal"] = 0
    df.loc[bo_long  & trend_up & (rsi < 70), "signal"] =  1
    df.loc[bo_short & trend_dn & (rsi > 30), "signal"] = -1
    df["SL_dist"] = df["ATR14"] * {sl}
    df["TP_dist"] = df["ATR14"] * {tp}
    return df
"""
    explanation = (
        f"Baseline breakout strategy (iteration {iteration}): "
        f"EMA trend filter + 6-bar channel breakout + RSI extremes guard. "
        f"SL={sl}xATR, TP={tp}xATR."
    )
    return explanation, config, code


def generate_strategy(
    ticker: str,
    timeframe: str,
    df: pd.DataFrame,
    iteration: int,
    prev_lessons: str,
) -> tuple[str, dict, str]:
    """
    Call Claude to generate a strategy.
    Returns (explanation, config, code).
    Falls back to hard-coded baseline if ANTHROPIC_API_KEY is missing.
    """
    if not ANTHROPIC_KEY:
        print("  [No ANTHROPIC_API_KEY — using baseline strategy]")
        return _baseline_strategy(ticker, timeframe, iteration)

    import anthropic
    import re

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY, timeout=90.0)

    asset_stats = _build_asset_stats(df, ticker, timeframe)

    # Fetch brain context (theory + empirical lessons via semantic search)
    brain_ctx = ""
    try:
        from api.routers.brain import get_brain_context
        brain_ctx = get_brain_context(
            f"trading strategy {ticker} {timeframe}",
            asset=ticker,
        ) or ""
    except Exception:
        pass

    user_content = (
        f"Iteration {iteration} — generate a new trading strategy.\n\n"
        f"Asset statistics:\n{asset_stats}\n\n"
        + (f"Previous run lessons (learn from these):\n{prev_lessons}\n\n" if prev_lessons else "")
        + "Generate a strategy that addresses any weaknesses shown in previous runs. "
          "Be creative: vary entry logic, regime filters, and directional bias each iteration."
    )

    system = (brain_ctx + "\n\n" if brain_ctx else "") + _SYSTEM_PROMPT

    resp = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    full_text = resp.content[0].text

    # Extract config
    config: dict = {}
    m = re.search(r"```json\s*(\{.*?\})\s*```", full_text, re.DOTALL)
    if m:
        try:
            config = json.loads(m.group(1))
        except Exception:
            pass
    if not config:
        config = {
            "ticker": ticker, "timeframe": timeframe,
            "sl_mult": 2.0, "tp_mult": 4.0,
            "active_hours": [6, 22], "risk_per_trade": 1.0, "direction": "ALL",
        }

    # Extract code
    code = ""
    m2 = re.search(r"```python\s*(.*?)\s*```", full_text, re.DOTALL)
    if m2:
        code = m2.group(1).strip()

    explanation = full_text[:400].strip()
    return explanation, config, code


# ─────────────────────────────────────────────────────────────────────────────
# 4. Strategy save
# ─────────────────────────────────────────────────────────────────────────────

def save_strategy(name: str, config: dict, code: str) -> str:
    """Persist strategy to DuckDB and return its ID."""
    conn = get_conn()
    sid  = str(uuid.uuid4())[:8]
    conn.execute(
        "INSERT INTO strategies (id, name, strategy_type, config, code, status) "
        "VALUES (?,?,?,?,?,?)",
        [sid, name, "vibe_loop", json.dumps(config), code, "research"],
    )
    return sid


# ─────────────────────────────────────────────────────────────────────────────
# 5. Backtest pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_backtest(df: pd.DataFrame, config: dict, code: str) -> dict:
    """
    Full pipeline: indicators -> versions (V1/V2/V4/V_Agent) -> WFO.
    Returns a result dict suitable for evaluate() and save_run().
    """
    print("  Computing indicators...")
    df_ind = compute_indicators_v2(df, fit_garch=True)

    # Normalise config values
    sl   = float(config.get("sl_mult",        2.0))
    tp   = float(config.get("tp_mult",        5.0))
    hrs  = list(config.get("active_hours",    [6, 22]))
    comm = float(config.get("commission",     0.0004))
    slip = float(config.get("slippage",       0.0001))
    risk = float(config.get("risk_per_trade", 1.0))
    if risk > 0.1:   # normalise % -> decimal
        risk /= 100.0
    dirn = config.get("direction", "ALL")

    cfg: dict = {
        "sl_mult":        sl,
        "tp_mult":        tp,
        "active_hours":   hrs,
        "commission":     comm,
        "slippage":       slip,
        "risk_per_trade": risk,
    }

    # Compile and inject agent_fn
    if code and code.strip():
        try:
            ns: dict = {}
            exec(compile(code, "<agent_fn>", "exec"), ns)
            if "agent_fn" in ns:
                cfg["agent_fn"] = ns["agent_fn"]
                print("  agent_fn compiled OK")
            else:
                print("  Warning: code compiled but agent_fn not found in namespace")
        except Exception as exc:
            print(f"  Warning: agent_fn compile failed: {exc}")

    print("  Running versions (V1 / V2 / V4 / V_Agent)...")
    versions = run_versions(df_ind, cfg, direction=dirn)

    print("  Running WFO...")
    try:
        wfo_df   = run_wfo(df_ind, cfg, direction=dirn)
        wfo_rows = wfo_df.to_dict("records") if not wfo_df.empty else []
    except Exception as exc:
        print(f"  WFO error (non-blocking): {exc}")
        wfo_rows = []

    # Identify best version key
    best_key = "V_Agent" if "V_Agent" in versions and "metrics" in versions["V_Agent"] \
               else "V4 +GARCH+Costi"
    if best_key not in versions or "metrics" not in versions.get(best_key, {}):
        # Fallback to whatever has metrics
        for k in versions:
            if "metrics" in versions[k]:
                best_key = k
                break

    metrics_out = {k: v["metrics"] for k, v in versions.items() if "metrics" in v}
    best_m      = metrics_out.get(best_key, {})

    return {
        "metrics":      metrics_out,
        "best_key":     best_key,
        "best_metrics": best_m,
        "wfo":          wfo_rows,
        "_df_ind":      df_ind,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Run persistence
# ─────────────────────────────────────────────────────────────────────────────

def save_run(
    run_id: str,
    strategy_id: str,
    ticker: str,
    timeframe: str,
    config: dict,
    result: dict,
) -> None:
    """Persist run record and run_results to DuckDB."""
    conn   = get_conn()
    params = dict(config)
    params["_strategy_id"] = strategy_id

    conn.execute(
        "INSERT INTO runs (id, name, ticker, timeframe, params, status, strategy_id) "
        "VALUES (?,?,?,?,?,?,?)",
        [run_id, f"vibe_loop_{run_id}", ticker, timeframe,
         json.dumps(params), "done", strategy_id],
    )

    existing = conn.execute(
        "SELECT run_id FROM run_results WHERE run_id=?", [run_id]
    ).fetchone()

    metrics_json = json.dumps(result.get("metrics", {}))
    wfo_json     = json.dumps(result.get("wfo", []))

    if existing:
        conn.execute(
            "UPDATE run_results SET metrics=?, equity=?, trades=?, wfo=?, sweep=?, mc=? "
            "WHERE run_id=?",
            [metrics_json, "[]", "[]", wfo_json, "[]", "{}", run_id],
        )
    else:
        conn.execute(
            "INSERT INTO run_results (run_id, metrics, equity, trades, wfo, sweep, mc) "
            "VALUES (?,?,?,?,?,?,?)",
            [run_id, metrics_json, "[]", "[]", wfo_json, "[]", "{}"],
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Evaluation
# ─────────────────────────────────────────────────────────────────────────────

def evaluate(result: dict) -> tuple[float, float | None, str]:
    """
    Returns (sharpe, wfo_efficiency, verdict).
    verdict is one of: 'ROBUST', 'marginal', 'failed'.
    """
    best_m = result.get("best_metrics", {})
    sharpe = float(best_m.get("sharpe_ratio", 0) or 0)

    wfo_eff: float | None = None
    wfo = result.get("wfo", [])
    if wfo:
        effs = [
            float(r.get("efficiency_factor", 0) or 0)
            for r in wfo
            if r.get("efficiency_factor") is not None
        ]
        wfo_eff = round(float(np.mean(effs)), 3) if effs else None

    wfo_ok  = wfo_eff is None or wfo_eff >= STOP_WFO_EFF
    verdict = (
        "ROBUST"   if sharpe >= STOP_SHARPE and wfo_ok else
        "marginal" if sharpe > 0.5                      else
        "failed"
    )
    return sharpe, wfo_eff, verdict


# ─────────────────────────────────────────────────────────────────────────────
# 8. Main loop
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Iterative strategy generation + backtest loop"
    )
    parser.add_argument("--ticker",    default="BTC-USD", help="Asset ticker")
    parser.add_argument("--timeframe", default="1h",      help="Timeframe string")
    parser.add_argument("--max-iter",  type=int, default=MAX_ITER,
                        help="Maximum loop iterations")
    args = parser.parse_args()

    ticker    = args.ticker
    timeframe = args.timeframe
    max_iter  = args.max_iter

    print(f"\n{'='*62}")
    print(f"  Vibe Strategy Loop  |  {ticker}  {timeframe}")
    print(f"  Stop criteria : Sharpe >= {STOP_SHARPE}  AND  WFO eff >= {STOP_WFO_EFF}")
    print(f"  Max iterations: {max_iter}")
    print(f"  API key       : {'set' if ANTHROPIC_KEY else 'NOT set (baseline fallback)'}")
    print(f"{'='*62}\n")

    # ── Step 1: load data ────────────────────────────────────────────────────
    print("[1] Loading OHLCV data...")
    try:
        df = load_ohlcv(ticker, timeframe)
    except RuntimeError as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)

    # ── Iteration loop ───────────────────────────────────────────────────────
    best_sharpe      = float("-inf")
    best_strategy_id = None
    best_result      = None

    for iteration in range(1, max_iter + 1):
        print(f"\n{'─'*62}")
        print(f"  ITERATION {iteration} / {max_iter}")
        print(f"{'─'*62}")

        # Gather prior lessons for context
        prev_lessons = _get_history_summary(ticker, timeframe)
        if prev_lessons:
            print(f"  Brain context: {len(prev_lessons)} chars of lessons loaded")

        # ── 2: Generate strategy ─────────────────────────────────────────────
        print(f"\n[{iteration}.1] Generating strategy...")
        try:
            explanation, config, code = generate_strategy(
                ticker, timeframe, df, iteration, prev_lessons
            )
        except Exception as exc:
            print(f"  Strategy generation failed: {exc}")
            continue

        print(f"  Rationale : {explanation[:120].strip()}...")
        print(
            f"  Config    : SL={config.get('sl_mult')}x  TP={config.get('tp_mult')}x  "
            f"dir={config.get('direction')}  risk={config.get('risk_per_trade')}%  "
            f"hours={config.get('active_hours')}"
        )

        # ── 3: Save strategy ─────────────────────────────────────────────────
        strat_name   = f"vibe_loop_iter{iteration}_{ticker.replace('-','_')}"
        strategy_id  = save_strategy(strat_name, config, code)
        print(f"  Strategy ID: {strategy_id}")

        # ── 4: Run backtest ──────────────────────────────────────────────────
        print(f"\n[{iteration}.2] Running backtest...")
        try:
            result = run_backtest(df, config, code)
        except Exception as exc:
            import traceback
            print(f"  Backtest failed: {exc}")
            traceback.print_exc()
            continue

        # ── 5: Persist run ───────────────────────────────────────────────────
        run_id = uuid.uuid4().hex[:12]
        config_with_ref = dict(config)
        config_with_ref["_strategy_id"] = strategy_id
        try:
            save_run(run_id, strategy_id, ticker, timeframe, config_with_ref, result)
            print(f"  Run ID     : {run_id}")
        except Exception as exc:
            print(f"  Run save failed (non-blocking): {exc}")

        # ── 6: Save lesson ───────────────────────────────────────────────────
        print(f"\n[{iteration}.3] Saving lesson to brain_chunks...")
        try:
            from api.routers.learning import save_run_lesson
            save_run_lesson(
                run_id        = run_id,
                asset         = ticker,
                timeframe     = timeframe,
                strategy_code = code,
                params        = config_with_ref,
                all_metrics   = result.get("metrics", {}),
                wfo_folds     = result.get("wfo", []),
                df_ind        = result.get("_df_ind"),
            )
            print("  Lesson saved OK")
        except Exception as exc:
            print(f"  Lesson save failed (non-blocking): {exc}")

        # ── 7: Evaluate ──────────────────────────────────────────────────────
        sharpe, wfo_eff, verdict = evaluate(result)
        best_m = result.get("best_metrics", {})

        print(f"\n[{iteration}.4] Results  (version: {result.get('best_key', '?')})")
        print(f"  Sharpe   : {sharpe:.3f}  (target >= {STOP_SHARPE})")
        print(f"  CAGR     : {float(best_m.get('cagr_pct', 0)):.1f}%")
        print(f"  Max DD   : {float(best_m.get('max_drawdown_pct', 0)):.1f}%")
        print(f"  N trades : {int(best_m.get('n_trades', 0))}")
        print(f"  Win rate : {float(best_m.get('win_rate_pct', 0)):.1f}%")
        if wfo_eff is not None:
            print(f"  WFO eff  : {wfo_eff:.3f}  (target >= {STOP_WFO_EFF})")
        else:
            print("  WFO eff  : n/a")
        print(f"  Verdict  : {verdict}")

        if sharpe > best_sharpe:
            best_sharpe      = sharpe
            best_strategy_id = strategy_id
            best_result      = result

        if verdict == "ROBUST":
            print(f"\n{'='*62}")
            print(f"  ROBUST STRATEGY FOUND at iteration {iteration}")
            print(f"  Strategy ID : {strategy_id}")
            print(f"  Sharpe      : {sharpe:.3f}")
            if wfo_eff is not None:
                print(f"  WFO eff     : {wfo_eff:.3f}")
            print(f"{'='*62}")
            return

    # Loop exhausted without a robust result
    print(f"\n{'='*62}")
    print(f"  Loop completed ({max_iter} iterations — no robust strategy found)")
    print(f"  Best Sharpe so far : {best_sharpe:.3f}  (strategy: {best_strategy_id})")
    if best_sharpe < STOP_SHARPE:
        print("  Tip: review brain_chunks for accumulated lessons and retry.")
    print(f"{'='*62}")


if __name__ == "__main__":
    main()
