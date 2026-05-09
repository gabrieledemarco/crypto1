"""
02_analyze.py
=============
Analisi statistica della serie storica dell'asset selezionato.
Produce analysis_report.json e REPORT.txt usati dall'agent per
progettare la strategia ottimale.

Input:  STRATEGY_ASSET env var (default: BTC-USD)
        output/{asset}_hourly.csv

Output:
  output/analysis_report.json  — statistiche strutturate + baseline V4
  output/REPORT.txt            — versione testuale per l'agent
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd
from strategy_core import (
    load_hourly, compute_indicators_v2, generate_signals_v2,
    backtest_v2, compute_metrics, fit_garch11, OUTPUT_DIR, ticker_to_fname,
)

STRATEGY_ASSET  = os.environ.get("STRATEGY_ASSET", "BTC-USD")
INITIAL_CAPITAL = 10_000


def _hurst(prices: np.ndarray) -> float:
    lp = np.log(np.asarray(prices, dtype=float))
    lags = [2, 4, 8, 16, 32, 64, 128]
    valid = [l for l in lags if l < len(lp) - 1]
    if len(valid) < 3:
        return 0.5
    rs = [np.std(np.diff(lp, lag)) for lag in valid]
    return float(np.polyfit(np.log(valid), np.log(rs), 1)[0])


def run_analysis(asset: str) -> dict:
    print(f"  Caricamento dati {asset}...")
    df = load_hourly(asset)

    print("  Calcolo indicatori + GARCH(1,1) (~30s)...")
    df_ind = compute_indicators_v2(df, fit_garch=True)

    # ── Serie storica stats ────────────────────────────────────────────────────
    ret = df["Close"].pct_change().dropna()
    H   = _hurst(df["Close"].values)
    acf1 = float(ret.autocorr(1))
    kurt = float(ret.kurtosis())
    vol  = float(ret.std() * np.sqrt(24 * 365) * 100)

    # Intraday pattern — group by hour of ret.index directly
    by_hour     = ret.groupby(pd.to_datetime(ret.index).hour).mean()
    best_hours  = sorted(by_hour.nlargest(8).index.tolist())
    worst_hours = sorted(by_hour.nsmallest(3).index.tolist())
    hourly_bps  = {int(h): round(float(v * 10_000), 3) for h, v in by_hour.items()}

    # ── GARCH params ───────────────────────────────────────────────────────────
    garch_omega = garch_alpha = garch_beta = 0.0
    regime_pct: dict = {}
    if "garch_h" in df_ind.columns:
        log_ret = np.log(df_ind["Close"] / df_ind["Close"].shift(1)).dropna().values
        try:
            garch_omega, garch_alpha, garch_beta, _ = fit_garch11(log_ret)
        except Exception:
            pass
    if "garch_regime" in df_ind.columns:
        for r, p in df_ind["garch_regime"].value_counts(normalize=True).items():
            regime_pct[str(r)] = round(float(p * 100), 1)

    # ── Regime label ───────────────────────────────────────────────────────────
    if H > 0.55:
        regime      = "trend_following"
        regime_desc = ("Serie con memoria positiva (trending). "
                       "Consigliata strategia trend following / momentum.")
    elif H < 0.45:
        regime      = "mean_reversion"
        regime_desc = ("Serie mean-reverting. "
                       "Consigliata strategia mean reversion / Bollinger Bands / RSI.")
    else:
        regime      = "breakout"
        regime_desc = ("Serie quasi-random-walk. "
                       "Consigliata strategia breakout o range trading.")

    # ── V4 baseline (da battere) ───────────────────────────────────────────────
    print("  Calcolo baseline V4 (GARCH+taker 0.04%)...")
    df_v4  = generate_signals_v2(df_ind, atr_mult_sl=2.0, atr_mult_tp=5.0,
                                  active_hours=(6, 22), use_garch_filter=True)
    res_v4 = backtest_v2(df_v4, INITIAL_CAPITAL, 0.01,
                          commission=0.0004, slippage=0.0001)
    m_v4   = compute_metrics(res_v4, INITIAL_CAPITAL)

    report = {
        "asset":          asset,
        "period_start":   str(df.index[0]),
        "period_end":     str(df.index[-1]),
        "n_bars_hourly":  len(df),
        "current_price":  float(df["Close"].iloc[-1]),
        "statistics": {
            "hurst_exponent":    round(H, 4),
            "regime":            regime,
            "regime_description": regime_desc,
            "acf_lag1":          round(acf1, 4),
            "excess_kurtosis":   round(kurt, 4),
            "ann_vol_pct":       round(vol, 2),
            "best_hours_utc":    best_hours,
            "worst_hours_utc":   worst_hours,
            "hourly_returns_bps": hourly_bps,
        },
        "garch": {
            "omega":       float(garch_omega),
            "alpha":       round(float(garch_alpha), 4),
            "beta":        round(float(garch_beta), 4),
            "persistence": round(float(garch_alpha + garch_beta), 4),
            "regime_pct":  regime_pct,
        },
        "v4_baseline": {
            "cagr_pct":          round(m_v4.get("cagr_pct", -999), 2),
            "sharpe_ratio":      round(m_v4.get("sharpe_ratio", -999), 4),
            "max_drawdown_pct":  round(m_v4.get("max_drawdown_pct", -999), 2),
            "win_rate_pct":      round(m_v4.get("win_rate_pct", 0), 2),
            "n_trades":          int(m_v4.get("n_trades", 0)),
            "profit_factor":     round(float(m_v4.get("profit_factor", 0)), 3),
        },
    }
    return report


def _make_report_txt(report: dict) -> str:
    s  = report["statistics"]
    g  = report["garch"]
    v4 = report["v4_baseline"]
    target_sharpe = max(0.5, v4["sharpe_ratio"] + 0.5)
    target_cagr   = max(0.0, v4["cagr_pct"] + 5)
    lines = [
        f"ANALISI STATISTICA — {report['asset']}",
        f"Periodo: {report['period_start']} → {report['period_end']}  "
        f"({report['n_bars_hourly']} barre orarie)",
        f"Prezzo attuale: {report['current_price']:.4f}",
        "",
        "═" * 60,
        "PROPRIETÀ SERIE STORICA",
        "═" * 60,
        f"Hurst exponent : {s['hurst_exponent']:.4f}  →  {s['regime'].upper()}",
        f"  {s['regime_description']}",
        f"ACF lag-1      : {s['acf_lag1']:.4f}  "
        f"({'momentum' if s['acf_lag1'] > 0 else 'mean-reversion'})",
        f"Kurtosis (exc) : {s['excess_kurtosis']:.4f}  "
        f"({'fat tails — widen SL' if s['excess_kurtosis'] > 5 else 'normal tails'})",
        f"Vol annualiz.  : {s['ann_vol_pct']:.2f}%",
        f"Ore UTC migliori  (avg return +): {s['best_hours_utc']}",
        f"Ore UTC peggiori  (avg return -): {s['worst_hours_utc']}",
        "",
        "Rendimento medio per ora (bps):",
        "  " + "  ".join(f"{h:02d}h={v:+.1f}" for h, v
                          in sorted(s["hourly_returns_bps"].items())),
        "",
        "═" * 60,
        "GARCH(1,1)",
        "═" * 60,
        f"alpha (shock impact)  : {g['alpha']:.4f}",
        f"beta  (persistence)   : {g['beta']:.4f}",
        f"alpha+beta            : {g['persistence']:.4f}  (< 1 → stazionario)",
        f"Distribuzione regimi  : {g['regime_pct']}",
        "",
        "═" * 60,
        "BASELINE V4  (ATR breakout + GARCH filter, taker 0.04%)",
        "═" * 60,
        f"CAGR          : {v4['cagr_pct']:.2f}%",
        f"Sharpe Ratio  : {v4['sharpe_ratio']:.4f}",
        f"Max Drawdown  : {v4['max_drawdown_pct']:.2f}%",
        f"Win Rate      : {v4['win_rate_pct']:.2f}%",
        f"N. Trade      : {v4['n_trades']}",
        f"Profit Factor : {v4['profit_factor']:.3f}",
        "",
        "═" * 60,
        "OBIETTIVO AGENT",
        "═" * 60,
        f"Progetta una strategia con Sharpe > {target_sharpe:.2f} e CAGR > {target_cagr:.1f}%.",
        "Sfrutta le proprietà statistiche sopra per scegliere il tipo di strategia ottimale.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print("=" * 60)
    print(f"  ANALISI STATISTICA — {STRATEGY_ASSET}")
    print("=" * 60)

    report = run_analysis(STRATEGY_ASSET)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Generic file (backward-compat) + asset-specific file
    json_path = os.path.join(OUTPUT_DIR, "analysis_report.json")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)
    fname = ticker_to_fname(STRATEGY_ASSET)
    asset_json = os.path.join(OUTPUT_DIR, f"analysis_report_{fname}.json")
    with open(asset_json, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Saved: analysis_report.json + analysis_report_{fname}.json")

    txt_path = os.path.join(OUTPUT_DIR, "REPORT.txt")
    with open(txt_path, "w") as f:
        f.write(_make_report_txt(report))
    print(f"  Saved: REPORT.txt")

    s  = report["statistics"]
    v4 = report["v4_baseline"]
    print(f"\n  Hurst : {s['hurst_exponent']:.3f}  → {s['regime']}")
    print(f"  ACF-1 : {s['acf_lag1']:.3f}")
    print(f"  Kurt  : {s['excess_kurtosis']:.2f}")
    print(f"  Vol   : {s['ann_vol_pct']:.1f}%")
    print(f"  Ore migliori: {s['best_hours_utc']}")
    print(f"\n  V4 baseline → "
          f"CAGR: {v4['cagr_pct']:.1f}%  "
          f"Sharpe: {v4['sharpe_ratio']:.2f}  "
          f"MaxDD: {v4['max_drawdown_pct']:.1f}%  "
          f"Trade: {v4['n_trades']}")
    print("\nAnalisi statistica completata.")
