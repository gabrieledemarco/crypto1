"""
BTC/USD Time Series Analysis
- Stationarity (ADF, KPSS)
- Autocorrelation / Partial Autocorrelation
- Log-returns distribution (skewness, kurtosis, fat tails)
- Volatility clustering (ARCH effects)
- Rolling statistics
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
from scipy import stats
from statsmodels.tsa.stattools import adfuller, kpss, acf, pacf
from statsmodels.stats.diagnostic import het_arch
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
import warnings, os

warnings.filterwarnings("ignore")
sns.set_theme(style="darkgrid")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def load_daily():
    df = pd.read_csv(os.path.join(OUTPUT_DIR, "btc_daily.csv"),
                     index_col="Date", parse_dates=True)
    df = df[["Close", "Volume"]].dropna()
    df["log_ret"] = np.log(df["Close"] / df["Close"].shift(1))
    df["ret"] = df["Close"].pct_change()
    return df.dropna()


# ── 1. Stationarity ──────────────────────────────────────────────────────────

def stationarity_tests(series, name):
    print(f"\n{'═'*55}")
    print(f"  STATIONARITY: {name}")
    print(f"{'═'*55}")

    # ADF
    adf_res = adfuller(series.dropna(), autolag="AIC")
    print(f"  ADF  stat={adf_res[0]:.4f}  p={adf_res[1]:.4f}  "
          f"{'STAZIONARIA ✓' if adf_res[1] < 0.05 else 'NON stazionaria ✗'}")

    # KPSS
    kpss_res = kpss(series.dropna(), regression="c", nlags="auto")
    print(f"  KPSS stat={kpss_res[0]:.4f}  p={kpss_res[1]:.4f}  "
          f"{'STAZIONARIA ✓' if kpss_res[1] > 0.05 else 'NON stazionaria ✗'}")


# ── 2. Distribution ──────────────────────────────────────────────────────────

def distribution_analysis(df):
    r = df["log_ret"]
    print(f"\n{'═'*55}")
    print("  DISTRIBUZIONE LOG-RENDIMENTI")
    print(f"{'═'*55}")
    print(f"  Media:        {r.mean():.6f}  ({r.mean()*252:.2f}% ann.)")
    print(f"  Std:          {r.std():.6f}  ({r.std()*np.sqrt(252):.2f}% ann.)")
    print(f"  Skewness:     {r.skew():.4f}")
    print(f"  Kurtosis:     {r.kurtosis():.4f}  (normale=0, fat tails se >0)")
    print(f"  Min:          {r.min():.4f}  ({r.min()*100:.1f}%)")
    print(f"  Max:          {r.max():.4f}  ({r.max()*100:.1f}%)")
    # Jarque-Bera
    jb_stat, jb_p = stats.jarque_bera(r)
    print(f"  Jarque-Bera:  stat={jb_stat:.1f}  p={jb_p:.2e}  "
          f"{'NON normale' if jb_p < 0.05 else 'normale'}")
    # VaR
    var95 = np.percentile(r, 5)
    var99 = np.percentile(r, 1)
    print(f"  VaR 95%:      {var95*100:.2f}%")
    print(f"  VaR 99%:      {var99*100:.2f}%")
    # ARCH test
    arch_lm, arch_p, _, _ = het_arch(r, nlags=10)
    print(f"  ARCH LM(10):  stat={arch_lm:.2f}  p={arch_p:.4f}  "
          f"{'ARCH effects ✓' if arch_p < 0.05 else 'no ARCH'}")


# ── 3. Plot: prices, returns, ACF ────────────────────────────────────────────

def plot_timeseries(df):
    fig = plt.figure(figsize=(18, 22))
    gs = gridspec.GridSpec(5, 2, figure=fig, hspace=0.45, wspace=0.3)

    # Price
    ax1 = fig.add_subplot(gs[0, :])
    ax1.semilogy(df.index, df["Close"], color="#F7931A", linewidth=1.2)
    ax1.set_title("BTC/USD Price (log scale) — 2015-2025", fontsize=14, fontweight="bold")
    ax1.set_ylabel("USD (log)")

    # Log returns
    ax2 = fig.add_subplot(gs[1, :])
    ax2.plot(df.index, df["log_ret"], color="#4A90D9", linewidth=0.6, alpha=0.8)
    ax2.axhline(0, color="red", linewidth=0.8)
    ax2.set_title("Log-Rendimenti Giornalieri", fontsize=13)
    ax2.set_ylabel("log-return")

    # Rolling vol 30d
    ax3 = fig.add_subplot(gs[2, :])
    roll_vol = df["log_ret"].rolling(30).std() * np.sqrt(252)
    ax3.plot(df.index, roll_vol, color="#E74C3C", linewidth=1)
    ax3.set_title("Volatilità Realizzata Rolling 30d (annualizzata)", fontsize=13)
    ax3.set_ylabel("Volatilità")

    # Distribution vs normal
    ax4 = fig.add_subplot(gs[3, 0])
    r = df["log_ret"]
    x = np.linspace(r.min(), r.max(), 300)
    ax4.hist(r, bins=120, density=True, alpha=0.6, color="#4A90D9", label="BTC")
    ax4.plot(x, stats.norm.pdf(x, r.mean(), r.std()), "r--", label="Normale", linewidth=2)
    ax4.plot(x, stats.t.pdf(x, *stats.t.fit(r)), "g-", label="t-Student", linewidth=2)
    ax4.set_title("Distribuzione Rendimenti", fontsize=13)
    ax4.legend()
    ax4.set_xlim(-0.3, 0.3)

    # QQ plot
    ax5 = fig.add_subplot(gs[3, 1])
    stats.probplot(r, dist="norm", plot=ax5)
    ax5.set_title("QQ Plot vs Normale", fontsize=13)

    # ACF returns
    ax6 = fig.add_subplot(gs[4, 0])
    acf_vals = acf(r, nlags=40, fft=True)
    ax6.bar(range(len(acf_vals)), acf_vals, color="#4A90D9", width=0.6)
    ax6.axhline(1.96/np.sqrt(len(r)), linestyle="--", color="red", linewidth=0.8)
    ax6.axhline(-1.96/np.sqrt(len(r)), linestyle="--", color="red", linewidth=0.8)
    ax6.set_title("ACF Log-Rendimenti", fontsize=13)
    ax6.set_xlabel("Lag (giorni)")

    # ACF |returns| (volatility clustering)
    ax7 = fig.add_subplot(gs[4, 1])
    acf_abs = acf(r.abs(), nlags=40, fft=True)
    ax7.bar(range(len(acf_abs)), acf_abs, color="#E74C3C", width=0.6)
    ax7.axhline(1.96/np.sqrt(len(r)), linestyle="--", color="red", linewidth=0.8)
    ax7.axhline(-1.96/np.sqrt(len(r)), linestyle="--", color="red", linewidth=0.8)
    ax7.set_title("ACF |Log-Rendimenti| — Volatility Clustering", fontsize=13)
    ax7.set_xlabel("Lag (giorni)")

    fig.suptitle("BTC/USD — Analisi Serie Storica 2015-2025", fontsize=16, fontweight="bold", y=1.01)
    plt.savefig(os.path.join(OUTPUT_DIR, "01_timeseries_analysis.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved: 01_timeseries_analysis.png")


# ── 4. Yearly / halving analysis ─────────────────────────────────────────────

def halving_analysis(df):
    halvings = {
        "Halving 1 (Nov 2012)": "2012-11-28",
        "Halving 2 (Jul 2016)": "2016-07-09",
        "Halving 3 (May 2020)": "2020-05-11",
        "Halving 4 (Apr 2024)": "2024-04-19",
    }
    print(f"\n{'═'*55}")
    print("  PERFORMANCE POST-HALVING (365 giorni dopo)")
    print(f"{'═'*55}")
    for name, date in halvings.items():
        hdate = pd.Timestamp(date)
        if hdate < df.index[0] or hdate > df.index[-1]:
            continue
        end_date = hdate + pd.Timedelta(days=365)
        try:
            p0 = df.loc[hdate:, "Close"].iloc[0]
            p1 = df.loc[:end_date, "Close"].iloc[-1] if end_date <= df.index[-1] else df["Close"].iloc[-1]
            perf = (p1 / p0 - 1) * 100
            print(f"  {name}: {perf:+.1f}% (da ${p0:,.0f} a ${p1:,.0f})")
        except Exception:
            pass


if __name__ == "__main__":
    df = load_daily()
    stationarity_tests(df["Close"], "BTC Close Price")
    stationarity_tests(df["log_ret"], "Log-Rendimenti")
    distribution_analysis(df)
    halving_analysis(df)
    plot_timeseries(df)
    print("\nAnalisi time series completata.")
