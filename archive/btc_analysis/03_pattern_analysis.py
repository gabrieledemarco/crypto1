"""
BTC/USD Pattern Analysis
- Day-of-week effect (giorno della settimana)
- Month-of-year seasonality (stagionalità mensile)
- Hour-of-day effect su dati orari (sessioni di trading)
- Momentum / mean-reversion patterns
- Drawdown analysis
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
from scipy import stats
import os, warnings

warnings.filterwarnings("ignore")
sns.set_theme(style="darkgrid")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
DAYS_IT = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
MONTHS_IT = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
             "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]


def load_data():
    daily = pd.read_csv(os.path.join(OUTPUT_DIR, "btc_daily.csv"),
                        index_col="Date", parse_dates=True)
    daily.columns = [c[0] if isinstance(c, tuple) else c for c in daily.columns]
    daily = daily[["Close", "Volume"]].dropna()
    daily["log_ret"] = np.log(daily["Close"] / daily["Close"].shift(1))
    daily["ret"] = daily["Close"].pct_change()
    daily = daily.dropna()

    hourly = pd.read_csv(os.path.join(OUTPUT_DIR, "btc_hourly.csv"),
                         index_col="Date", parse_dates=True)
    hourly.columns = [c[0] if isinstance(c, tuple) else c for c in hourly.columns]
    hourly = hourly[["Close", "Volume"]].dropna()
    hourly["log_ret"] = np.log(hourly["Close"] / hourly["Close"].shift(1))
    hourly["ret"] = hourly["Close"].pct_change()
    hourly = hourly.dropna()
    return daily, hourly


# ── 1. Day-of-week effect ────────────────────────────────────────────────────

def dow_analysis(daily):
    daily["dow"] = daily.index.dayofweek
    dow_stats = daily.groupby("dow")["log_ret"].agg(["mean", "std", "count"])
    dow_stats["mean_ann"] = dow_stats["mean"] * 252
    dow_stats["sharpe"] = dow_stats["mean"] / dow_stats["std"]
    dow_stats["t_stat"] = dow_stats["mean"] / (dow_stats["std"] / np.sqrt(dow_stats["count"]))
    dow_stats["p_value"] = 2 * (1 - stats.t.cdf(abs(dow_stats["t_stat"]), df=dow_stats["count"] - 1))
    dow_stats.index = DAYS_IT
    print(f"\n{'═'*65}")
    print("  EFFETTO GIORNO DELLA SETTIMANA")
    print(f"{'═'*65}")
    print(f"  {'Giorno':<12} {'Media':>8} {'Std':>8} {'Sharpe':>8} {'t-stat':>8} {'p-val':>8}")
    print(f"  {'-'*60}")
    for g, row in dow_stats.iterrows():
        sig = "★" if row["p_value"] < 0.05 else " "
        print(f"  {g:<12} {row['mean']*100:>7.3f}% {row['std']*100:>7.3f}% "
              f"{row['sharpe']:>8.3f} {row['t_stat']:>8.3f} {row['p_value']:>8.4f} {sig}")
    return dow_stats


# ── 2. Month-of-year seasonality ─────────────────────────────────────────────

def monthly_seasonality(daily):
    daily["month"] = daily.index.month
    mon_stats = daily.groupby("month")["log_ret"].agg(["mean", "std", "count"])
    mon_stats["t_stat"] = mon_stats["mean"] / (mon_stats["std"] / np.sqrt(mon_stats["count"]))
    mon_stats["p_value"] = 2 * (1 - stats.t.cdf(abs(mon_stats["t_stat"]), df=mon_stats["count"] - 1))
    mon_stats.index = MONTHS_IT
    print(f"\n{'═'*65}")
    print("  STAGIONALITÀ MENSILE")
    print(f"{'═'*65}")
    print(f"  {'Mese':<6} {'Media/giorno':>13} {'Std':>8} {'t-stat':>8} {'p-val':>8}")
    print(f"  {'-'*55}")
    for m, row in mon_stats.iterrows():
        sig = "★" if row["p_value"] < 0.05 else " "
        print(f"  {m:<6} {row['mean']*100:>12.3f}% {row['std']*100:>7.3f}% "
              f"{row['t_stat']:>8.3f} {row['p_value']:>8.4f} {sig}")
    return mon_stats


# ── 3. Hour-of-day effect ────────────────────────────────────────────────────

def hourly_pattern(hourly):
    hourly["hour"] = hourly.index.hour
    h_stats = hourly.groupby("hour")["log_ret"].agg(["mean", "std", "count"])
    h_stats["t_stat"] = h_stats["mean"] / (h_stats["std"] / np.sqrt(h_stats["count"]))
    h_stats["p_value"] = 2 * (1 - stats.t.cdf(abs(h_stats["t_stat"]), df=h_stats["count"] - 1))

    print(f"\n{'═'*65}")
    print("  EFFETTO ORA DEL GIORNO (UTC)")
    print(f"{'═'*65}")
    print(f"  {'Ora':>4} {'Media':>9} {'Std':>8} {'t-stat':>8} {'p-val':>8}  Sessione")
    print(f"  {'-'*60}")
    for h, row in h_stats.iterrows():
        sig = "★" if row["p_value"] < 0.05 else " "
        if 0 <= h < 8:
            sess = "Asia"
        elif 8 <= h < 16:
            sess = "Europa"
        else:
            sess = "USA"
        print(f"  {h:>4}h {row['mean']*100:>8.4f}% {row['std']*100:>7.3f}% "
              f"{row['t_stat']:>8.3f} {row['p_value']:>8.4f} {sig}  {sess}")
    return h_stats


# ── 4. Momentum analysis ─────────────────────────────────────────────────────

def momentum_analysis(daily):
    print(f"\n{'═'*65}")
    print("  MOMENTUM / MEAN-REVERSION — Autocorrelazione rendimenti")
    print(f"{'═'*65}")
    from statsmodels.tsa.stattools import acf
    r = daily["log_ret"]
    acf_vals = acf(r, nlags=20, fft=True)
    ci = 1.96 / np.sqrt(len(r))
    print(f"  {'Lag':>4}  {'ACF':>8}  Significativo")
    for i in range(1, 21):
        sig = "★" if abs(acf_vals[i]) > ci else " "
        print(f"  {i:>4}  {acf_vals[i]:>8.4f}  {sig}")

    # Hurst exponent
    lags = range(2, 50)
    tau = [daily["Close"].rolling(lag).std().mean() for lag in lags]
    reg = np.polyfit(np.log(lags), np.log(tau), 1)
    H = reg[0]
    print(f"\n  Esponente di Hurst: H = {H:.4f}")
    if H < 0.45:
        print("  → Mean-reverting (H < 0.5)")
    elif H > 0.55:
        print("  → Trending / persistente (H > 0.5)")
    else:
        print("  → Random walk (H ≈ 0.5)")
    return H


# ── 5. Drawdown analysis ─────────────────────────────────────────────────────

def drawdown_analysis(daily):
    close = daily["Close"]
    rolling_max = close.cummax()
    dd = (close - rolling_max) / rolling_max * 100
    print(f"\n{'═'*55}")
    print("  DRAWDOWN ANALYSIS")
    print(f"{'═'*55}")
    print(f"  Max Drawdown: {dd.min():.1f}%")
    print(f"  Drawdown medio: {dd.mean():.1f}%")
    # Top 5 drawdown periods
    return dd


# ── 6. Heatmap dow × month ───────────────────────────────────────────────────

def heatmap_dow_month(daily):
    daily["dow"] = daily.index.dayofweek
    daily["month"] = daily.index.month
    pivot = daily.pivot_table(values="log_ret", index="dow", columns="month",
                               aggfunc="mean") * 100
    pivot.index = DAYS_IT
    pivot.columns = MONTHS_IT
    return pivot


# ── 7. Plots ─────────────────────────────────────────────────────────────────

def plot_patterns(daily, hourly, dow_stats, mon_stats, h_stats, dd, heatmap_data):
    fig = plt.figure(figsize=(20, 26))
    gs = gridspec.GridSpec(5, 2, figure=fig, hspace=0.5, wspace=0.35)

    colors_dow = ["#2ECC71" if v > 0 else "#E74C3C" for v in dow_stats["mean"]]
    ax1 = fig.add_subplot(gs[0, 0])
    bars = ax1.bar(dow_stats.index, dow_stats["mean"] * 100, color=colors_dow, edgecolor="white")
    ax1.axhline(0, color="black", linewidth=0.8)
    ax1.set_title("Rendimento Medio per Giorno della Settimana", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Log-Return medio (%)")
    ax1.tick_params(axis="x", rotation=30)
    for bar, p in zip(bars, dow_stats["p_value"]):
        if p < 0.05:
            ax1.annotate("★", (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                         ha="center", va="bottom", fontsize=12, color="gold")

    colors_mon = ["#2ECC71" if v > 0 else "#E74C3C" for v in mon_stats["mean"]]
    ax2 = fig.add_subplot(gs[0, 1])
    bars2 = ax2.bar(mon_stats.index, mon_stats["mean"] * 100, color=colors_mon, edgecolor="white")
    ax2.axhline(0, color="black", linewidth=0.8)
    ax2.set_title("Rendimento Medio per Mese", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Log-Return medio (%)")
    ax2.tick_params(axis="x", rotation=30)
    for bar, p in zip(bars2, mon_stats["p_value"]):
        if p < 0.05:
            ax2.annotate("★", (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                         ha="center", va="bottom", fontsize=12, color="gold")

    ax3 = fig.add_subplot(gs[1, :])
    colors_h = ["#2ECC71" if v > 0 else "#E74C3C" for v in h_stats["mean"]]
    ax3.bar(h_stats.index, h_stats["mean"] * 100, color=colors_h, edgecolor="white")
    ax3.axhline(0, color="black", linewidth=0.8)
    ax3.axvspan(-0.5, 7.5, alpha=0.07, color="blue", label="Asia (00-08 UTC)")
    ax3.axvspan(7.5, 15.5, alpha=0.07, color="green", label="Europa (08-16 UTC)")
    ax3.axvspan(15.5, 23.5, alpha=0.07, color="orange", label="USA (16-24 UTC)")
    ax3.set_title("Rendimento Medio per Ora del Giorno (UTC) — Dati Orari 2023-2025",
                  fontsize=12, fontweight="bold")
    ax3.set_ylabel("Log-Return medio (%)")
    ax3.set_xlabel("Ora UTC")
    ax3.set_xticks(range(24))
    ax3.legend(loc="upper right")

    ax4 = fig.add_subplot(gs[2, :])
    ax4.fill_between(dd.index, dd.values, 0, color="#E74C3C", alpha=0.7)
    ax4.set_title("Drawdown BTC/USD", fontsize=12, fontweight="bold")
    ax4.set_ylabel("Drawdown (%)")

    ax5 = fig.add_subplot(gs[3, :])
    sns.heatmap(heatmap_data, annot=True, fmt=".2f", cmap="RdYlGn",
                center=0, ax=ax5, cbar_kws={"label": "Mean log-return (%)"})
    ax5.set_title("Heatmap Rendimento Medio — Giorno × Mese (%)", fontsize=12, fontweight="bold")
    ax5.set_ylabel("Giorno settimana")
    ax5.set_xlabel("Mese")

    # Hourly vol by hour
    h_vol = hourly.groupby("hour")["log_ret"].std() * 100
    ax6 = fig.add_subplot(gs[4, :])
    ax6.bar(h_vol.index, h_vol.values, color="#9B59B6", edgecolor="white")
    ax6.axvspan(-0.5, 7.5, alpha=0.07, color="blue")
    ax6.axvspan(7.5, 15.5, alpha=0.07, color="green")
    ax6.axvspan(15.5, 23.5, alpha=0.07, color="orange")
    ax6.set_title("Volatilità per Ora del Giorno (Std Log-Return %)", fontsize=12, fontweight="bold")
    ax6.set_ylabel("Std (%)")
    ax6.set_xlabel("Ora UTC")
    ax6.set_xticks(range(24))

    fig.suptitle("BTC/USD — Pattern Analysis", fontsize=16, fontweight="bold")
    plt.savefig(os.path.join(OUTPUT_DIR, "02_pattern_analysis.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved: 02_pattern_analysis.png")


if __name__ == "__main__":
    daily, hourly = load_data()
    dow_stats = dow_analysis(daily)
    mon_stats = monthly_seasonality(daily)
    h_stats = hourly_pattern(hourly)
    H = momentum_analysis(daily)
    dd = drawdown_analysis(daily)
    heatmap_data = heatmap_dow_month(daily)
    plot_patterns(daily, hourly, dow_stats, mon_stats, h_stats, dd, heatmap_data)
    print("\nAnalisi pattern completata.")
