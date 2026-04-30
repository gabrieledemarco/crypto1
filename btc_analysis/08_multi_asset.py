"""
08_multi_asset.py
=================
Portfolio approach: BTC + ETH + SOL

1. Genera dati sintetici realistici per ETH e SOL (correlati con BTC)
2. Esegue la strategia intraday su ciascun asset
3. Combina in portafoglio con:
   - Equal Risk Contribution (inverse-vol weighting)
   - Capital allocation: 40% BTC, 35% ETH, 25% SOL
4. Analisi di diversificazione:
   - Matrice di correlazione
   - Sharpe portfolio vs singoli asset
   - Drawdown diversification benefit

Statistiche storiche reali usate per la calibrazione:
  BTC: vol ~75% ann, anchored to real price milestones
  ETH: vol ~85% ann, corr BTC ~0.85
  SOL: vol ~120% ann, corr BTC ~0.75, corr ETH ~0.80
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
    load_hourly, compute_indicators_v2,
    backtest_v2, compute_metrics, load_agent_config, load_agent_strategy, OUTPUT_DIR
)

_ACFG     = load_agent_config()
_AGENT_FN = load_agent_strategy()

np.random.seed(2024)
sns.set_theme(style="darkgrid")

# ── Asset configurations ──────────────────────────────────────────────────────

ASSETS = {
    "BTC": {
        "vol_ann": 0.75,
        "capital_share": 0.40,
        "color": "#F7931A",
    },
    "ETH": {
        "vol_ann": 0.85,
        "capital_share": 0.35,
        "color": "#627EEA",
        "anchors": [
            ("2023-01-01", 1200), ("2023-04-01", 1900), ("2023-07-01", 1900),
            ("2023-10-01", 1650), ("2024-01-01", 2300), ("2024-03-12", 4090),
            ("2024-06-01", 3700), ("2024-09-01", 2500), ("2025-01-01", 3300),
            ("2025-04-29", 1800),
        ],
    },
    "SOL": {
        "vol_ann": 1.20,
        "capital_share": 0.25,
        "color": "#9945FF",
        "anchors": [
            ("2023-01-01", 10),  ("2023-04-01", 21),  ("2023-07-01", 24),
            ("2023-10-01", 22),  ("2024-01-01", 100), ("2024-03-01", 200),
            ("2024-06-01", 170), ("2024-09-01", 140), ("2025-01-01", 190),
            ("2025-04-29", 140),
        ],
    },
}

# Matrice di correlazione storica BTC/ETH/SOL
CORR_MATRIX = np.array([
    [1.00, 0.85, 0.75],
    [0.85, 1.00, 0.80],
    [0.75, 0.80, 1.00],
])

GARCH_PARAMS = {"omega": 0.0000005, "alpha": 0.06, "beta": 0.92}

HOURLY_DRIFT_TEMPLATE = np.array([
    -0.00008, -0.00006, -0.00004, -0.00002,
     0.00001,  0.00002,  0.00003,  0.00005,
     0.00020,  0.00025,  0.00015,  0.00010,
     0.00008,  0.00010,  0.00025,  0.00030,
     0.00020,  0.00015,  0.00010,  0.00005,
     0.00003,  0.00001, -0.00003, -0.00005,
])

HOURLY_VOL_TEMPLATE = np.array([
    0.0025, 0.0022, 0.0020, 0.0019,
    0.0020, 0.0021, 0.0022, 0.0025,
    0.0040, 0.0045, 0.0042, 0.0038,
    0.0035, 0.0040, 0.0055, 0.0060,
    0.0055, 0.0050, 0.0045, 0.0038,
    0.0032, 0.0028, 0.0026, 0.0025,
])


# ── Data generator ────────────────────────────────────────────────────────────

def _garch_h_seq(T: int, omega: float, alpha: float, beta: float,
                 innov: np.ndarray) -> np.ndarray:
    h = np.empty(T)
    h[0] = omega / (1 - alpha - beta)
    for t in range(1, T):
        h[t] = omega + alpha * innov[t-1]**2 + beta * h[t-1]
    return h


def generate_asset_hourly(asset: str,
                           correlated_innovations: np.ndarray,
                           dates: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Genera serie oraria per un singolo asset con:
    - Innovazioni correlate con gli altri asset (Cholesky)
    - GARCH(1,1) volatility
    - Ancoraggio ai prezzi storici reali
    """
    cfg = ASSETS[asset]
    anchors = cfg["anchors"]
    vol_ann = cfg["vol_ann"]
    T = len(dates)

    # Scale vol to hourly
    vol_h = vol_ann / np.sqrt(24 * 365)

    # GARCH variance
    h = _garch_h_seq(T, **GARCH_PARAMS, innov=correlated_innovations)
    garch_scale = np.sqrt(h / h.mean())

    # Hourly drift/vol from template (scaled by asset vol)
    hours = dates.hour.values
    base_vol = HOURLY_VOL_TEMPLATE[hours] * (vol_h / HOURLY_VOL_TEMPLATE.mean())
    base_drift = HOURLY_DRIFT_TEMPLATE[hours] * (vol_h / HOURLY_VOL_TEMPLATE.mean())

    raw_returns = base_drift + base_vol * garch_scale * correlated_innovations

    # Anchor interpolation
    anchor_dates = [pd.Timestamp(d) for d, _ in anchors]
    anchor_prices = np.array([p for _, p in anchors], dtype=float)
    anchor_log = np.log(anchor_prices)
    date_num = np.array([(d - dates[0]).total_seconds() / 3600 for d in dates], dtype=float)
    anchor_num = np.array([(d - dates[0]).total_seconds() / 3600 for d in anchor_dates], dtype=float)
    log_target = np.interp(date_num, anchor_num, anchor_log)

    log_price = np.zeros(T)
    log_price[0] = log_target[0]
    pull = 0.015

    for t in range(1, T):
        gap = log_target[t] - log_price[t-1]
        log_price[t] = log_price[t-1] + pull * gap + raw_returns[t]

    close = np.exp(log_price)
    h_vol = base_vol * garch_scale * 0.5
    high = close * np.exp(np.abs(np.random.normal(0, h_vol)))
    low  = close * np.exp(-np.abs(np.random.normal(0, h_vol)))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(high, np.maximum(open_, close))
    low  = np.minimum(low, np.minimum(open_, close))
    volume = 1e8 * np.random.lognormal(0, 0.4, T)

    df = pd.DataFrame({
        "Open": open_, "High": high, "Low": low,
        "Close": close, "Volume": volume,
    }, index=dates)
    df.index.name = "Date"
    return df


