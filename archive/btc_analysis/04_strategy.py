"""
BTC/USD Intraday Algorithmic Trading Strategy
==============================================

STRATEGIA: Multi-Signal Intraday Mean-Reversion + Momentum Breakout

Basata sui findings dell'analisi:
  1. BTC mostra volatility clustering → usare regime di volatilità come filtro
  2. Effetto ora del giorno → entrare nelle ore ad alto rendimento atteso
  3. Esponente di Hurst ~0.55 → lieve trending, ma con mean-reversion intraday
  4. Sessione europea (08-14 UTC) e apertura USA (14-18 UTC) = maggior volume

LOGICA:
  - Timeframe: 1h candles
  - Segnale 1: Breakout orario (momentum) su massimo/minimo delle ultime N ore
  - Segnale 2: RSI mean-reversion per uscita/contro-trend
  - Filtro 1: ATR-based volatility filter (entra solo se vol > soglia)
  - Filtro 2: Time-of-day filter (solo sessioni liquide)
  - Filtro 3: Trend filter daily (EMA 50d — opera solo in direzione trend)
  - Position sizing: Kelly fraction + ATR-based stop loss
  - Risk management: stop loss a 1.5×ATR, take profit a 2.5×ATR
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
import os, warnings

warnings.filterwarnings("ignore")
sns.set_theme(style="darkgrid")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


# ── Indicators ───────────────────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # ATR
    df["HL"] = df["High"] - df["Low"]
    df["HC"] = (df["High"] - df["Close"].shift(1)).abs()
    df["LC"] = (df["Low"] - df["Close"].shift(1)).abs()
    df["TR"] = df[["HL", "HC", "LC"]].max(axis=1)
    df["ATR14"] = df["TR"].ewm(span=14, adjust=False).mean()

    # RSI 14
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI14"] = 100 - 100 / (1 + rs)

    # EMA trend filter (hourly)
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

    # Rolling high/low (breakout)
    df["RollHigh6"] = df["High"].rolling(6).max().shift(1)   # massimo ultime 6 ore (esclusa corrente)
    df["RollLow6"] = df["Low"].rolling(6).min().shift(1)

    # Hourly return
    df["ret"] = df["Close"].pct_change()

    # Sessione UTC
    df["hour"] = df.index.hour
    df["dow"] = df.index.dayofweek

    # Volatility regime: ATR relativo al prezzo
    df["ATR_pct"] = df["ATR14"] / df["Close"]
    df["vol_regime"] = df["ATR_pct"].rolling(24).mean()   # media mobile 24h

    return df.dropna()


# ── Signal generation ────────────────────────────────────────────────────────

def generate_signals(df: pd.DataFrame,
                     atr_mult_sl: float = 1.5,
                     atr_mult_tp: float = 2.5,
                     rsi_ob: float = 70,
                     rsi_os: float = 30,
                     min_atr_pct: float = 0.003,
                     active_hours: tuple = (8, 21)) -> pd.DataFrame:
    """
    Genera segnali long/short con SL e TP basati sull'ATR.

    Regole:
      LONG:
        - Close > RollHigh6 (breakout rialzista) AND
        - EMA50 > EMA200 (trend long) AND
        - RSI < rsi_ob (non in ipercomprato) AND
        - ora in active_hours AND
        - ATR_pct > min_atr_pct (sufficiente volatilità)

      SHORT:
        - Close < RollLow6 (breakout ribassista) AND
        - EMA50 < EMA200 (trend short) AND
        - RSI > rsi_os (non in ipervenduto) AND
        - ora in active_hours AND
        - ATR_pct > min_atr_pct
    """
    df = df.copy()
    h0, h1 = active_hours

    time_filter = (df["hour"] >= h0) & (df["hour"] <= h1)
    vol_filter = df["ATR_pct"] > min_atr_pct

    trend_long = df["EMA50"] > df["EMA200"]
    trend_short = df["EMA50"] < df["EMA200"]

    breakout_long = df["Close"] > df["RollHigh6"]
    breakout_short = df["Close"] < df["RollLow6"]

    rsi_not_ob = df["RSI14"] < rsi_ob
    rsi_not_os = df["RSI14"] > rsi_os

    df["signal"] = 0
    df.loc[breakout_long & trend_long & rsi_not_ob & time_filter & vol_filter, "signal"] = 1
    df.loc[breakout_short & trend_short & rsi_not_os & time_filter & vol_filter, "signal"] = -1

    df["SL_dist"] = df["ATR14"] * atr_mult_sl
    df["TP_dist"] = df["ATR14"] * atr_mult_tp

    return df


# ── Backtest ─────────────────────────────────────────────────────────────────

def backtest(df: pd.DataFrame,
             initial_capital: float = 10_000,
             risk_per_trade: float = 0.01) -> dict:
    """
    Backtest event-driven su barre orarie con SL/TP.
    risk_per_trade: frazione del capitale rischiata per trade.
    """
    capital = initial_capital
    equity = [capital]
    trades = []

    in_trade = False
    entry_price = 0.0
    direction = 0
    sl = 0.0
    tp = 0.0
    qty = 0.0
    entry_time = None

    prices = df["Close"].values
    signals = df["signal"].values
    sl_dists = df["SL_dist"].values
    tp_dists = df["TP_dist"].values
    highs = df["High"].values
    lows = df["Low"].values
    times = df.index

    for i in range(len(df)):
        if in_trade:
            exit_price = None
            exit_reason = None

            if direction == 1:
                # Check SL/TP on current candle
                if lows[i] <= sl:
                    exit_price = sl
                    exit_reason = "SL"
                elif highs[i] >= tp:
                    exit_price = tp
                    exit_reason = "TP"
            else:
                if highs[i] >= sl:
                    exit_price = sl
                    exit_reason = "SL"
                elif lows[i] <= tp:
                    exit_price = tp
                    exit_reason = "TP"

            if exit_price is not None:
                pnl = direction * qty * (exit_price - entry_price)
                capital += pnl
                trades.append({
                    "entry_time": entry_time,
                    "exit_time": times[i],
                    "direction": "LONG" if direction == 1 else "SHORT",
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "qty": qty,
                    "pnl": pnl,
                    "pnl_pct": pnl / (entry_price * qty) * 100,
                    "exit_reason": exit_reason,
                })
                in_trade = False

        # New signal
        if not in_trade and signals[i] != 0:
            direction = signals[i]
            entry_price = prices[i]
            sl_d = sl_dists[i]
            tp_d = tp_dists[i]
            risk_amount = capital * risk_per_trade
            qty = risk_amount / sl_d if sl_d > 0 else 0

            if direction == 1:
                sl = entry_price - sl_d
                tp = entry_price + tp_d
            else:
                sl = entry_price + sl_d
                tp = entry_price - tp_d

            in_trade = True
            entry_time = times[i]

        equity.append(capital)

    equity_series = pd.Series(equity[1:], index=df.index)
    return {
        "trades": pd.DataFrame(trades) if trades else pd.DataFrame(),
        "equity": equity_series,
        "final_capital": capital,
    }


# ── Metrics ──────────────────────────────────────────────────────────────────

def compute_metrics(result: dict, initial_capital: float) -> dict:
    trades = result["trades"]
    equity = result["equity"]

    if trades.empty:
        return {"error": "Nessun trade eseguito"}

    total_return = (result["final_capital"] / initial_capital - 1) * 100
    n_trades = len(trades)
    wins = trades[trades["pnl"] > 0]
    losses = trades[trades["pnl"] <= 0]
    win_rate = len(wins) / n_trades * 100

    avg_win = wins["pnl"].mean() if len(wins) else 0
    avg_loss = losses["pnl"].mean() if len(losses) else 0
    profit_factor = wins["pnl"].sum() / abs(losses["pnl"].sum()) if len(losses) else np.inf

    # Annualized return
    days = (equity.index[-1] - equity.index[0]).days
    cagr = ((result["final_capital"] / initial_capital) ** (365 / max(days, 1)) - 1) * 100

    # Max drawdown
    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max * 100
    max_dd = dd.min()

    # Sharpe (hourly → annualized)
    ret_series = equity.pct_change().dropna()
    sharpe = ret_series.mean() / ret_series.std() * np.sqrt(24 * 365) if ret_series.std() > 0 else 0

    # Calmar
    calmar = cagr / abs(max_dd) if max_dd != 0 else np.inf

    return {
        "total_return_pct": total_return,
        "cagr_pct": cagr,
        "n_trades": n_trades,
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor,
        "avg_win_usd": avg_win,
        "avg_loss_usd": avg_loss,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio": sharpe,
        "calmar_ratio": calmar,
        "sl_hits": len(trades[trades["exit_reason"] == "SL"]),
        "tp_hits": len(trades[trades["exit_reason"] == "TP"]),
    }


# ── Plot backtest ─────────────────────────────────────────────────────────────

def plot_backtest(result: dict, metrics: dict, df: pd.DataFrame):
    trades = result["trades"]
    equity = result["equity"]

    fig = plt.figure(figsize=(20, 24))
    gs = gridspec.GridSpec(5, 2, figure=fig, hspace=0.5, wspace=0.35)

    # Equity curve
    ax1 = fig.add_subplot(gs[0, :])
    ax1.plot(equity.index, equity.values, color="#2ECC71", linewidth=1.5)
    ax1.fill_between(equity.index, equity.values, equity.values[0],
                     where=(equity.values > equity.values[0]),
                     alpha=0.2, color="#2ECC71")
    ax1.fill_between(equity.index, equity.values, equity.values[0],
                     where=(equity.values < equity.values[0]),
                     alpha=0.3, color="#E74C3C")
    ax1.set_title("Equity Curve — Strategia Multi-Signal Intraday", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Capitale (USD)")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # Drawdown
    ax2 = fig.add_subplot(gs[1, :])
    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max * 100
    ax2.fill_between(dd.index, dd.values, 0, color="#E74C3C", alpha=0.7)
    ax2.set_title("Drawdown", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Drawdown (%)")

    # PnL per trade
    if not trades.empty:
        ax3 = fig.add_subplot(gs[2, 0])
        colors_t = ["#2ECC71" if p > 0 else "#E74C3C" for p in trades["pnl"]]
        ax3.bar(range(len(trades)), trades["pnl"].values, color=colors_t, width=0.7)
        ax3.axhline(0, color="black", linewidth=0.8)
        ax3.set_title("PnL per Trade (USD)", fontsize=12, fontweight="bold")
        ax3.set_xlabel("Trade #")
        ax3.set_ylabel("PnL (USD)")

        # Cumulative PnL
        ax4 = fig.add_subplot(gs[2, 1])
        ax4.plot(trades["pnl"].cumsum().values, color="#3498DB", linewidth=1.5)
        ax4.axhline(0, color="black", linewidth=0.8)
        ax4.set_title("PnL Cumulato", fontsize=12, fontweight="bold")
        ax4.set_ylabel("PnL totale (USD)")

        # Win/Loss distribution
        ax5 = fig.add_subplot(gs[3, 0])
        wins = trades[trades["pnl"] > 0]["pnl"]
        losses = trades[trades["pnl"] <= 0]["pnl"]
        ax5.hist(wins, bins=30, color="#2ECC71", alpha=0.7, label=f"Win ({len(wins)})")
        ax5.hist(losses, bins=30, color="#E74C3C", alpha=0.7, label=f"Loss ({len(losses)})")
        ax5.set_title("Distribuzione PnL per Trade", fontsize=12, fontweight="bold")
        ax5.set_xlabel("PnL (USD)")
        ax5.legend()

        # Trade duration (hours)
        if "entry_time" in trades.columns and "exit_time" in trades.columns:
            trades["duration_h"] = (trades["exit_time"] - trades["entry_time"]).dt.total_seconds() / 3600
            ax6 = fig.add_subplot(gs[3, 1])
            ax6.hist(trades["duration_h"], bins=30, color="#9B59B6", edgecolor="white")
            ax6.set_title("Durata Trade (ore)", fontsize=12, fontweight="bold")
            ax6.set_xlabel("Ore")
            ax6.set_ylabel("Frequenza")

        # Long vs Short
        ax7 = fig.add_subplot(gs[4, 0])
        direction_pnl = trades.groupby("direction")["pnl"].sum()
        ax7.bar(direction_pnl.index, direction_pnl.values,
                color=["#2ECC71" if v > 0 else "#E74C3C" for v in direction_pnl.values])
        ax7.set_title("PnL Totale: Long vs Short", fontsize=12, fontweight="bold")
        ax7.set_ylabel("PnL (USD)")

        # Monthly PnL
        ax8 = fig.add_subplot(gs[4, 1])
        if not trades.empty and "exit_time" in trades.columns:
            trades["ym"] = trades["exit_time"].dt.to_period("M")
            monthly = trades.groupby("ym")["pnl"].sum()
            colors_m = ["#2ECC71" if v > 0 else "#E74C3C" for v in monthly.values]
            ax8.bar(range(len(monthly)), monthly.values, color=colors_m)
            ax8.set_title("PnL Mensile", fontsize=12, fontweight="bold")
            ax8.set_ylabel("PnL (USD)")
            tick_step = max(1, len(monthly) // 12)
            ax8.set_xticks(range(0, len(monthly), tick_step))
            ax8.set_xticklabels([str(p) for p in monthly.index[::tick_step]], rotation=45, fontsize=7)

    # Metrics text
    m_text = (
        f"Rendimento Totale: {metrics.get('total_return_pct', 0):.1f}%\n"
        f"CAGR: {metrics.get('cagr_pct', 0):.1f}%\n"
        f"Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}\n"
        f"Max Drawdown: {metrics.get('max_drawdown_pct', 0):.1f}%\n"
        f"Calmar Ratio: {metrics.get('calmar_ratio', 0):.2f}\n"
        f"N Trade: {metrics.get('n_trades', 0)}\n"
        f"Win Rate: {metrics.get('win_rate_pct', 0):.1f}%\n"
        f"Profit Factor: {metrics.get('profit_factor', 0):.2f}\n"
        f"Avg Win: ${metrics.get('avg_win_usd', 0):.2f}\n"
        f"Avg Loss: ${metrics.get('avg_loss_usd', 0):.2f}\n"
        f"SL hits: {metrics.get('sl_hits', 0)} | TP hits: {metrics.get('tp_hits', 0)}"
    )
    fig.text(0.02, 0.01, m_text, fontsize=10,
             bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.4),
             verticalalignment="bottom", fontfamily="monospace")

    fig.suptitle("BTC/USD — Backtest Strategia Intraday (1h, 2023-2025)",
                 fontsize=16, fontweight="bold")
    plt.savefig(os.path.join(OUTPUT_DIR, "03_backtest.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print("  Saved: 03_backtest.png")


# ── Parameter optimization (grid search) ─────────────────────────────────────

def optimize_params(df: pd.DataFrame, initial_capital: float = 10_000) -> pd.DataFrame:
    print("\n  Grid search parametri...")
    results = []
    param_grid = [
        (sl, tp, hours)
        for sl in [1.0, 1.5, 2.0]
        for tp in [2.0, 2.5, 3.0]
        for hours in [(6, 22), (8, 20), (8, 18)]
    ]
    for sl_mult, tp_mult, h_range in param_grid:
        df_sig = generate_signals(df, atr_mult_sl=sl_mult, atr_mult_tp=tp_mult,
                                  active_hours=h_range)
        res = backtest(df_sig, initial_capital=initial_capital)
        m = compute_metrics(res, initial_capital)
        if "error" not in m:
            results.append({
                "sl_mult": sl_mult, "tp_mult": tp_mult,
                "h_from": h_range[0], "h_to": h_range[1],
                "sharpe": m["sharpe_ratio"],
                "cagr": m["cagr_pct"],
                "max_dd": m["max_drawdown_pct"],
                "win_rate": m["win_rate_pct"],
                "n_trades": m["n_trades"],
                "calmar": m["calmar_ratio"],
            })

    opt_df = pd.DataFrame(results).sort_values("sharpe", ascending=False)
    return opt_df


# ── Main ──────────────────────────────────────────────────────────────────────

def load_hourly():
    df = pd.read_csv(os.path.join(OUTPUT_DIR, "btc_hourly.csv"),
                     index_col="Date", parse_dates=True)
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return df


if __name__ == "__main__":
    INITIAL_CAPITAL = 10_000
    RISK_PER_TRADE = 0.01   # 1% del capitale per trade

    print("Caricamento dati orari...")
    df_raw = load_hourly()
    print(f"  {len(df_raw)} barre orarie | {df_raw.index[0]} → {df_raw.index[-1]}")

    print("\nCalcolo indicatori...")
    df_ind = compute_indicators(df_raw)

    print("\nGenerazione segnali (parametri base)...")
    df_sig = generate_signals(df_ind)
    n_long = (df_sig["signal"] == 1).sum()
    n_short = (df_sig["signal"] == -1).sum()
    print(f"  Segnali LONG: {n_long} | SHORT: {n_short}")

    print("\nEsecuzione backtest...")
    result = backtest(df_sig, initial_capital=INITIAL_CAPITAL, risk_per_trade=RISK_PER_TRADE)
    metrics = compute_metrics(result, INITIAL_CAPITAL)

    print(f"\n{'═'*55}")
    print("  RISULTATI BACKTEST — Parametri Base")
    print(f"{'═'*55}")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k:<30} {v:.4f}")
        else:
            print(f"  {k:<30} {v}")

    print("\nGrid search ottimizzazione parametri...")
    opt_df = optimize_params(df_ind, initial_capital=INITIAL_CAPITAL)
    print(f"\n  Top 10 combinazioni per Sharpe Ratio:")
    print(opt_df.head(10).to_string(index=False))

    # Backtest con i migliori parametri
    best = opt_df.iloc[0]
    print(f"\n  Migliori parametri: SL={best['sl_mult']}×ATR, TP={best['tp_mult']}×ATR, "
          f"Ore={best['h_from']}-{best['h_to']} UTC")
    df_best = generate_signals(df_ind,
                               atr_mult_sl=best["sl_mult"],
                               atr_mult_tp=best["tp_mult"],
                               active_hours=(int(best["h_from"]), int(best["h_to"])))
    result_best = backtest(df_best, initial_capital=INITIAL_CAPITAL, risk_per_trade=RISK_PER_TRADE)
    metrics_best = compute_metrics(result_best, INITIAL_CAPITAL)

    print(f"\n{'═'*55}")
    print("  RISULTATI BACKTEST — Parametri Ottimizzati")
    print(f"{'═'*55}")
    for k, v in metrics_best.items():
        if isinstance(v, float):
            print(f"  {k:<30} {v:.4f}")
        else:
            print(f"  {k:<30} {v}")

    print("\nGenerazione grafici backtest...")
    plot_backtest(result_best, metrics_best, df_best)

    # Save results
    if not result_best["trades"].empty:
        result_best["trades"].to_csv(os.path.join(OUTPUT_DIR, "trades.csv"), index=False)
    opt_df.to_csv(os.path.join(OUTPUT_DIR, "optimization_results.csv"), index=False)
    print("  Saved: trades.csv, optimization_results.csv")

    print("\nStrategia completata.")
