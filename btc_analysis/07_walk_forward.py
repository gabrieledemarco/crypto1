"""
07_walk_forward.py
==================
Walk-Forward Optimization (WFO) con:
  - Finestre estese: IS=8 mesi, OOS=2 mesi, step=2 mesi
  - Multi-window sensitivity: confronto 4 configurazioni IS/OOS
  - Statistical significance: t-test su OOS returns, IC (Information Coefficient)
  - Walk-Forward Efficiency (WFE = OOS_sharpe / IS_sharpe)
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
from scipy import stats
from strategy_core import (
    load_hourly, compute_indicators_v2,
    backtest_v2, compute_metrics, load_agent_config, load_agent_strategy, OUTPUT_DIR
)

sns.set_theme(style="darkgrid")

INITIAL_CAPITAL = 10_000
RISK            = 0.01
HOURS_MONTH     = 24 * 30   # ~720 ore/mese

# Load agent config — drives fixed hours and param grid centre
_ACFG       = load_agent_config()
COMMISSION  = _ACFG.get("commission", 0.0004)
SLIPPAGE    = _ACFG.get("slippage",   0.0001)
FIXED_HOURS = tuple(_ACFG["active_hours"])

# SL/TP scale grid: the agent strategy sets its own SL_dist/TP_dist;
# WFO searches for the best multiplicative scale factor around 1.0
SL_TP_SCALES = [0.75, 1.0, 1.25]

# Load agent signal function once at module level
_AGENT_FN = load_agent_strategy()

# Configurazioni IS/OOS da confrontare
WINDOW_CONFIGS = [
    {"label": "IS=4m OOS=1m",  "train": 4,  "test": 1,  "step": 1},
    {"label": "IS=6m OOS=2m",  "train": 6,  "test": 2,  "step": 2},
    {"label": "IS=8m OOS=2m",  "train": 8,  "test": 2,  "step": 2},
    {"label": "IS=8m OOS=3m",  "train": 8,  "test": 3,  "step": 2},
]


# ── Core: singolo backtest ────────────────────────────────────────────────────

def _run(df_win: pd.DataFrame, sl_scale: float, tp_scale: float, cap: float) -> dict:
    """Run agent strategy with SL/TP scaled by the given multipliers."""
    df_s = _AGENT_FN(df_win)
    df_s["SL_dist"] = df_s["SL_dist"] * sl_scale
    df_s["TP_dist"] = df_s["TP_dist"] * tp_scale
    res = backtest_v2(df_s, cap, RISK, COMMISSION, SLIPPAGE)
    return compute_metrics(res, cap), res


# ── WFO per una coppia di finestre ────────────────────────────────────────────

def walk_forward(df_ind: pd.DataFrame, train_m: int, test_m: int, step_m: int,
                 label: str) -> dict:
    train_bars = train_m * HOURS_MONTH
    test_bars  = test_m  * HOURS_MONTH
    step_bars  = step_m  * HOURS_MONTH
    n_bars     = len(df_ind)

    if n_bars < train_bars + test_bars:
        print(f"  [{label}] Dati insufficienti ({n_bars} barre)")
        return {}

    fold_results  = []
    oos_parts     = []
    oos_capital   = INITIAL_CAPITAL
    start_idx     = 0
    fold          = 0

    while start_idx + train_bars + test_bars <= n_bars:
        train_end = start_idx + train_bars
        test_end  = train_end + test_bars

        df_train = df_ind.iloc[start_idx:train_end]
        df_test  = df_ind.iloc[train_end:test_end]

        if len(df_train) < 200 or len(df_test) < 24:
            break

        # ── IS optimisation: search SL/TP scale factors ──────────────────────
        best_sh, best_p, best_res_is = -np.inf, (1.0, 1.0), None
        for sl_s in SL_TP_SCALES:
            for tp_s in SL_TP_SCALES:
                m, res = _run(df_train, sl_s, tp_s, INITIAL_CAPITAL)
                if "error" not in m and m["sharpe_ratio"] > best_sh:
                    best_sh, best_p, best_res_is = m["sharpe_ratio"], (sl_s, tp_s), res

        # ── OOS test ─────────────────────────────────────────────────────────
        m_oos, res_oos = _run(df_test, *best_p, cap=oos_capital)
        oos_capital = res_oos["final_capital"]

        fold_results.append({
            "fold":       fold + 1,
            "period":     f"{df_train.index[0].strftime('%Y-%m')} → "
                          f"{df_test.index[-1].strftime('%Y-%m')}",
            "train_start": df_train.index[0],
            "test_start":  df_test.index[0],
            "test_end":    df_test.index[-1],
            "best_sl_scale": best_p[0],
            "best_tp_scale": best_p[1],
            "is_sharpe":   best_sh,
            "oos_sharpe":  m_oos.get("sharpe_ratio", 0),
            "is_cagr":     compute_metrics(best_res_is, INITIAL_CAPITAL).get("cagr_pct", 0)
                           if best_res_is else 0,
            "oos_cagr":    m_oos.get("cagr_pct", 0),
            "oos_maxdd":   m_oos.get("max_drawdown_pct", 0),
            "oos_trades":  m_oos.get("n_trades", 0),
            "oos_winrate": m_oos.get("win_rate_pct", 0),
        })
        oos_parts.append(res_oos["equity"])

        fold += 1
        start_idx += step_bars

    if not fold_results:
        return {}

    folds_df   = pd.DataFrame(fold_results)
    oos_equity = pd.concat(oos_parts) if oos_parts else pd.Series(dtype=float)

    # ── Aggregate metrics ────────────────────────────────────────────────────
    is_m  = folds_df["is_sharpe"].mean()
    oos_m = folds_df["oos_sharpe"].mean()
    wfe   = oos_m / is_m if is_m != 0 else 0
    pct_pos = (folds_df["oos_sharpe"] > 0).mean() * 100

    # t-test: OOS sharpe significativamente diverso da 0?
    t_stat, p_val = stats.ttest_1samp(folds_df["oos_sharpe"], 0)

    # IC: correlazione IS_sharpe → OOS_sharpe
    if len(folds_df) > 2:
        ic, ic_p = stats.pearsonr(folds_df["is_sharpe"], folds_df["oos_sharpe"])
    else:
        ic, ic_p = 0, 1

    return {
        "label":       label,
        "train_m":     train_m,
        "test_m":      test_m,
        "n_folds":     len(folds_df),
        "folds":       folds_df,
        "oos_equity":  oos_equity,
        "oos_final":   oos_capital,
        "is_sharpe":   is_m,
        "oos_sharpe":  oos_m,
        "wfe":         wfe,
        "pct_pos":     pct_pos,
        "t_stat":      t_stat,
        "p_val":       p_val,
        "ic":          ic,
        "ic_p":        ic_p,
    }


# ── Print singolo WFO ─────────────────────────────────────────────────────────

def print_wfo(w: dict):
    folds = w["folds"]
    print(f"\n{'═'*72}")
    print(f"  WFO: {w['label']}  |  {w['n_folds']} fold")
    print(f"{'═'*72}")
    print(f"  IS Sharpe medio:      {w['is_sharpe']:+.3f}")
    print(f"  OOS Sharpe medio:     {w['oos_sharpe']:+.3f}")
    print(f"  WFE (OOS/IS):         {w['wfe']:+.3f}  "
          f"{'✓ robusto' if w['wfe'] > 0.5 else '⚠ overfitting'}")
    print(f"  Fold OOS Sharpe > 0:  {w['pct_pos']:.0f}%")
    print(f"  t-test OOS≠0:         t={w['t_stat']:.2f}  p={w['p_val']:.3f}  "
          f"{'★ significativo' if w['p_val'] < 0.05 else 'non sign.'}")
    print(f"  IC IS↔OOS:            r={w['ic']:.3f}  p={w['ic_p']:.3f}")
    print(f"  Capitale OOS finale:  ${w['oos_final']:,.0f}")
    print(f"\n  {'Fold':>4}  {'Periodo':<26}  {'SL':>4} {'TP':>4}  "
          f"{'IS Sh':>7} {'OOS Sh':>8} {'OOS CAGR':>9}")
    print(f"  {'─'*68}")
    for _, r in folds.iterrows():
        ok = "✓" if r["oos_sharpe"] > 0 else "✗"
        sl_tp = (f"{r['best_sl']:>4.1f} {r['best_tp']:>4.1f}"
                 if "best_sl" in r.index else "  —   —")
        print(f"  {int(r['fold']):>4}  {r.get('period','?'):<26}  "
              f"{sl_tp}  "
              f"{r['is_sharpe']:>7.2f} {r['oos_sharpe']:>8.2f} "
              f"{r['oos_cagr']:>9.1f}%  {ok}")


# ── Plot confronto multi-window ───────────────────────────────────────────────

def plot_multi_window(wfos: list):
    fig = plt.figure(figsize=(22, 30))
    gs  = gridspec.GridSpec(6, 2, figure=fig, hspace=0.55, wspace=0.35)

    COLORS = ["#3498DB", "#2ECC71", "#E74C3C", "#F39C12"]

    # ── 1. OOS equity curves tutte le config ────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :])
    for w, c in zip(wfos, COLORS):
        eq = w["oos_equity"]
        if eq.empty:
            continue
        lbl = (f"{w['label']}  "
               f"(WFE={w['wfe']:+.2f}, OOS Sh={w['oos_sharpe']:+.2f})")
        ax1.plot(eq.index, eq.values, color=c, linewidth=1.8, label=lbl)
    ax1.axhline(INITIAL_CAPITAL, color="gray", linewidth=0.8, linestyle="--")
    ax1.set_title("OOS Equity Curve — Confronto Finestre IS/OOS", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Capitale (USD)")
    ax1.legend(fontsize=9)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # ── 2. WFE per configurazione ────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[1, 0])
    labels = [w["label"] for w in wfos]
    wfes   = [w["wfe"]    for w in wfos]
    bar_c  = ["#2ECC71" if v > 0.5 else ("#F39C12" if v > 0 else "#E74C3C")
               for v in wfes]
    ax2.bar(range(len(wfos)), wfes, color=bar_c, edgecolor="white")
    ax2.axhline(0.5,  color="green",  linewidth=1.2, linestyle="--", label="WFE=0.5 (target)")
    ax2.axhline(0.0,  color="black",  linewidth=0.8)
    ax2.set_xticks(range(len(wfos)))
    ax2.set_xticklabels([l.replace(" ", "\n") for l in labels], fontsize=8)
    ax2.set_title("Walk-Forward Efficiency per Config", fontsize=12, fontweight="bold")
    ax2.set_ylabel("WFE")
    ax2.legend(fontsize=8)
    for i, v in enumerate(wfes):
        ax2.annotate(f"{v:.2f}", (i, v), ha="center",
                     va="bottom" if v >= 0 else "top", fontsize=9)

    # ── 3. OOS Sharpe medio per config ──────────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 1])
    oos_sh = [w["oos_sharpe"] for w in wfos]
    is_sh  = [w["is_sharpe"]  for w in wfos]
    x = np.arange(len(wfos))
    ax3.bar(x - 0.2, is_sh,  0.35, color="#3498DB", label="IS Sharpe",  alpha=0.85)
    ax3.bar(x + 0.2, oos_sh, 0.35,
            color=["#2ECC71" if v > 0 else "#E74C3C" for v in oos_sh],
            label="OOS Sharpe", alpha=0.85)
    ax3.axhline(0, color="black", linewidth=0.8)
    ax3.set_xticks(x)
    ax3.set_xticklabels([l.replace(" ", "\n") for l in labels], fontsize=8)
    ax3.set_title("IS vs OOS Sharpe medio per Config", fontsize=12, fontweight="bold")
    ax3.legend()

    # ── 4. Heatmap IS_sharpe per fold — config principale (IS=8m OOS=2m) ───
    best_wfo = max(wfos, key=lambda w: w["wfe"])
    ax4 = fig.add_subplot(gs[2, :])
    folds = best_wfo["folds"]
    ax4b  = ax4.twinx()
    x_f   = np.arange(len(folds))
    w_bar = 0.35
    ax4.bar(x_f - w_bar/2, folds["is_sharpe"].values,  w_bar,
            color="#3498DB", alpha=0.75, label="IS Sharpe")
    ax4.bar(x_f + w_bar/2, folds["oos_sharpe"].values, w_bar,
            color=["#2ECC71" if s > 0 else "#E74C3C" for s in folds["oos_sharpe"]],
            alpha=0.85, label="OOS Sharpe")
    ax4b.plot(x_f, folds["oos_cagr"].values, "o--",
              color="#F39C12", linewidth=1.4, markersize=5, label="OOS CAGR%")
    ax4.axhline(0, color="black", linewidth=0.8)
    ax4.set_xticks(x_f)
    ax4.set_xticklabels([r["period"].replace(" → ", "\n→") for _, r in folds.iterrows()],
                         fontsize=7, rotation=30)
    ax4.set_title(f"Sharpe IS vs OOS per Fold — {best_wfo['label']}",
                  fontsize=12, fontweight="bold")
    ax4.set_ylabel("Sharpe")
    ax4b.set_ylabel("OOS CAGR%")
    lines1, lab1 = ax4.get_legend_handles_labels()
    lines2, lab2 = ax4b.get_legend_handles_labels()
    ax4.legend(lines1 + lines2, lab1 + lab2, fontsize=9)

    # ── 5. IS vs OOS scatter — config principale ─────────────────────────────
    ax5 = fig.add_subplot(gs[3, 0])
    x_s = folds["is_sharpe"].values
    y_s = folds["oos_sharpe"].values
    sc  = ax5.scatter(x_s, y_s, c=range(len(folds)), cmap="viridis", s=80, zorder=5)
    plt.colorbar(sc, ax=ax5, label="Fold #")
    if len(x_s) > 2:
        z  = np.polyfit(x_s, y_s, 1)
        xl = np.linspace(x_s.min(), x_s.max(), 50)
        ax5.plot(xl, np.poly1d(z)(xl), "r--", linewidth=1.5)
    ax5.axhline(0, color="black", linewidth=0.8)
    ax5.axvline(0, color="black", linewidth=0.8)
    ax5.set_title(f"IS↔OOS Sharpe Scatter — {best_wfo['label']}\n"
                  f"IC={best_wfo['ic']:.3f}  p={best_wfo['ic_p']:.3f}",
                  fontsize=11, fontweight="bold")
    ax5.set_xlabel("IS Sharpe")
    ax5.set_ylabel("OOS Sharpe")

    # ── 6. OOS drawdown — config principale ──────────────────────────────────
    ax6 = fig.add_subplot(gs[3, 1])
    eq_best = best_wfo["oos_equity"]
    if not eq_best.empty:
        dd = (eq_best - eq_best.cummax()) / eq_best.cummax() * 100
        ax6.fill_between(dd.index, dd.values, 0, color="#E74C3C", alpha=0.7)
        ax6.set_title(f"OOS Drawdown — {best_wfo['label']}", fontsize=12, fontweight="bold")
        ax6.set_ylabel("Drawdown (%)")

    # ── 7. Param stability ────────────────────────────────────────────────────
    ax7 = fig.add_subplot(gs[4, 0])
    if "best_sl" in folds.columns and "best_tp" in folds.columns:
        ax7.plot(folds["fold"], folds["best_sl"], "o-", color="#E74C3C", label="SL ×ATR")
        ax7.plot(folds["fold"], folds["best_tp"], "s-", color="#3498DB", label="TP ×ATR")
        ax7.legend()
        ax7.set_ylabel("Moltiplicatore ATR")
    else:
        ax7.text(0.5, 0.5, "Params fissi (no grid search)", ha="center", va="center",
                 transform=ax7.transAxes, fontsize=11, color="gray")
    ax7.set_title("Stabilità Parametri per Fold", fontsize=12, fontweight="bold")
    ax7.set_xlabel("Fold")
    ax7.set_xticks(folds["fold"])

    # ── 8. Riepilogo statistico WFE vs n_fold ────────────────────────────────
    ax8 = fig.add_subplot(gs[4, 1])
    n_folds_list = [w["n_folds"]  for w in wfos]
    wfe_list     = [w["wfe"]      for w in wfos]
    pct_pos_list = [w["pct_pos"]  for w in wfos]
    ax8.scatter(n_folds_list, wfe_list, s=120, c=COLORS[:len(wfos)], zorder=5)
    for w, c in zip(wfos, COLORS):
        ax8.annotate(w["label"], (w["n_folds"], w["wfe"]),
                     textcoords="offset points", xytext=(5, 5), fontsize=8, color=c)
    ax8.axhline(0, color="black", linewidth=0.8)
    ax8.axhline(0.5, color="green", linewidth=1, linestyle="--")
    ax8.set_title("WFE vs N Fold per Configurazione", fontsize=12, fontweight="bold")
    ax8.set_xlabel("Numero di fold")
    ax8.set_ylabel("WFE")

    # ── 9. Rendimenti mensili OOS — config principale ─────────────────────────
    ax9 = fig.add_subplot(gs[5, :])
    if not eq_best.empty:
        monthly = eq_best.resample("ME").last().pct_change().dropna() * 100
        colors_m = ["#2ECC71" if v > 0 else "#E74C3C" for v in monthly.values]
        ax9.bar(range(len(monthly)), monthly.values, color=colors_m, edgecolor="white")
        ax9.axhline(0, color="black", linewidth=0.8)
        step_t = max(1, len(monthly) // 10)
        ax9.set_xticks(range(0, len(monthly), step_t))
        ax9.set_xticklabels(
            [monthly.index[i].strftime("%b%y") for i in range(0, len(monthly), step_t)],
            rotation=45, fontsize=8)
        ax9.set_title(f"Rendimenti Mensili OOS — {best_wfo['label']}", fontsize=12, fontweight="bold")
        ax9.set_ylabel("Return %")

    fig.suptitle("Walk-Forward Optimization — Analisi Multi-Window (IS/OOS estesi)",
                 fontsize=14, fontweight="bold")
    plt.savefig(os.path.join(OUTPUT_DIR, "05_walk_forward.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved: 05_walk_forward.png")


# ── Riepilogo comparativo ─────────────────────────────────────────────────────

def print_summary(wfos: list):
    print(f"\n{'═'*80}")
    print("  RIEPILOGO CONFRONTO FINESTRE IS/OOS")
    print(f"{'═'*80}")
    print(f"  {'Config':<18} {'Fold':>5} {'IS Sh':>8} {'OOS Sh':>9} {'WFE':>7} "
          f"{'%>0':>5} {'t-p':>7} {'IC':>6}  {'Cap OOS':>10}")
    print(f"  {'─'*76}")
    for w in wfos:
        sig = "★" if w["p_val"] < 0.05 else " "
        print(f"  {w['label']:<18} {w['n_folds']:>5} {w['is_sharpe']:>8.2f} "
              f"{w['oos_sharpe']:>9.2f} {w['wfe']:>7.2f} "
              f"{w['pct_pos']:>5.0f}% {w['p_val']:>7.3f} {w['ic']:>6.3f} "
              f" ${w['oos_final']:>9,.0f}  {sig}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Caricamento dati orari BTC...")
    df_raw = load_hourly("BTC")

    print("Calcolo indicatori + GARCH(1,1)...")
    df_ind = compute_indicators_v2(df_raw, fit_garch=True)
    print(f"  {len(df_ind)} barre disponibili  "
          f"({df_ind.index[0].date()} → {df_ind.index[-1].date()})")

    wfos = []
    for cfg in WINDOW_CONFIGS:
        print(f"\n{'─'*60}")
        print(f"  Avvio WFO: {cfg['label']}  "
              f"(train={cfg['train']}m, test={cfg['test']}m, step={cfg['step']}m)")
        w = walk_forward(df_ind,
                         train_m=cfg["train"],
                         test_m=cfg["test"],
                         step_m=cfg["step"],
                         label=cfg["label"])
        if w:
            print_wfo(w)
            wfos.append(w)
            w["folds"].to_csv(
                os.path.join(OUTPUT_DIR,
                             f"wfo_{cfg['label'].replace(' ', '_').replace('=','')}.csv"),
                index=False)

    if wfos:
        print_summary(wfos)
        print("\nGenerazione grafici multi-window...")
        plot_multi_window(wfos)

    print("\nWalk-Forward completato.")
