"""
07_walk_forward.py
==================
Walk-Forward Optimization (WFO) per validazione out-of-sample (OOS).

Procedura:
  - Finestra train: 4 mesi (rolling)
  - Finestra test:  1 mese (OOS)
  - Step:           1 mese
  - Ottimizzazione IS: max Sharpe su griglia parametri (sl_mult × tp_mult)
  - OOS: applica best params al periodo successivo
  - Raccoglie equity OOS concatenata → confronta con equity IS

Metriche di robustezza:
  - Correlazione Sharpe IS vs OOS
  - % fold con OOS Sharpe > 0
  - Degradazione media IS→OOS
  - Walk-Forward Efficiency (WFE)
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
    load_hourly, compute_indicators_v2, generate_signals_v2,
    backtest_v2, compute_metrics, OUTPUT_DIR
)

sns.set_theme(style="darkgrid")

INITIAL_CAPITAL = 10_000
RISK = 0.01
COMMISSION = 0.0004
SLIPPAGE = 0.0001
TRAIN_MONTHS = 4
TEST_MONTHS = 1
HOURS_YEAR = 24 * 30   # ~720 ore per mese

# Griglia ridotta per velocità (già sappiamo le ore ottimali)
PARAM_GRID = [
    (sl, tp)
    for sl in [1.0, 1.5, 2.0]
    for tp in [2.0, 2.5, 3.0]
]
FIXED_HOURS = (6, 22)


def _run_single(df_window: pd.DataFrame, sl: float, tp: float,
                cap: float = INITIAL_CAPITAL) -> dict:
    """Backtest su finestra con parametri dati."""
    df_s = generate_signals_v2(df_window, atr_mult_sl=sl, atr_mult_tp=tp,
                                active_hours=FIXED_HOURS, use_garch_filter=True)
    res = backtest_v2(df_s, cap, RISK, COMMISSION, SLIPPAGE)
    return compute_metrics(res, cap), res


def walk_forward(df_ind: pd.DataFrame) -> dict:
    """
    Esegue la walk-forward optimization e restituisce:
      - fold_results: lista di dict per ogni fold
      - oos_equity: equity OOS concatenata
      - is_equity:  equity IS concatenata (con best params)
    """
    n_bars = len(df_ind)
    train_bars = TRAIN_MONTHS * HOURS_YEAR
    test_bars = TEST_MONTHS * HOURS_YEAR

    if n_bars < train_bars + test_bars:
        print(f"  Dati insufficienti: {n_bars} barre, servono {train_bars+test_bars}")
        return {}

    fold_results = []
    oos_equity_parts = []
    is_equity_parts = []
    oos_capital = INITIAL_CAPITAL  # capitale OOS evolve da fold a fold

    fold = 0
    start_idx = 0

    while start_idx + train_bars + test_bars <= n_bars:
        train_end = start_idx + train_bars
        test_end = train_end + test_bars

        df_train = df_ind.iloc[start_idx:train_end]
        df_test = df_ind.iloc[train_end:test_end]

        if len(df_train) < 200 or len(df_test) < 50:
            break

        # ── IS optimization ──────────────────────────────────────────────
        best_sharpe_is = -np.inf
        best_params = PARAM_GRID[0]
        best_is_res = None

        for sl, tp in PARAM_GRID:
            m, res = _run_single(df_train, sl, tp, INITIAL_CAPITAL)
            if "error" not in m and m["sharpe_ratio"] > best_sharpe_is:
                best_sharpe_is = m["sharpe_ratio"]
                best_params = (sl, tp)
                best_is_res = res

        # ── OOS test ─────────────────────────────────────────────────────
        m_oos, res_oos = _run_single(df_test, *best_params, cap=oos_capital)

        # Aggiorna capitale OOS per il fold successivo
        oos_capital = res_oos["final_capital"]

        period_label = (
            f"{df_train.index[0].strftime('%Y-%m')} – "
            f"{df_test.index[-1].strftime('%Y-%m')}"
        )
        fold_results.append({
            "fold": fold + 1,
            "period": period_label,
            "train_start": df_train.index[0],
            "train_end": df_train.index[-1],
            "test_start": df_test.index[0],
            "test_end": df_test.index[-1],
            "best_sl": best_params[0],
            "best_tp": best_params[1],
            "is_sharpe": best_sharpe_is,
            "oos_sharpe": m_oos.get("sharpe_ratio", 0),
            "is_cagr": compute_metrics(best_is_res, INITIAL_CAPITAL).get("cagr_pct", 0)
                        if best_is_res else 0,
            "oos_cagr": m_oos.get("cagr_pct", 0),
            "oos_maxdd": m_oos.get("max_drawdown_pct", 0),
            "oos_trades": m_oos.get("n_trades", 0),
            "oos_winrate": m_oos.get("win_rate_pct", 0),
        })

        if best_is_res:
            is_equity_parts.append(best_is_res["equity"].iloc[:test_bars]
                                    if len(best_is_res["equity"]) >= test_bars
                                    else best_is_res["equity"])
        oos_equity_parts.append(res_oos["equity"])

        fold += 1
        start_idx += test_bars   # step di 1 mese

        print(f"  Fold {fold:>2}: {period_label}  "
              f"IS Sharpe={best_sharpe_is:>6.2f}  OOS Sharpe={m_oos.get('sharpe_ratio', 0):>6.2f}  "
              f"params=SL{best_params[0]} TP{best_params[1]}")

    # Concatena equity OOS
    if oos_equity_parts:
        oos_equity = pd.concat(oos_equity_parts)
    else:
        oos_equity = pd.Series(dtype=float)

    return {
        "fold_results": pd.DataFrame(fold_results),
        "oos_equity": oos_equity,
        "oos_final_capital": oos_capital,
    }


def compute_wfo_metrics(wfo: dict) -> None:
    folds = wfo["fold_results"]
    oos_eq = wfo["oos_equity"]

    print(f"\n{'═'*65}")
    print("  WALK-FORWARD OPTIMIZATION — RISULTATI")
    print(f"{'═'*65}")
    print(f"\n  Fold analizzati: {len(folds)}")
    print(f"  Capitale OOS finale: ${wfo['oos_final_capital']:,.0f}  "
          f"(da ${INITIAL_CAPITAL:,.0f})")

    if not folds.empty:
        pct_pos = (folds["oos_sharpe"] > 0).mean() * 100
        pct_profit = (folds["oos_cagr"] > 0).mean() * 100
        corr_is_oos, pval = stats.pearsonr(folds["is_sharpe"], folds["oos_sharpe"])
        is_mean = folds["is_sharpe"].mean()
        oos_mean = folds["oos_sharpe"].mean()
        wfe = oos_mean / is_mean if is_mean != 0 else 0

        print(f"\n  Sharpe medio IS:        {is_mean:.3f}")
        print(f"  Sharpe medio OOS:       {oos_mean:.3f}")
        print(f"  WFE (OOS/IS ratio):     {wfe:.3f}  "
              f"({'buono ✓' if wfe > 0.5 else 'overfitting sospetto ⚠'})")
        print(f"  Corr Sharpe IS↔OOS:    {corr_is_oos:.3f}  (p={pval:.3f})")
        print(f"  Fold con OOS Sharpe>0:  {pct_pos:.0f}%")
        print(f"  Fold con OOS CAGR>0:    {pct_profit:.0f}%")
        print(f"  OOS MaxDD medio:        {folds['oos_maxdd'].mean():.1f}%")
        print(f"\n  Parametri più frequenti (best IS):")
        print(f"    SL: {folds['best_sl'].value_counts().to_dict()}")
        print(f"    TP: {folds['best_tp'].value_counts().to_dict()}")

        print(f"\n  {'Fold':>4} {'Periodo':<30} {'SL':>4} {'TP':>4} "
              f"{'IS Sharpe':>10} {'OOS Sharpe':>10} {'OOS CAGR%':>10}")
        print(f"  {'-'*78}")
        for _, r in folds.iterrows():
            flag = "✓" if r["oos_sharpe"] > 0 else "✗"
            print(f"  {int(r['fold']):>4} {r['period']:<30} {r['best_sl']:>4.1f} "
                  f"{r['best_tp']:>4.1f} {r['is_sharpe']:>10.2f} "
                  f"{r['oos_sharpe']:>10.2f} {r['oos_cagr']:>10.1f}% {flag}")


def plot_wfo(wfo: dict):
    folds = wfo["fold_results"]
    oos_eq = wfo["oos_equity"]

    fig = plt.figure(figsize=(20, 26))
    gs = gridspec.GridSpec(5, 2, figure=fig, hspace=0.5, wspace=0.35)

    # ── 1. OOS Equity Curve ─────────────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :])
    if not oos_eq.empty:
        ax1.plot(oos_eq.index, oos_eq.values, color="#2ECC71", linewidth=1.5,
                 label="OOS Equity (concatenata)")
        ax1.axhline(INITIAL_CAPITAL, color="gray", linewidth=0.8, linestyle="--")
        # Vertical lines per fold boundaries
        if not folds.empty:
            for _, r in folds.iterrows():
                ax1.axvline(r["test_start"], color="orange", linewidth=0.8, alpha=0.5)
        ax1.fill_between(oos_eq.index, oos_eq.values, INITIAL_CAPITAL,
                         where=(oos_eq.values >= INITIAL_CAPITAL),
                         alpha=0.2, color="#2ECC71")
        ax1.fill_between(oos_eq.index, oos_eq.values, INITIAL_CAPITAL,
                         where=(oos_eq.values < INITIAL_CAPITAL),
                         alpha=0.3, color="#E74C3C")
    ax1.set_title("Walk-Forward OOS Equity Curve (capitale reale evoluto fold-per-fold)",
                  fontsize=13, fontweight="bold")
    ax1.set_ylabel("Capitale (USD)")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax1.legend()

    # ── 2. OOS Drawdown ─────────────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[1, :])
    if not oos_eq.empty:
        dd = (oos_eq - oos_eq.cummax()) / oos_eq.cummax() * 100
        ax2.fill_between(dd.index, dd.values, 0, color="#E74C3C", alpha=0.7)
    ax2.set_title("OOS Drawdown", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Drawdown (%)")

    # ── 3. IS vs OOS Sharpe scatter ─────────────────────────────────────────
    ax3 = fig.add_subplot(gs[2, 0])
    if not folds.empty:
        sc = ax3.scatter(folds["is_sharpe"], folds["oos_sharpe"],
                         c=folds["fold"], cmap="viridis", s=80, zorder=5)
        plt.colorbar(sc, ax=ax3, label="Fold #")
        # Regression line
        x = folds["is_sharpe"].values
        y = folds["oos_sharpe"].values
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        x_line = np.linspace(x.min(), x.max(), 50)
        ax3.plot(x_line, p(x_line), "r--", linewidth=1.5)
        ax3.axhline(0, color="black", linewidth=0.8)
        ax3.axvline(0, color="black", linewidth=0.8)
        corr, pv = stats.pearsonr(x, y)
        ax3.set_title(f"IS vs OOS Sharpe (r={corr:.2f}, p={pv:.3f})",
                      fontsize=12, fontweight="bold")
        ax3.set_xlabel("IS Sharpe")
        ax3.set_ylabel("OOS Sharpe")

    # ── 4. Sharpe IS vs OOS per fold (bar) ──────────────────────────────────
    ax4 = fig.add_subplot(gs[2, 1])
    if not folds.empty:
        x = np.arange(len(folds))
        w = 0.35
        ax4.bar(x - w/2, folds["is_sharpe"].values, w, label="IS", color="#3498DB", alpha=0.8)
        ax4.bar(x + w/2, folds["oos_sharpe"].values, w, label="OOS",
                color=["#2ECC71" if s > 0 else "#E74C3C" for s in folds["oos_sharpe"].values],
                alpha=0.8)
        ax4.axhline(0, color="black", linewidth=0.8)
        ax4.set_xticks(x)
        ax4.set_xticklabels([f"F{int(f)}" for f in folds["fold"].values], fontsize=8)
        ax4.set_title("Sharpe IS vs OOS per Fold", fontsize=12, fontweight="bold")
        ax4.legend()

    # ── 5. Best parameters stability ────────────────────────────────────────
    ax5 = fig.add_subplot(gs[3, 0])
    if not folds.empty:
        ax5.plot(folds["fold"].values, folds["best_sl"].values, "o-",
                 color="#E74C3C", label="Best SL ×ATR")
        ax5.plot(folds["fold"].values, folds["best_tp"].values, "s-",
                 color="#3498DB", label="Best TP ×ATR")
        ax5.set_title("Stabilità Parametri Ottimali per Fold", fontsize=12, fontweight="bold")
        ax5.set_xlabel("Fold #")
        ax5.set_ylabel("Moltiplicatore ATR")
        ax5.legend()
        ax5.set_xticks(folds["fold"].values)

    # ── 6. OOS CAGR per fold ────────────────────────────────────────────────
    ax6 = fig.add_subplot(gs[3, 1])
    if not folds.empty:
        colors_oos = ["#2ECC71" if v > 0 else "#E74C3C" for v in folds["oos_cagr"].values]
        ax6.bar(folds["fold"].values, folds["oos_cagr"].values, color=colors_oos)
        ax6.axhline(0, color="black", linewidth=0.8)
        ax6.set_title("OOS CAGR% per Fold", fontsize=12, fontweight="bold")
        ax6.set_xlabel("Fold #")
        ax6.set_ylabel("CAGR%")

    # ── 7. OOS cumulative returns distribution ───────────────────────────────
    ax7 = fig.add_subplot(gs[4, :])
    if not folds.empty and not oos_eq.empty:
        monthly_ret = oos_eq.resample("ME").last().pct_change().dropna() * 100
        colors_m = ["#2ECC71" if v > 0 else "#E74C3C" for v in monthly_ret.values]
        ax7.bar(range(len(monthly_ret)), monthly_ret.values, color=colors_m)
        ax7.axhline(0, color="black", linewidth=0.8)
        tick_step = max(1, len(monthly_ret) // 12)
        ax7.set_xticks(range(0, len(monthly_ret), tick_step))
        ax7.set_xticklabels([str(d.strftime("%b%y")) for d in monthly_ret.index[::tick_step]],
                             rotation=45, fontsize=8)
        ax7.set_title("Rendimenti Mensili OOS", fontsize=12, fontweight="bold")
        ax7.set_ylabel("Return mensile (%)")

    fig.suptitle("BTC/USD — Walk-Forward Optimization (train=4m, test=1m, step=1m)",
                 fontsize=15, fontweight="bold")
    plt.savefig(os.path.join(OUTPUT_DIR, "05_walk_forward.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved: 05_walk_forward.png")


if __name__ == "__main__":
    print("Caricamento dati orari BTC...")
    df_raw = load_hourly("BTC")

    print("Calcolo indicatori + GARCH(1,1)...")
    df_ind = compute_indicators_v2(df_raw, fit_garch=True)
    print(f"  {len(df_ind)} barre disponibili per WFO")

    print(f"\nAvvio Walk-Forward Optimization")
    print(f"  Train: {TRAIN_MONTHS} mesi | Test: {TEST_MONTHS} mese | Grid: {len(PARAM_GRID)} combo")
    print(f"  {'─'*78}")
    wfo = walk_forward(df_ind)

    if wfo:
        compute_wfo_metrics(wfo)
        print("\nGenerazione grafici WFO...")
        plot_wfo(wfo)
        wfo["fold_results"].to_csv(
            os.path.join(OUTPUT_DIR, "walk_forward_results.csv"), index=False)
        print("  Saved: walk_forward_results.csv")

    print("\nWalk-Forward completato.")
