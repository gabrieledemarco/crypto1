"""
api/routers/learning.py
=======================
Post-run knowledge extraction. Called after every completed backtest.
Saves a structured lesson to brain_chunks for future Vibe generations.
"""
import json
import re
import uuid
import numpy as np
import pandas as pd

from api.db import get_conn


# ── Strategy type inference ────────────────────────────────────────────────────

_PATTERNS = {
    "ema_crossover":      [r"EMA50.*EMA200", r"ema200", r"golden.?cross", r"death.?cross"],
    "breakout":           [r"RollHigh", r"RollLow", r"breakout", r"resistance.*break", r"support.*break"],
    "rsi_reversion":      [r"RSI.*[<>].*[234][05]", r"oversold", r"overbought"],
    "bollinger_reversion": [r"BBupper", r"BBlower", r"bollinger", r"\bBB\b"],
    "momentum":           [r"\bmomentum\b", r"\bROC\b", r"rate.of.change"],
    "macd":               [r"\bMACD\b", r"\bmacd\b"],
    "vwap":               [r"\bVWAP\b", r"\bvwap\b"],
}

def infer_strategy_type(code: str) -> str:
    if not code:
        return "custom"
    for name, patterns in _PATTERNS.items():
        if any(re.search(p, code, re.IGNORECASE) for p in patterns):
            return name
    return "custom"


# ── Verdict classification ─────────────────────────────────────────────────────

def compute_verdict(all_metrics: dict, wfo_folds: list) -> str:
    """promising / marginal / failed based on Sharpe + WFO efficiency."""
    best_key = "V_Agent" if "V_Agent" in all_metrics else "V4 +GARCH+Costi"
    if best_key not in all_metrics and all_metrics:
        best_key = next(iter(all_metrics))
    m = all_metrics.get(best_key, {})
    sharpe = float(m.get("sharpe_ratio", 0) or 0)

    wfo_eff = None
    if wfo_folds:
        effs = [float(f.get("efficiency_factor", 0) or 0) for f in wfo_folds
                if f.get("efficiency_factor") is not None]
        wfo_eff = float(np.mean(effs)) if effs else None

    if sharpe > 1.5 and (wfo_eff is None or wfo_eff > 0.6):
        return "promising"
    if sharpe > 0.5:
        return "marginal"
    return "failed"


# ── Regime vector extraction ───────────────────────────────────────────────────

