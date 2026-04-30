"""
06_enhanced_strategy.py
========================
Confronto sistematico tra 4 versioni della strategia:
  V1: Base (no costi, no GARCH)
  V2: +Costi (commissioni 0.06% + slippage 0.03%)
  V3: +GARCH (filtro regime vol, no costi)
  V4: +Costi +GARCH (versione realistica completa)

Analisi aggiuntiva:
  - Visualizzazione varianza condizionale GARCH(1,1)
  - Heatmap regime × ora del giorno
  - Impatto costi per N trade
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
from strategy_core import (
    load_hourly, compute_indicators_v2, generate_signals_v2,
    backtest_v2, compute_metrics, fit_garch11, compute_garch_regime,
    load_agent_config, load_agent_strategy, OUTPUT_DIR
)

sns.set_theme(style="darkgrid")

INITIAL_CAPITAL = 10_000
RISK = 0.01
COMMISSION = 0.0004   # 0.04% Binance taker fee (VIP 0)
SLIPPAGE = 0.0001     # 0.01% market impact BTC/USDT

# Load agent-proposed config; fall back to V5 defaults if not available
_ACFG    = load_agent_config()
BEST_SL  = _ACFG["sl_mult"]
BEST_TP  = _ACFG["tp_mult"]
BEST_HOURS = tuple(_ACFG["active_hours"])
_A_COMMISSION = _ACFG["commission"]
_A_SLIPPAGE   = _ACFG["slippage"]
_A_RISK       = _ACFG.get("risk_per_trade", RISK)


def run_versions(df_ind: pd.DataFrame) -> dict:
    """Esegue le versioni della strategia (V1-V4 + V_Agent) e ritorna i risultati."""
    results = {}

    configs = {
        "V1 Base":          {"use_garch_filter": False, "commission": 0.0, "slippage": 0.0},
        "V2 +Costi":        {"use_garch_filter": False, "commission": COMMISSION, "slippage": SLIPPAGE},
        "V3 +GARCH":        {"use_garch_filter": True,  "commission": 0.0, "slippage": 0.0},
        "V4 +GARCH+Costi":  {"use_garch_filter": True,  "commission": COMMISSION, "slippage": SLIPPAGE},
    }

    for name, cfg in configs.items():
        print(f"  Esecuzione {name}...")
        df_sig = generate_signals_v2(df_ind,
                                      atr_mult_sl=BEST_SL,
                                      atr_mult_tp=BEST_TP,
                                      active_hours=BEST_HOURS,
                                      use_garch_filter=cfg["use_garch_filter"])
        res = backtest_v2(df_sig, INITIAL_CAPITAL, RISK,
                          commission=cfg["commission"], slippage=cfg["slippage"])
        metrics = compute_metrics(res, INITIAL_CAPITAL)
        results[name] = {"result": res, "metrics": metrics, "df": df_sig}

    # V_Agent: strategia generata dall'AI agent
    print("  Esecuzione V_Agent (agent-designed strategy)...")
    try:
        _agent_fn = load_agent_strategy()
        df_agent  = _agent_fn(df_ind)
        res_agent = backtest_v2(df_agent, INITIAL_CAPITAL, _A_RISK,
                                commission=_A_COMMISSION, slippage=_A_SLIPPAGE)
        m_agent   = compute_metrics(res_agent, INITIAL_CAPITAL)
        results["V_Agent"] = {"result": res_agent, "metrics": m_agent, "df": df_agent}
    except Exception as exc:
        print(f"  [V_Agent] errore: {exc} — skip")

    return results


def print_comparison(results: dict):
    print(f"\n{'═'*80}")
    print("  CONFRONTO VERSIONI STRATEGIA")
    print(f"{'═'*80}")
    header = f"  {'Versione':<20} {'CAGR%':>8} {'Sharpe':>8} {'MaxDD%':>8} "
    header += f"{'WinRate':>8} {'PF':>6} {'N':>5} {'Costi$':>8}"
    print(header)
    print(f"  {'-'*76}")
    for name, data in results.items():
        m = data["metrics"]
        if "error" in m:
            print(f"  {name:<20} {'ERROR':>8}")
            continue
        costs = m.get("total_costs_usd", 0)
        print(f"  {name:<20} {m['cagr_pct']:>8.1f} {m['sharpe_ratio']:>8.2f} "
              f"{m['max_drawdown_pct']:>8.1f} {m['win_rate_pct']:>8.1f} "
              f"{m['profit_factor']:>6.2f} {m['n_trades']:>5} {costs:>8.0f}")


def plot_comparison(results: dict, df_ind: pd.DataFrame):
    fig = plt.figure(figsize=(20, 28))
    gs = gridspec.GridSpec(5, 2, figure=fig, hspace=0.5, wspace=0.35)

    # ── 1. Equity curves confronto ──────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :])
    colors = {"V1 Base": "#3498DB", "V2 +Costi": "#E74C3C",
               "V3 +GARCH": "#2ECC71", "V4 +GARCH+Costi": "#F39C12",
               "V_Agent": "#9B59B6"}
    styles = {"V1 Base": "--", "V2 +Costi": "-.",
               "V3 +GARCH": ":", "V4 +GARCH+Costi": "-",
               "V_Agent": "-"}
    for name, data in results.items():
        eq = data["result"]["equity"]
        m = data["metrics"]
        label = f"{name} (CAGR={m.get('cagr_pct', 0):.1f}%, Sharpe={m.get('sharpe_ratio', 0):.2f})"
        c = colors.get(name, "#AAAAAA")
        s = styles.get(name, "-")
        ax1.plot(eq.index, eq.values, color=c,
                 linestyle=s, linewidth=1.8, label=label)
    ax1.axhline(INITIAL_CAPITAL, color="gray", linewidth=0.8, linestyle="--")
    ax1.set_title("Equity Curve — Confronto Versioni Strategia", fontsize=14, fontweight="bold")
    ax1.set_ylabel("Capitale (USD)")
    ax1.legend(fontsize=9)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # ── 2. GARCH conditional variance ───────────────────────────────────────
    ax2 = fig.add_subplot(gs[1, :])
    if "garch_h" in df_ind.columns:
        h = df_ind["garch_h"]
        ax2.fill_between(h.index, np.sqrt(h.values) * np.sqrt(24 * 365) * 100,
                         alpha=0.6, color="#9B59B6")
        pct25 = np.percentile(h.values, 25)
        pct75 = np.percentile(h.values, 75)
        ax2.axhline(np.sqrt(pct25) * np.sqrt(24 * 365) * 100,
                    color="green", linestyle="--", linewidth=1, label="25° pct (LOW)")
        ax2.axhline(np.sqrt(pct75) * np.sqrt(24 * 365) * 100,
                    color="red", linestyle="--", linewidth=1, label="75° pct (HIGH)")
        ax2.set_title("GARCH(1,1) — Volatilità Condizionale Annualizzata (%)", fontsize=12, fontweight="bold")
        ax2.set_ylabel("Vol %")
        ax2.legend()

    # ── 3. Regime distribution ─────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[2, 0])
    if "garch_regime" in df_ind.columns:
        reg_counts = df_ind["garch_regime"].value_counts()
        reg_colors = {"LOW": "#3498DB", "MED": "#2ECC71", "HIGH": "#E74C3C"}
        bars = ax3.bar(reg_counts.index, reg_counts.values,
                       color=[reg_colors.get(r, "gray") for r in reg_counts.index])
        ax3.set_title("Distribuzione Regimi GARCH", fontsize=12, fontweight="bold")
        ax3.set_ylabel("N. barre orarie")
        for bar, val in zip(bars, reg_counts.values):
            ax3.annotate(f"{val/len(df_ind)*100:.0f}%",
                         (bar.get_x() + bar.get_width()/2, bar.get_height()),
                         ha="center", va="bottom")

    # ── 4. PnL medio per regime ─────────────────────────────────────────────
    ax4 = fig.add_subplot(gs[2, 1])
    v4_trades = results["V4 +GARCH+Costi"]["result"]["trades"]
    v1_trades = results["V1 Base"]["result"]["trades"]
    if not v4_trades.empty and "garch_regime" in results["V4 +GARCH+Costi"]["df"].columns:
        # Merge regime at entry time
        df_regime = results["V4 +GARCH+Costi"]["df"][["garch_regime"]].copy()
        v4_trades_r = v4_trades.copy()
        v4_trades_r.index = range(len(v4_trades_r))
        try:
            v4_trades_r["regime"] = [
                df_regime.asof(t) if hasattr(df_regime, "asof") else "MED"
                for t in v4_trades_r["entry_time"]
            ]
            pnl_by_regime = v4_trades_r.groupby("regime")["pnl"].mean()
            col = [reg_colors.get(r, "gray") for r in pnl_by_regime.index]
            ax4.bar(pnl_by_regime.index, pnl_by_regime.values, color=col)
            ax4.axhline(0, color="black", linewidth=0.8)
            ax4.set_title("PnL Medio per Regime GARCH (V4)", fontsize=12, fontweight="bold")
            ax4.set_ylabel("PnL medio (USD)")
        except Exception:
            pass

    # ── 5. Costi cumulati ──────────────────────────────────────────────────
    ax5 = fig.add_subplot(gs[3, :])
    for name in ["V2 +Costi", "V4 +GARCH+Costi"]:
        t = results[name]["result"]["trades"]
        if not t.empty and "costs" in t.columns:
            cum_costs = t["costs"].cumsum()
            cum_costs.index = range(len(cum_costs))
            ax5.plot(cum_costs.values, label=name,
                     color=colors.get(name, "#AAAAAA"), linewidth=1.5)
    ax5.set_title("Costi Cumulati (Commissioni + Slippage)", fontsize=12, fontweight="bold")
    ax5.set_xlabel("Trade #")
    ax5.set_ylabel("Costi cumulati (USD)")
    ax5.legend()

    # ── 6. Barchart metriche ───────────────────────────────────────────────
    ax6 = fig.add_subplot(gs[4, 0])
    names = list(results.keys())
    sharpes = [results[n]["metrics"].get("sharpe_ratio", 0) for n in names]
    cagrs = [results[n]["metrics"].get("cagr_pct", 0) for n in names]
    x = np.arange(len(names))
    w = 0.35
    ax6.bar(x - w/2, sharpes, w, label="Sharpe", color="#3498DB")
    ax6b = ax6.twinx()
    ax6b.bar(x + w/2, cagrs, w, label="CAGR%", color="#F39C12", alpha=0.8)
    ax6.set_xticks(x)
    ax6.set_xticklabels([n.replace(" ", "\n") for n in names], fontsize=8)
    ax6.set_title("Sharpe vs CAGR per Versione", fontsize=12, fontweight="bold")
    ax6.set_ylabel("Sharpe", color="#3498DB")
    ax6b.set_ylabel("CAGR%", color="#F39C12")

    # ── 7. Drawdown comparison ─────────────────────────────────────────────
    ax7 = fig.add_subplot(gs[4, 1])
    for name, data in results.items():
        eq = data["result"]["equity"]
        dd = (eq - eq.cummax()) / eq.cummax() * 100
        ax7.plot(dd.index, dd.values, color=colors.get(name, "#AAAAAA"),
                 linestyle=styles.get(name, "-"), linewidth=1, label=name)
    ax7.set_title("Drawdown Confronto", fontsize=12, fontweight="bold")
    ax7.set_ylabel("Drawdown (%)")
    ax7.legend(fontsize=8)

    fig.suptitle("BTC/USD — Enhanced Strategy: GARCH Filter + Costi Transazione",
                 fontsize=15, fontweight="bold")
    plt.savefig(os.path.join(OUTPUT_DIR, "04_enhanced_strategy.png"),
                dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved: 04_enhanced_strategy.png")


if __name__ == "__main__":
    print("Caricamento dati orari BTC...")
    df_raw = load_hourly("BTC")

    print("Calcolo indicatori + GARCH(1,1) (potrebbe richiedere ~30s)...")
    df_ind = compute_indicators_v2(df_raw, fit_garch=True)

    omega, alpha, beta = 0.0, 0.0, 0.0
    if "garch_h" in df_ind.columns:
        log_ret = np.log(df_ind["Close"] / df_ind["Close"].shift(1)).dropna().values
        try:
            omega, alpha, beta, _ = fit_garch11(log_ret)
        except Exception:
            pass

    print(f"\n  GARCH(1,1) parametri stimati:")
    print(f"    omega = {omega:.2e}")
    print(f"    alpha = {alpha:.4f}  (impatto shock)")
    print(f"    beta  = {beta:.4f}  (persistenza volatilità)")
    print(f"    alpha+beta = {alpha+beta:.4f}  (< 1 → stazionario ✓)")

    if "garch_regime" in df_ind.columns:
        reg_pct = df_ind["garch_regime"].value_counts(normalize=True) * 100
        print(f"\n  Distribuzione regimi:")
        for r, p in reg_pct.items():
            print(f"    {r}: {p:.1f}%")

    print("\nEsecuzione 4 versioni strategia...")
    results = run_versions(df_ind)
    print_comparison(results)

    print("\nGenerazione grafici...")
    plot_comparison(results, df_ind)

    # Save summary CSV
    rows = []
    for name, data in results.items():
        m = data["metrics"]
        m["version"] = name
        rows.append(m)
    pd.DataFrame(rows).to_csv(
        os.path.join(OUTPUT_DIR, "enhanced_strategy_comparison.csv"), index=False)
    print("  Saved: enhanced_strategy_comparison.csv")

    # ── Break-even analysis ──────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print("  BREAK-EVEN ANALYSIS — Commissioni vs Sharpe Ratio")
    print(f"{'═'*60}")
    commission_levels = [0.0, 0.0001, 0.0002, 0.0003, 0.0004,
                         0.0005, 0.0008, 0.001, 0.002]
    print(f"  {'Comm/side':>10} {'Slip/side':>10} {'Round-trip':>11} "
          f"{'CAGR%':>8} {'Sharpe':>8}")
    print(f"  {'-'*52}")
    for c in commission_levels:
        slip = 0.0001
        df_s = generate_signals_v2(df_ind, atr_mult_sl=BEST_SL, atr_mult_tp=BEST_TP,
                                    active_hours=BEST_HOURS, use_garch_filter=True)
        res_c = backtest_v2(df_s, INITIAL_CAPITAL, RISK, commission=c, slippage=slip)
        m_c = compute_metrics(res_c, INITIAL_CAPITAL)
        rt = (c + slip) * 2 * 100
        flag = " ← maker fee" if abs(c - 0.0001) < 1e-6 else (
               " ← taker fee" if abs(c - 0.0004) < 1e-6 else "")
        print(f"  {c*100:>9.3f}%  {slip*100:>9.3f}%  {rt:>10.3f}%  "
              f"{m_c.get('cagr_pct',0):>8.1f}  {m_c.get('sharpe_ratio',0):>8.2f}{flag}")

    # ── V5 (Agent): uses agent-proposed parameters ────────────────────────────
    _src = _ACFG.get("source", "default")
    print(f"\n{'═'*60}")
    print(f"  V5 (Agent config — source: {_src})")
    print(f"  SL={BEST_SL}×ATR  TP={BEST_TP}×ATR  "
          f"comm={_A_COMMISSION*100:.3f}%  slip={_A_SLIPPAGE*100:.3f}%")
    print(f"{'═'*60}")
    df_v5 = generate_signals_v2(df_ind,
                                 atr_mult_sl=BEST_SL,
                                 atr_mult_tp=BEST_TP,
                                 active_hours=BEST_HOURS,
                                 use_garch_filter=_ACFG.get("use_garch_filter", True),
                                 rsi_ob=_ACFG.get("rsi_ob", 70),
                                 rsi_os=_ACFG.get("rsi_os", 30),
                                 min_atr_pct=_ACFG.get("min_atr_pct", 0.003))
    res_v5 = backtest_v2(df_v5, INITIAL_CAPITAL, _A_RISK,
                          commission=_A_COMMISSION, slippage=_A_SLIPPAGE)
    m_v5 = compute_metrics(res_v5, INITIAL_CAPITAL)
    for k, v in m_v5.items():
        if isinstance(v, float):
            print(f"  {k:<30} {v:.4f}")
        else:
            print(f"  {k:<30} {v}")

    # Plot V5 equity vs V1
    fig2, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(16, 10), sharex=False)
    eq_v1 = results["V1 Base"]["result"]["equity"]
    eq_v4 = results["V4 +GARCH+Costi"]["result"]["equity"]
    eq_v5 = res_v5["equity"]
    ax_a.plot(eq_v1.index, eq_v1.values, "--", color="#3498DB", label="V1 Base (no costi)")
    ax_a.plot(eq_v4.index, eq_v4.values, "-.", color="#E74C3C", label="V4 +GARCH+Costi (taker)")
    ax_a.plot(eq_v5.index, eq_v5.values, "-",  color="#2ECC71", linewidth=2,
              label=f"V5 Stop2×ATR + Maker (CAGR={m_v5.get('cagr_pct',0):.1f}%,"
                    f" Sharpe={m_v5.get('sharpe_ratio',0):.2f})")
    ax_a.axhline(INITIAL_CAPITAL, color="gray", linewidth=0.8, linestyle=":")
    ax_a.set_title("Confronto Equity: V1 vs V4 vs V5 (Raccomandato per live trading)",
                   fontsize=12, fontweight="bold")
    ax_a.set_ylabel("Capitale (USD)")
    ax_a.legend(fontsize=9)
    ax_a.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # Cost breakdown per strategy
    versions_labels = ["V1\n(nessun costo)", "V2\n(taker 0.04%)", "V4\n(GARCH+taker)", "V5\n(maker 0.01%)"]
    costs_total = [
        0,
        results["V2 +Costi"]["metrics"].get("total_costs_usd", 0),
        results["V4 +GARCH+Costi"]["metrics"].get("total_costs_usd", 0),
        m_v5.get("total_costs_usd", 0),
    ]
    bar_c = ["#3498DB", "#E74C3C", "#F39C12", "#2ECC71"]
    ax_b.bar(versions_labels, costs_total, color=bar_c, edgecolor="white")
    ax_b.set_title("Costi Totali per Versione (USD su $10k capitale)", fontsize=12, fontweight="bold")
    ax_b.set_ylabel("Costi totali (USD)")
    for i, c in enumerate(costs_total):
        ax_b.annotate(f"${c:.0f}", (i, c), ha="center", va="bottom", fontsize=10)

    fig2.tight_layout()
    fig2.savefig(os.path.join(OUTPUT_DIR, "04b_v5_comparison.png"), dpi=150, bbox_inches="tight")
    plt.close(fig2)
    print("\n  Saved: 04b_v5_comparison.png")
    print("\nAnalisi enhanced strategy completata.")
