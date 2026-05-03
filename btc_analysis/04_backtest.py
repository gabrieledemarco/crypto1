"""
04_backtest.py
==============
Backtest completo: V1/V2/V4/V_Agent + Walk-Forward + Grid Search.
Legge analysis_report.json per asset e context, carica agent strategy code.

Input:  STRATEGY_ASSET env var (default: BTC-USD)
        output/analysis_report.json
        output/agent_strategy_code.py

Output:
  output/trades.csv                       — trade V_Agent
  output/enhanced_strategy_comparison.csv — metriche tutte le versioni
  output/walk_forward_results.csv         — WFO folds
  output/optimization_results.csv         — grid search SL/TP
  output/strategy_meta.json               — asset usato nell'ultimo run
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from strategy_core import (
    load_features, generate_signals_v2,
    backtest_v2, compute_metrics, load_agent_config, load_agent_strategy,
    ticker_to_fname, OUTPUT_DIR,
)

STRATEGY_ASSET  = os.environ.get("STRATEGY_ASSET", "BTC-USD")
INITIAL_CAPITAL = 10_000
RISK            = 0.01
COMMISSION      = 0.0004
SLIPPAGE        = 0.0001
HOURS_MONTH     = 24 * 30


# ── Load agent config at module level ─────────────────────────────────────────

_ACFG      = load_agent_config()
BEST_SL    = _ACFG["sl_mult"]
BEST_TP    = _ACFG["tp_mult"]
BEST_HOURS = tuple(_ACFG["active_hours"])
_A_COMM    = _ACFG["commission"]
_A_SLIP    = _ACFG["slippage"]
_A_RISK    = _ACFG.get("risk_per_trade", RISK)


# ── Version backtests ─────────────────────────────────────────────────────────

def run_versions(df_ind: pd.DataFrame) -> dict:
    results = {}
    configs = {
        "V1 Base":         {"use_garch_filter": False, "commission": 0.0,        "slippage": 0.0},
        "V2 +Costi":       {"use_garch_filter": False, "commission": COMMISSION,  "slippage": SLIPPAGE},
        "V4 +GARCH+Costi": {"use_garch_filter": True,  "commission": COMMISSION,  "slippage": SLIPPAGE},
    }
    for name, cfg in configs.items():
        print(f"  {name}...")
        df_s = generate_signals_v2(df_ind, atr_mult_sl=BEST_SL, atr_mult_tp=BEST_TP,
                                    active_hours=BEST_HOURS,
                                    use_garch_filter=cfg["use_garch_filter"])
        res = backtest_v2(df_s, INITIAL_CAPITAL, RISK,
                          commission=cfg["commission"], slippage=cfg["slippage"])
        results[name] = {"result": res, "metrics": compute_metrics(res, INITIAL_CAPITAL)}

    print("  V_Agent (strategia AI)...")
    try:
        agent_fn = load_agent_strategy()
        df_a     = agent_fn(df_ind)
        res_a    = backtest_v2(df_a, INITIAL_CAPITAL, _A_RISK,
                                commission=_A_COMM, slippage=_A_SLIP)
        results["V_Agent"] = {"result": res_a, "metrics": compute_metrics(res_a, INITIAL_CAPITAL)}
    except Exception as exc:
        print(f"  [V_Agent] errore: {exc}")

    return results


# ── Walk-Forward Optimization ─────────────────────────────────────────────────

def run_wfo(df_ind: pd.DataFrame) -> pd.DataFrame:
    agent_fn = load_agent_strategy()
    comm     = _ACFG.get("commission", COMMISSION)
    slip     = _ACFG.get("slippage",   SLIPPAGE)

    window_configs = [
        {"label": "IS=4m OOS=1m", "train": 4 * HOURS_MONTH, "test": 1 * HOURS_MONTH},
        {"label": "IS=6m OOS=2m", "train": 6 * HOURS_MONTH, "test": 2 * HOURS_MONTH},
        {"label": "IS=8m OOS=2m", "train": 8 * HOURS_MONTH, "test": 2 * HOURS_MONTH},
        {"label": "IS=8m OOS=3m", "train": 8 * HOURS_MONTH, "test": 3 * HOURS_MONTH},
    ]

    rows = []
    for cfg in window_configs:
        is_len  = cfg["train"]
        oos_len = cfg["test"]
        step    = oos_len
        fold    = 0
        i       = 0
        while i + is_len + oos_len <= len(df_ind):
            is_data  = df_ind.iloc[i : i + is_len]
            oos_data = df_ind.iloc[i + is_len : i + is_len + oos_len]

            df_is  = agent_fn(is_data)
            res_is = backtest_v2(df_is,  INITIAL_CAPITAL, RISK, comm, slip)
            m_is   = compute_metrics(res_is, INITIAL_CAPITAL)

            df_os  = agent_fn(oos_data)
            res_os = backtest_v2(df_os, INITIAL_CAPITAL, RISK, comm, slip)
            m_os   = compute_metrics(res_os, INITIAL_CAPITAL)

            rows.append({
                "window_config":  cfg["label"],
                "fold":           fold,
                "is_sharpe":      m_is.get("sharpe_ratio", 0),
                "oos_sharpe":     m_os.get("sharpe_ratio", 0),
                "is_cagr":        m_is.get("cagr_pct",     0),
                "oos_cagr":       m_os.get("cagr_pct",     0),
                "is_n_trades":    m_is.get("n_trades",      0),
                "oos_n_trades":   m_os.get("n_trades",      0),
                "is_max_dd":      m_is.get("max_drawdown_pct", 0),
                "oos_max_dd":     m_os.get("max_drawdown_pct", 0),
            })
            fold += 1
            i    += step

    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ── Grid-search optimization ──────────────────────────────────────────────────

def run_optimization(df_ind: pd.DataFrame) -> pd.DataFrame:
    comm = _ACFG.get("commission", COMMISSION)
    slip = _ACFG.get("slippage",   SLIPPAGE)
    SL_RANGE = [1.0, 1.5, 2.0, 2.5, 3.0]
    TP_RANGE = [2.0, 3.0, 4.0, 5.0, 7.0]
    HOUR_WINDOWS = [(6, 22), (8, 20), (0, 23)]

    rows = []
    for sl in SL_RANGE:
        for tp in TP_RANGE:
            if tp <= sl:
                continue
            for h in HOUR_WINDOWS:
                df_s = generate_signals_v2(df_ind, atr_mult_sl=sl, atr_mult_tp=tp,
                                            active_hours=h, use_garch_filter=True)
                res  = backtest_v2(df_s, INITIAL_CAPITAL, RISK, comm, slip)
                m    = compute_metrics(res, INITIAL_CAPITAL)
                rows.append({
                    "sl_mult":          sl,
                    "tp_mult":          tp,
                    "active_hours":     f"{h[0]}-{h[1]}",
                    "sharpe_ratio":     m.get("sharpe_ratio",     0),
                    "cagr_pct":         m.get("cagr_pct",         0),
                    "max_drawdown_pct": m.get("max_drawdown_pct", 0),
                    "n_trades":         m.get("n_trades",          0),
                    "win_rate_pct":     m.get("win_rate_pct",      0),
                })

    df_opt = pd.DataFrame(rows)
    return df_opt.sort_values("sharpe_ratio", ascending=False) if not df_opt.empty else df_opt


# ── Comparison chart ──────────────────────────────────────────────────────────

def _save_chart(results: dict, asset: str):
    colors = {
        "V1 Base": "#3498DB", "V2 +Costi": "#E74C3C",
        "V4 +GARCH+Costi": "#F39C12", "V_Agent": "#9B59B6",
    }
    styles = {
        "V1 Base": "--", "V2 +Costi": "-.",
        "V4 +GARCH+Costi": "-", "V_Agent": "-",
    }
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=False)
    ax_eq, ax_dd = axes

    for name, data in results.items():
        eq  = data["result"]["equity"]
        m   = data["metrics"]
        lbl = f"{name} (CAGR={m.get('cagr_pct',0):.1f}%, Sharpe={m.get('sharpe_ratio',0):.2f})"
        ax_eq.plot(eq.index, eq.values,
                   color=colors.get(name, "#AAAAAA"),
                   linestyle=styles.get(name, "-"),
                   linewidth=1.8, label=lbl)
        dd = (eq - eq.cummax()) / eq.cummax() * 100
        ax_dd.plot(dd.index, dd.values,
                   color=colors.get(name, "#AAAAAA"),
                   linestyle=styles.get(name, "-"),
                   linewidth=1, label=name)

    ax_eq.axhline(INITIAL_CAPITAL, color="gray", linewidth=0.8, linestyle=":")
    ax_eq.set_title(f"{asset} — Equity Curve confronto versioni", fontweight="bold")
    ax_eq.set_ylabel("Capitale (USD)")
    ax_eq.legend(fontsize=8)
    ax_eq.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    ax_dd.axhline(0, color="gray", linewidth=0.5)
    ax_dd.set_title("Drawdown (%)", fontweight="bold")
    ax_dd.set_ylabel("Drawdown (%)")
    ax_dd.legend(fontsize=8)

    fig.tight_layout()
    out = os.path.join(OUTPUT_DIR, "04_enhanced_strategy.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {os.path.basename(out)}")


# ── Print comparison table ────────────────────────────────────────────────────

def _print_comparison(results: dict):
    print(f"\n{'═'*80}")
    print("  CONFRONTO VERSIONI")
    print(f"{'═'*80}")
    hdr = f"  {'Versione':<20} {'CAGR%':>8} {'Sharpe':>8} {'MaxDD%':>8} {'WinRate':>8} {'N':>5}"
    print(hdr)
    print(f"  {'-'*60}")
    for name, data in results.items():
        m = data["metrics"]
        if "error" in m:
            print(f"  {name:<20} ERROR")
            continue
        print(f"  {name:<20} {m['cagr_pct']:>8.1f} {m['sharpe_ratio']:>8.2f} "
              f"{m['max_drawdown_pct']:>8.1f} {m['win_rate_pct']:>8.1f} {m['n_trades']:>5}")


if __name__ == "__main__":
    print("=" * 60)
    print(f"  BACKTEST — {STRATEGY_ASSET}")
    print("=" * 60)

    print(f"\nCaricamento feature {STRATEGY_ASSET}...")
    df_ind = load_features(STRATEGY_ASSET)

    print("\nEsecuzione versioni strategia...")
    results = run_versions(df_ind)
    _print_comparison(results)

    # Save comparison CSV
    rows = []
    for name, data in results.items():
        m = data["metrics"].copy()
        m["version"] = name
        rows.append(m)
    cmp_path = os.path.join(OUTPUT_DIR, "enhanced_strategy_comparison.csv")
    pd.DataFrame(rows).to_csv(cmp_path, index=False)
    print(f"\n  Saved: enhanced_strategy_comparison.csv")

    # Save V_Agent trades
    if "V_Agent" in results:
        tr = results["V_Agent"]["result"]["trades"]
        if not tr.empty:
            tr.to_csv(os.path.join(OUTPUT_DIR, "trades.csv"), index=False)
            print(f"  Saved: trades.csv  ({len(tr)} trade)")
    elif "V4 +GARCH+Costi" in results:
        tr = results["V4 +GARCH+Costi"]["result"]["trades"]
        if not tr.empty:
            tr.to_csv(os.path.join(OUTPUT_DIR, "trades.csv"), index=False)
            print(f"  Saved: trades.csv  (V4 fallback, {len(tr)} trade)")

    # Walk-Forward
    print("\nWalk-Forward Optimization...")
    wfo = run_wfo(df_ind)
    if not wfo.empty:
        wfo.to_csv(os.path.join(OUTPUT_DIR, "walk_forward_results.csv"), index=False)
        print(f"  Saved: walk_forward_results.csv  ({len(wfo)} folds)")
        oos_avg = wfo["oos_sharpe"].mean()
        is_avg  = wfo["is_sharpe"].mean()
        wfe     = oos_avg / is_avg if is_avg != 0 else 0
        print(f"  IS Sharpe medio: {is_avg:.3f}  |  OOS Sharpe medio: {oos_avg:.3f}  |  WFE: {wfe:.3f}")

    # Grid search
    print("\nGrid search SL/TP...")
    opt = run_optimization(df_ind)
    if not opt.empty:
        opt.to_csv(os.path.join(OUTPUT_DIR, "optimization_results.csv"), index=False)
        best = opt.iloc[0]
        print(f"  Saved: optimization_results.csv")
        print(f"  Best: SL={best['sl_mult']} TP={best['tp_mult']} "
              f"hours={best['active_hours']} Sharpe={best['sharpe_ratio']:.3f}")

    # Chart
    print("\nGenerazione grafici...")
    _save_chart(results, STRATEGY_ASSET)

    # strategy_meta.json
    with open(os.path.join(OUTPUT_DIR, "strategy_meta.json"), "w") as f:
        json.dump({"asset": STRATEGY_ASSET}, f)

    print("\nBacktest completato.")