def _compute_hurst_rs(prices: np.ndarray) -> float:
    """Simple R/S Hurst estimator — no external library needed."""
    prices = np.asarray(prices, dtype=float)
    prices = prices[np.isfinite(prices) & (prices > 0)]
    if len(prices) < 50:
        return 0.5
    try:
        log_prices = np.log(prices)
        n = len(log_prices)
        lags = [max(2, n // k) for k in [8, 4, 2]]
        rs_vals, lag_vals = [], []
        for lag in lags:
            series = log_prices[:lag]
            mean = series.mean()
            dev = np.cumsum(series - mean)
            r = dev.max() - dev.min()
            s = series.std()
            if s > 0:
                rs_vals.append(np.log(r / s))
                lag_vals.append(np.log(lag))
        if len(rs_vals) >= 2:
            h = float(np.polyfit(lag_vals, rs_vals, 1)[0])
            return max(0.1, min(0.9, h))
        return 0.5
    except Exception:
        return 0.5


def extract_regime_vector(df_ind: pd.DataFrame) -> dict:
    """Snapshot of market regime conditions during the backtest."""
    try:
        close_col = "Close" if "Close" in df_ind.columns else "close"
        prices = df_ind[close_col].dropna().values
        hurst = round(_compute_hurst_rs(prices), 3)
    except Exception:
        hurst = 0.5

    try:
        ret_col = "ret" if "ret" in df_ind.columns else None
        if ret_col:
            rets = df_ind[ret_col].dropna().values
        else:
            close_col = "Close" if "Close" in df_ind.columns else "close"
            rets = np.diff(np.log(df_ind[close_col].dropna().values))
        ann_vol = float(np.std(rets[np.isfinite(rets)]) * np.sqrt(24 * 365) * 100)
    except Exception:
        ann_vol = 50.0

    try:
        if "garch_h" in df_ind.columns:
            h = df_ind["garch_h"].dropna().values
            autocorr = float(pd.Series(h).autocorr(lag=1)) if len(h) > 10 else 0.9
            persistence = max(0.0, min(1.0, autocorr))
        else:
            persistence = 0.9
    except Exception:
        persistence = 0.9

    try:
        if "EMA50" in df_ind.columns and "EMA200" in df_ind.columns:
            trending_pct = float((df_ind["EMA50"] > df_ind["EMA200"]).mean())
        else:
            trending_pct = 0.5
    except Exception:
        trending_pct = 0.5

    try:
        if "garch_regime" in df_ind.columns:
            high_pct = float((df_ind["garch_regime"] == "HIGH").mean())
        else:
            high_pct = 0.2
    except Exception:
        high_pct = 0.2

    return {
        "hurst": hurst,
        "garch_persistence": round(persistence, 3),
        "ann_vol_pct": round(ann_vol, 1),
        "trending_pct": round(trending_pct, 3),
        "high_regime_pct": round(high_pct, 3),
    }


# ── Scope classification ───────────────────────────────────────────────────────

def classify_scope(strategy_type: str, verdict: str) -> str:
    """
    universal → risk management / always-true principles
    regime    → depends on market regime (trending/mean-rev/vol)
    asset     → asset-specific observation
    """
    if verdict == "failed" and strategy_type in ("rsi_reversion", "bollinger_reversion"):
        return "regime"
    return "asset"


# ── Lesson text generation ─────────────────────────────────────────────────────

def generate_lesson_text(
    asset: str, timeframe: str,
    strategy_type: str, params: dict,
    all_metrics: dict, verdict: str,
    regime: dict, wfo_folds: list,
) -> str:
    best_key = "V_Agent" if "V_Agent" in all_metrics else "V4 +GARCH+Costi"
    if best_key not in all_metrics and all_metrics:
        best_key = next(iter(all_metrics))
    m = all_metrics.get(best_key, {})
    sharpe  = round(float(m.get("sharpe_ratio", 0) or 0), 3)
    cagr    = round(float(m.get("cagr_pct", 0) or 0), 1)
    max_dd  = round(float(m.get("max_drawdown_pct", 0) or 0), 1)
    n_trades = int(m.get("n_trades", 0) or 0)
    win_rate = round(float(m.get("win_rate_pct", 0) or 0), 1)

    wfo_eff = None
    if wfo_folds:
        effs = [float(f.get("efficiency_factor", 0) or 0) for f in wfo_folds
                if f.get("efficiency_factor") is not None]
        wfo_eff = round(float(np.mean(effs)), 3) if effs else None

    hurst_regime = (
        "trending" if regime["hurst"] > 0.55 else
        "mean-reverting" if regime["hurst"] < 0.45 else
        "random-walk"
    )

    sl   = params.get("sl_mult", "?")
    tp   = params.get("tp_mult", "?")
    hrs  = params.get("active_hours", [6, 22])
    dirn = params.get("direction", "ALL")
    risk = params.get("risk_per_trade", "?")

    verdict_icon = "✓" if verdict == "promising" else ("~" if verdict == "marginal" else "✗")
    wfo_str = f", WFO eff {wfo_eff}" if wfo_eff is not None else ""

    lines = [
        f"{asset} {timeframe} — {strategy_type.replace('_',' ')} ({verdict}) {verdict_icon}",
        f"  Performance: Sharpe {sharpe}, CAGR {cagr}%, MaxDD {max_dd}%, "
        f"N trades {n_trades}, WinRate {win_rate}%{wfo_str}",
        f"  Params: SL {sl}×ATR, TP {tp}×ATR, direction={dirn}, "
        f"hours={hrs[0]}-{hrs[1]}, risk={risk}%",
        f"  Regime: H={regime['hurst']} ({hurst_regime}), "
        f"GARCH persistence={regime['garch_persistence']}, "
        f"ann.vol={regime['ann_vol_pct']}%",
    ]
    if verdict == "promising":
        lines.append(f"  → This strategy type worked well on {asset} in this regime.")
    elif verdict == "failed":
        lines.append(
            f"  → {strategy_type.replace('_',' ')} failed on {asset} "
            f"in {hurst_regime} regime. Avoid or adjust significantly."
        )

    return "\n".join(lines)


# ── Main entry point ───────────────────────────────────────────────────────────

def save_run_lesson(
    run_id: str,
    asset: str,
    timeframe: str,
    strategy_code: str | None,
    params: dict,
    all_metrics: dict,
    wfo_folds: list,
    df_ind: pd.DataFrame | None,
) -> None:
    """
    Extract and persist a learning lesson from a completed backtest run.
    Called from _run_backtest in runs.py after run completes.
    """
    if df_ind is None or df_ind.empty:
        return

    strategy_type = infer_strategy_type(strategy_code or "")
    verdict       = compute_verdict(all_metrics, wfo_folds)
    regime        = extract_regime_vector(df_ind)
    scope         = classify_scope(strategy_type, verdict)
    lesson_text   = generate_lesson_text(
        asset, timeframe, strategy_type, params,
        all_metrics, verdict, regime, wfo_folds,
    )

    lesson_id = f"lesson_{run_id}"
    tags = json.dumps([asset, timeframe, strategy_type, verdict, scope])

    conn = get_conn()
    # Check if columns exist (schema may not be migrated yet in tests)
    existing = conn.execute(
        "SELECT id FROM brain_chunks WHERE id=?", [lesson_id]
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE brain_chunks SET title=?, content=?, tags=?, source=?, scope=?, "
            "asset=?, timeframe=?, verdict=?, regime_vector=?, run_id=?, "
            "synced_at=CURRENT_TIMESTAMP WHERE id=?",
            [
                f"{asset} {timeframe} — {strategy_type} ({verdict})",
                lesson_text, tags, "empirical", scope, asset, timeframe,
                verdict, json.dumps(regime), run_id, lesson_id,
            ]
        )
    else:
        conn.execute(
            "INSERT INTO brain_chunks "
            "(id,title,content,tags,source,scope,asset,timeframe,verdict,regime_vector,run_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                lesson_id,
                f"{asset} {timeframe} — {strategy_type} ({verdict})",
                lesson_text, tags, "empirical", scope, asset, timeframe,
                verdict, json.dumps(regime), run_id,
            ]
        )
