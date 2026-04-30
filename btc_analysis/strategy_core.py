"""
strategy_core.py — Enhanced Strategy Engine
============================================
Libreria condivisa per tutti gli script di analisi avanzata.
Fornisce:
  - fit_garch11(): GARCH(1,1) via MLE (scipy L-BFGS-B)
  - compute_garch_regime(): classifica regime vol LOW/MED/HIGH
  - compute_indicators_v2(): indicatori tecnici + GARCH h_t
  - generate_signals_v2(): segnali con filtro regime GARCH
  - backtest_v2(): backtest event-driven con commissioni e slippage
  - compute_metrics(): metriche di performance complete
  - load_hourly(): carica dati orari con colonne standardizzate
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
import os, warnings

warnings.filterwarnings("ignore")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


# ── GARCH(1,1) ────────────────────────────────────────────────────────────────

def _garch_h(params: np.ndarray, r: np.ndarray) -> np.ndarray:
    """Sequenza di varianze condizionali GARCH(1,1)."""
    omega, alpha, beta = params
    T = len(r)
    h = np.empty(T)
    h[0] = np.var(r)
    for t in range(1, T):
        h[t] = omega + alpha * r[t - 1] ** 2 + beta * h[t - 1]
    return h


def fit_garch11(returns: np.ndarray) -> tuple:
    """
    Stima GARCH(1,1) via Maximum Likelihood.
    Ritorna: (omega, alpha, beta, h)
      h = array delle varianze condizionali
    """
    r = np.asarray(returns, dtype=float)
    var_r = float(np.var(r)) if np.var(r) > 0 else 1e-6

    def neg_ll(params):
        omega, alpha, beta = params
        if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 0.9999:
            return 1e10
        h = _garch_h(params, r)
        if np.any(h <= 0) or not np.all(np.isfinite(h)):
            return 1e10
        return float(0.5 * np.sum(np.log(h) + r ** 2 / h))

    x0 = np.array([var_r * 0.03, 0.05, 0.90])
    bounds = [(1e-10, var_r), (0.001, 0.499), (0.001, 0.998)]
    res = minimize(neg_ll, x0, method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": 300, "ftol": 1e-9})
    omega, alpha, beta = res.x
    h = _garch_h(res.x, r)
    return float(omega), float(alpha), float(beta), h


def compute_garch_regime(h: np.ndarray,
                         low_pct: float = 25,
                         high_pct: float = 75) -> np.ndarray:
    """
    Classifica ogni timestep in regime di volatilità:
      'LOW'  → h < low_pct percentile  (mercato silenzioso, pochi breakout)
      'MED'  → low_pct <= h <= high_pct (condizioni ottimali)
      'HIGH' → h > high_pct percentile  (volatilità estrema, ridurre size)
    """
    lo = np.percentile(h, low_pct)
    hi = np.percentile(h, high_pct)
    regime = np.full(len(h), "MED", dtype=object)
    regime[h < lo] = "LOW"
    regime[h > hi] = "HIGH"
    return regime


# ── Indicators ────────────────────────────────────────────────────────────────

def compute_indicators_v2(df: pd.DataFrame,
                           fit_garch: bool = True) -> pd.DataFrame:
    """
    Calcola indicatori tecnici + GARCH(1,1) regime sul dataframe orario.
    Aggiunge colonne:
      ATR14, RSI14, EMA50, EMA200, RollHigh6, RollLow6,
      ATR_pct, hour, dow, ret,
      garch_h (varianza condizionale), garch_regime (LOW/MED/HIGH),
      size_mult (1.0/MED, 0.5/HIGH, 0.0/LOW)
    """
    df = df.copy()

    # ATR
    df["HL"] = df["High"] - df["Low"]
    df["HC"] = (df["High"] - df["Close"].shift(1)).abs()
    df["LC"] = (df["Low"] - df["Close"].shift(1)).abs()
    df["TR"] = df[["HL", "HC", "LC"]].max(axis=1)
    df["ATR14"] = df["TR"].ewm(span=14, adjust=False).mean()

    # RSI
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
    df["RSI14"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))

    # EMA
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

    # Breakout levels
    df["RollHigh6"] = df["High"].rolling(6).max().shift(1)
    df["RollLow6"] = df["Low"].rolling(6).min().shift(1)

    # Misc
    df["ret"] = df["Close"].pct_change()
    df["ATR_pct"] = df["ATR14"] / df["Close"]
    df["hour"] = df.index.hour
    df["dow"] = df.index.dayofweek

    df = df.dropna()

    # GARCH regime
    if fit_garch and len(df) > 100:
        log_ret = np.log(df["Close"] / df["Close"].shift(1)).dropna().values
        r_aligned = np.log(df["Close"] / df["Close"].shift(1)).fillna(0).values
        try:
            _, _, _, h_all = fit_garch11(r_aligned[1:])
            h_padded = np.concatenate([[h_all[0]], h_all])
            df["garch_h"] = h_padded[:len(df)]
        except Exception:
            df["garch_h"] = df["ret"].rolling(24).var().fillna(df["ret"].var())

        regime = compute_garch_regime(df["garch_h"].values)
        df["garch_regime"] = regime
        # size_mult: 0=skip LOW, 1=normal MED, 0.5=reduced HIGH
        df["size_mult"] = np.where(regime == "LOW", 0.0,
                          np.where(regime == "HIGH", 0.5, 1.0))
    else:
        df["garch_h"] = df["ret"].rolling(24).var().fillna(df["ret"].var())
        df["garch_regime"] = "MED"
        df["size_mult"] = 1.0

    return df


# ── Signal generation ─────────────────────────────────────────────────────────

def generate_signals_v2(df: pd.DataFrame,
                         atr_mult_sl: float = 1.0,
                         atr_mult_tp: float = 2.5,
                         active_hours: tuple = (6, 22),
                         use_garch_filter: bool = True,
                         rsi_ob: float = 70,
                         rsi_os: float = 30,
                         min_atr_pct: float = 0.003) -> pd.DataFrame:
    """
    Genera segnali long/short con filtro GARCH regime opzionale.
    """
    df = df.copy()
    h0, h1 = active_hours
    time_ok = (df["hour"] >= h0) & (df["hour"] <= h1)
    vol_ok = df["ATR_pct"] > min_atr_pct
    trend_long = df["EMA50"] > df["EMA200"]
    trend_short = df["EMA50"] < df["EMA200"]
    bo_long = df["Close"] > df["RollHigh6"]
    bo_short = df["Close"] < df["RollLow6"]
    rsi_ok_l = df["RSI14"] < rsi_ob
    rsi_ok_s = df["RSI14"] > rsi_os

    # GARCH regime filter: salta segnali in regime LOW
    if use_garch_filter and "garch_regime" in df.columns:
        regime_ok = df["garch_regime"] != "LOW"
    else:
        regime_ok = pd.Series(True, index=df.index)

    df["signal"] = 0
    long_cond = bo_long & trend_long & rsi_ok_l & time_ok & vol_ok & regime_ok
    short_cond = bo_short & trend_short & rsi_ok_s & time_ok & vol_ok & regime_ok
    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    df["SL_dist"] = df["ATR14"] * atr_mult_sl
    df["TP_dist"] = df["ATR14"] * atr_mult_tp

    return df


# ── Backtest v2: con costi di transazione ─────────────────────────────────────

def backtest_v2(df: pd.DataFrame,
                initial_capital: float = 10_000,
                risk_per_trade: float = 0.01,
                commission: float = 0.0004,   # 0.04% Binance taker fee
                slippage: float = 0.0001      # 0.01% market impact BTC/USDT
                ) -> dict:
    """
    Backtest event-driven 1h con:
      - Stop Loss e Take Profit basati su ATR
      - Commissioni e slippage su entrata + uscita
      - Position sizing: risk_per_trade % capitale / SL_dist
      - Leverage cap: max 3× il capitale per trade
      - Riduzione size in regime HIGH (size_mult)
    """
    capital = initial_capital
    equity = [capital]
    trades = []

    in_trade = False
    entry_price = direction = sl = tp = qty = 0.0
    entry_cost = 0.0
    entry_time = None

    prices = df["Close"].values
    signals = df["signal"].values
    sl_dists = df["SL_dist"].values
    tp_dists = df["TP_dist"].values
    highs = df["High"].values
    lows = df["Low"].values
    times = df.index
    size_mults = df["size_mult"].values if "size_mult" in df.columns else np.ones(len(df))

    cost_rate = commission + slippage  # costo per lato (entrata o uscita)
    max_leverage = 3.0                 # cap: notionale max 3× capitale

    for i in range(len(df)):
        if in_trade:
            exit_price = exit_reason = None

            if direction == 1:
                if lows[i] <= sl:
                    exit_price, exit_reason = sl, "SL"
                elif highs[i] >= tp:
                    exit_price, exit_reason = tp, "TP"
            else:
                if highs[i] >= sl:
                    exit_price, exit_reason = sl, "SL"
                elif lows[i] <= tp:
                    exit_price, exit_reason = tp, "TP"

            if exit_price is not None:
                gross_pnl = direction * qty * (exit_price - entry_price)
                exit_cost = exit_price * qty * cost_rate
                pnl = gross_pnl - exit_cost
                capital += pnl
                trades.append({
                    "entry_time": entry_time,
                    "exit_time": times[i],
                    "direction": "LONG" if direction == 1 else "SHORT",
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "qty": qty,
                    "gross_pnl": gross_pnl,
                    "costs": entry_cost + exit_cost,
                    "pnl": pnl,
                    "pnl_pct": pnl / (entry_price * qty) * 100 if qty > 0 else 0,
                    "exit_reason": exit_reason,
                })
                in_trade = False

        if not in_trade and signals[i] != 0:
            direction = int(signals[i])
            ep = prices[i]
            sl_d = sl_dists[i]
            tp_d = tp_dists[i]
            sm = float(size_mults[i])
            if sl_d > 0 and sm > 0:
                risk_amount = capital * risk_per_trade * sm
                qty = risk_amount / sl_d
                # Cap notionale a max_leverage × capitale
                max_qty = (capital * max_leverage) / ep
                qty = min(qty, max_qty)

                entry_cost = ep * qty * cost_rate
                capital -= entry_cost

                sl = ep - sl_d if direction == 1 else ep + sl_d
                tp = ep + tp_d if direction == 1 else ep - tp_d

                in_trade = True
                entry_price = ep
                entry_time = times[i]

        equity.append(capital)

    equity_s = pd.Series(equity[1:], index=df.index)
    return {
        "trades": pd.DataFrame(trades) if trades else pd.DataFrame(),
        "equity": equity_s,
        "final_capital": capital,
    }


# ── Metrics ───────────────────────────────────────────────────────────────────

def compute_metrics(result: dict, initial_capital: float) -> dict:
    trades = result["trades"]
    equity = result["equity"]

    if trades.empty or len(equity) < 2:
        return {"error": "Nessun trade", "sharpe_ratio": -999,
                "cagr_pct": -999, "total_return_pct": -999}

    total_return = (result["final_capital"] / initial_capital - 1) * 100
    n = len(trades)
    wins = trades[trades["pnl"] > 0]
    losses = trades[trades["pnl"] <= 0]
    win_rate = len(wins) / n * 100 if n > 0 else 0
    avg_win = wins["pnl"].mean() if len(wins) > 0 else 0
    avg_loss = losses["pnl"].mean() if len(losses) > 0 else 0
    pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) \
         if len(losses) > 0 and losses["pnl"].sum() != 0 else np.inf

    days = max((equity.index[-1] - equity.index[0]).days, 1)
    cagr = ((result["final_capital"] / initial_capital) ** (365 / days) - 1) * 100

    ret_s = equity.pct_change().dropna()
    sharpe = ret_s.mean() / ret_s.std() * np.sqrt(24 * 365) \
             if ret_s.std() > 0 else 0

    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max * 100
    max_dd = dd.min()
    calmar = cagr / abs(max_dd) if max_dd != 0 else np.inf

    total_costs = trades["costs"].sum() if "costs" in trades.columns else 0

    return {
        "total_return_pct": total_return,
        "cagr_pct": cagr,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": max_dd,
        "calmar_ratio": calmar,
        "n_trades": n,
        "win_rate_pct": win_rate,
        "profit_factor": pf,
        "avg_win_usd": avg_win,
        "avg_loss_usd": avg_loss,
        "sl_hits": len(trades[trades["exit_reason"] == "SL"]),
        "tp_hits": len(trades[trades["exit_reason"] == "TP"]),
        "total_costs_usd": total_costs,
    }


# ── Agent config loader ───────────────────────────────────────────────────────

_AGENT_CONFIG_DEFAULTS = {
    "sl_mult": 2.0,
    "tp_mult": 5.0,
    "active_hours": [6, 22],
    "rsi_ob": 70.0,
    "rsi_os": 30.0,
    "min_atr_pct": 0.003,
    "use_garch_filter": True,
    "commission": 0.0001,
    "slippage": 0.0001,
    "risk_per_trade": 0.01,
}

def load_agent_config() -> dict:
    """
    Load agent-proposed strategy config from output/agent_strategy_config.json.
    Falls back to V5 defaults if the file does not exist.
    """
    import json
    path = os.path.join(OUTPUT_DIR, "agent_strategy_config.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                cfg = json.load(f)
            cfg.setdefault("active_hours", _AGENT_CONFIG_DEFAULTS["active_hours"])
            return cfg
        except Exception:
            pass
    return dict(_AGENT_CONFIG_DEFAULTS)


# ── Data loader ───────────────────────────────────────────────────────────────

def load_hourly(asset: str = "BTC") -> pd.DataFrame:
    fname = f"{asset.lower()}_hourly.csv"
    path = os.path.join(OUTPUT_DIR, fname)
    df = pd.read_csv(path, index_col="Date", parse_dates=True)
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return df


def load_daily(asset: str = "BTC") -> pd.DataFrame:
    fname = f"{asset.lower()}_daily.csv"
    path = os.path.join(OUTPUT_DIR, fname)
    df = pd.read_csv(path, index_col="Date", parse_dates=True)
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return df