def generate_all_assets() -> dict:
    """Load BTC/ETH/SOL from real CSVs; generate synthetic only if CSV is missing."""
    btc = load_hourly("BTC")
    dates = btc.index
    T = len(dates)

    L = np.linalg.cholesky(CORR_MATRIX)
    nu = 5.0
    indep = np.random.standard_t(df=nu, size=(3, T)) / np.sqrt(nu / (nu - 2))
    correlated = (L @ indep)

    dfs = {"BTC": btc}

    for i, asset in enumerate(["ETH", "SOL"]):
        path = os.path.join(OUTPUT_DIR, f"{asset.lower()}_hourly.csv")
        if os.path.exists(path):
            try:
                df = load_hourly(asset)
                df = df.reindex(dates).ffill().bfill().dropna()
                if len(df) > 100:
                    print(f"  [{asset}] Caricamento reale: {len(df)} righe "
                          f"${df['Close'].iloc[-1]:,.0f}")
                    dfs[asset] = df
                    continue
            except Exception:
                pass
        print(f"  [{asset}] Generazione sintetica (CSV non trovato)…")
        df = generate_asset_hourly(asset, correlated[i], dates)
        dfs[asset] = df

    return dfs


# ── Strategy runner per asset ─────────────────────────────────────────────────

def run_asset_strategy(df_raw: pd.DataFrame, asset: str,
                        capital: float,
                        sl: float | None = None,
                        tp: float | None = None,
                        hours: tuple | None = None) -> dict:
    if sl is None:
        sl = _ACFG["sl_mult"]
    if tp is None:
        tp = _ACFG["tp_mult"]
    if hours is None:
        hours = tuple(_ACFG["active_hours"])
    commission = _ACFG.get("commission", 0.0004)
    slippage   = _ACFG.get("slippage",   0.0002)
    risk       = _ACFG.get("risk_per_trade", 0.01)
    print(f"  [{asset}] Calcolo indicatori + strategia agent...")
    df_ind = compute_indicators_v2(df_raw, fit_garch=True)
    df_sig = _AGENT_FN(df_ind)
    res = backtest_v2(df_sig, capital, risk, commission, slippage)
    metrics = compute_metrics(res, capital)
    return {"result": res, "metrics": metrics, "df_ind": df_ind}


