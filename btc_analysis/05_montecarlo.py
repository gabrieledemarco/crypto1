"""
05_montecarlo.py
================
Simulazione Monte Carlo (bootstrap + stress test) a partire da trades.csv.

Input:  STRATEGY_ASSET env var
        output/trades.csv  (generato da 04_backtest.py)

Output:
  output/mc_bootstrap_results.csv
  output/mc_stress_results.csv
  output/07_monte_carlo.png
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from strategy_core import OUTPUT_DIR, load_agent_config

STRATEGY_ASSET   = os.environ.get("STRATEGY_ASSET", "BTC-USD")
INITIAL_CAPITAL  = 10_000
N_SIMS           = int(os.environ.get("MC_N_SIMS", "5000"))
SIM_MULTIPLIER   = float(os.environ.get("MC_SIM_MULTIPLIER", "1.0"))
np.random.seed(42)

_ACFG = load_agent_config()


# ── Bootstrap MC ──────────────────────────────────────────────────────────────

def run_bootstrap(pnl: np.ndarray, n_sims: int = N_SIMS,
                  sim_multiplier: float = SIM_MULTIPLIER) -> dict:
    K          = len(pnl)
    sim_length = max(1, int(K * sim_multiplier))
    idx = np.random.randint(0, K, size=(n_sims, sim_length))
    sim = pnl[idx]
    eq  = INITIAL_CAPITAL + np.cumsum(sim, axis=1)

    final       = eq[:, -1]
    cagr_arr    = ((final / INITIAL_CAPITAL) ** (1 / max((sim_length / (24 * 365)), 0.1)) - 1) * 100
    max_dd_arr  = np.array([
        ((e - np.maximum.accumulate(e)) / np.maximum.accumulate(e)).min() * 100
        for e in eq
    ])
    sharpe_arr  = np.array([
        (np.diff(e) / INITIAL_CAPITAL).mean() / (np.diff(e) / INITIAL_CAPITAL).std() * np.sqrt(24 * 365)
        if (np.diff(e) / INITIAL_CAPITAL).std() > 0 else 0
        for e in eq
    ])

    return {
        "final_capital": final,
        "cagr_pct":      cagr_arr,
        "sharpe":        sharpe_arr,
        "max_dd_pct":    max_dd_arr,
        "equity_matrix": eq,
    }


# ── Stress tests ──────────────────────────────────────────────────────────────

def run_stress(pnl: np.ndarray) -> list:
    scenarios = [
        ("Worst 10% trade risampling",  lambda x: x[x <= np.percentile(x, 10)]),
        ("Drawdown consecutivo ×3",     lambda x: np.concatenate([x[x < 0] * 1.5, x[x >= 0]])),
        ("Commissioni raddoppiate",     lambda x: x - abs(x) * 0.002),
        ("50% meno trade",             lambda x: x[::2]),
    ]
    rows = []
    for label, transform in scenarios:
        try:
            stressed  = transform(pnl.copy())
            if len(stressed) < 5:
                continue
            eq        = INITIAL_CAPITAL + np.cumsum(stressed)
            final_cap = float(eq[-1])
            ret       = final_cap / INITIAL_CAPITAL - 1
            dd        = ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100
            rows.append({
                "scenario":       label,
                "final_cap_usd":  round(final_cap, 2),
                "total_return_pct": round(ret * 100, 2),
                "max_drawdown_pct": round(float(dd), 2),
            })
        except Exception:
            pass
    return rows


# ── Fan chart ─────────────────────────────────────────────────────────────────

def _save_chart(bs: dict, stress_rows: list, asset: str):
    eq_mat = bs["equity_matrix"]
    pcts   = [1, 5, 25, 50, 75, 95, 99]
    x      = np.arange(eq_mat.shape[1])

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    ax_fan, ax_dist = axes

    # Fan chart
    p_vals = {p: np.percentile(eq_mat, p, axis=0) for p in pcts}
    ax_fan.fill_between(x, p_vals[5],  p_vals[95],  alpha=0.15, color="#3498DB", label="5-95%")
    ax_fan.fill_between(x, p_vals[25], p_vals[75],  alpha=0.30, color="#3498DB", label="25-75%")
    ax_fan.plot(x, p_vals[50], color="#3498DB", linewidth=2, label="Mediana")
    ax_fan.axhline(INITIAL_CAPITAL, color="gray", linewidth=0.8, linestyle="--")
    _mult_label = f" · {SIM_MULTIPLIER}× periodi" if SIM_MULTIPLIER != 1.0 else ""
    ax_fan.set_title(f"{asset} — Bootstrap MC ({N_SIMS:,} sim{_mult_label})", fontweight="bold")
    ax_fan.set_xlabel("Trade #")
    ax_fan.set_ylabel("Capitale (USD)")
    ax_fan.legend(fontsize=8)
    ax_fan.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:,.0f}"))

    # CAGR distribution
    ax_dist.hist(bs["cagr_pct"], bins=60, color="#2ECC71", alpha=0.75, edgecolor="none")
    ax_dist.axvline(np.percentile(bs["cagr_pct"], 5),  color="red",   linestyle="--", label="5° pct")
    ax_dist.axvline(np.percentile(bs["cagr_pct"], 50), color="white", linestyle="-",  label="Mediana")
    ax_dist.set_title("Distribuzione CAGR%", fontweight="bold")
    ax_dist.set_xlabel("CAGR %")
    ax_dist.legend(fontsize=8)

    fig.tight_layout()
    out = os.path.join(OUTPUT_DIR, "07_monte_carlo.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {os.path.basename(out)}")


if __name__ == "__main__":
    print("=" * 60)
    print(f"  MONTE CARLO — {STRATEGY_ASSET}")
    print("=" * 60)

    trades_path = os.path.join(OUTPUT_DIR, "trades.csv")
    if not os.path.exists(trades_path):
        print("  ERRORE: trades.csv non trovato. Esegui prima 04_backtest.py.")
        sys.exit(1)

    trades = pd.read_csv(trades_path)
    if trades.empty or "pnl" not in trades.columns:
        print("  ERRORE: trades.csv vuoto o senza colonna pnl.")
        sys.exit(1)

    pnl = trades["pnl"].values
    sim_length = max(1, int(len(pnl) * SIM_MULTIPLIER))
    print(f"  Trade letti: {len(pnl)}  |  Periodi/percorso: {sim_length} ({SIM_MULTIPLIER}×)")
    print(f"  PnL medio: ${pnl.mean():.2f}  |  Std: ${pnl.std():.2f}")

    # Bootstrap
    print(f"\n  Bootstrap {N_SIMS:,} simulazioni ({sim_length} trade/percorso)...")
    bs = run_bootstrap(pnl, N_SIMS, SIM_MULTIPLIER)

    # Percentili summary
    pcts = [1, 5, 25, 50, 75, 95, 99]
    summary_rows = []
    for p in pcts:
        summary_rows.append({
            "percentile":     p,
            "final_cap_bs":   round(float(np.percentile(bs["final_capital"], p)), 2),
            "cagr_bs":        round(float(np.percentile(bs["cagr_pct"],     p)), 2),
            "sharpe_bs":      round(float(np.percentile(bs["sharpe"],        p)), 4),
            "maxdd_bs":       round(float(np.percentile(bs["max_dd_pct"],    p)), 2),
        })
    df_bs = pd.DataFrame(summary_rows)
    df_bs.to_csv(os.path.join(OUTPUT_DIR, "mc_bootstrap_results.csv"), index=False)
    print("  Saved: mc_bootstrap_results.csv")

    med = df_bs[df_bs["percentile"] == 50].iloc[0]
    p5  = df_bs[df_bs["percentile"] == 5].iloc[0]
    print(f"  Mediana CAGR: {med['cagr_bs']:.1f}%  Sharpe: {med['sharpe_bs']:.2f}  MaxDD: {med['maxdd_bs']:.1f}%")
    print(f"  5° pct  CAGR: {p5['cagr_bs']:.1f}%  Sharpe: {p5['sharpe_bs']:.2f}  MaxDD: {p5['maxdd_bs']:.1f}%")

    # Stress tests
    print("\n  Stress tests...")
    stress_rows = run_stress(pnl)
    pd.DataFrame(stress_rows).to_csv(
        os.path.join(OUTPUT_DIR, "mc_stress_results.csv"), index=False)
    print("  Saved: mc_stress_results.csv")
    for row in stress_rows:
        print(f"  [{row['scenario'][:40]:<40}] "
              f"Return: {row['total_return_pct']:+.1f}%  MaxDD: {row['max_drawdown_pct']:.1f}%")

    # Chart
    print("\n  Generazione grafico...")
    _save_chart(bs, stress_rows, STRATEGY_ASSET)

    print("\nMonte Carlo completato.")
