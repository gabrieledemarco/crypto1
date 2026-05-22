"""
09_monte_carlo.py
=================
Simulazione Monte Carlo della strategia V5
(SL=2×ATR, TP=5×ATR, maker fee 0.01%, GARCH filter)

Struttura:
  1. MC Engine     — bootstrap vectorizzato (10.000 simulazioni)
  2. Parametric MC — fit t-skewed + generazione sequenze sintetiche
  3. Stress tests  — 4 scenari avversi
  4. Visualizzazioni — fan chart, distribuzioni, stress, serial correlation
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
from statsmodels.tsa.stattools import acf
from strategy_core import (
    load_hourly, compute_indicators_v2,
    backtest_v2, compute_metrics, load_agent_config, load_agent_strategy, OUTPUT_DIR
)

_ACFG     = load_agent_config()
_AGENT_FN = load_agent_strategy()

np.random.seed(42)
sns.set_theme(style="darkgrid")

INITIAL_CAPITAL = 10_000
N_SIMS          = 10_000      # simulazioni bootstrap
N_YEARS         = 2.33        # durata dataset orario (gen 2023 – apr 2025)


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 1 — ENGINE: caricamento trade V5
# ══════════════════════════════════════════════════════════════════════════════

def get_v5_trades() -> pd.DataFrame:
    """Esegue la strategia agent e restituisce i trade per il Monte Carlo."""
    df_raw = load_hourly("BTC")
    df_ind = compute_indicators_v2(df_raw, fit_garch=True)
    df_sig = _AGENT_FN(df_ind)
    res = backtest_v2(df_sig, INITIAL_CAPITAL,
                      risk_per_trade=_ACFG.get("risk_per_trade", 0.01),
                      commission=_ACFG.get("commission", 0.0001),
                      slippage=_ACFG.get("slippage", 0.0001))
    trades = res["trades"].copy()
    if "entry_time" in trades.columns and "exit_time" in trades.columns:
        trades["duration_h"] = (
            trades["exit_time"] - trades["entry_time"]
        ).dt.total_seconds() / 3600
    return trades, res["equity"]


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 2 — BOOTSTRAP VECTORIZZATO
# ══════════════════════════════════════════════════════════════════════════════

def run_bootstrap(pnl: np.ndarray,
                  n_sims: int = N_SIMS,
                  capital: float = INITIAL_CAPITAL) -> dict:
    """
    Bootstrap MC: ricampiona i P&L dei trade con replacement.
    Tutto vectorizzato — matrice (n_sims × K).
    """
    K   = len(pnl)
    idx = np.random.randint(0, K, size=(n_sims, K))        # (N, K)
    sim = pnl[idx]                                          # (N, K) P&L ricampionati

    # Equity curves
    eq = capital + np.cumsum(sim, axis=1)                   # (N, K)

    # ── Metriche per simulazione ─────────────────────────────────────────────
    final_cap = eq[:, -1]
    total_ret = (final_cap / capital - 1) * 100
    cagr      = ((final_cap / capital) ** (1 / N_YEARS) - 1) * 100

    # Max drawdown
    running_max = np.maximum.accumulate(eq, axis=1)
    dd          = (eq - running_max) / running_max * 100
    max_dd      = dd.min(axis=1)

    # Sharpe (trade-level, annualizzato)
    r_per_trade = sim / capital
    sharpe = (r_per_trade.mean(axis=1)
              / (r_per_trade.std(axis=1) + 1e-12)
              * np.sqrt(K / N_YEARS))

    # Calmar
    calmar = np.where(max_dd != 0, cagr / np.abs(max_dd), np.inf)

    # Probabilità di ruin: equity scende sotto il 70% del capitale iniziale
    ruin_threshold = capital * 0.70
    p_ruin = (eq.min(axis=1) < ruin_threshold).mean() * 100

    # Target probabilities
    p_50   = (final_cap >= capital * 1.50).mean() * 100
    p_100  = (final_cap >= capital * 2.00).mean() * 100
    p_200  = (final_cap >= capital * 3.00).mean() * 100

    # VaR e CVaR (sulla distribuzione dei rendimenti totali)
    var_95  = np.percentile(total_ret, 5)
    var_99  = np.percentile(total_ret, 1)
    cvar_95 = total_ret[total_ret <= var_95].mean()
    cvar_99 = total_ret[total_ret <= var_99].mean()

    # Percentili equity al passo finale
    pctiles = {p: np.percentile(final_cap, p)
               for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]}

    return {
        "equity_matrix": eq,
        "final_cap":     final_cap,
        "total_ret":     total_ret,
        "cagr":          cagr,
        "max_dd":        max_dd,
        "sharpe":        sharpe,
        "calmar":        calmar,
        "p_ruin":        p_ruin,
        "p_50":          p_50,
        "p_100":         p_100,
        "p_200":         p_200,
        "var_95":        var_95,
        "var_99":        var_99,
        "cvar_95":       cvar_95,
        "cvar_99":       cvar_99,
        "pctiles":       pctiles,
        "K":             K,
    }


def print_bootstrap_stats(bs: dict, label: str = "Bootstrap"):
    fc = bs["final_cap"]
    print(f"\n{'═'*60}")
    print(f"  {label}  (N={N_SIMS:,} simulazioni, K={bs['K']} trade)")
    print(f"{'═'*60}")
    print(f"  Capitale finale — mediana:  ${np.median(fc):>10,.0f}")
    print(f"  Capitale finale — media:    ${fc.mean():>10,.0f}")
    print(f"  Capitale finale — std:      ${fc.std():>10,.0f}")
    print(f"")
    print(f"  Percentili capitale finale:")
    for p, v in bs["pctiles"].items():
        bar = "█" * int(max(0, (v - INITIAL_CAPITAL) / 500))
        print(f"    {p:>3}°: ${v:>10,.0f}  {bar}")
    print(f"")
    print(f"  CAGR  — mediana: {np.median(bs['cagr']):>+7.1f}%  "
          f"[5°={np.percentile(bs['cagr'],5):+.1f}%  "
          f"95°={np.percentile(bs['cagr'],95):+.1f}%]")
    print(f"  Sharpe— mediana: {np.median(bs['sharpe']):>+7.2f}  "
          f"[5°={np.percentile(bs['sharpe'],5):+.2f}  "
          f"95°={np.percentile(bs['sharpe'],95):+.2f}]")
    print(f"  MaxDD — mediana: {np.median(bs['max_dd']):>+7.1f}%  "
          f"[5°={np.percentile(bs['max_dd'],5):+.1f}%  "
          f"95°={np.percentile(bs['max_dd'],95):+.1f}%]")
    print(f"")
    print(f"  VaR 95%:   {bs['var_95']:>+7.1f}%   CVaR 95%: {bs['cvar_95']:>+7.1f}%")
    print(f"  VaR 99%:   {bs['var_99']:>+7.1f}%   CVaR 99%: {bs['cvar_99']:>+7.1f}%")
    print(f"")
    print(f"  P(ruin  <−30%): {bs['p_ruin']:>5.1f}%")
    print(f"  P(+50%)       : {bs['p_50']:>5.1f}%")
    print(f"  P(+100%)      : {bs['p_100']:>5.1f}%")
    print(f"  P(+200%)      : {bs['p_200']:>5.1f}%")


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 3 — MC PARAMETRICO
# ══════════════════════════════════════════════════════════════════════════════

def run_parametric_mc(pnl: np.ndarray,
                      n_sims: int = N_SIMS,
                      capital: float = INITIAL_CAPITAL) -> dict:
    """
    MC parametrico: fitta distribuzione t-skewed ai P&L reali,
    genera N×K sequenze sintetiche e costruisce equity curves.
    """
    K = len(pnl)

    # Fit t-skewed (scipy skewnorm approssima bene con fat tails)
    params_norm = stats.norm.fit(pnl)
    params_t    = stats.t.fit(pnl)          # (df, loc, scale)

    # Genera trade sintetici dalla t di Student fittata
    df_t, loc_t, scale_t = params_t
    synthetic = stats.t.rvs(df_t, loc=loc_t, scale=scale_t,
                             size=(n_sims, K))

    eq      = capital + np.cumsum(synthetic, axis=1)
    final_c = eq[:, -1]
    tot_ret = (final_c / capital - 1) * 100
    cagr_p  = ((final_c / capital) ** (1 / N_YEARS) - 1) * 100

    run_max = np.maximum.accumulate(eq, axis=1)
    dd      = (eq - run_max) / run_max * 100
    max_dd  = dd.min(axis=1)

    r_pt   = synthetic / capital
    sharpe = (r_pt.mean(axis=1)
              / (r_pt.std(axis=1) + 1e-12)
              * np.sqrt(K / N_YEARS))

    return {
        "equity_matrix": eq,
        "final_cap":     final_c,
        "total_ret":     tot_ret,
        "cagr":          cagr_p,
        "max_dd":        max_dd,
        "sharpe":        sharpe,
        "t_params":      params_t,
        "K":             K,
    }


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 4 — STRESS TESTS
# ══════════════════════════════════════════════════════════════════════════════

def run_stress_tests(trades: pd.DataFrame,
                     capital: float = INITIAL_CAPITAL) -> dict:
    """
    4 scenari avversi applicati alla sequenza di trade reali:
      S1: Win rate  −10%  (converte 10% dei win in loss)
      S2: Avg loss  +30%  (peggiora le perdite del 30%)
      S3: S1 + S2   combinati
      S4: Sidewalk  (elimina i long trade — solo short, mercato laterale)
    """
    pnl_real = trades["pnl"].values.copy()
    results  = {}

    def equity_from_pnl(arr):
        eq = capital + np.cumsum(arr)
        return pd.Series(eq)

    def metrics_from_equity(eq_s, pnl_arr):
        fc = eq_s.iloc[-1]
        tr = (fc / capital - 1) * 100
        cg = ((fc / capital) ** (1 / N_YEARS) - 1) * 100
        rm = eq_s.cummax()
        dd = ((eq_s - rm) / rm * 100).min()
        r  = pnl_arr / capital
        sh = r.mean() / (r.std() + 1e-12) * np.sqrt(len(r) / N_YEARS)
        return {"cagr": cg, "total_ret": tr, "max_dd": dd, "sharpe": sh,
                "n_trades": len(pnl_arr), "final_cap": fc}

    # Baseline V5 reale
    eq_base = equity_from_pnl(pnl_real)
    results["V5 Baseline"] = {
        "equity": eq_base,
        **metrics_from_equity(eq_base, pnl_real),
        "color": "#2ECC71",
    }

    # S1: Win rate −10%
    pnl_s1 = pnl_real.copy()
    win_idx = np.where(pnl_s1 > 0)[0]
    n_flip  = max(1, int(len(win_idx) * 0.10))
    flip_idx = np.random.choice(win_idx, n_flip, replace=False)
    pnl_s1[flip_idx] = -np.abs(pnl_s1[flip_idx]) * 0.8
    eq_s1 = equity_from_pnl(pnl_s1)
    results["S1: Win Rate −10%"] = {
        "equity": eq_s1,
        **metrics_from_equity(eq_s1, pnl_s1),
        "color": "#F39C12",
    }

    # S2: Avg loss +30%
    pnl_s2 = pnl_real.copy()
    loss_idx = np.where(pnl_s2 < 0)[0]
    pnl_s2[loss_idx] *= 1.30
    eq_s2 = equity_from_pnl(pnl_s2)
    results["S2: Avg Loss +30%"] = {
        "equity": eq_s2,
        **metrics_from_equity(eq_s2, pnl_s2),
        "color": "#E67E22",
    }

    # S3: S1 + S2
    pnl_s3 = pnl_s2.copy()
    win_idx3 = np.where(pnl_s3 > 0)[0]
    n_flip3  = max(1, int(len(win_idx3) * 0.10))
    flip3    = np.random.choice(win_idx3, n_flip3, replace=False)
    pnl_s3[flip3] = -np.abs(pnl_s3[flip3]) * 0.8
    eq_s3 = equity_from_pnl(pnl_s3)
    results["S3: S1+S2 Combinati"] = {
        "equity": eq_s3,
        **metrics_from_equity(eq_s3, pnl_s3),
        "color": "#E74C3C",
    }

    # S4: solo SHORT (mercato laterale / bear, niente long)
    short_mask = trades["direction"] == "SHORT"
    pnl_s4 = trades.loc[short_mask, "pnl"].values
    if len(pnl_s4) > 0:
        eq_s4 = equity_from_pnl(pnl_s4)
    else:
        eq_s4 = pd.Series([capital])
        pnl_s4 = np.array([0.0])
    results["S4: Solo Short (Bear)"] = {
        "equity": eq_s4,
        **metrics_from_equity(eq_s4, pnl_s4),
        "color": "#9B59B6",
    }

    return results


def print_stress_results(stress: dict):
    print(f"\n{'═'*72}")
    print("  STRESS TEST — 4 SCENARI AVVERSI")
    print(f"{'═'*72}")
    print(f"  {'Scenario':<26} {'CAGR%':>8} {'Sharpe':>8} {'MaxDD%':>8} "
          f"{'N trade':>8} {'Cap finale':>12}")
    print(f"  {'─'*70}")
    for name, r in stress.items():
        print(f"  {name:<26} {r['cagr']:>+8.1f} {r['sharpe']:>8.2f} "
              f"{r['max_dd']:>8.1f} {r['n_trades']:>8} "
              f"  ${r['final_cap']:>10,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
# SEZIONE 5 — VISUALIZZAZIONI
# ══════════════════════════════════════════════════════════════════════════════

def plot_monte_carlo(bs: dict, pm: dict, stress: dict,
                     actual_equity: pd.Series, trades: pd.DataFrame):

    fig = plt.figure(figsize=(22, 32))
    gs  = gridspec.GridSpec(6, 2, figure=fig, hspace=0.55, wspace=0.35)

    # ── 1. Fan chart bootstrap ───────────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :])
    eq_m    = bs["equity_matrix"]
    x_trade = np.arange(bs["K"])
    pct_bands = [(5, 95, 0.15), (10, 90, 0.20), (25, 75, 0.30)]
    palette   = ["#1A5276", "#2471A3", "#5DADE2"]
    for (lo, hi, alpha), color in zip(pct_bands, palette):
        ax1.fill_between(x_trade,
                         np.percentile(eq_m, lo, axis=0),
                         np.percentile(eq_m, hi, axis=0),
                         alpha=alpha, color=color,
                         label=f"{lo}°–{hi}° pct")
    ax1.plot(x_trade, np.median(eq_m, axis=0),
             color="white", linewidth=2, label="Mediana")
    ax1.plot(x_trade, np.percentile(eq_m, 5,  axis=0),
             color="#E74C3C", linewidth=1, linestyle="--")
    ax1.plot(x_trade, np.percentile(eq_m, 95, axis=0),
             color="#2ECC71", linewidth=1, linestyle="--")
    # Equity reale ricalcolata trade-per-trade (allineata all'asse x bootstrap)
    actual_eq_trade = INITIAL_CAPITAL + np.cumsum(trades["pnl"].values)
    ax1.plot(x_trade, actual_eq_trade,
             color="#F39C12", linewidth=2.5, label="Equity reale V5", zorder=10)
    ax1.axhline(INITIAL_CAPITAL, color="gray", linewidth=0.8, linestyle=":")
    ax1.set_title(f"Fan Chart Bootstrap — {N_SIMS:,} simulazioni (V5 strategy)",
                  fontsize=13, fontweight="bold")
    ax1.set_ylabel("Capitale (USD)")
    ax1.set_xlabel("Trade #")
    ax1.legend(fontsize=9)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # ── 2. Distribuzione capitale finale: bootstrap vs parametrico ───────────
    ax2 = fig.add_subplot(gs[1, :])
    ax2.hist(bs["final_cap"], bins=120, density=True,
             color="#3498DB", alpha=0.6, label="Bootstrap")
    ax2.hist(pm["final_cap"], bins=120, density=True,
             color="#E74C3C", alpha=0.4, label="Parametrico (t-Student)")
    ax2.axvline(INITIAL_CAPITAL,
                color="white", linewidth=2, linestyle="--", label="Capitale iniziale")
    ax2.axvline(bs["pctiles"][5],
                color="#E74C3C", linewidth=1.5, linestyle=":", label=f"5° pct ${bs['pctiles'][5]:,.0f}")
    ax2.axvline(bs["pctiles"][50],
                color="#2ECC71", linewidth=1.5, linestyle=":", label=f"50° pct ${bs['pctiles'][50]:,.0f}")
    ax2.axvline(bs["pctiles"][95],
                color="#3498DB", linewidth=1.5, linestyle=":", label=f"95° pct ${bs['pctiles'][95]:,.0f}")

    # Annotazioni probabilità
    ruin_x  = INITIAL_CAPITAL * 0.70
    target_x = INITIAL_CAPITAL * 2.0
    ax2.axvline(ruin_x,   color="#E74C3C", linewidth=1, alpha=0.5)
    ax2.axvline(target_x, color="#2ECC71", linewidth=1, alpha=0.5)
    ymax = ax2.get_ylim()[1] if ax2.get_ylim()[1] > 0 else 1
    ax2.text(ruin_x,   ymax * 0.85, f"P(ruin)\n{bs['p_ruin']:.1f}%",
             ha="right", color="#E74C3C", fontsize=9)
    ax2.text(target_x, ymax * 0.85, f"P(+100%)\n{bs['p_100']:.1f}%",
             ha="left",  color="#2ECC71", fontsize=9)
    ax2.set_title("Distribuzione Capitale Finale — Bootstrap vs Parametrico",
                  fontsize=12, fontweight="bold")
    ax2.set_xlabel("Capitale finale (USD)")
    ax2.legend(fontsize=9)
    ax2.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # ── 3. Distribuzione Sharpe ──────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[2, 0])
    ax3.hist(bs["sharpe"], bins=80, density=True,
             color="#9B59B6", alpha=0.75, label="Bootstrap")
    ax3.hist(pm["sharpe"], bins=80, density=True,
             color="#F39C12", alpha=0.5, label="Parametrico")
    ax3.axvline(0, color="white", linewidth=1.5, linestyle="--")
    ax3.axvline(np.median(bs["sharpe"]), color="#2ECC71", linewidth=2,
                label=f"Mediana={np.median(bs['sharpe']):.2f}")
    ci5  = np.percentile(bs["sharpe"], 5)
    ci95 = np.percentile(bs["sharpe"], 95)
    ax3.axvspan(ci5, ci95, alpha=0.1, color="#2ECC71",
                label=f"CI 90%: [{ci5:.2f}, {ci95:.2f}]")
    ax3.set_title("Distribuzione Sharpe Ratio", fontsize=12, fontweight="bold")
    ax3.set_xlabel("Sharpe")
    ax3.legend(fontsize=8)

    # ── 4. Distribuzione Max Drawdown ────────────────────────────────────────
    ax4 = fig.add_subplot(gs[2, 1])
    ax4.hist(bs["max_dd"], bins=80, density=True,
             color="#E74C3C", alpha=0.75, label="Bootstrap")
    ax4.hist(pm["max_dd"], bins=80, density=True,
             color="#F39C12", alpha=0.5, label="Parametrico")
    ax4.axvline(np.median(bs["max_dd"]), color="white", linewidth=2,
                label=f"Mediana={np.median(bs['max_dd']):.1f}%")
    ax4.axvline(np.percentile(bs["max_dd"], 5), color="#E74C3C",
                linewidth=1.5, linestyle=":",
                label=f"5° pct={np.percentile(bs['max_dd'],5):.1f}%")
    ax4.set_title("Distribuzione Max Drawdown", fontsize=12, fontweight="bold")
    ax4.set_xlabel("Max Drawdown (%)")
    ax4.legend(fontsize=8)

    # ── 5. Stress test — equity curves ──────────────────────────────────────
    ax5 = fig.add_subplot(gs[3, :])
    for name, r in stress.items():
        eq = r["equity"]
        lbl = (f"{name}  "
               f"(CAGR={r['cagr']:+.1f}%, Sh={r['sharpe']:.2f}, DD={r['max_dd']:.1f}%)")
        ax5.plot(range(len(eq)), eq.values,
                 color=r["color"], linewidth=1.8, label=lbl)
    ax5.axhline(INITIAL_CAPITAL, color="gray", linewidth=0.8, linestyle=":")
    ax5.set_title("Stress Test — 4 Scenari Avversi (equity curve)",
                  fontsize=12, fontweight="bold")
    ax5.set_ylabel("Capitale (USD)")
    ax5.set_xlabel("Trade #")
    ax5.legend(fontsize=8)
    ax5.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # ── 6. Metriche stress test — barchart ───────────────────────────────────
    ax6 = fig.add_subplot(gs[4, 0])
    names_s  = list(stress.keys())
    cagrs_s  = [stress[n]["cagr"]   for n in names_s]
    colors_s = [stress[n]["color"]  for n in names_s]
    ax6.bar(range(len(names_s)), cagrs_s, color=colors_s, edgecolor="white")
    ax6.axhline(0, color="black", linewidth=0.8)
    ax6.set_xticks(range(len(names_s)))
    ax6.set_xticklabels([n.replace(" ", "\n") for n in names_s], fontsize=7)
    ax6.set_title("CAGR% per Scenario Stress", fontsize=12, fontweight="bold")
    ax6.set_ylabel("CAGR%")

    # ── 7. Serial correlation dei P&L trade ──────────────────────────────────
    ax7 = fig.add_subplot(gs[4, 1])
    pnl_arr = trades["pnl"].values
    acf_vals = acf(pnl_arr, nlags=20, fft=True)
    ci_acf   = 1.96 / np.sqrt(len(pnl_arr))
    ax7.bar(range(len(acf_vals)), acf_vals,
            color=["#E74C3C" if abs(v) > ci_acf else "#3498DB"
                   for v in acf_vals], width=0.6)
    ax7.axhline( ci_acf, color="red", linewidth=1, linestyle="--")
    ax7.axhline(-ci_acf, color="red", linewidth=1, linestyle="--")
    ax7.set_title("ACF P&L Trade (serial correlation)",
                  fontsize=12, fontweight="bold")
    ax7.set_xlabel("Lag")
    ax7.set_ylabel("ACF")

    # ── 8. P(obiettivo) vs P(ruin) — gauge ───────────────────────────────────
    ax8 = fig.add_subplot(gs[5, :])
    targets  = ["P(ruin <−30%)", "P(+50%)", "P(+100%)", "P(+200%)"]
    probs    = [bs["p_ruin"], bs["p_50"], bs["p_100"], bs["p_200"]]
    col_prob = ["#E74C3C", "#F39C12", "#2ECC71", "#3498DB"]
    bars = ax8.barh(targets, probs, color=col_prob, edgecolor="white")
    ax8.set_xlim(0, 105)
    ax8.axvline(50, color="white", linewidth=1, linestyle="--")
    for bar, p in zip(bars, probs):
        ax8.annotate(f"{p:.1f}%",
                     (p + 1, bar.get_y() + bar.get_height() / 2),
                     va="center", fontsize=11, fontweight="bold")
    ax8.set_title("Probabilità di raggiungere obiettivi/ruin (bootstrap)",
                  fontsize=12, fontweight="bold")
    ax8.set_xlabel("Probabilità (%)")

    fig.suptitle("Monte Carlo — Strategia V5 BTC/USD (10.000 simulazioni)",
                 fontsize=15, fontweight="bold")
    out_path = os.path.join(OUTPUT_DIR, "07_monte_carlo.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: 07_monte_carlo.png")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    # 1. Trade V5
    print("Caricamento e riesecuzione strategia V5 (SL=2×ATR, maker fee)...")
    trades, actual_equity = get_v5_trades()
    pnl = trades["pnl"].values
    K   = len(trades)
    print(f"  Trade totali: {K} | PnL totale: ${pnl.sum():,.0f} "
          f"| Win rate: {(pnl>0).mean()*100:.1f}%")

    # 2. Bootstrap
    print(f"\nBootstrap MC ({N_SIMS:,} simulazioni)...")
    bs = run_bootstrap(pnl)
    print_bootstrap_stats(bs, "Bootstrap MC")

    # 3. Parametric MC
    print(f"\nMC Parametrico (t-Student fit)...")
    pm = run_parametric_mc(pnl)
    df_t, loc_t, sc_t = pm["t_params"]
    print(f"  t-Student: df={df_t:.2f}  loc={loc_t:.2f}  scale={sc_t:.2f}")
    print(f"  CAGR mediana (parametrico): {np.median(pm['cagr']):+.1f}%")

    # 4. Stress tests
    print(f"\nStress tests...")
    stress = run_stress_tests(trades)
    print_stress_results(stress)

    # 5. Plot
    print(f"\nGenerazione grafici Monte Carlo...")
    plot_monte_carlo(bs, pm, stress, actual_equity, trades)

    # 6. Salva risultati
    summary_rows = []
    for pct in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
        summary_rows.append({
            "percentile":    pct,
            "final_cap_bs":  bs["pctiles"][pct],
            "cagr_bs":       np.percentile(bs["cagr"],    pct),
            "sharpe_bs":     np.percentile(bs["sharpe"],  pct),
            "maxdd_bs":      np.percentile(bs["max_dd"],  pct),
            "cagr_pm":       np.percentile(pm["cagr"],    pct),
            "sharpe_pm":     np.percentile(pm["sharpe"],  pct),
            "maxdd_pm":      np.percentile(pm["max_dd"],  pct),
        })
    pd.DataFrame(summary_rows).to_csv(
        os.path.join(OUTPUT_DIR, "mc_bootstrap_results.csv"), index=False)

    stress_rows = [{"scenario": n, **{k: v for k, v in r.items()
                                       if k not in ("equity", "color")}}
                   for n, r in stress.items()]
    pd.DataFrame(stress_rows).to_csv(
        os.path.join(OUTPUT_DIR, "mc_stress_results.csv"), index=False)

    print("  Saved: mc_bootstrap_results.csv, mc_stress_results.csv")
    print("\nMonte Carlo completato.")