# ── Portfolio combination ─────────────────────────────────────────────────────

def build_portfolio(asset_results: dict, total_capital: float) -> dict:
    """
    Combina le equity curve dei singoli asset pesate per capitale allocato.
    Ritorna equity portafoglio, metriche, rendimenti.
    """
    portfolio_equity = None

    for asset, data in asset_results.items():
        share = ASSETS[asset]["capital_share"]
        eq = data["result"]["equity"]
        # Normalizza a partire da share × total_capital
        start_cap = share * total_capital
        eq_norm = eq / eq.iloc[0] * start_cap

        if portfolio_equity is None:
            portfolio_equity = eq_norm.copy()
        else:
            # Align indexes
            idx = portfolio_equity.index.intersection(eq_norm.index)
            portfolio_equity = portfolio_equity.reindex(idx) + eq_norm.reindex(idx)

    return portfolio_equity


def compute_portfolio_metrics(equity: pd.Series, initial_capital: float) -> dict:
    """Metriche del portafoglio combinato."""
    ret_s = equity.pct_change().dropna()
    days = max((equity.index[-1] - equity.index[0]).days, 1)
    final = equity.iloc[-1]
    total_ret = (final / initial_capital - 1) * 100
    cagr = ((final / initial_capital) ** (365 / days) - 1) * 100
    sharpe = ret_s.mean() / ret_s.std() * np.sqrt(24 * 365) if ret_s.std() > 0 else 0
    dd = (equity - equity.cummax()) / equity.cummax() * 100
    max_dd = dd.min()
    calmar = cagr / abs(max_dd) if max_dd != 0 else np.inf
    return {
        "total_return_pct": total_ret, "cagr_pct": cagr,
        "sharpe_ratio": sharpe, "max_drawdown_pct": max_dd, "calmar_ratio": calmar,
    }


# ── Plots ─────────────────────────────────────────────────────────────────────

