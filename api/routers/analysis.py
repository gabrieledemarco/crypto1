"""
api/routers/analysis.py
=======================
Analysis endpoints called by Claude tool-use during Vibe generation.
GET /analysis/{ticker}/autocorrelation
GET /analysis/{ticker}/seasonality
GET /analysis/{ticker}/volatility-cone
GET /analysis/{ticker}/return-distribution
"""
import json
import numpy as np
import pandas as pd
import scipy.stats
from statsmodels.tsa.stattools import acf as sm_acf
from fastapi import APIRouter, HTTPException, Query

from api.db import get_conn

router = APIRouter()

BARS_PER_YEAR = {"1m": 525600, "5m": 105120, "15m": 35040, "30m": 17520,
                 "1h": 8760, "4h": 2190, "1d": 365, "1wk": 52, "1mo": 12}


def _load_bars(ticker: str, interval: str) -> pd.DataFrame:
    """Load OHLCV bars from DuckDB for a given ticker/interval."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT ts, open, high, low, close, volume FROM assets "
        "WHERE ticker=? AND source LIKE ? ORDER BY ts",
        [ticker, f"%:{interval}"]
    ).fetchall()
    if not rows:
        # fallback: any source
        rows = conn.execute(
            "SELECT ts, open, high, low, close, volume FROM assets "
            "WHERE ticker=? ORDER BY ts",
            [ticker]
        ).fetchall()
    if not rows:
        raise HTTPException(404, f"No data for {ticker}")
    df = pd.DataFrame(rows, columns=["ts", "Open", "High", "Low", "Close", "Volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.set_index("ts").sort_index()
    return df


@router.get("/{ticker}/autocorrelation")
def get_autocorrelation(
    ticker: str,
    interval: str = Query("1h"),
    lags: int = Query(20, ge=5, le=50),
):
    """ACF on log-returns — identifies momentum vs mean-reversion lags."""
    df = _load_bars(ticker, interval)
    rets = np.diff(np.log(df["Close"].values))
    rets = rets[np.isfinite(rets)]
    if len(rets) < 50:
        raise HTTPException(400, "Insufficient data for ACF")

    try:
        acf_vals, confint = sm_acf(rets, nlags=lags, alpha=0.05)
        threshold = 2.0 / np.sqrt(len(rets))
        sig_lags = [int(i) for i in range(1, lags + 1) if abs(acf_vals[i]) > threshold]
        momentum_score = float(np.mean(acf_vals[1:6]))  # lags 1-5
    except Exception as e:
        raise HTTPException(500, str(e))

    interpretation = (
        "short-term momentum — consider trend-following strategies"
        if momentum_score > 0.05 else
        "short-term mean-reversion — consider mean-reversion / oscillator strategies"
        if momentum_score < -0.05 else
        "near-random-walk at short lags — breakout or regime-based strategies preferred"
    )

    return {
        "n_bars": len(rets),
        "significant_lags": sig_lags,
        "lag_values": {str(i): round(float(acf_vals[i]), 4) for i in range(1, lags + 1)},
        "momentum_score_lag1_5": round(momentum_score, 4),
        "interpretation": interpretation,
        "strategy_hint": (
            "Use EMA crossover or breakout" if momentum_score > 0.05 else
            "Use RSI/BB mean-reversion" if momentum_score < -0.05 else
            "Use breakout with wide SL"
        ),
    }


@router.get("/{ticker}/seasonality")
def get_intraday_seasonality(ticker: str, interval: str = Query("1h")):
    """Intraday return/volume seasonality by hour UTC."""
    df = _load_bars(ticker, interval)
    df["ret"] = np.log(df["Close"] / df["Close"].shift(1))
    df["hour"] = df.index.hour
    df["dow"]  = df.index.dayofweek  # 0=Mon, 6=Sun

    if len(df) < 200:
        raise HTTPException(400, "Insufficient data for seasonality")

    hourly = df.groupby("hour").agg(
        mean_ret=("ret", "mean"),
        mean_vol=("Volume", "mean"),
        count=("ret", "count"),
    )
    mean_vol_overall = float(hourly["mean_vol"].mean()) or 1.0

    top3_hours   = hourly.nlargest(3, "mean_ret").index.tolist()
    worst3_hours = hourly.nsmallest(3, "mean_ret").index.tolist()
    vol_premium  = float(hourly.loc[top3_hours]["mean_vol"].mean()) / mean_vol_overall

    # Day-of-week summary
    daily = df.groupby("dow").agg(mean_ret=("ret", "mean"))
    best_days  = daily.nlargest(2, "mean_ret").index.tolist()
    worst_days = daily.nsmallest(2, "mean_ret").index.tolist()
    dow_names  = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    return {
        "peak_hours_utc": top3_hours,
        "low_hours_utc": worst3_hours,
        "suggested_active_hours": [int(min(top3_hours)), int(max(top3_hours))],
        "vol_premium_peak_vs_avg": round(vol_premium, 2),
        "hourly_mean_return_pct": {
            str(int(h)): round(float(r) * 100, 4)
            for h, r in hourly["mean_ret"].items()
        },
        "best_days": [dow_names[d] for d in best_days],
        "worst_days": [dow_names[d] for d in worst_days],
        "strategy_hint": (
            f"Trade between {min(top3_hours):02d}:00 and {max(top3_hours):02d}:00 UTC. "
            f"Avoid {', '.join(str(h) for h in worst3_hours[:2])}:00 UTC."
        ),
    }


@router.get("/{ticker}/volatility-cone")
def get_volatility_cone(ticker: str, interval: str = Query("1h")):
    """Current ATR vs. historical distribution at multiple windows."""
    df = _load_bars(ticker, interval)
    if len(df) < 60:
        raise HTTPException(400, "Insufficient data for volatility cone")

    # ATR
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift(1)).abs()
    lc = (df["Low"]  - df["Close"].shift(1)).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    atr14 = tr.ewm(span=14, adjust=False).mean()
    atr_pct = atr14 / df["Close"]

    current_atr_pct = float(atr_pct.iloc[-1])
    result = {"current_atr_pct": round(current_atr_pct * 100, 4)}

    for window in [10, 20, 40, 80]:
        hist = atr_pct.rolling(window).mean().dropna()
        if len(hist) > 5:
            pct = float(scipy.stats.percentileofscore(hist.values, current_atr_pct))
            result[f"percentile_w{window}"] = round(pct, 1)

    pct20 = result.get("percentile_w20", 50)
    result["interpretation"] = (
        f"ATR is elevated (p{pct20:.0f} historically) — widen SL multiplier (>= 3xATR), reduce position size"
        if pct20 > 75 else
        f"ATR is compressed (p{pct20:.0f} historically) — potential breakout setup, keep TP wide"
        if pct20 < 25 else
        f"ATR near historical median (p{pct20:.0f}) — standard sizing and SL appropriate"
    )
    result["suggested_sl_mult"] = (
        3.0 if pct20 > 75 else
        1.5 if pct20 < 25 else
        2.0
    )
    return result


@router.get("/{ticker}/return-distribution")
def get_return_distribution(ticker: str, interval: str = Query("1h")):
    """Return distribution characteristics: skew, kurtosis, fat tails, VaR."""
    df = _load_bars(ticker, interval)
    rets = np.diff(np.log(df["Close"].values))
    rets = rets[np.isfinite(rets)]
    if len(rets) < 50:
        raise HTTPException(400, "Insufficient data")

    skew     = float(scipy.stats.skew(rets))
    kurt     = float(scipy.stats.kurtosis(rets))   # excess kurtosis
    jb_stat, jb_p = scipy.stats.jarque_bera(rets)
    var_1    = float(np.percentile(rets, 1))
    var_5    = float(np.percentile(rets, 5))
    cvar_5   = float(rets[rets <= np.percentile(rets, 5)].mean())
    fat_tails = bool(kurt > 1.5 and jb_p < 0.05)

    sizing_hint = (
        "Fat left tail detected — reduce risk_per_trade, use SL >= 3x ATR to avoid premature stops on whipsaws"
        if fat_tails and skew < -0.3 else
        "Fat right tail (positive skew) — momentum/breakout strategies benefit from asymmetric TP > SL"
        if fat_tails and skew > 0.3 else
        "Near-normal distribution — standard sizing and risk parameters apply"
    )

    return {
        "n_bars": len(rets),
        "skewness": round(skew, 4),
        "excess_kurtosis": round(kurt, 4),
        "fat_tails": fat_tails,
        "jarque_bera_pvalue": round(float(jb_p), 4),
        "var_1pct": round(var_1 * 100, 3),
        "var_5pct": round(var_5 * 100, 3),
        "cvar_5pct": round(cvar_5 * 100, 3),
        "sizing_hint": sizing_hint,
        "suggested_sl_adjustment": (
            "increase SL width by 20-30%" if fat_tails else "no adjustment needed"
        ),
    }