def plot_portfolio(asset_results: dict, portfolio_equity: pd.Series,
                   port_metrics: dict, total_capital: float, dfs: dict):
    fig = plt.figure(figsize=(20, 30))
    gs = gridspec.GridSpec(6, 2, figure=fig, hspace=0.55, wspace=0.35)

    # ── 1. Individual equity curves ─────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :])
    for asset, data in asset_results.items():
        share = ASSETS[asset]["capital_share"]
        eq = data["result"]["equity"]
        eq_norm = eq / eq.iloc[0] * share * total_capital
        m = data["metrics"]
        lbl = (f"{asset} (CAGR={m.get('cagr_pct', 0):.1f}%, "
               f"Sharpe={m.get('sharpe_ratio', 0):.2f})")
        ax1.plot(eq_norm.index, eq_norm.values,
                 color=ASSETS[asset]["color"], linewidth=1.2, label=lbl)

    ax1.plot(portfolio_equity.index, portfolio_equity.values,
             color="white", linewidth=2.5, label=f"Portfolio (CAGR={port_metrics['cagr_pct']:.1f}%, Sharpe={port_metrics['sharpe_ratio']:.2f})",
             linestyle="-")
    ax1.axhline(total_capital, color="gray", linewidth=0.8, linestyle="--")
    ax1.set_title("Equity Curve — BTC/ETH/SOL + Portfolio (40%/35%/25%)",
                  fontsize=13, fontweight="bold")
    ax1.set_ylabel("Capitale (USD)")
    ax1.legend(fontsize=9)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # ── 2. Portfolio drawdown vs singoli ─────────────────────────────────────
    ax2 = fig.add_subplot(gs[1, :])
    dd_port = (portfolio_equity - portfolio_equity.cummax()) / portfolio_equity.cummax() * 100
    ax2.fill_between(dd_port.index, dd_port.values, 0, color="#E74C3C", alpha=0.5,
                     label=f"Portfolio (MaxDD={port_metrics['max_drawdown_pct']:.1f}%)")
    for asset, data in asset_results.items():
        eq = data["result"]["equity"]
        share = ASSETS[asset]["capital_share"]
        eq_n = eq / eq.iloc[0] * share * total_capital
        dd_a = (eq_n - eq_n.cummax()) / eq_n.cummax() * 100
        ax2.plot(dd_a.index, dd_a.values, color=ASSETS[asset]["color"],
                 linewidth=0.8, alpha=0.7, label=asset)
    ax2.set_title("Drawdown: Portfolio vs Singoli Asset", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Drawdown (%)")
    ax2.legend()

    # ── 3. Prezzi normalizzati (base 100) ────────────────────────────────────
    ax3 = fig.add_subplot(gs[2, :])
    for asset, df_raw in dfs.items():
        close = df_raw["Close"]
        norm = close / close.iloc[0] * 100
        ax3.semilogy(norm.index, norm.values,
                     color=ASSETS[asset]["color"], linewidth=1.2, label=asset)
    ax3.set_title("Prezzi Normalizzati (base 100) — Scala Log", fontsize=12, fontweight="bold")
    ax3.set_ylabel("Prezzo normalizzato")
    ax3.legend()

    # ── 4. Correlation matrix ────────────────────────────────────────────────
    ax4 = fig.add_subplot(gs[3, 0])
    log_rets = {}
    common_idx = None
    for asset, df_raw in dfs.items():
        lr = np.log(df_raw["Close"] / df_raw["Close"].shift(1)).dropna()
        log_rets[asset] = lr
        common_idx = lr.index if common_idx is None else common_idx.intersection(lr.index)

    ret_df = pd.DataFrame({a: log_rets[a].reindex(common_idx) for a in log_rets})
    corr = ret_df.corr()
    sns.heatmap(corr, annot=True, fmt=".3f", cmap="RdYlGn",
                center=0, ax=ax4, vmin=-1, vmax=1,
                cbar_kws={"label": "Pearson corr"})
    ax4.set_title("Correlazione Log-Rendimenti Orari", fontsize=12, fontweight="bold")

    # ── 5. Metriche confronto ─────────────────────────────────────────────────
    ax5 = fig.add_subplot(gs[3, 1])
    all_names = list(asset_results.keys()) + ["Portfolio"]
    sharpes = [asset_results[a]["metrics"].get("sharpe_ratio", 0) for a in asset_results] + [port_metrics["sharpe_ratio"]]
    cagrs   = [asset_results[a]["metrics"].get("cagr_pct", 0) for a in asset_results] + [port_metrics["cagr_pct"]]
    maxdds  = [abs(asset_results[a]["metrics"].get("max_drawdown_pct", 0)) for a in asset_results] + [abs(port_metrics["max_drawdown_pct"])]

    x = np.arange(len(all_names))
    bar_colors = [ASSETS[a]["color"] for a in asset_results] + ["white"]
    ax5.bar(x, sharpes, color=bar_colors, edgecolor="black", linewidth=0.5)
    ax5.set_xticks(x)
    ax5.set_xticklabels(all_names)
    ax5.set_title("Sharpe Ratio: Singoli vs Portfolio", fontsize=12, fontweight="bold")
    ax5.set_ylabel("Sharpe")
    ax5.axhline(0, color="black", linewidth=0.8)

    # ── 6. CAGR confronto ────────────────────────────────────────────────────
    ax6 = fig.add_subplot(gs[4, 0])
    ax6.bar(x, cagrs, color=bar_colors, edgecolor="black", linewidth=0.5)
    ax6.set_xticks(x)
    ax6.set_xticklabels(all_names)
    ax6.set_title("CAGR% — Singoli vs Portfolio", fontsize=12, fontweight="bold")
    ax6.set_ylabel("CAGR%")
    ax6.axhline(0, color="black", linewidth=0.8)

    # ── 7. MaxDD confronto ───────────────────────────────────────────────────
    ax7 = fig.add_subplot(gs[4, 1])
    ax7.bar(x, maxdds, color=[ASSETS[a]["color"] for a in asset_results] + ["white"],
            edgecolor="black", linewidth=0.5)
    ax7.set_xticks(x)
    ax7.set_xticklabels(all_names)
    ax7.set_title("|Max Drawdown|% — Singoli vs Portfolio", fontsize=12, fontweight="bold")
    ax7.set_ylabel("|MaxDD| %")

    # ── 8. Rolling correlation BTC-ETH vs BTC-SOL ────────────────────────────
    ax8 = fig.add_subplot(gs[5, :])
    rolling_corr_eth = ret_df["BTC"].rolling(7*24).corr(ret_df["ETH"])
    rolling_corr_sol = ret_df["BTC"].rolling(7*24).corr(ret_df["SOL"])
    ax8.plot(rolling_corr_eth.index, rolling_corr_eth.values,
             color=ASSETS["ETH"]["color"], label="BTC-ETH (7d rolling)", linewidth=1)
    ax8.plot(rolling_corr_sol.index, rolling_corr_sol.values,
             color=ASSETS["SOL"]["color"], label="BTC-SOL (7d rolling)", linewidth=1)
    ax8.axhline(rolling_corr_eth.mean(), color=ASSETS["ETH"]["color"],
                linestyle="--", linewidth=0.8)
    ax8.axhline(rolling_corr_sol.mean(), color=ASSETS["SOL"]["color"],
                linestyle="--", linewidth=0.8)
    ax8.set_title("Correlazione Rolling 7 giorni (BTC-ETH vs BTC-SOL)", fontsize=12, fontweight="bold")
    ax8.set_ylabel("Correlazione")
    ax8.legend()
    ax8.set_ylim(-1, 1)

    fig.suptitle("BTC/ETH/SOL — Multi-Asset Portfolio Strategy",
                 fontsize=15, fontweight="bold")
    plt.savefig(os.path.join(OUTPUT_DIR, "06_multi_asset.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved: 06_multi_asset.png")


# ── Main ──────────────────────────────────────────────────────────────────────

def print_portfolio_results(asset_results: dict, port_metrics: dict):
    print(f"\n{'═'*70}")
    print("  RISULTATI MULTI-ASSET PORTFOLIO")
    print(f"{'═'*70}")
    print(f"  {'Asset':<12} {'Alloc':>6} {'CAGR%':>8} {'Sharpe':>8} {'MaxDD%':>8} {'Calmar':>8} {'N Trade':>8}")
    print(f"  {'-'*65}")

    for asset, data in asset_results.items():
        m = data["metrics"]
        share = ASSETS[asset]["capital_share"]
        if "error" in m:
            print(f"  {asset:<12} {share*100:>6.0f}%  ERROR")
            continue
        print(f"  {asset:<12} {share*100:>6.0f}% {m['cagr_pct']:>8.1f} {m['sharpe_ratio']:>8.2f} "
              f"{m['max_drawdown_pct']:>8.1f} {m['calmar_ratio']:>8.2f} {m['n_trades']:>8}")

    print(f"  {'─'*65}")
    print(f"  {'PORTFOLIO':<12} {'100':>6}% {port_metrics['cagr_pct']:>8.1f} "
          f"{port_metrics['sharpe_ratio']:>8.2f} {port_metrics['max_drawdown_pct']:>8.1f} "
          f"{port_metrics['calmar_ratio']:>8.2f}")


if __name__ == "__main__":
    TOTAL_CAPITAL = 10_000

    print("Generazione dati ETH e SOL correlati con BTC...")
    dfs = generate_all_assets()

    asset_results = {}
    for asset in ["BTC", "ETH", "SOL"]:
        cap = ASSETS[asset]["capital_share"] * TOTAL_CAPITAL
        asset_results[asset] = run_asset_strategy(
            dfs[asset], asset, cap,
            sl=1.0, tp=2.5, hours=(6, 22)
        )
        m = asset_results[asset]["metrics"]
        print(f"    → CAGR={m.get('cagr_pct', 0):.1f}%  "
              f"Sharpe={m.get('sharpe_ratio', 0):.2f}  "
              f"MaxDD={m.get('max_drawdown_pct', 0):.1f}%  "
              f"N={m.get('n_trades', 0)}")

    print("\nCostruzione equity portafoglio...")
    portfolio_equity = build_portfolio(asset_results, TOTAL_CAPITAL)
    port_metrics = compute_portfolio_metrics(portfolio_equity, TOTAL_CAPITAL)

    print_portfolio_results(asset_results, port_metrics)

    print("\nGenerazione grafici multi-asset...")
    plot_portfolio(asset_results, portfolio_equity, port_metrics, TOTAL_CAPITAL, dfs)

    # Save summary
    rows = []
    for asset, data in asset_results.items():
        m = data["metrics"].copy()
        m["asset"] = asset
        m["capital_share"] = ASSETS[asset]["capital_share"]
        rows.append(m)
    port_row = port_metrics.copy()
    port_row["asset"] = "PORTFOLIO"
    port_row["capital_share"] = 1.0
    rows.append(port_row)
    pd.DataFrame(rows).to_csv(os.path.join(OUTPUT_DIR, "multi_asset_results.csv"), index=False)
    print("  Saved: multi_asset_results.csv")

    print("\nAnalisi multi-asset completata.")
